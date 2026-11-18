"""Une note locale reste conservée quand sa remise Telegram échoue."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé avant les imports Jarvis
from jarvis import cli, memoire


class NoteTelegramTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-note-telegram-")
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / "journal.md"

    def noter(self, *arguments, remis=True):
        self.sortie, self.erreur = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(cli.store, "state_path", return_value=self.journal),
            mock.patch.object(cli.store, "feed_add") as fil,
            mock.patch.object(memoire, "noter") as memoire_note,
            mock.patch.object(cli.notify, "telegram", return_value=remis) as telegram,
            contextlib.redirect_stdout(self.sortie),
            contextlib.redirect_stderr(self.erreur),
        ):
            code = cli.main(["note", *arguments])
        return code, telegram, fil, memoire_note

    def test_sans_option_envoyer_ne_contacte_pas_telegram(self):
        code, telegram, fil, memoire_note = self.noter("Lecture du Board terminée.")
        self.assertEqual(code, 0)
        self.assertIn("Lecture du Board terminée.", self.journal.read_text())
        telegram.assert_not_called()
        fil.assert_called_once()
        memoire_note.assert_called_once()

    def test_confirmation_telegram_reussie(self):
        code, telegram, _, _ = self.noter("Ton Board contient trois cartes.", "--envoyer")
        self.assertEqual(code, 0)
        telegram.assert_called_once_with("📝 Bilan du chef\n\nTon Board contient trois cartes.")
        self.assertIn("envoyé sur Telegram", self.sortie.getvalue())
        self.assertEqual(self.erreur.getvalue(), "")

    def test_echec_telegram_est_signale_et_note_conservee(self):
        code, telegram, fil, memoire_note = self.noter("Voici ma réponse.", "--envoyer", remis=False)
        self.assertNotEqual(code, 0)
        telegram.assert_called_once()
        self.assertIn("Voici ma réponse.", self.journal.read_text())
        fil.assert_called_once()
        memoire_note.assert_called_once()
        self.assertIn("Note conservée", self.erreur.getvalue())
        self.assertIn("envoi Telegram non confirmé", self.erreur.getvalue())
        self.assertNotIn("envoyé sur Telegram", self.sortie.getvalue())

    def test_note_vide_necrit_et_nenvoie_rien(self):
        code, telegram, fil, memoire_note = self.noter(" ", "--envoyer")
        self.assertNotEqual(code, 0)
        self.assertFalse(self.journal.exists())
        telegram.assert_not_called()
        fil.assert_not_called()
        memoire_note.assert_not_called()


if __name__ == "__main__":
    unittest.main()
