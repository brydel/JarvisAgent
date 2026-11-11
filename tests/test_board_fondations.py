"""Fondations de données du Board : requêtes constantes, schéma appliqué une fois, index, flux repris au curseur
et filtré par espace, lecture ciblée (delta), versions partout (objets, déplacement, relations, suppression),
référence indexée des cartes de travail. Chaque test prouve un défaut de l'audit corrigé."""

from __future__ import annotations

import http.client
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
import test_board_v2
import test_missions
import test_studio

from jarvis import adaptateurs as ad, board, config, coureur, missions as mi, travail_board  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]


class Requetes:
    """Compte les requêtes SQL du moteur (trace SQLite) pendant un bloc `with`."""

    def __init__(self):
        self.sql: list[str] = []

    def __enter__(self):
        origine = mi.BackendSQLite.connecter
        compteur = self

        def connecter(backend, tenant_id):
            c = origine(backend, tenant_id)
            c.set_trace_callback(lambda s: compteur.sql.append(s)
                                 if not s.lstrip().upper().startswith(("PRAGMA", "BEGIN", "COMMIT", "ROLLBACK")) else None)
            return c
        self._patch = mock.patch.object(mi.BackendSQLite, "connecter", connecter)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()

    @property
    def n(self) -> int:
        return len(self.sql)


def sqlite_seulement(test):
    def enveloppe(self, *a, **kw):
        if mi.backend().nom != "sqlite":
            self.skipTest("propre à SQLite")
        return test(self, *a, **kw)
    enveloppe.__name__ = test.__name__
    enveloppe.__doc__ = test.__doc__
    return enveloppe


def peupler(org: str, espace: str, n: int) -> list[str]:
    """n cartes : une sur dix est une carte mission (avec tâche), une sur dix porte un fichier, une sur cinq est
    commentée, une relation toutes les deux cartes."""
    with mi.transaction(org) as c:
        if not c.execute("SELECT 1 FROM board_assets WHERE id='AS-00000000f00d'").fetchone():
            c.execute("INSERT INTO board_assets (id, tenant_id, sha256, mime, taille, nom, fichier, meta, cree) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", ("AS-00000000f00d", org, "f" * 64, "image/png", 10, "image.png", "f.png",
                                                    '{"famille": "image"}', 1.0))
    ids = []
    for i in range(n):
        if i % 10 == 0:
            m = mi.creer_mission(org, f"Mission {i}", [{"type": "analyse_document", "niveau": "L1", "capacites": ["analyse"],
                                                       "travail": {"document": "x"}}], source="test", demandeur="test")
            o = mi.board_ajouter(org, espace, "mission", "", auteur="test", mission_id=m["mission_id"], analyser=False)
        elif i % 10 == 1:
            o = mi.board_ajouter(org, espace, "image", "", auteur="test", asset_id="AS-00000000f00d", analyser=False)
        else:
            o = mi.board_ajouter(org, espace, "note", f"note {i}", auteur="test", analyser=False)
        ids.append(o["objet_id"])
    for i in range(0, n, 5):
        board.commenter(org, ids[i], "vu", auteur="test")
    for i in range(0, n - 1, 2):
        board.lier(org, espace, ids[i], ids[i + 1], par="test")
    return ids


# --- 3. Requêtes N+1 ---------------------------------------------------------------------------------------------

class RequetesConstantesTest(test_board_v2.Base):
    @sqlite_seulement
    def test_objets_meme_nombre_de_requetes_pour_10_et_500_cartes(self):
        comptes = {}
        for n in (10, 500):
            espace = f"charge-{n}"
            peupler(self.org, espace, n)
            with Requetes() as r:
                etat = board.objets(self.org, espace)
            self.assertEqual(len(etat["objets"]), n)
            comptes[n] = r.n
        self.assertEqual(comptes[10], comptes[500], comptes)
        self.assertLessEqual(comptes[500], 12, comptes)

    @sqlite_seulement
    def test_lecture_ciblee_et_board_v1_aussi_constants(self):
        ids10, ids500 = peupler(self.org, "a", 10), peupler(self.org, "b", 500)
        with Requetes() as r10:
            board.lire(self.org, "a", objets=ids10)
        with Requetes() as r150:
            board.lire(self.org, "b", objets=ids500[:150])
        self.assertEqual(r10.n, r150.n)
        self.assertLessEqual(r150.n, 12)
        with Requetes() as v10:
            mi.board(self.org, "a")
        with Requetes() as v500:
            self.assertEqual(len(mi.board(self.org, "b")), 500)
        self.assertEqual(v10.n, v500.n)
        self.assertLessEqual(v500.n, 3)

    def test_meme_contenu_qu_avant_fichier_mission_artefacts_commentaires(self):
        """Les agrégats groupés rendent exactement ce que rendaient les requêtes par carte."""
        mi.declarer_connexion(self.org, "factice", "factice")
        m = mi.creer_mission(self.org, "Préparer la démo", [{"type": "analyse_document", "niveau": "L1",
                             "capacites": ["analyse"], "travail": {"document": "Compte rendu"}}], source="test", demandeur="test")
        carte = self.objet("mission", "", mission_id=m["mission_id"])
        rid, secret = mi.enroler_executant(self.org, "poste", capacites=["analyse"], fournisseurs=["factice"])
        self.assertEqual(coureur.Coureur(coureur.TransportLocal(rid, secret), {"factice": ad.Factice()}).tour()["etat"], "fait")
        a = self.fichier(test_board_v2.png(4, 3), "photo.png")
        image = self.objet("image", "", asset_id=a["id"])
        note = self.objet()
        board.commenter(self.org, note, "premier", auteur="test")
        board.commenter(self.org, note, "second", auteur="test")
        par_id = {o["id"]: o for o in board.objets(self.org, "accueil")["objets"]}
        mission = par_id[carte]["mission"]
        self.assertEqual((mission["id"], mission["objectif"], mission["total"], mission["faites"], mission["progression"],
                          mission["approbations_en_attente"]), (m["mission_id"], "Préparer la démo", 1, 1, 100, 0))
        self.assertEqual(mission["statut"], mi.SUCCEEDED)
        self.assertEqual([(t["type"], t["statut"]) for t in mission["taches"]], [("analyse_document", mi.SUCCEEDED)])
        self.assertEqual([(g["executant"], g["role"], g["issue"]) for g in mission["agents"]],
                         [("poste", "analyse_document", "reussi")])
        self.assertIsInstance(mission["agents"][0]["outils"], list)
        self.assertEqual(len(par_id[carte]["artefacts"]), 1)
        self.assertEqual(set(par_id[carte]["artefacts"][0]), {"id", "fournisseur", "factice", "revue", "contenu"})
        self.assertEqual((par_id[image]["asset"]["id"], par_id[image]["asset"]["meta"]["largeur"]), (a["id"], 4))
        self.assertEqual((par_id[note]["commentaires"], par_id[image]["commentaires"]), (2, 0))
        self.assertNotIn("mission", par_id[note])
        self.assertNotIn("travail_ref", par_id[note])
        # la lecture ciblée rend la même forme que le chargement complet
        seul = board.lire(self.org, "accueil", objets=[carte])["objets"][0]
        self.assertEqual(seul, par_id[carte])


