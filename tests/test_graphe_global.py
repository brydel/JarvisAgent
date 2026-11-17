"""Graphe global, appartenances de session, pagination et cloisonnement."""
import json
import sqlite3
import unittest
from unittest import mock

import test_missions
from jarvis import agent_runtime, board, graphe_global, missions as mi, protocole_executant as proto


class GrapheGlobalTest(test_missions.Base):
    def setUp(self):
        super().setUp()
        self.patches = [
            mock.patch.object(graphe_global.agents, "status_all", return_value=([], "")),
            mock.patch.object(graphe_global.taches, "toutes", return_value=[]),
            mock.patch.object(graphe_global.config, "projects", return_value={}),
            mock.patch.object(graphe_global, "_cache_sessions", (0, None, "")),
        ]
        self.runtime_patch = mock.patch.object(graphe_global, "_runtimes", return_value=([], 0, []))
        self.patches.append(self.runtime_patch)
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def ajouter(self, espace, titre, *, tenant=None, meta=None, mission_id=None):
        return mi.board_ajouter(tenant or self.org, espace, "note", titre, auteur="test",
                                meta=meta or {"titre": titre}, mission_id=mission_id, analyser=False)["objet_id"]

    def test_tous_projets_et_pages_sans_objets_supprimes_ni_autre_tenant(self):
        a = self.ajouter("alpha", "Origine")
        b = self.ajouter("beta", "Cible")
        c = self.ajouter("beta", "Héritage")
        board.lier(self.org, "beta", b, c, style="alimente", par="test")
        retiree = self.ajouter("alpha", "Retirée")
        board.supprimer(self.org, [retiree], par="test")
        autre = mi.creer_organisation("Autre")
        privee = self.ajouter("secret", "Carte étrangère", tenant=autre)
        ids, liens, page = set(), set(), 1
        while page:
            lot = graphe_global.lire(self.org, page=page, limite=1)
            ids.update(o["id"] for o in lot["objets"])
            liens.update(l["id"] for l in lot["liens"])
            page = lot["suivant"]
        self.assertEqual(ids, {a, b, c})
        self.assertEqual(len(liens), 1)
        self.assertNotIn(privee, ids)
        self.assertEqual(lot["couverture"]["objets"]["total"], 3)
        self.assertEqual({p["nom"] for p in lot["projets"]}, {"alpha", "beta"})
        selection = graphe_global.lire(self.org, limite=1, objet=c)
        self.assertIn(c, {o["id"] for o in selection["objets"]})
        self.assertNotIn(privee, {o["id"] for o in graphe_global.lire(self.org, objet=privee)["objets"]})
        self.assertNotEqual(graphe_global.lire(autre)["cle_disposition"], lot["cle_disposition"])

    def test_deux_tentatives_partagent_mission_et_gardent_leurs_preuves(self):
        m = self.mission_simple()
        self.ajouter("alpha", "Mission alpha", mission_id=m["mission_id"])
        self.ajouter("beta", "Mission beta", mission_id=m["mission_id"])
        rid, secret = self.executant()
        premier = mi.reclamer(rid, secret, now=100)
        mi.rendre_resultat(rid, secret, proto.resultat(premier, "echec", erreur="Données absentes",
                           frustration="Source à retrouver"), now=101)
        mi.recuperer(now=113)
        second = mi.reclamer(rid, secret, now=114)
        contenu = "## Résumé\nUn résultat attesté.\n## Points clés\nDonnées disponibles."
        mi.rendre_resultat(rid, secret, proto.resultat(second, "reussi", contenu=contenu), now=115)
        lot = graphe_global.lire(self.org)
        sessions = {s["id"]: s for s in lot["sessions"]}
        self.assertEqual(set(sessions), {premier["tentative_id"], second["tentative_id"]})
        for s in sessions.values():
            self.assertEqual(s["mission_ids"], [m["mission_id"]])
            self.assertEqual(s["projets"], ["alpha", "beta"])
            self.assertEqual(s["projet"], "")
            self.assertEqual(s["objet_ids"], [])
        for e in lot["entrees"]:
            tentative = e["preuve"].get("tentative_id")
            if tentative:
                self.assertIn(e["id"], sessions[tentative]["evenement_ids"])
                autre = second["tentative_id"] if tentative == premier["tentative_id"] else premier["tentative_id"]
                self.assertNotIn(e["id"], sessions[autre]["evenement_ids"])
        premier_lot = graphe_global.lire(self.org, limite=1, session=premier["tentative_id"])
        self.assertIn(premier["tentative_id"], {s["id"] for s in premier_lot["sessions"]})
        self.assertNotIn(secret, json.dumps(lot))

    def test_entree_historique_ciblee_retrouve_sa_session_sans_fuite(self):
        m = self.mission_simple()
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret, now=100)
        mi.rendre_resultat(rid, secret, proto.resultat(env, "echec", erreur="Ancienne preuve"), now=101)
        premiere = next(e for e in graphe_global.lire(self.org)["entrees"] if e["nature"] == "echec")
        self.mission_simple(niveau="L3")
        sans_cible = graphe_global.lire(self.org, limite=1)
        self.assertNotIn(premiere["id"], {e["id"] for e in sans_cible["entrees"]})
        lot = graphe_global.lire(self.org, limite=1, entree=premiere["id"])
        self.assertIn(premiere["id"], {e["id"] for e in lot["entrees"]})
        session = next(s for s in lot["sessions"] if s["id"] == env["tentative_id"])
        self.assertIn(premiere["id"], session["evenement_ids"])
        autre = mi.creer_organisation("Journal étranger")
        self.assertEqual(graphe_global.lire(autre, entree=premiere["id"])["entrees"], [])
        for ident in ("memoire:0", "memoire:-1", "memoire:9223372036854775808", "../123"):
            with self.assertRaises(ValueError):
                graphe_global.lire(self.org, entree=ident)

    def test_registres_locaux_et_appartenances_hors_sous_page(self):
        self.runtime_patch.stop()
        carte = self.ajouter("alpha", "Issue JRV", meta={"travail_ref": "JRV-EXACT", "titre": "Issue JRV"})
        declaree = self.ajouter("alpha", "Appartenance déclarée", meta={"session_id": "T-00001"})
        autre = mi.creer_organisation("Autre tenant")
        privee = self.ajouter("secret", "Privée", tenant=autre)
        ident = "AR-" + "a" * 24
        c = agent_runtime._db()
        c.execute("DELETE FROM agent_runtime_runs")
        self.addCleanup(lambda: agent_runtime._db().execute("DELETE FROM agent_runtime_runs"))
        for suffixe, date in (("a", 1), ("b", 2)):
            doc = {"tache": {"objective": "Travail attesté", "inputs": ["board:" + carte, "board:" + privee]},
                   "created_at": date, "messages_prives": ["TOKEN-NE-PAS-EXPOSER"]}
            c.execute("INSERT INTO agent_runtime_runs VALUES(?,?,?,?,?)",
                      ("AR-" + suffixe * 24, "alpha", "succeeded", date, json.dumps(doc)))
        fiches = [{"id": "T-00001", "projet": "alpha", "issue": "JRV-EXACT", "worktree": "ancien",
                   "statut": "terminee", "cree": 1, "debut": 1, "fin": 2},
                  {"id": "T-00002", "projet": "beta", "issue": "AUTRE", "worktree": "nouveau", "statut": "lancee"}]
        with mock.patch.object(graphe_global.taches, "toutes", return_value=list(reversed(fiches))):
            lot = graphe_global.lire(self.org, limite=1, session=ident, objet=declaree)
            donnees = {s["id"]: s for s in lot["sessions"]}
            self.assertIn(carte, donnees[ident]["objet_ids"])
            self.assertNotIn(privee, donnees[ident]["objet_ids"])
            self.assertIn(carte, donnees["T-00001"]["objet_ids"])
            self.assertIn(declaree, donnees["T-00001"]["objet_ids"])
            self.assertNotIn("TOKEN-NE-PAS-EXPOSER", json.dumps(lot))
            c.execute("SELECT 1")  # le lecteur global ne ferme pas la connexion thread-local des outils
            with mock.patch.object(graphe_global.taches, "toutes") as registre:
                foreign = graphe_global.lire(autre)
                registre.assert_not_called()
            self.assertEqual(foreign["sessions"], [])
            self.assertNotIn("alpha", {p["nom"] for p in foreign["projets"]})

    def test_registre_runtime_indisponible_et_parametres_bornes(self):
        carte = self.ajouter("alpha", "Reste consultable")
        self.runtime_patch.stop()
        agent_runtime._db()
        ouvrir = sqlite3.connect

        def connecter(cible, *args, **kwargs):
            if str(cible).startswith("file:"):
                raise sqlite3.OperationalError("verrou")
            return ouvrir(cible, *args, **kwargs)

        with mock.patch.object(graphe_global.sqlite3, "connect", side_effect=connecter):
            lot = graphe_global.lire(self.org)
        self.assertIn(carte, {o["id"] for o in lot["objets"]})
        self.assertTrue(lot["avertissements"])
        for options in ({"page": 0}, {"limite": 101}, {"objet": "../x"}, {"session": "../x"}, {"page": True}):
            with self.assertRaises(ValueError):
                graphe_global.lire(self.org, **options)


if __name__ == "__main__":
    unittest.main()
