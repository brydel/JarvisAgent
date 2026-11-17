"""Les serveurs et outils de test ne doivent jamais viser la vraie session tmux.

Un état isolé ne suffit pas : tmux est global, et un dépôt sur un Board de test réveillait le vrai chef.
"""
import re
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = ("studio/board-v2/scripts/serveur_test.py", "outils/mesurer_board.py", "outils/verifier_mission_reelle.py")


class IsolationSessionTest(unittest.TestCase):
    def test_la_reinitialisation_refuse_un_etat_hors_de_la_suite(self):
        import test_missions

        etat_hors_suite = test_missions.test_jarvis.TMP / "autre-etat"
        with mock.patch.object(test_missions.config, "STATE_DIR", etat_hors_suite):
            with mock.patch.object(test_missions.mi, "backend") as backend:
                with self.assertRaisesRegex(RuntimeError, "Réinitialisation refusée"):
                    test_missions._reinitialiser()
                backend.assert_not_called()

    def test_chaque_script_isole_change_aussi_de_session_tmux(self):
        for chemin in SCRIPTS:
            texte = (RACINE / chemin).read_text(encoding="utf-8")
            etat = re.search(r'os\.environ\["JARVIS_STATE_DIR"\] = ', texte)
            session = re.search(r'os\.environ\["JARVIS_SESSION"\] = ', texte)
            self.assertTrue(etat and session, chemin)
            importe = re.search(r"^\s*from jarvis import", texte, re.M)
            self.assertLess(session.start(), importe.start(), f"{chemin} : la session doit être fixée avant l'import")

    def test_tout_script_qui_isole_l_etat_est_dans_la_liste(self):
        trouves = set()
        for dossier in ("studio/board-v2/scripts", "outils"):
            for f in (RACINE / dossier).glob("*.py"):
                if 'os.environ["JARVIS_STATE_DIR"] = ' in f.read_text(encoding="utf-8"):
                    trouves.add(f"{dossier}/{f.name}")
        self.assertEqual(trouves, set(SCRIPTS))


if __name__ == "__main__":
    unittest.main()
