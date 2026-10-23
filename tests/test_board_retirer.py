"""Le chef range le Board : retirer les cartes de travail finies (ou désignées), restaurer, sans rien effacer."""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
import test_board_v2
import test_travail_social

from jarvis import board, cli, missions as mi, plans, store, synchro, taches, travail_board  # noqa: E402

agent = test_travail_social.agent


class RetirerTest(test_board_v2.Base):
    def setUp(self):
        super().setUp()
        store.write_json(plans.PLANS_FILE, {"seq": 0, "plans": []})
        store.write_json(taches.FILE, {"seq": 0, "taches": []})
        store.write_json(travail_board.RETRAITS, {})
        p = plans.create("Vague", [plans.parse_item("repriceo:BIS-1:claude@frontend:a"),
                                   plans.parse_item("repriceo:BIS-2:codex@qa:b")])
        plans.decide(p["id"], True, par="test")
        taches.enregistrer(projet="repriceo", issue="BIS-1", agent="claude", worktree="bis-1", role="frontend", plan=p["id"])
        taches.enregistrer(projet="repriceo", issue="BIS-2", agent="codex", worktree="bis-2", role="qa", plan=p["id"])
        travail_board.synchroniser([agent("bis-1", "done"), agent("bis-2", "working")])
        self.note = mi.board_ajouter(self.org, "repriceo", "note", "Ma note perso", auteur="humain")["objet_id"]

    def chef(self, *args):
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"JARVIS_ROLE": "chef"}), contextlib.redirect_stdout(sortie):
            code = cli.main(["board", *args])
        return code, sortie.getvalue()

    def visibles(self):
        return {o["id"]: o for o in board.objets(self.org, "repriceo")["objets"]}

    def test_retirer_les_termines_seulement(self):
        code, texte = self.chef("retirer", "--espace", "repriceo", "--termines", "--essai")
        self.assertEqual(code, 0)
        self.assertIn("essai : rien n'a été retiré", texte)
        self.assertEqual(len(self.visibles()), 5, "l'essai ne touche à rien")
        code, texte = self.chef("retirer", "--espace", "repriceo", "--termines")
        self.assertEqual(code, 0)
        reste = self.visibles()
        types = sorted(o["type"] for o in reste.values())
        # la tâche BIS-2 travaille encore : elle, son plan et l'équipe restent ; BIS-1 (finie) part ; la note reste
        self.assertEqual(types, ["agents", "note", "plan", "tache"])
        self.assertIn(self.note, reste)
        self.assertEqual(next(o for o in reste.values() if o["type"] == "tache")["meta"]["issue"], "BIS-2")
        self.assertIn("1 carte(s) retirée(s)", texte)
        envois = [a for n, a in self.envois if n == "telegram"]
        self.assertTrue(envois and "🧹 Le chef a retiré 1 carte(s)" in envois[0][0], "l'humain est prévenu")

    def test_tout_fini_puis_restaurer_et_pas_de_recreation(self):
        travail_board.synchroniser([agent("bis-1", "done"), agent("bis-2", "done")])
        self.chef("retirer", "--espace", "repriceo", "--termines")
        self.assertEqual([o["type"] for o in self.visibles().values()], ["note"], "plan, tâches et équipe au repos partent")
        travail_board.synchroniser([agent("bis-1", "done"), agent("bis-2", "done")])
        self.assertEqual(len(self.visibles()), 1, "la synchronisation ne recrée pas les cartes retirées")
        code, texte = self.chef("restaurer", "--dernier")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.visibles()), 5)
        self.assertEqual(self.chef("restaurer", "--dernier")[0], 1, "un retrait ne se restaure qu'une fois")

    def test_l_equipe_revient_quand_le_travail_reprend(self):
        travail_board.synchroniser([agent("bis-1", "done"), agent("bis-2", "done")])
        self.chef("retirer", "--espace", "repriceo", "--termines")
        self.assertFalse(any(o["type"] == "agents" for o in self.visibles().values()))
        taches.enregistrer(projet="repriceo", issue="BIS-3", agent="claude", worktree="bis-3", role="backend")
        travail_board.synchroniser([agent("bis-3", "working")])
        equipe = [o for o in self.visibles().values() if o["type"] == "agents"]
        self.assertEqual(len(equipe), 1)
        self.assertEqual(equipe[0]["meta"]["actifs"], 1)

    def test_par_le_vrai_lanceur_comme_le_chef(self):
        """`jarvis board …` passe par bin/jarvis : les sous-commandes doivent atteindre le Board (pas workmux)."""
        import subprocess
        racine = test_jarvis.ROOT
        r = subprocess.run([str(racine / "bin" / "jarvis"), "board", "retirer", "--espace", "repriceo", "--termines", "--essai"],
                           capture_output=True, text=True, timeout=60, env={**os.environ, "JARVIS_ROLE": "chef"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("seraient retirées du Board repriceo", r.stdout)
        r = subprocess.run([str(racine / "bin" / "jarvis"), "board", "voir", "--espace", "repriceo"],
                           capture_output=True, text=True, timeout=60)
        self.assertIn("Board repriceo", r.stdout)

    def test_cartes_designees_et_garde_fous(self):
        code, _ = self.chef("retirer", "--espace", "repriceo", self.note)
        self.assertEqual(code, 0, "une carte que l'humain désigne peut être retirée, même une note")
        self.assertNotIn(self.note, self.visibles())
        self.assertEqual(self.chef("retirer", "--espace", "repriceo", "BO-000000000000")[0], 1, "carte inconnue")
        self.assertEqual(self.chef("retirer", "--espace", "repriceo")[0], 1, "rien à désigner : refus")
        self.assertEqual(self.chef("restaurer", self.note)[0], 0)
        self.assertIn(self.note, self.visibles())


if __name__ == "__main__":
    unittest.main()
