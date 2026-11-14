"""La remise au chef vise un volet vivant, même après un redémarrage incomplet."""
import os
import time
import unittest
from unittest import mock

import test_jarvis
from jarvis import agents, config, store


class CibleChefTest(unittest.TestCase):
    def setUp(self):
        self.session = f"jcible-{os.getpid()}"
        self.tmux = test_jarvis.tmux
        self.tmux("new-session", "-d", "-s", self.session, "-n", "cockpit", "sh")
        self.addCleanup(self.tmux, "kill-session", "-t", self.session)
        for objet, nom, valeur in ((config, "SESSION", self.session),):
            patch = mock.patch.object(objet, nom, valeur)
            patch.start()
            self.addCleanup(patch.stop)
        store.supprimer(agents.CHEF_QUEUE)
        self.addCleanup(store.supprimer, agents.CHEF_QUEUE)
        from jarvis import chef_moteur
        patch = mock.patch.object(chef_moteur, "courant", return_value="claude")
        patch.start()
        self.addCleanup(patch.stop)

    def chef(self, commande):
        cible = self.tmux("new-window", "-d", "-P", "-F", "#{pane_id}", "-t", self.session + ":",
                          "-n", "chef", commande).strip()
        time.sleep(0.15)
        return cible

    def test_un_shell_avant_le_chef_ne_recoit_jamais_le_message(self):
        shell = self.chef("sh")
        chef = self.chef("cat")
        self.assertTrue(agents.chef_inject("MARQUEUR_CHEF_VIVANT"))
        time.sleep(0.15)
        self.assertIn("MARQUEUR_CHEF_VIVANT", self.tmux("capture-pane", "-p", "-t", chef))
        self.assertNotIn("MARQUEUR_CHEF_VIVANT", self.tmux("capture-pane", "-p", "-t", shell))
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), [])

    def test_la_question_du_vrai_chef_garde_le_message_en_attente(self):
        shell = self.chef("sh")
        chef = self.chef("cat")
        self.tmux("send-keys", "-t", chef, "-l", "Do you want to proceed")
        self.tmux("send-keys", "-t", chef, "Enter")
        time.sleep(0.15)
        self.assertTrue(agents.chef_inject("MESSAGE_EN_ATTENTE"))
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), ["MESSAGE_EN_ATTENTE"])
        self.assertNotIn("MESSAGE_EN_ATTENTE", self.tmux("capture-pane", "-p", "-t", shell))
        self.assertNotIn("MESSAGE_EN_ATTENTE", self.tmux("capture-pane", "-p", "-t", chef))

    def test_un_volet_shell_selectionne_ne_detourne_pas_la_remise(self):
        chef = self.chef("cat")
        shell = self.tmux("split-window", "-P", "-F", "#{pane_id}", "-t", chef, "sh").strip()
        time.sleep(0.15)
        self.assertTrue(agents.chef_inject("MESSAGE_AU_VOLET"))
        time.sleep(0.15)
        self.assertIn("MESSAGE_AU_VOLET", self.tmux("capture-pane", "-p", "-t", chef))
        self.assertNotIn("MESSAGE_AU_VOLET", self.tmux("capture-pane", "-p", "-t", shell))


    def test_arret_entre_saisie_et_entree_garde_le_message(self):
        self.chef("cat")
        execute = agents._run
        apres_saisie = False
        commandes = []
        vivant = agents._chef_cible_vivante

        def run(args, **kwargs):
            nonlocal apres_saisie
            commandes.append(args)
            resultat = execute(args, **kwargs)
            if args[1] == "send-keys" and "-l" in args:
                apres_saisie = True
            return resultat

        with mock.patch.object(agents, "_run", side_effect=run), mock.patch.object(
                agents, "_chef_cible_vivante", side_effect=lambda cible: not apres_saisie and vivant(cible)):
            self.assertTrue(agents.chef_inject("MESSAGE_NON_VALIDE"))
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), ["MESSAGE_NON_VALIDE"])
        self.assertFalse(any(cmd[1] == "send-keys" and cmd[-1] == "Enter" for cmd in commandes))

    def test_un_volet_mort_ne_recoit_rien(self):
        chef = self.chef("cat")
        self.tmux("set-window-option", "-t", chef, "remain-on-exit", "on")
        self.tmux("send-keys", "-t", chef, "C-d")
        time.sleep(0.15)
        self.assertFalse(agents.chef_running())
        self.assertFalse(agents._type_into_chef("MESSAGE_SANS_DESTINATAIRE"))


if __name__ == "__main__":
    unittest.main()
