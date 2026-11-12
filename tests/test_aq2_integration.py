"""Lot 2, intégration des quatre volets : ce que chaque volet attendait des autres.
Voir docs/autonomy/agents-qualite.md, section « Lot 2 — intégration des quatre volets »."""

from __future__ import annotations

import contextlib
import io
import time
import types
import unittest
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
from test_jarvis import ROOT

from jarvis import chef_moteur, cli, comptes_rendus as cr, evaluation, prompt_agent, roles  # noqa: E402


class EvaluationDuRelecteurTest(unittest.TestCase):
    def test_le_relecteur_evalue_recoit_le_gabarit_du_verdict(self):
        prompt = prompt_agent.pour_evaluation(roles.get("revue"), "Relis le travail et écris verdict.md.")
        fin = prompt.split("## Fini et compte rendu")[1]
        self.assertIn(cr.GABARIT_VERDICT, fin)
        self.assertNotIn("✅ TERMINÉ", fin)
        self.assertNotIn("gh pr review", fin, "pas de PR en évaluation")
        autre = prompt_agent.pour_evaluation(roles.get("backend"), "Écris la fonction.")
        self.assertIn(cr.GABARIT_TERMINE, autre)
        self.assertNotIn(cr.GABARIT_VERDICT, autre)

    def test_le_dernier_verdict_de_la_sortie_est_relu(self):
        prompt = prompt_agent.pour_evaluation(roles.get("revue"), "Relis le travail.")
        verdict = ("VERDICT : CORRECTIONS\nCritères :\n1. remise plafonnée → non satisfait : correction n° 1\nCorrections exigées :\n"
                   "1. [bloquant] app/remise.py:5 — la remise dépasse 100 % ; attendu : plafonnée à 100\n"
                   "Suggestions :\n- aucune\nVérifications :\n- `python3 -m unittest` → OK, 2 tests\n")
        r = evaluation.analyser_sortie(prompt + "\njournal du CLI…\n" + verdict)
        self.assertEqual((r["type"], r["conforme"]), ("verdict", True), r)
        gabarit = "```\n" + cr.GABARIT_VERDICT + "\n```\n"
        seul = evaluation.analyser_sortie("journal\n" + gabarit)
        self.assertEqual((seul["type"], seul["conforme"]), ("inconnu", False),
                         "le gabarit recopié par le CLI n'est pas un verdict rendu")

    def test_eval_resultats_affiche_l_etat_du_compte_rendu(self):
        base = {"ts": time.time(), "agent": "claude", "modele": "m", "brief": "abc", "duree_s": 3.0, "ok": True}
        res = [dict(base, cas="a/ancien"),
               dict(base, cas="a/bon", compte_rendu={"type": "termine", "conforme": True, "anomalies": []}),
               dict(base, cas="a/faux", compte_rendu={"type": "termine", "conforme": False, "anomalies": ["x", "y"]}),
               dict(base, cas="a/rien", compte_rendu={"type": "inconnu", "conforme": False, "anomalies": ["z"]})]
        sortie = io.StringIO()
        with mock.patch.object(evaluation, "resultats", return_value=res), contextlib.redirect_stdout(sortie):
            self.assertEqual(cli.cmd_eval(types.SimpleNamespace(action="resultats", n=30)), 0)
        lignes = sortie.getvalue().splitlines()
        self.assertEqual(len(lignes), 4)
        for ligne, attendu in zip(lignes, ("compte rendu non analysé", "compte rendu conforme",
                                           "compte rendu non conforme (2 anomalies)", "compte rendu absent")):
            self.assertTrue(ligne.endswith(attendu), ligne)


class RolesAlignesTest(unittest.TestCase):
    def test_le_role_du_chef_decrit_le_verdict_tel_qu_il_est_code(self):
        role = (ROOT / "chef" / "CLAUDE.md").read_text(encoding="utf-8")
        etape = role.split("4. Quand le relecteur a fini")[1].split("\n5. ")[0]
        for attendu in ("`jarvis verdict <projet> <ISSUE>`", "sans le recopier", "--pr 123", "verdict absent",
                        "non conforme ou ambigu", "contradiction", 'pret|corrections "résumé"', "rien n'est écrit"):
            self.assertIn(attendu, etape)
        # Les motifs cités sont ceux que le code lève.
        from jarvis import verdicts
        for motif in ("absent", "non_conforme", "ambigu", "contradiction"):
            self.assertIn(motif, verdicts.MOTIFS)
        codex = chef_moteur.role_codex(role)
        self.assertIn("jarvis-chef jarvis verdict <projet> <ISSUE>", codex)
        self.assertIn("non conforme ou ambigu", codex)

    def test_l_incertitude_bloquante_se_dit_partout_pareil(self):
        for chemin in ("templates/CLAUDE.md", "templates/AGENTS.md", "CLAUDE.md", "chef/CLAUDE.md"):
            texte = (ROOT / chemin).read_text(encoding="utf-8")
            self.assertRegex(texte, r"ne (?:la )?touche pas", chemin)
            self.assertRegex(texte, r"[Nn]e livre rien qui dépende de (?:la|ta) réponse", chemin)
        self.assertIn("ne livre rien qui dépende de la réponse", " ".join(prompt_agent.INCERTITUDE))
        self.assertEqual((ROOT / "templates" / "CLAUDE.md").read_bytes(), (ROOT / "templates" / "AGENTS.md").read_bytes())

    def test_les_briefs_renvoient_au_bloc_d_outils(self):
        for nom in ("recherche", "frontend", "qa", "design"):
            self.assertIn("« Outils de cette session »", roles.get(nom)["corps"], nom)
        # Le titre cité est celui que le prompt porte vraiment.
        from jarvis import outils_session
        self.assertEqual(outils_session.bloc(agent="", projet="")[0], "## Outils de cette session")
        self.assertNotIn("si tu n'as aucun outil de recherche web", roles.get("recherche")["corps"])


if __name__ == "__main__":
    unittest.main()
