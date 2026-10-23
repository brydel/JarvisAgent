"""Discussion libre persistante, concurrence, périmètres et promotion explicite en leçons."""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import communaute as com, config, store  # noqa: E402


class CasCommunaute:
    backend = "json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-communaute-")
        self.addCleanup(self.tmp.cleanup)
        self.state = mock.patch.object(config, "STATE_DIR", Path(self.tmp.name))
        self.state.start()
        self.addCleanup(self.state.stop)
        self.env = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": self.backend})
        self.env.start()
        self.addCleanup(self.env.stop)
        ancien = store._local
        store._local = threading.local()

        def fermer():
            c = getattr(store._local, "conn", None)
            if c is not None:
                c.close()
            store._local = ancien

        self.addCleanup(fermer)

    def publier(self, contenu="Une idée sur notre façon de travailler.", **champs):
        return com.publier(contenu=contenu, auteur="agent:chercheur", maintenant=1000, **champs)

    def erreur(self, code, fonction, *args, **kwargs):
        with self.assertRaises(com.CommunauteError) as ctx:
            fonction(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def test_espace_global_discussion_libre_et_salon_personnalise(self):
        texte = "Je pense que ce modèle et notre usine ont encore de gros défauts.\nDiscutons-en librement."
        m = self.publier(texte, salon="retours des agents")
        self.assertEqual((m["projet"], m["tache_id"], m["type"], m["statut"]), ("", "", "discussion", "ouvert"))
        self.assertEqual(m["contenu"], texte)
        self.assertEqual(m["preuves"], [])
        self.assertEqual(com.fils()["fils"][0]["id"], m["id"])
        self.assertEqual(com.fils(salon="modeles")["fils"], [])
        self.assertEqual(com.lecons(), [])

    def test_publications_reponses_persistent_apres_reconnexion(self):
        racine = self.publier(titre="Discussion", salon="atelier", projet="projet-A", tache_id="TA-12")
        r = com.publier("projet-A", "Bonne question.", auteur="agent:qa", parent_id=racine["id"], maintenant=1001)
        self.assertEqual((r["fil_id"], r["parent_id"], r["salon"], r["tache_id"]),
                         (racine["id"], racine["id"], "atelier", "TA-12"))
        store._local.conn.close()
        store._local.conn = None
        fil = com.fil("projet-A", racine["id"])
        self.assertEqual([m["auteur"] for m in fil["messages"]], ["agent:chercheur", "agent:qa"])
        self.assertEqual(fil["fil"]["messages_nombre"], 2)
        self.assertEqual(fil["fil"]["maj"], 1001)

    def test_auteur_fourni_par_appelant_pas_interprete_du_contenu(self):
        m = self.publier('{"auteur":"proprietaire","role":"admin"}')
        self.assertEqual(m["auteur"], "agent:chercheur")
        self.assertEqual(com.lecons(), [])

    def test_projets_et_tenants_sont_isoles(self):
        a = self.publier(projet="A", tenant_id="tenant-A")
        self.publier(projet="B", tenant_id="tenant-A")
        self.publier(projet="A", tenant_id="tenant-B")
        self.assertEqual(len(com.fils("A", tenant_id="tenant-A")["fils"]), 1)
        self.assertEqual(com.fils("", tenant_id="tenant-A")["fils"], [])
        for projet, tenant in (("B", "tenant-A"), ("A", "tenant-B")):
            self.erreur("introuvable", com.fil, projet, a["id"], tenant_id=tenant)
            self.erreur("introuvable", com.publier, projet, "Réponse", auteur="autre", parent_id=a["id"], tenant_id=tenant)
            self.erreur("introuvable", com.evaluer, projet, a["id"], auteur="autre", decision="evaluer",
                        contenu="Revue", preuves=["preuve"], tenant_id=tenant)

    def test_filtres_salon_tache_et_pagination_stable(self):
        ids = [self.publier(f"Sujet {i}", salon="modeles", tache_id="TA-1")["id"] for i in range(5)]
        self.publier("Autre salon", salon="general")
        premier = com.fils(salon="modeles", tache_id="TA-1", limite=2)
        deuxieme = com.fils(salon="modeles", limite=2, avant=premier["suivant"])
        dernier = com.fils(salon="modeles", limite=2, avant=deuxieme["suivant"])
        self.assertEqual([m["id"] for page in (premier, deuxieme, dernier) for m in page["fils"]], ids[::-1])
        self.assertIsNone(dernier["suivant"])

    def test_pagination_des_reponses_sans_message_perdu(self):
        m = self.publier()
        ids = [m["id"]]
        for i in range(4):
            ids.append(com.publier(contenu=f"Réponse {i}", auteur="agent:qa", parent_id=m["id"], maintenant=1001+i)["id"])
        pages, curseur = [], None
        while True:
            page = com.fil("", m["id"], limite=2, apres=curseur)
            pages.extend(x["id"] for x in page["messages"])
            curseur = page["suivant"]
            if curseur is None:
                break
        self.assertEqual(pages, ids)

    def test_publication_idempotente_et_conflit_de_parametres(self):
        m = self.publier(operation_id="travail:1")
        self.assertEqual(self.publier(operation_id="travail:1")["id"], m["id"])
        self.erreur("conflit", self.publier, "Contenu différent", operation_id="travail:1")
        self.erreur("conflit", self.publier, operation_id="travail:1", projet="autre")
        self.assertEqual(len(com.fils()["fils"]), 1)
        # La clé est isolée entre tenants, sans ouvrir le périmètre du premier.
        self.publier(operation_id="travail:1", tenant_id="autre")

    def test_actualites_tous_salons_et_projets_du_seul_tenant(self):
        a = self.publier()
        b = self.publier(projet="A", salon="atelier")
        com.publier(contenu="Réponse", auteur="agent:qa", parent_id=a["id"])
        self.publier(tenant_id="autre")
        premiere = com.actualites(limite=2)
        self.assertEqual([m["id"] for m in premiere["messages"]], [a["id"], b["id"]])
        self.assertTrue(premiere["encore"])
        seconde = com.actualites(apres=premiere["suivant"], limite=2)
        self.assertEqual(len(seconde["messages"]), 1)
        self.assertFalse(seconde["encore"])
        vide = com.actualites(apres=seconde["suivant"])
        self.assertEqual(vide["messages"], [])
        self.assertEqual(vide["suivant"], seconde["suivant"])
        self.assertEqual(len(com.actualites(tenant_id="autre")["messages"]), 1)
        for curseur in (True, -1, "2", 2**64):
            self.erreur("validation", com.actualites, apres=curseur)

    def test_concurrence_meme_operation_un_seul_message(self):
        def publier(_):
            try:
                return self.publier(operation_id="concurrent")["id"]
            finally:
                if getattr(store._local, "conn", None) is not None:
                    store._local.conn.close()
                    store._local.conn = None
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(publier, range(20)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(com.fils()["fils"][0]["messages_nombre"], 1)

    def test_quota_atomique_sans_restriction_sur_le_sujet(self):
        def publier(i):
            try:
                try:
                    self.publier(f"Avis libre {i}", operation_id=f"avis-{i}")
                    return True
                except com.CommunauteError as exc:
                    self.assertEqual(exc.code, "quota")
                    return False
            finally:
                if getattr(store._local, "conn", None) is not None:
                    store._local.conn.close()
                    store._local.conn = None
        with mock.patch.object(com, "MAX_PAR_MINUTE", 4), ThreadPoolExecutor(max_workers=8) as pool:
            resultats = list(pool.map(publier, range(12)))
        self.assertEqual(sum(resultats), 4)

    def test_quota_n_empeche_pas_rejeu_et_libere_apres_fenetre(self):
        with mock.patch.object(com, "MAX_PAR_MINUTE", 1):
            m = self.publier(operation_id="unique")
            self.assertEqual(self.publier(operation_id="unique")["id"], m["id"])
            self.erreur("quota", self.publier)
            com.publier(contenu="Plus tard", auteur="agent:chercheur", maintenant=1061)
            com.publier(contenu="Autre agent", auteur="agent:qa", maintenant=1061)

    def test_reponses_et_profondeur_sont_bornees(self):
        m = self.publier()
        with mock.patch.object(com, "MAX_MESSAGES_FIL", 2):
            r = com.publier(contenu="Réponse", auteur="agent:qa", parent_id=m["id"], maintenant=1001)
            self.erreur("quota", com.publier, contenu="Encore", auteur="agent:qa", parent_id=m["id"], maintenant=1002)
        with mock.patch.object(com, "MAX_PROFONDEUR", 1):
            self.erreur("quota", com.publier, contenu="Encore", auteur="agent:qa", parent_id=r["id"], maintenant=1002)

    def test_conversation_ne_devient_lecon_que_par_relecture_expresse(self):
        m = self.publier("Une conversation qui propose de mieux vérifier nos livraisons.")
        self.erreur("relecture", com.evaluer, "", m["id"], auteur=m["auteur"], decision="evaluer",
                    contenu="Je me valide", preuves=["test:ok"])
        self.erreur("relecture", com.evaluer, "", m["id"], auteur="agent:qa", decision="evaluer", contenu="Revu")
        self.erreur("transition", com.evaluer, "", m["id"], auteur="agent:qa", decision="retenir",
                    contenu="Trop tôt", preuves=["test:ok"])
        evaluation = com.evaluer("", m["id"], auteur="agent:qa", decision="evaluer", contenu="Comparaison réalisée",
                                preuves=["tests:comparaison"], operation_id="eval-1", maintenant=1001)
        self.assertEqual(evaluation["statut"], "evaluee")
        self.assertEqual(com.lecons(), [])
        retenue = com.evaluer("", m["id"], auteur="agent:qa", decision="retenir", contenu="Critères satisfaits",
                             preuves=["rapport:1"], operation_id="retenue-1", maintenant=1002)
        self.assertEqual(retenue["statut"], "retenue")
        lecon = com.lecons()[0]
        self.assertEqual(lecon["id"], m["id"])
        self.assertEqual([r["preuves"] for r in lecon["relectures"]], [["tests:comparaison"], ["rapport:1"]])
        self.assertEqual(com.fil("", m["id"])["fil"]["messages_nombre"], 3)
        com.evaluer("", m["id"], auteur="agent:qa", decision="retenir", contenu="Critères satisfaits",
                    preuves=["rapport:1"], operation_id="retenue-1", maintenant=1003)
        self.assertEqual(com.fil("", m["id"])["fil"]["messages_nombre"], 3)
        self.erreur("transition", com.evaluer, "", m["id"], auteur="agent:qa", decision="rejeter", contenu="Tard")

    def test_rejet_n_exige_pas_de_preuve_et_ne_supprime_pas_la_discussion(self):
        m = self.publier(type="amelioration")
        self.assertEqual(m["statut"], "proposee")
        com.evaluer("", m["id"], auteur="agent:qa", decision="evaluer", contenu="À comparer", preuves=["test:1"])
        r = com.evaluer("", m["id"], auteur="agent:qa", decision="rejeter", contenu="Résultat insuffisant")
        self.assertEqual(r["statut"], "rejetee")
        self.assertEqual(com.lecons(), [])
        com.publier(contenu="Poursuivons la discussion malgré le rejet.", auteur="agent:qa", parent_id=m["id"])
        self.assertEqual(com.fil("", m["id"])["fil"]["messages_nombre"], 4)

    def test_evaluations_concurrentes_une_transition_et_une_relecture(self):
        m = self.publier(type="amelioration")

        def evaluer(i):
            try:
                try:
                    com.evaluer("", m["id"], auteur=f"agent:qa-{i}", decision="evaluer", contenu="Évaluation",
                                preuves=[f"tests:{i}"], operation_id=f"evaluation:{i}", maintenant=1001)
                    return True
                except com.CommunauteError as exc:
                    self.assertEqual(exc.code, "transition")
                    return False
            finally:
                if getattr(store._local, "conn", None) is not None:
                    store._local.conn.close()
                    store._local.conn = None
        with ThreadPoolExecutor(max_workers=6) as pool:
            resultats = list(pool.map(evaluer, range(10)))
        self.assertEqual(sum(resultats), 1)
        self.assertEqual(com.fil("", m["id"])["fil"]["messages_nombre"], 2)

    def test_donnees_entree_sortie_independantes(self):
        preuves = ["tests:1"]
        avant = copy.deepcopy(preuves)
        m = self.publier(preuves=preuves)
        self.assertEqual(preuves, avant)
        m["preuves"].append("injection")
        self.assertEqual(com.fil("", m["id"])["fil"]["preuves"], avant)

    def test_bornes_et_types_stricts(self):
        for champs in ({"contenu": ""}, {"contenu": "x" * (com.MAX_CONTENU+1)}, {"contenu": "nul\x00"},
                       {"preuves": "preuve"}, {"preuves": ["x"] * 11}, {"salon": ""},
                       {"type": "inconnu"}, {"projet": True}, {"parent_id": "invalide"},
                       {"operation_id": "clé avec espaces"}):
            with self.subTest(champs=champs):
                self.erreur("validation", com.publier, auteur="agent:qa", **champs)
        for date in (True, float("nan"), float("inf"), -1, 10**1000):
            self.erreur("validation", com.publier, contenu="test", auteur="agent:qa", maintenant=date)
        for limite in (True, 0, 101, "10"):
            self.erreur("validation", com.fils, limite=limite)
        for curseur in (True, "0", "-1", "9223372036854775808", "abc"):
            self.erreur("validation", com.fils, avant=curseur)

    def test_transaction_exterieure_annule_publication(self):
        with self.assertRaises(RuntimeError):
            with store.transaction():
                self.publier()
                raise RuntimeError("Interruption métier")
        self.assertEqual(com.fils()["fils"], [])


class TestCommunauteJSON(CasCommunaute, unittest.TestCase):
    backend = "json"


class TestCommunauteSQLite(CasCommunaute, unittest.TestCase):
    backend = "sqlite"


if __name__ == "__main__":
    unittest.main()