# --- 4. Schéma appliqué une fois, index ----------------------------------------------------------------------------

class SchemaTest(test_board_v2.Base):
    @sqlite_seulement
    def test_schema_applique_une_fois_par_processus_et_par_fichier(self):
        with mock.patch.object(mi.BackendSQLite, "_preparer", autospec=True, side_effect=mi.BackendSQLite._preparer) as p:
            mi.backend().reinitialiser()
            for _ in range(25):
                mi._connecter(self.org).close()
            self.assertEqual(p.call_count, 1)
            mi.backend().reinitialiser()  # un autre fichier (base recréée) repasse par la préparation, une fois
            mi._connecter(self.org).close()
            mi._connecter(self.org).close()
            self.assertEqual(p.call_count, 2)

    @sqlite_seulement
    def test_une_connexion_ordinaire_n_execute_aucun_ddl(self):
        mi._connecter(self.org).close()
        vues: list[str] = []
        origine = sqlite3.connect

        def connect(*a, **kw):
            c = origine(*a, **kw)
            c.set_trace_callback(vues.append)
            return c
        with mock.patch.object(sqlite3, "connect", connect):
            mi._connecter(self.org).close()
        self.assertTrue(vues)
        self.assertFalse([s for s in vues if re.match(r"\s*(CREATE|ALTER|INSERT|UPDATE)", s, re.I)], vues)

    @sqlite_seulement
    def test_fichier_remplace_dans_le_dos_du_processus(self):
        """Une base supprimée par ailleurs (restauration, autre processus) est repréparée, pas crue prête."""
        mi._connecter(self.org).close()
        for suffixe in ("", "-wal", "-shm"):
            (config.STATE_DIR / (mi.FICHIER + suffixe)).unlink(missing_ok=True)
        self.assertEqual(board.objets(mi.tenant_local(), "accueil")["objets"], [])

    @sqlite_seulement
    def test_index_presents_et_utilises(self):
        c = mi._connecter(self.org)
        try:
            index = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            for nom in ("board_objets_espace", "board_objets_mission", "board_objets_ref", "board_liens_espace",
                        "board_liens_source", "board_liens_cible", "board_commentaires_objet", "evenements_tenant",
                        "evenements_mission", "taches_mission", "artefacts_mission"):
                self.assertIn(nom, index)

            def plan(sql, params):
                return " ".join(r["detail"] for r in c.execute("EXPLAIN QUERY PLAN " + sql, params))
            self.assertIn("board_objets_espace", plan(
                "SELECT * FROM board_objets WHERE tenant_id=? AND espace=? AND supprime=0", (self.org, "accueil")))
            self.assertIn("board_liens_espace", plan(
                "SELECT * FROM board_liens WHERE tenant_id=? AND espace=? AND supprime=0", (self.org, "accueil")))
            self.assertIn("board_liens_", plan(
                "SELECT id FROM board_liens WHERE tenant_id=? AND (source_id=? OR cible_id=?)", (self.org, "x", "x")))
            self.assertIn("board_commentaires_objet", plan(
                "SELECT COUNT(*) FROM board_commentaires WHERE tenant_id=? AND objet_id=?", (self.org, "x")))
            self.assertIn("evenements_tenant", plan(
                "SELECT * FROM evenements WHERE tenant_id=? AND seq > ? ORDER BY seq LIMIT 200", (self.org, 0)))
            self.assertIn("board_objets_ref", plan(
                "SELECT id FROM board_objets WHERE tenant_id=? AND travail_ref=? AND espace=?", (self.org, "x", "y")))
        finally:
            c.close()

    @sqlite_seulement
    def test_migration_d_une_base_existante_sans_perte_et_retour_arriere_possible(self):
        """Base écrite par la version précédente (schéma 4, sans les ajouts) : colonnes et index ajoutés, données
        intactes, références des cartes de travail reprises ; schema_version reste 4 (l'ancien code la rouvre)."""
        ref = self.objet("tache", "", meta={"titre": "T", "travail_ref": "tache:T-1", "source": "chef"})
        note = self.objet()
        autre = self.objet()
        lien = board.lier(self.org, "accueil", note, autre, par="test")
        c = sqlite3.connect(mi.chemin_base())  # on défait les ajouts : état exact d'une base d'avant
        for index in mi.INDEX_AJOUTS:
            c.execute("DROP INDEX " + index.split(" ON ")[0].rsplit(" ", 1)[1])
        c.execute("ALTER TABLE board_objets DROP COLUMN travail_ref")
        c.execute("ALTER TABLE board_liens DROP COLUMN version")
        c.execute("ALTER TABLE evenements DROP COLUMN espace")
        c.execute("DELETE FROM meta WHERE cle='schema_ajouts'")
        c.commit()
        c.close()
        mi.BackendSQLite._prets.clear()  # nouveau processus
        etat = board.objets(self.org, "accueil")
        self.assertEqual({o["id"] for o in etat["objets"]}, {ref, note, autre})
        self.assertEqual([(l["id"], l["version"]) for l in etat["liens"]], [(lien, 1)])
        c = mi._connecter(self.org)
        try:
            self.assertEqual(c.execute("SELECT travail_ref FROM board_objets WHERE id=?", (ref,)).fetchone()[0], "tache:T-1")
            self.assertIsNone(c.execute("SELECT travail_ref FROM board_objets WHERE id=?", (note,)).fetchone()[0])
            self.assertEqual(travail_board._trouver(c, self.org, "accueil", "tache:T-1")["id"], ref)
            meta = dict(c.execute("SELECT cle, valeur FROM meta").fetchall())
            self.assertEqual((meta["schema_version"], meta["schema_ajouts"]), ("4", str(mi.AJOUTS_VERSION)))
        finally:
            c.close()
        self.assertEqual(mi.SCHEMA_VERSION, 4)

    @sqlite_seulement
    def test_migration_concurrente_de_plusieurs_processus(self):
        """Huit processus ouvrent en même temps une base d'avant (v1) : aucun n'échoue, la base est migrée une fois."""
        mi.backend().reinitialiser()
        c = sqlite3.connect(mi.chemin_base())
        c.executescript("""
            CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
            INSERT INTO meta VALUES ('schema_version', '1');
            CREATE TABLE board_objets (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, espace TEXT NOT NULL,
              type TEXT NOT NULL, contenu TEXT NOT NULL, x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0,
              mission_id TEXT, auteur TEXT NOT NULL, cree REAL NOT NULL);
            INSERT INTO board_objets VALUES ('BO-000000000001', 'ORG-personnel', 'accueil', 'note', 'ancienne note',
              120, 80, NULL, 'humain', 1);""")
        c.commit()
        c.close()
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); from jarvis import board, missions as mi\n"
                "while time.time() < float(sys.argv[2]): pass\n"
                "print(len(board.objets(mi.TENANT_LOCAL, 'accueil')['objets']))")
        import time
        depart = str(time.time() + 1.0)
        env = {**os.environ, "JARVIS_STATE_DIR": str(config.STATE_DIR), "JARVIS_CONFIG_DIR": str(config.CONFIG_DIR)}
        env.pop("JARVIS_MISSIONS_PG", None)
        procs = [subprocess.Popen([sys.executable, "-c", code, str(RACINE / "lib"), depart], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        sorties = [p.communicate(timeout=60) for p in procs]
        self.assertEqual([(p.returncode, s[0].strip()) for p, s in zip(procs, sorties)], [(0, "1")] * 8,
                         [s[1][-400:] for s in sorties])
        mi.BackendSQLite._prets.clear()
        c = mi._connecter(mi.tenant_local())
        try:
            colonnes = [r["name"] for r in c.execute("PRAGMA table_info(board_objets)")]
            self.assertEqual(len(colonnes), len(set(colonnes)))
            self.assertIn("travail_ref", colonnes)
        finally:
            c.close()

    def test_postgresql_porte_les_memes_colonnes_et_index(self):
        """services/controle_pg/schema.sql suit SQLite : mêmes ajouts, mêmes index (noms et colonnes)."""
        sql = (RACINE / "services" / "controle_pg" / "controle_pg" / "schema.sql").read_text()
        normal = re.sub(r"\s+", " ", sql)
        for index in mi.INDEX_AJOUTS:
            self.assertIn(index, normal)
        for table, colonnes in mi.COLONNES_AJOUTS.items():
            for nom, _definition in colonnes:
                self.assertRegex(normal, rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {nom} ")
        self.assertIn("('schema_version', '4')", sql)


# --- 5. Versions partout, événements qui portent de quoi patcher -------------------------------------------------

class VersionsTest(test_board_v2.Base):
    def evenements(self, type_):
        return [e for e in mi.evenements(self.org, limite=1000) if e["type"] == type_]

    def version(self, oid):
        return next(o for o in board.objets(self.org, "accueil")["objets"] if o["id"] == oid)["version"]

    def test_deplacement_versionne(self):
        oid = self.objet()
        self.assertEqual(mi.board_deplacer(self.org, oid, 10, 20, par="studio"), {"version": 2})
        self.assertEqual(self.version(oid), 2)
        with self.assertRaises(mi.MissionError) as ctx:
            mi.board_deplacer(self.org, oid, 99, 99, par="studio", version=1)  # version périmée : refusé
        self.assertEqual(ctx.exception.code, "conflit")
        o = next(o for o in board.objets(self.org, "accueil")["objets"] if o["id"] == oid)
        self.assertEqual((o["x"], o["y"], o["version"]), (10, 20, 2))
        self.assertEqual(mi.board_deplacer(self.org, oid, 30, 40, par="studio", version=2), {"version": 3})
        e = self.evenements("board_deplace")[-1]["donnees"]
        self.assertEqual((e["objet_id"], e["espace"], e["version"]), (oid, "accueil", 3))
        # un client resté sur l'ancienne version ne peut plus écraser le déplacement
        with self.assertRaises(mi.MissionError) as ctx:
            board.mettre_a_jour(self.org, oid, {"x": 0}, version=1, par="studio")
        self.assertEqual(ctx.exception.code, "conflit")

    def test_chaque_evenement_du_board_porte_identifiant_espace_et_version(self):
        a, b = self.objet(), self.objet()
        board.mettre_a_jour(self.org, a, {"priorite": "P1"}, version=1, par="studio")
        lid = board.lier(self.org, "accueil", a, b, par="studio")
        board.modifier_lien(self.org, lid, libelle="alimente", version=1, par="studio")
        board.commenter(self.org, a, "vu", auteur="studio")
        board.supprimer(self.org, [a], par="studio")
        board.supprimer(self.org, [a], par="studio", restaurer=True)
        attendus = {"board_objet": ("objet_id", 1), "board_maj": ("objet_id", 2), "board_lien": ("lien_id", 1),
                    "board_lien_maj": ("lien_id", 2), "board_commentaire": ("objet_id", None),
                    "board_supprime": ("objets", None), "board_restaure": ("objets", None)}
        for type_, (cle, version) in attendus.items():
            e = self.evenements(type_)[-1]["donnees"]
            self.assertEqual(e["espace"], "accueil", type_)
            self.assertIn(cle, e, type_)
            if version is not None:
                self.assertEqual(e["version"], version, type_)
        self.assertEqual(self.evenements("board_supprime")[-1]["donnees"]["objets"], [a])
        c = mi._connecter(self.org)
        try:  # la colonne (filtre du flux) et les données disent le même espace
            self.assertEqual({r["espace"] for r in c.execute(
                "SELECT espace FROM evenements WHERE tenant_id=? AND type LIKE ?", (self.org, "board%"))},
                {"accueil"})
        finally:
            c.close()

    def test_suppression_d_un_grand_lot_un_evenement_par_espace_avec_tous_les_identifiants(self):
        ids = [self.objet() for _ in range(60)]
        ailleurs = mi.board_ajouter(self.org, "autre", "note", "x", auteur="test", analyser=False)["objet_id"]
        self.assertEqual(board.supprimer(self.org, ids + [ailleurs], par="studio"), 61)
        par_espace = {e["donnees"]["espace"]: e["donnees"]["objets"] for e in self.evenements("board_supprime")}
        self.assertEqual((sorted(par_espace["accueil"]), par_espace["autre"]), (sorted(ids), [ailleurs]))

    def test_relation_versionnee(self):
        a, b = self.objet(), self.objet()
        lid = board.lier(self.org, "accueil", a, b, par="studio")
        self.assertEqual(board.objets(self.org, "accueil")["liens"][0]["version"], 1)
        self.assertEqual(board.modifier_lien(self.org, lid, libelle="alimente", version=1, par="studio"), {"version": 2})
        with self.assertRaises(mi.MissionError) as ctx:
            board.modifier_lien(self.org, lid, libelle="autre nom", version=1, par="studio")
        self.assertEqual(ctx.exception.code, "conflit")
        with self.assertRaises(mi.MissionError) as ctx:
            board.modifier_lien(self.org, lid, supprime=True, version=1, par="studio")
        self.assertEqual(ctx.exception.code, "conflit")
        l = board.objets(self.org, "accueil")["liens"][0]
        self.assertEqual((l["libelle"], l["version"]), ("alimente", 2))
        board.modifier_lien(self.org, lid, supprime=True, version=2, par="studio")
        self.assertEqual(board.objets(self.org, "accueil")["liens"], [])
        self.assertTrue(self.evenements("board_lien_maj")[-1]["donnees"]["supprime"])
        board.modifier_lien(self.org, lid, supprime=False, par="studio")  # sans version : compatibilité (CLI, V1)
        self.assertEqual(board.objets(self.org, "accueil")["liens"][0]["version"], 4)

    def test_suppression_versionnee_tout_ou_rien(self):
        a, b = self.objet(), self.objet()
        lid = board.lier(self.org, "accueil", a, b, par="studio")
        board.mettre_a_jour(self.org, b, {"contenu": "réécrit ailleurs"}, par="autre onglet")
        with self.assertRaises(mi.MissionError) as ctx:
            board.supprimer(self.org, [a, b], par="studio", versions={a: 1, b: 1})
        self.assertEqual(ctx.exception.code, "conflit")
        self.assertEqual(len(board.objets(self.org, "accueil")["objets"]), 2)  # rien n'a été supprimé, pas même `a`
        r = board.supprimer_detail(self.org, [a, b], par="studio", versions={a: 1, b: 2})
        self.assertEqual((r["n"], r["versions"], r["liens"]), (2, {a: 2, b: 3}, [lid]))
        self.assertEqual(board.supprimer(self.org, [a], par="studio", restaurer=True), 1)  # ancienne signature intacte

    def test_lot_signale_le_code_de_conflit(self):
        a, b = self.objet(), self.objet()
        board.mettre_a_jour(self.org, a, {"x": 5}, par="autre onglet")
        r = board.mettre_a_jour_lot(self.org, [{"id": a, "champs": {"x": 1}, "version": 1},
                                               {"id": b, "champs": {"x": 2}, "version": 1},
                                               {"id": "BO-000000000000", "champs": {"x": 3}}], par="studio")
        self.assertEqual([(x["ok"], x.get("code"), x.get("version")) for x in r],
                         [(False, "conflit", None), (True, None, 2), (False, "inconnue", None)])

    def test_mission_rattachee_a_une_carte_signalee_sans_changer_sa_version(self):
        """La contextualisation lie la carte à sa mission : un événement le dit (le client relit la carte), mais la
        version ne bouge pas — l'écriture que l'utilisateur est en train de faire sur sa note reste valable."""
        oid = mi.board_ajouter(self.org, "accueil", "note", "Idée de campagne", auteur="studio", analyser=False,
                               contextualiser=True)
        e = [x for x in self.evenements("board_maj") if x["donnees"].get("champs") == ["mission_id"]][-1]
        self.assertEqual((e["donnees"]["objet_id"], e["donnees"]["espace"], e["mission_id"]),
                         (oid["objet_id"], "accueil", oid["mission_id"]))
        self.assertNotIn("version", e["donnees"])
        self.assertEqual(board.mettre_a_jour(self.org, oid["objet_id"], {"x": 4}, version=1, par="studio"), {"version": 2})


# --- 1. Lecture ciblée (delta) -------------------------------------------------------------------------------------

class DeltaTest(test_board_v2.Base):
    def test_lecture_ciblee_objets_liens_et_absents(self):
        a, b, c = self.objet(), self.objet(), self.objet()
        ailleurs = mi.board_ajouter(self.org, "autre", "note", "x", auteur="test", analyser=False)["objet_id"]
        l1 = board.lier(self.org, "accueil", a, b, par="test")
        l2 = board.lier(self.org, "accueil", b, c, par="test")
        board.supprimer(self.org, [c], par="test")
        avant = mi.curseur(self.org)
        r = board.lire(self.org, "accueil", objets=[a, c, ailleurs, "BO-ffffffffffff"], liens=[l2, "BL-ffffffffffff"])
        self.assertEqual([o["id"] for o in r["objets"]], [a])
        self.assertEqual([l["id"] for l in r["liens"]], [l1])  # les relations qui touchent `a` ; l2 est partie avec `c`
        self.assertEqual(r["absents"], {"objets": [c, ailleurs, "BO-ffffffffffff"], "liens": [l2, "BL-ffffffffffff"]})
        self.assertEqual((r["espace"], r["curseur"]), ("accueil", avant))
        self.assertEqual(board.lire(self.org, "accueil", liens=[l1])["liens"][0]["id"], l1)
        self.assertEqual(board.lire(self.org, "accueil")["objets"], [])
        with self.assertRaises(mi.MissionError):
            board.lire(self.org, "accueil", objets=[f"BO-{i:012x}" for i in range(board.LIRE_MAX + 1)])

    def test_isolation_du_tenant(self):
        a = self.objet()
        autre = mi.creer_organisation("Autre organisation")
        self.assertEqual(board.lire(autre, "accueil", objets=[a])["absents"]["objets"], [a])

    def test_curseur_du_chargement_et_evenements_filtres(self):
        self.objet()
        etat = board.objets(self.org, "accueil")
        self.assertEqual(etat["curseur"], mi.curseur(self.org))
        mi.board_ajouter(self.org, "autre", "note", "ailleurs", auteur="test", analyser=False)
        ici = self.objet()
        mi.regler_board(self.org, auto_analyse=False, par="test")  # sans espace : concerne tous les Boards
        suite = mi.evenements(self.org, apres=etat["curseur"], espace="accueil")
        self.assertEqual([(e["type"], e["donnees"].get("objet_id")) for e in suite],
                         [("board_objet", ici), ("reglages_board", None)])
        self.assertEqual(len(mi.evenements(self.org, apres=etat["curseur"])), 3)  # sans filtre : tout, comme avant
        self.assertEqual([e["seq"] for e in mi.evenements(self.org, derniers=2)],
                         [e["seq"] for e in mi.evenements(self.org, limite=1000)][-2:])
        self.assertEqual(set(suite[0]), {"seq", "tenant_id", "mission_id", "tache_id", "type", "donnees", "ts"})


class LecteurTest(test_board_v2.Base):
    def test_tour_a_vide_sans_requete_puis_reprise(self):
        self.objet()
        lecteur = mi.LecteurEvenements(self.org, espace="accueil")
        try:
            depart = lecteur.curseur()
            self.assertEqual(lecteur.lire(depart), ([], depart))
            if mi.backend().nom == "sqlite":
                vues: list[str] = []
                lecteur._c.set_trace_callback(vues.append)
                for _ in range(50):
                    self.assertEqual(lecteur.lire(depart), ([], depart))
                self.assertEqual({s for s in vues}, {"PRAGMA data_version"})  # aucune table lue tant que rien n'est écrit
                lecteur._c.set_trace_callback(None)
            mi.board_ajouter(self.org, "autre", "note", "ailleurs", auteur="test", analyser=False)
            lot, examine = lecteur.lire(depart)
            self.assertEqual((lot, examine), ([], mi.curseur(self.org)))  # rien pour ce Board, mais le curseur avance
            ici = self.objet()
            lot, examine2 = lecteur.lire(examine)
            self.assertEqual([e["donnees"]["objet_id"] for e in lot], [ici])
            self.assertEqual(examine2, lot[-1]["seq"])
            self.assertFalse(lecteur.retard(depart, 5))
            self.assertTrue(lecteur.retard(0, 1))
        finally:
            lecteur.fermer()


# --- 6. Cartes de travail retrouvées par une clé indexée ---------------------------------------------------------------

class ReferenceTest(test_board_v2.Base):
    def test_reference_rangee_dans_sa_colonne_et_tenue_a_jour(self):
        oid = self.objet("tache", "", meta={"titre": "T", "travail_ref": "tache:T-9"})
        c = mi._connecter(self.org)
        try:
            self.assertEqual(travail_board._trouver(c, self.org, "accueil", "tache:T-9")["id"], oid)
            self.assertIsNone(travail_board._trouver(c, self.org, "autre", "tache:T-9"))
            self.assertIsNone(travail_board._trouver(c, self.org, "accueil", "tache:T-"))  # égalité, plus de motif LIKE
        finally:
            c.close()
        self.assertEqual(travail_board._references(self.org), {"tache:T-9"})
        board.mettre_a_jour(self.org, oid, {"meta": {"titre": "T", "travail_ref": "tache:T-10"}}, par="studio")
        self.assertEqual(travail_board._references(self.org), {"tache:T-10"})
        board.mettre_a_jour(self.org, oid, {"meta": {"titre": "sans référence"}}, par="studio")
        self.assertEqual(travail_board._references(self.org), set())

    def test_reference_qui_contient_des_caracteres_de_motif(self):
        """Avec LIKE, « % » et « _ » dans une référence trouvaient d'autres cartes ; l'égalité indexée, non."""
        large = self.objet("tache", "", meta={"travail_ref": "tache:A_1"})
        self.objet("tache", "", meta={"travail_ref": "tache:AX1"})
        c = mi._connecter(self.org)
        try:
            self.assertEqual(travail_board._trouver(c, self.org, "accueil", "tache:A_1")["id"], large)
            self.assertIsNone(travail_board._trouver(c, self.org, "accueil", "tache:%"))
        finally:
            c.close()

    def test_cartes_d_avant_la_colonne_reprises_sans_doublon(self):
        """Carte posée par l'ancien code (référence seulement dans meta) : reprise, donc ni perdue ni recréée."""
        oid = self.objet("tache", "", meta={"titre": "T", "travail_ref": "tache:T-1"})
        with mi.transaction(self.org) as c:
            c.execute("UPDATE board_objets SET travail_ref=NULL WHERE id=?", (oid,))
        if mi.backend().nom == "sqlite":  # SQLite : reprise à la préparation du schéma (test de migration) ou à la demande
            self.assertEqual(travail_board._references(self.org), set())
            self.assertEqual(travail_board.migrer_references(self.org), 1)
        else:  # PostgreSQL : reprise au premier passage du module dans un processus
            travail_board._REPRIS.clear()
        self.assertEqual(travail_board._references(self.org), {"tache:T-1"})
        self.assertEqual(travail_board.migrer_references(self.org), 0)  # idempotent
        self.assertEqual(travail_board._references(self.org), {"tache:T-1"})
        self.assertEqual(travail_board._carte(self.org, "accueil", "tache:T-1", "tache", {"titre": "T2"}, now=5.0), oid)
        self.assertEqual(len(board.objets(self.org, "accueil")["objets"]), 1)
        e = [x for x in mi.evenements(self.org, limite=1000) if x["type"] == "board_maj"][-1]["donnees"]
        self.assertEqual((e["objet_id"], e["espace"], e["version"]), (oid, "accueil", 2))


# --- 1, 2, 5. L'API : delta, flux repris au curseur et filtré, conflits ----------------------------------------------

class ApiFondationsTest(unittest.TestCase):
    # même serveur réel et mêmes aides que test_studio.StudioTest, sans rejouer ses tests
    setUp = test_studio.StudioTest.setUp
    tearDown = test_studio.StudioTest.tearDown
    req = test_studio.StudioTest.req
    connecter = test_studio.StudioTest.connecter

    def flux(self, chemin, *, entetes=None, jusqu_a=None, attendus=1, delai=5.0):
        """Lit le flux jusqu'à `attendus` messages (ou jusqu'au numéro `jusqu_a`) : [(type, id, données)]."""
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=delai)
        c.request("GET", chemin, headers={"Host": f"localhost:{self.port}", "Cookie": self.cookie, **(entetes or {})})
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        messages, courant = [], {}
        try:
            while len(messages) < attendus:
                ligne = r.fp.readline().decode().rstrip("\n")
                if ligne.startswith(("event: ", "id: ", "data: ")):
                    cle, _, valeur = ligne.partition(": ")
                    courant[cle] = valeur
                elif not ligne and "data" in courant:
                    messages.append((courant.get("event", "message"), int(courant["id"]), json.loads(courant["data"])))
                    courant = {}
                    if jusqu_a is not None and messages[-1][1] >= jusqu_a:
                        break
                elif not ligne:
                    courant = {}
        except TimeoutError:
            pass
        finally:
            c.close()
        return messages

    def test_chargement_avec_curseur_et_flux_qui_ne_rejoue_pas_l_historique(self):
        self.connecter()
        for i in range(30):
            self.req("POST", "/api/v2/objets", {"type": "note", "contenu": f"note {i}", "analyser": False})
        etat = self.req("GET", "/api/v2/board")[1]
        self.assertEqual(etat["curseur"], mi.curseur(self.org))
        self.assertGreaterEqual(etat["curseur"], 30)
        resultat = {}
        fil = threading.Thread(target=lambda: resultat.update(m=self.flux(
            f"/api/flux?apres={etat['curseur']}&espace=accueil", attendus=1)))
        fil.start()
        import time
        time.sleep(0.3)
        nouveau = self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "après", "analyser": False})[1]["objet_id"]
        fil.join(10)
        (type_, seq, e), = resultat["m"]
        # le premier message reçu est le NOUVEL événement, pas le début de l'historique ; il porte de quoi patcher
        self.assertEqual((type_, e["type"], e["donnees"]["objet_id"], e["donnees"]["espace"], e["donnees"]["version"]),
                         ("message", "board_objet", nouveau, "accueil", 1))
        self.assertEqual((seq, e["prec"]), (etat["curseur"] + 1, etat["curseur"]))

    def test_flux_filtre_par_espace_cote_serveur_avec_curseur_et_chaine_prec(self):
        self.connecter()
        depart = self.req("GET", "/api/v2/board")[1]["curseur"]
        ids = []
        for espace in ("autre", "autre", "accueil", "autre", "accueil"):
            ids.append(self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "n", "analyser": False,
                                                           "espace": espace})[1]["objet_id"])
        fin = mi.curseur(self.org)
        messages = self.flux(f"/api/flux?apres={depart}&espace=accueil", jusqu_a=fin, attendus=10)
        evenements = [(t, d) for t, _, d in messages if t == "message"]
        self.assertEqual([d["donnees"]["objet_id"] for _, d in evenements], [ids[2], ids[4]])  # rien des autres Boards
        self.assertEqual({d["donnees"]["espace"] for _, d in evenements}, {"accueil"})
        precedent = depart
        for type_, seq, d in messages:  # chaîne continue : chaque message cite le précédent
            self.assertEqual(d["prec"], precedent)
            precedent = seq
        self.assertEqual(precedent, fin)
        # sans rien de neuf pour ce Board, un message « curseur » déplace quand même le point de reprise
        self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "n", "analyser": False, "espace": "autre"})
        suite = self.flux(f"/api/flux?apres={fin}&espace=accueil", attendus=1)
        self.assertEqual([(t, d) for t, _, d in suite], [("curseur", {"seq": fin + 1, "prec": fin})])

    def test_flux_reprise_par_last_event_id_resync_et_fin(self):
        self.connecter()
        a = self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "a", "analyser": False})[1]["objet_id"]
        milieu = mi.curseur(self.org)
        b = self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "b", "analyser": False})[1]["objet_id"]
        # reconnexion du navigateur : Last-Event-ID l'emporte sur ?apres=
        m = self.flux("/api/flux?apres=0&espace=accueil", entetes={"Last-Event-ID": str(milieu)}, attendus=1)
        self.assertEqual([(d["donnees"]["objet_id"], d["prec"]) for _, _, d in m], [(b, milieu)])
        self.assertNotEqual(a, b)
        # curseur plus loin que le journal (base réinitialisée) : relecture complète demandée, suite à partir d'ici
        fin = mi.curseur(self.org)
        m = self.flux(f"/api/flux?apres={fin + 500}&espace=accueil", attendus=1)
        self.assertEqual([(t, s, d) for t, s, d in m], [("resync", fin, {"seq": fin})])
        # reprise trop lointaine : même signal plutôt qu'un rejeu massif
        with mock.patch("jarvis.studio_api.RETARD_FLUX_MAX", 1):
            m = self.flux("/api/flux?apres=0&espace=accueil", attendus=1)
        self.assertEqual(m[0][0], "resync")
        # « fin » : à partir de maintenant (vues produit) ; sans espace, format historique inchangé (pas de prec)
        resultat = {}
        fil = threading.Thread(target=lambda: resultat.update(m=self.flux("/api/flux?apres=fin", attendus=1)))
        fil.start()
        import time
        time.sleep(0.3)
        c = self.req("POST", "/api/v2/objets", {"type": "note", "contenu": "c", "analyser": False})[1]["objet_id"]
        fil.join(10)
        (type_, _, e), = resultat["m"]
        self.assertEqual((type_, e["donnees"]["objet_id"]), ("message", c))
        self.assertNotIn("prec", e)

    def test_lecture_ciblee_par_l_api(self):
        self.assertEqual(self.req("GET", "/api/v2/objets?ids=BO-000000000000")[0], 401)  # session exigée
        self.connecter()
        ids = [self.req("POST", "/api/v2/objets", {"type": "note", "contenu": f"note {i}", "analyser": False})[1]["objet_id"]
               for i in range(3)]
        lid = self.req("POST", "/api/v2/liens", {"source_id": ids[0], "cible_id": ids[1]})[1]["id"]
        code, r, _ = self.req("GET", f"/api/v2/objets?ids={ids[0]},BO-ffffffffffff&liens={lid}&espace=accueil")
        self.assertEqual(code, 200)
        self.assertEqual(([o["id"] for o in r["objets"]], [l["id"] for l in r["liens"]], r["absents"]),
                         ([ids[0]], [lid], {"objets": ["BO-ffffffffffff"], "liens": []}))
        self.assertEqual((r["objets"][0]["version"], r["liens"][0]["version"], r["curseur"]), (1, 1, mi.curseur(self.org)))
        self.assertIn("auto_analyse", r["reglages"])
        self.assertEqual(self.req("GET", f"/api/v2/objets?ids={ids[0]}&espace=autre")[1]["absents"]["objets"], [ids[0]])
        for mauvais in ("ids=1%20OR%201=1", "ids=BO-xyz", "liens=BO-000000000000", "ids=" + ",".join(f"BO-{i:012x}" for i in range(201))):
            self.assertEqual(self.req("GET", f"/api/v2/objets?{mauvais}")[0], 400, mauvais)
        self.assertEqual(self.req("GET", "/api/v2/objets", hote="attaquant.example")[0], 403)
        hist = self.req("GET", "/api/evenements?dernier=2&espace=accueil")[1]["evenements"]
        self.assertEqual([e["type"] for e in hist], ["board_objet", "board_lien"])

    def test_conflits_409_objets_deplacement_relations_suppression(self):
        self.connecter()
        a, b = (self.req("POST", "/api/v2/objets", {"type": "note", "contenu": f"note {i}", "analyser": False})[1]["objet_id"]
                for i in range(2))
        lid = self.req("POST", "/api/v2/liens", {"source_id": a, "cible_id": b})[1]["id"]
        # un autre onglet modifie la carte et la relation
        self.assertEqual(self.req("POST", f"/api/v2/objets/{a}", {"champs": {"x": 50}, "version": 1})[1], {"version": 2})
        self.assertEqual(self.req("POST", f"/api/v2/liens/{lid}", {"libelle": "alimente", "version": 1})[1],
                         {"ok": True, "version": 2})
        # mon onglet, resté sur la version 1 : tout est refusé, rien n'est écrasé
        r = self.req("POST", "/api/v2/objets/lot", {"modifications": [{"id": a, "champs": {"x": 0}, "version": 1}]})[1]
        self.assertEqual((r["resultats"][0]["ok"], r["resultats"][0]["code"]), (False, "conflit"))
        self.assertEqual(self.req("POST", f"/api/board/{a}/position", {"x": 0, "y": 0, "version": 1})[0], 409)
        self.assertEqual(self.req("POST", f"/api/v2/liens/{lid}", {"libelle": "écrasé", "version": 1})[0], 409)
        self.assertEqual(self.req("POST", f"/api/v2/liens/{lid}", {"supprime": True, "version": 1})[0], 409)
        self.assertEqual(self.req("POST", "/api/v2/objets/supprimer", {"ids": [a, b], "versions": {a: 1, b: 1}})[0], 409)
        self.assertEqual(self.req("POST", "/api/v2/objets/supprimer", {"ids": [a], "versions": {a: "1"}})[0], 400)
        etat = self.req("GET", "/api/v2/board")[1]
        self.assertEqual([(o["id"], o["x"], o["version"]) for o in etat["objets"]], [(a, 50, 2), (b, 0, 1)])
        self.assertEqual([(l["libelle"], l["version"]) for l in etat["liens"]], [("alimente", 2)])
        # avec la bonne version : accepté ; le déplacement V1 sans version reste accepté (compatibilité) et versionne
        self.assertEqual(self.req("POST", f"/api/board/{a}/position", {"x": 7, "y": 8})[1], {"ok": True, "version": 3})
        self.assertEqual(self.req("POST", f"/api/board/{a}/position", {"x": 9, "y": 9, "version": 3})[1], {"ok": True, "version": 4})
        r = self.req("POST", "/api/v2/objets/supprimer", {"ids": [a, b], "versions": {a: 4, b: 1}})[1]
        self.assertEqual(r, {"n": 2, "versions": {a: 5, b: 2}})
        self.assertEqual(self.req("POST", "/api/v2/objets/supprimer", {"ids": [a], "restaurer": True})[1]["n"], 1)  # V2 d'avant

    def test_studio_v1_inchange(self):
        """Le Studio V1 lit toujours /api/board et le flux complet depuis ?apres=0, au même format."""
        self.connecter()
        o = self.req("POST", "/api/board", {"contenu": "note v1", "x": 3, "y": 4})[1]
        objets = self.req("GET", "/api/board?espace=accueil")[1]["objets"]
        self.assertEqual([(x["id"], x["contenu"], x["x"], x["y"]) for x in objets], [(o["objet_id"], "note v1", 3, 4)])
        self.assertEqual(self.req("POST", f"/api/board/{o['objet_id']}/position", {"x": 30, "y": 40})[0], 200)
        tous = mi.evenements(self.org)
        m = self.flux("/api/flux?apres=0", jusqu_a=tous[-1]["seq"], attendus=len(tous))
        self.assertEqual([d for _, _, d in m], tous)
        self.assertEqual({t for t, _, _ in m}, {"message"})


if __name__ == "__main__":
    unittest.main()
