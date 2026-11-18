"""Le canal de retour Telegram suit le moteur du Chef, pour le texte et les fichiers."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_jarvis  # noqa: F401 — environnement de test isolé
from jarvis import chef_moteur, config, daemon, telegram


class FauxBot:
    def __init__(self):
        self.messages = []
        self.fichiers = []

    def send(self, destinataire, texte, buttons=None):
        self.messages.append((destinataire, texte))

    def download(self, identifiant, destination, max_bytes):
        self.fichiers.append((identifiant, destination, max_bytes))
        destination.write_bytes(b"document factice")


class ReponsesTelegramTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-telegram-reponses-")
        self.addCleanup(self.tmp.cleanup)
        self.patches = (
            mock.patch.object(config, "DATA_DIR", Path(self.tmp.name)),
            mock.patch.object(daemon.store, "feed_add"),
            mock.patch.object(daemon, "_deposer_sur_board", return_value=None),
            mock.patch.object(daemon.ag, "chef_inject", return_value=True),
            mock.patch.object(chef_moteur, "courant", return_value="codex"),
            mock.patch.object(telegram.Bot, "call", side_effect=AssertionError("Aucun appel Telegram réel")),
            mock.patch.object(daemon.notify, "telegram", side_effect=AssertionError("Pas de réponse implicite")),
        )
        effets = [patch.start() for patch in self.patches]
        for patch in self.patches:
            self.addCleanup(patch.stop)
        self.deposer, self.injecter, self.moteur = effets[2:5]
        self.appel_reseau, self.envoi_implicite = effets[5:7]

    def tearDown(self):
        self.appel_reseau.assert_not_called()
        self.envoi_implicite.assert_not_called()

    def verifier_rappel(self, texte, moteur):
        commande = "jarvis-chef jarvis note" if moteur == "codex" else "jarvis note"
        self.assertIn(f'avec : {commande} "<ta réponse>" --envoyer', texte)
        self.assertIn("n'est pas transmise à Telegram", texte)
        self.assertIn("que si cette commande réussit", texte)
        self.assertEqual(texte.count("[Message de ton humain via Telegram]"), 1)

    def test_texte_garde_le_contenu_et_rappelle_la_porte_du_moteur(self):
        for moteur in ("claude", "codex"):
            with self.subTest(moteur=moteur):
                self.moteur.return_value = moteur
                self.injecter.reset_mock()
                bot = FauxBot()
                daemon.handle_update(bot, "42", {"message": {
                    "chat": {"id": 42}, "from": {"id": 42}, "text": "Analyse ces couleurs"}})
                self.injecter.assert_called_once()
                texte = self.injecter.call_args.args[0]
                self.assertTrue(texte.startswith("[Message de ton humain via Telegram] Analyse ces couleurs"))
                self.verifier_rappel(texte, moteur)
                self.assertEqual(bot.messages, [("42", "✔ Transmis au chef.")])

    def test_fichier_garde_la_preuve_et_rappelle_la_porte_du_moteur(self):
        for moteur in ("claude", "codex"):
            with self.subTest(moteur=moteur):
                self.moteur.return_value = moteur
                self.injecter.reset_mock()
                bot = FauxBot()
                daemon.handle_update(bot, "42", {"message": {
                    "chat": {"id": 42}, "from": {"id": 42}, "message_id": 73,
                    "caption": "Synthèse jointe", "document": {
                        "file_id": "document-factice", "file_name": "brief.pdf", "file_size": 20}}})
                self.injecter.assert_called_once()
                texte = self.injecter.call_args.args[0]
                self.assertTrue(texte.startswith("[Message de ton humain via Telegram] Fichier joint :"))
                self.assertIn("Légende : Synthèse jointe", texte)
                self.assertNotIn("l'outil Read", texte)
                self.assertEqual(len(bot.fichiers), 1)
                self.assertIn(str(bot.fichiers[0][1]), texte)
                self.assertTrue(bot.fichiers[0][1].is_file())
                self.verifier_rappel(texte, moteur)
                self.assertEqual(bot.messages, [("42", "✔ Fichier transmis au chef.")])

    def test_depot_board_conserve_sa_provenance(self):
        self.deposer.return_value = {"espace": "atelier", "objet_id": "BO-000000000001"}
        bot = FauxBot()
        daemon.handle_update(bot, "42", {"message": {
            "chat": {"id": 42}, "from": {"id": 42}, "text": "#atelier https://exemple.test/brief"}})
        texte = self.injecter.call_args.args[0]
        self.assertIn("déposé sur le Board atelier, carte BO-000000000001", texte)
        self.verifier_rappel(texte, "codex")
        self.assertEqual(len(bot.messages), 2)

    def test_chef_absent_ne_produit_pas_de_fausse_reponse(self):
        self.injecter.return_value = False
        bot = FauxBot()
        daemon.handle_update(bot, "42", {"message": {
            "chat": {"id": 42}, "from": {"id": 42}, "text": "Question de test"}})
        self.assertEqual(len(bot.messages), 1)
        self.assertIn("Le chef n'est pas lancé", bot.messages[0][1])
        self.assertNotIn("Transmis", bot.messages[0][1])

    def test_intrus_ne_recoit_pas_le_rappel_ni_un_acces_au_chef(self):
        bot = FauxBot()
        daemon.handle_update(bot, "42", {"message": {
            "chat": {"id": 666}, "from": {"id": 666}, "text": "Message de test"}})
        self.injecter.assert_not_called()
        self.moteur.assert_not_called()
        self.assertEqual(bot.messages, [(666, "⛔ Ce Jarvis est privé.")])
