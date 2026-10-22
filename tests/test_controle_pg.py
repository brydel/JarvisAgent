"""Jarvis Next sur PostgreSQL : le même moteur, la RLS, les comptes, la migration depuis SQLite.

Base jetable `jarvis_test` (créée puis supprimée). Ignoré si psycopg ou PostgreSQL manquent
(services/controle_pg/installer_postgres.sh). Toutes les suites du moteur et du Studio y sont rejouées.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

import test_jarvis  # noqa: F401 — environnement isolé
import test_board_v2
import test_missions
import test_studio

from jarvis import adaptateurs as ad, config, coureur, missions as mi  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "controle_pg"))
try:
    import psycopg
    from psycopg.rows import dict_row

    from controle_pg import admin, comptes
    from controle_pg.backend import BackendPostgres
    with psycopg.connect("dbname=postgres", connect_timeout=3):
        pass
    DISPONIBLE, RAISON = True, ""
except Exception as exc:  # noqa: BLE001 — toute absence (paquet, serveur, rôle) rend ces tests sans objet
    DISPONIBLE, RAISON = False, f"PostgreSQL indisponible ({type(exc).__name__}: {exc})"

BASE = "jarvis_test"
_PRECEDENT = {}


def setUpModule():
    if not DISPONIBLE:
        return
    _PRECEDENT["cfg"] = config.CONFIG_DIR
    admin.supprimer_base(BASE)
    _PRECEDENT["dsn"] = admin.preparer(BASE)


def tearDownModule():
    if DISPONIBLE:
        mi.utiliser(None)
        admin.supprimer_base(BASE)


class SurPostgres:
    """Bascule le moteur sur PostgreSQL (rôle jarvis_app) pour la durée de chaque test."""

    def setUp(self):
        mi.utiliser(BackendPostgres(_PRECEDENT["dsn"], dsn_admin=admin.dsn_admin(BASE)))
        super().setUp()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            mi.utiliser(None)


def _rejouer(*classes):
    for cls in classes:
        nom = cls.__name__ + "PG"
        globals()[nom] = unittest.skipUnless(DISPONIBLE, RAISON)(type(nom, (SurPostgres, cls), {}))


_rejouer(test_missions.MachineEtatsTest, test_missions.TrancheVerticaleTest, test_missions.ReprisesTest,
         test_missions.IsolationTest, test_missions.PolitiqueTest, test_missions.FournisseursTest,
         test_missions.CliTest, test_studio.StudioTest, test_board_v2.ObjetsTest, test_board_v2.FichiersTest, test_board_v2.ChefTest,
         test_board_v2.ApiV2Test)


@unittest.skipUnless(DISPONIBLE, RAISON)
class RlsTest(SurPostgres, unittest.TestCase):
    def setUp(self):
        super().setUp()
        test_missions._reinitialiser()
        self.a = mi.creer_organisation("A", id_="ORG-a")
        self.b = mi.creer_organisation("B", id_="ORG-b")
        for org in (self.a, self.b):
            mi.declarer_connexion(org, "factice", "factice")
            mi.board_ajouter(org, "accueil", "note", f"Note privée de {org} à analyser", auteur="test")

    def app(self, tenant=None):
        conn = psycopg.connect(_PRECEDENT["dsn"], autocommit=True, row_factory=dict_row)
        if tenant:
            conn.execute("SELECT set_config('jarvis.tenant_id', %s, false)", (tenant,))
        return conn

    def test_la_base_de_test_ne_touche_pas_au_role_reel(self):
        # régression : les rôles sont communs au serveur ; les tests changeaient le mot de passe de jarvis_app
        self.assertIn(f"user={admin.ROLE_APP}_{BASE} ", _PRECEDENT["dsn"])
        self.assertEqual(admin.role_app("jarvis"), "jarvis_app")

    def test_connexion_impossible_message_clair(self):
        b = BackendPostgres("host=127.0.0.1 port=5432 dbname=jarvis_inexistante_test user=personne password=x")
        with self.assertRaises(mi.MissionError) as ctx:
            b.connecter(None)
        self.assertEqual(ctx.exception.code, "base")
        self.assertIn("preparer --nouveau-mot-de-passe", str(ctx.exception))

    def test_role_applicatif_sans_privilege(self):
        with self.app() as c:
            r = c.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()
        self.assertEqual((r["rolsuper"], r["rolbypassrls"]), (False, False))

    def test_sans_contexte_rien_n_est_visible(self):
        with self.app() as c:
            for table in ("missions", "taches", "board_objets", "evenements", "organisations", "executants"):
                self.assertEqual(c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"], 0, table)

    def test_un_tenant_ne_voit_que_lui_meme_sans_filtre(self):
        with self.app(self.a) as c:  # requêtes SANS « WHERE tenant_id » : c'est la base qui filtre
            tenants = {r["tenant_id"] for r in c.execute("SELECT tenant_id FROM missions")}
            self.assertEqual(tenants, {self.a})
            self.assertEqual([r["id"] for r in c.execute("SELECT id FROM organisations")], [self.a])
            contenus = [r["contenu"] for r in c.execute("SELECT contenu FROM board_objets")]
            self.assertTrue(contenus and all(self.a in x for x in contenus))

    def test_ecriture_dans_un_autre_tenant_refusee(self):
        with self.app(self.a) as c:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("INSERT INTO board_objets (id, tenant_id, espace, type, contenu, auteur, cree) "
                          "VALUES ('BO-intrus', %s, 'x', 'note', 'x', 'x', 0)", (self.b,))
            n = c.execute("UPDATE missions SET objectif='détourné' WHERE tenant_id=%s", (self.b,)).rowcount
            self.assertEqual(n, 0)

    def test_journal_en_ajout_seul_et_comptes_illisibles(self):
        with self.app(self.a) as c:
            for requete in ("UPDATE evenements SET type='x'", "DELETE FROM evenements", "DELETE FROM missions",
                            "SELECT * FROM comptes", "TRUNCATE missions"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=requete):
                    c.execute(requete)

    def test_reclamations_concurrentes_un_seul_bail(self):
        test_missions._reinitialiser()
        org = mi.tenant_local()
        mi.declarer_connexion(org, "factice", "factice")
        m = mi.creer_mission(org, "une seule tâche", [{"capacites": ["analyse"]}])
        execs = [mi.enroler_executant(org, f"e{i}", capacites=["analyse"], fournisseurs=["factice"])
                 for i in range(6)]
        resultats, depart = [], threading.Barrier(len(execs))

        def prendre(rid, secret):
            depart.wait()
            resultats.append(mi.reclamer(rid, secret))

        fils = [threading.Thread(target=prendre, args=e) for e in execs]
        for f in fils:
            f.start()
        for f in fils:
            f.join(30)
        pris = [r for r in resultats if r]
        self.assertEqual(len(pris), 1, "une tâche, un seul bail, même avec six réclamations simultanées")
        self.assertEqual(pris[0]["tache_id"], m["taches"][0])


@unittest.skipUnless(DISPONIBLE, RAISON)
class ComptesTest(unittest.TestCase):
    def setUp(self):
        mi.utiliser(BackendPostgres(_PRECEDENT["dsn"], dsn_admin=admin.dsn_admin(BASE)))
        test_missions._reinitialiser()
        self.org = mi.creer_organisation("Atelier", id_="ORG-atelier")
        mi.creer_organisation("Autre", id_="ORG-autre")

    def tearDown(self):
        mi.utiliser(None)

    def test_creation_connexion_et_adhesions(self):
        dsn_adm = admin.dsn_admin(BASE)
        cid = comptes.creer(dsn_adm, "Fondateur@Exemple.test", "Fondateur", "un mot de passe assez long")
        comptes.adherer(dsn_adm, cid, self.org, "proprietaire")
        r = comptes.connexion(_PRECEDENT["dsn"], "fondateur@exemple.test", "un mot de passe assez long")
        self.assertEqual(r["id"], cid)
        self.assertEqual([(o["tenant_id"], o["role"]) for o in r["organisations"]], [(self.org, "proprietaire")])
        for courriel, mdp in (("fondateur@exemple.test", "mauvais mot de passe"),
                              ("inconnu@exemple.test", "un mot de passe assez long")):
            with self.assertRaises(comptes.CompteError) as ctx:
                comptes.connexion(_PRECEDENT["dsn"], courriel, mdp)
            self.assertEqual(str(ctx.exception), "courriel ou mot de passe incorrect")
        with self.assertRaises(comptes.CompteError):
            comptes.creer(dsn_adm, "fondateur@exemple.test", "Doublon", "un autre mot de passe long")
        with self.assertRaises(comptes.CompteError):
            comptes.creer(dsn_adm, "court@exemple.test", "Court", "court")
        with self.assertRaises(comptes.CompteError):
            comptes.adherer(dsn_adm, cid, self.org, "dieu")

    def test_empreinte_scrypt(self):
        e = comptes.hacher("phrase de passe correcte")
        self.assertTrue(e.startswith("scrypt$"))
        self.assertNotIn("phrase", e)
        self.assertTrue(comptes.verifier_empreinte("phrase de passe correcte", e))
        self.assertFalse(comptes.verifier_empreinte("phrase de passe incorrecte", e))
        self.assertNotEqual(e, comptes.hacher("phrase de passe correcte"), "sel aléatoire")


@unittest.skipUnless(DISPONIBLE, RAISON)
class MigrationTest(unittest.TestCase):
    BASE_M = "jarvis_migr_test"

    def tearDown(self):
        mi.utiliser(None)
        admin.supprimer_base(self.BASE_M)

    def test_sqlite_vers_postgres_verifie(self):
        mi.utiliser(None)  # SQLite : une vraie installation personnelle, avec une mission menée à terme
        test_missions._reinitialiser()
        org = mi.tenant_local()
        mi.declarer_connexion(org, "factice", "factice")
        o = mi.board_ajouter(org, "accueil", "note", "Compte rendu à migrer vers PostgreSQL", auteur="test")
        rid, secret = mi.enroler_executant(org, "poste", capacites=["analyse"], fournisseurs=["factice"])
        coureur.Coureur(coureur.TransportLocal(rid, secret), {"factice": ad.Factice()}).tour()
        avant = mi.inspecter(org, o["mission_id"])
        nb_evenements = len(mi.evenements(org, limite=10_000))

        admin.supprimer_base(self.BASE_M)
        dsn = admin.preparer(self.BASE_M)
        bilan = admin.migrer_depuis_sqlite(mi.chemin_base(), self.BASE_M)
        self.assertEqual(bilan["missions"], 1)
        self.assertEqual(bilan["evenements"], nb_evenements)
        with self.assertRaises(RuntimeError):  # pas de double import
            admin.migrer_depuis_sqlite(mi.chemin_base(), self.BASE_M)

        mi.utiliser(BackendPostgres(dsn))
        apres = mi.inspecter(org, o["mission_id"])
        self.assertEqual(apres["statut"], avant["statut"])
        self.assertEqual([t["transitions"] for t in apres["taches"]], [t["transitions"] for t in avant["taches"]])
        self.assertEqual(apres["artefacts"][0]["empreinte"], avant["artefacts"][0]["empreinte"])
        # le moteur continue sur PostgreSQL : nouvel événement numéroté après les anciens
        mi.board_ajouter(org, "accueil", "image", "capture.png", auteur="test", now=time.time())
        self.assertGreater(mi.evenements(org, limite=10_000)[-1]["seq"], nb_evenements)
        self.assertEqual(mi.reclamer(rid, secret), None, "l'exécutant migré s'authentifie toujours")


if __name__ == "__main__":
    unittest.main()
