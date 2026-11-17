"""Journal de mémoire : preuves, séparation des projets, rejeu et pagination."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import test_missions
from jarvis import adaptateurs, board, journal_memoire as journal, missions as mi, protocole_executant as proto


class JournalMemoireTest(test_missions.Base):
    def rattacher(self, mission, espace="Projet A", tenant=None):
        return mi.board_ajouter(tenant or self.org, espace, "mission", "Mission documentée", auteur="test",
                                mission_id=mission["mission_id"], analyser=False)["objet_id"]

    def test_echec_frustration_reprise_resolution_avec_preuves_stables(self):
        m = self.mission_simple()
        self.rattacher(m)
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret, now=100)
        r = proto.resultat(env, "echec", erreur="Données absentes",
                           frustration="Troisième demande de données (ghp_" + "e" * 30 + ")")
        self.assertEqual(mi.rendre_resultat(rid, secret, r, now=101)["statut"], mi.RETRY_SCHEDULED)
        self.assertTrue(mi.rendre_resultat(rid, secret, r, now=102)["doublon"])
        mi.recuperer(now=113)
        suivant = mi.reclamer(rid, secret, now=114)
        formate = "## Résumé\nUn résumé attesté.\n## Points clés\nDonnées disponibles."
        mi.rendre_resultat(rid, secret, proto.resultat(suivant, "reussi", contenu=formate), now=115)
        page = journal.lire(self.org, "Projet A")
        self.assertIsNone(page["avant"])
        reussite, reprise, echec, frustration = page["entrees"]
        self.assertEqual([e["nature"] for e in page["entrees"]], ["resolution", "reprise", "echec", "frustration"])
        self.assertEqual(reussite["cause_id"], reprise["id"])
        self.assertEqual(reprise["cause_id"], echec["id"])
        self.assertTrue(echec["factice"])
        self.assertEqual(frustration["auteur"], rid)
        self.assertIn("[expurgé]", frustration["detail"])
        self.assertNotIn("ghp_", frustration["detail"])
        self.assertEqual(frustration["preuve"]["tentative_id"], env["tentative_id"])
        self.assertEqual(reussite["preuve"]["tentative_id"], suivant["tentative_id"])
        preuve = {e["seq"]: e for e in mi.inspecter(self.org, m["mission_id"])["chronologie"]}
        self.assertTrue(all(x["preuve"]["sequence"] in preuve for x in page["entrees"]))
        self.assertEqual(preuve[frustration["preuve"]["sequence"]]["type"], "frustration_declaree")
        self.assertNotIn("ghp_", str(preuve[frustration["preuve"]["sequence"]]["donnees"]))

    def test_blocage_par_dependance_puis_reprise_relies_aux_transitions(self):
        cible = self.mission_simple()
        prerequisite = self.mission_simple()
        carte = self.rattacher(cible)
        autre = self.rattacher(prerequisite)
        board.lier(self.org, "Projet A", carte, autre, style="depend", par="test")
        rid, secret = self.executant()
        cr = self.coureur(rid, secret)
        self.assertEqual(cr.tour()["tache_id"], prerequisite["taches"][0])
        self.assertEqual(cr.tour()["tache_id"], cible["taches"][0])
        sequence = [p for p in journal.lire(self.org, "Projet A")["entrees"]
                    if p["preuve"]["mission_id"] == cible["mission_id"]]
        resolution, reprise, blocage = sequence
        self.assertEqual([p["nature"] for p in sequence], ["resolution", "reprise", "blocage"])
        self.assertEqual(resolution["cause_id"], reprise["id"])
        self.assertEqual(reprise["cause_id"], blocage["id"])

    def test_refus_revision_et_approbation_et_blocage_sont_distincts(self):
        a = self.mission_simple(niveau="L3")
        self.rattacher(a)
        ap = mi.approbations_en_attente(self.org)[0]
        mi.decider_approbation(self.org, ap["id"], False, acteur="studio:humain", acteur_type="humain")
        b = self.mission_simple()
        self.rattacher(b)
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret)
        mi.rendre_resultat(rid, secret, proto.resultat(env, "reussi", contenu="Contenu insuffisant."))
        page = journal.lire(self.org, "Projet A")
        review, refuse, bloque = page["entrees"]
        self.assertEqual([e["nature"] for e in page["entrees"]], ["refus", "refus", "blocage"])
        self.assertIn("revue refusée", review["detail"])
        self.assertEqual(refuse["preuve"]["approbation_id"], ap["id"])
        self.assertEqual(bloque["preuve"]["mission_id"], a["mission_id"])
        self.assertEqual(journal.lire(self.org, "Projet A", nature="refus")["entrees"], [review, refuse])

    def test_scoping_et_defilement_de_milliers_de_preuves(self):
        m = self.mission_simple()
        self.rattacher(m)
        self.rattacher(self.mission_simple(niveau="L3"), espace="Projet B")
        autre = mi.creer_organisation("autre")
        self.rattacher(self.mission_simple(autre, niveau="L3"), tenant=autre)
        self.mission_simple(niveau="L3")  # aucune preuve d'appartenance à un projet
        with mi.transaction(self.org) as c:
            for i in range(2501):
                mi._evenement(c, self.org, "tache_retenue", mission_id=m["mission_id"], tache_id=m["taches"][0],
                              now=i+1, raison=f"Raison {i}")
        avant = None
        preuves = []
        while True:
            page = journal.lire(self.org, "Projet A", avant=avant, limite=97)
            preuves.extend(e["preuve"] for e in page["entrees"])
            avant = page["avant"]
            if avant is None:
                break
        self.assertEqual(len(preuves), 2501)
        sequences = [e["sequence"] for e in preuves]
        self.assertEqual(sequences, sorted(set(sequences), reverse=True))
        self.assertTrue(all(e["mission_id"] == m["mission_id"] for e in preuves))
        self.assertEqual(len(journal.lire(self.org, "Projet B")["entrees"]), 1)
        self.assertEqual(len(journal.lire(autre, "Projet A")["entrees"]), 1)

    def test_declaration_exige_un_bail_authentifie(self):
        self.rattacher(self.mission_simple())
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret, now=100)
        r = proto.resultat(env, "echec", frustration="Une déclaration valide")
        with self.assertRaises(mi.MissionError):
            mi.rendre_resultat(rid, "faux-secret", r, now=101)
        with self.assertRaises(mi.MissionError):
            mi.rendre_resultat(rid, secret, r, now=100 + mi.BAIL_S + 1)
        avec_texte_non_valide = {**r, "frustration": ["annotation"]}
        with self.assertRaises(proto.EnveloppeInvalide):
            mi.rendre_resultat(rid, secret, avec_texte_non_valide, now=101)
        self.assertEqual(journal.lire(self.org, "Projet A", nature="frustration")["entrees"], [])

    def test_adaptateur_codex_collecte_une_declaration_explicite_et_la_retire_du_livrable(self):
        def execution_simulee(cmd, **kw):
            self.assertIn("JARVIS_FRICTION:", cmd[-1])
            Path(cmd[cmd.index("--output-last-message") + 1]).write_text(
                "## Résumé\nJARVIS_FRICTION: une citation d’exemple dans le texte\n"
                "## Points clés\nConclusion.\n\nJARVIS_FRICTION: attente d'une référence.\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        m = self.mission_simple()
        self.rattacher(m)
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret)
        with mock.patch.object(adaptateurs, "executer_processus", side_effect=execution_simulee):
            resultat = adaptateurs.Codex(binaire="factice").executer(env)
        self.assertEqual(resultat["frustration"], "attente d'une référence.")
        self.assertIn("citation d’exemple", resultat["contenu"])
        self.assertNotIn("attente d'une référence.", resultat["contenu"])
