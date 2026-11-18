"""Transport Codex : collage explicite et conservation de la file aux frontières d’échec."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import test_jarvis  # noqa: F401 — environnement isolé avant les modules Jarvis
from jarvis import agents, chef_moteur, config, store  # noqa: E402


class SaisieCodexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-chef-saisie-")
        self.addCleanup(self.tmp.cleanup)
        self.commandes = []
        self.echec = None
        for patch in (
            mock.patch.object(config, "STATE_DIR", Path(self.tmp.name)),
            mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": "json"}),
            mock.patch.object(agents, "_chef_cible", return_value=("%73", "4567")),
            mock.patch.object(agents, "_chef_cible_vivante", return_value=True),
            mock.patch.object(agents, "chef_has_dialog", return_value=False),
            mock.patch.object(agents, "chef_running", return_value=True),
            mock.patch.object(chef_moteur, "courant", return_value="codex"),
            mock.patch.object(agents, "CODEX_PAUSE_SAISIE", 0),
            mock.patch.object(agents, "_run", side_effect=self._executer),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _executer(self, args, **kwargs):
        self.commandes.append((args, kwargs))
        if self.echec and args[1] == self.echec[0]:
            resultat = self.echec[1]
            if isinstance(resultat, BaseException):
                raise resultat
            return subprocess.CompletedProcess(args, resultat, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def _sans_entree(self):
        self.assertFalse(any(args[1] == "send-keys" and args[-1] == "Enter" for args, _ in self.commandes))

    def test_message_long_unicode_transmis_par_stdin_et_collage_explicite(self):
        texte = "État du Board, sources et agents : " + ("preuve café ; $(commande) ' " * 100)
        self.assertGreater(len(texte), 2000)
        self.assertTrue(agents._type_into_chef(texte))
        self.assertEqual([args[1] for args, _ in self.commandes],
                         ["load-buffer", "paste-buffer", "send-keys", "delete-buffer"])
        charge, kwargs = self.commandes[0]
        tampon = charge[charge.index("-b") + 1]
        self.assertEqual(charge, ["tmux", "load-buffer", "-b", tampon, "-"])
        self.assertEqual(kwargs["input_text"], texte)
        self.assertEqual(self.commandes[1][0], ["tmux", "paste-buffer", "-p", "-d", "-b", tampon, "-t", "%73"])
        self.assertEqual(self.commandes[2][0], ["tmux", "send-keys", "-t", "%73", "Enter"])
        self.assertEqual(self.commandes[3][0], ["tmux", "delete-buffer", "-b", tampon])
        self.assertFalse(any(texte in args for args, _ in self.commandes))

    def test_chaque_remise_utilise_son_tampon_unique(self):
        self.assertTrue(agents._type_into_chef("premier"))
        self.assertTrue(agents._type_into_chef("second"))
        tampons = [args[args.index("-b") + 1] for args, _ in self.commandes if args[1] == "load-buffer"]
        self.assertEqual(len(set(tampons)), 2)
        self.assertTrue(all(tampon.startswith("jarvis-chef-") for tampon in tampons))

    def test_chaque_retour_tmux_en_echec_conserve_la_remise(self):
        for commande in ("load-buffer", "paste-buffer", "send-keys"):
            with self.subTest(commande=commande):
                self.commandes.clear()
                self.echec = (commande, 1)
                self.assertFalse(agents._type_into_chef("non remis"))
                self.assertEqual(self.commandes[-1][0][1], "delete-buffer")
                if commande != "send-keys":
                    self._sans_entree()

    def test_exceptions_de_transport_nettoient_toujours_le_tampon(self):
        for commande in ("load-buffer", "paste-buffer", "send-keys"):
            for erreur in (OSError("interruption"), subprocess.TimeoutExpired("tmux", 5)):
                with self.subTest(commande=commande, erreur=type(erreur).__name__):
                    self.commandes.clear()
                    self.echec = (commande, erreur)
                    self.assertFalse(agents._type_into_chef("non remis"))
                    self.assertEqual(self.commandes[-1][0][1], "delete-buffer")

    def test_nettoyage_deja_effectue_ne_masque_pas_la_validation(self):
        self.echec = ("delete-buffer", subprocess.TimeoutExpired("tmux", 5))
        self.assertTrue(agents._type_into_chef("remis une fois"))
        self.assertEqual(sum(args[1] == "send-keys" for args, _ in self.commandes), 1)

    def test_absence_ou_dialogue_initial_ne_charge_aucun_texte(self):
        with mock.patch.object(agents, "_chef_cible", return_value=None):
            self.assertFalse(agents._type_into_chef("absent"))
        with mock.patch.object(agents, "chef_has_dialog", return_value=True):
            self.assertFalse(agents._type_into_chef("dialogue"))
        self.assertEqual(self.commandes, [])

    def test_changement_cible_ou_dialogue_bloque_collage_et_entree(self):
        for garde, sequence, collage_autorise in (
            ("_chef_cible_vivante", [True, False], False),
            ("_chef_cible_vivante", [True, True, False], True),
            ("chef_has_dialog", [False, True], False),
            ("chef_has_dialog", [False, False, True], True),
        ):
            with self.subTest(garde=garde, sequence=sequence):
                self.commandes.clear()
                with mock.patch.object(agents, garde, side_effect=sequence):
                    self.assertFalse(agents._type_into_chef("garde modifiée"))
                self._sans_entree()
                self.assertEqual(any(args[1] == "paste-buffer" for args, _ in self.commandes), collage_autorise)
                self.assertEqual(self.commandes[-1][0][1], "delete-buffer")

    def test_transport_claude_conserve_la_frappe_litterale(self):
        with mock.patch.object(chef_moteur, "courant", return_value="claude"):
            self.assertTrue(agents._type_into_chef("une seule ligne"))
        self.assertEqual([args for args, _ in self.commandes], [
            ["tmux", "send-keys", "-t", "%73", "-l", "une seule ligne"],
            ["tmux", "send-keys", "-t", "%73", "Enter"],
        ])

    def test_file_identifiee_reste_non_acquittee_jusqua_reprise_reussie(self):
        self.echec = ("paste-buffer", 1)
        self.assertTrue(agents.chef_inject("message persistant", message_id="transport-codex"))
        entree = store.read_json(agents.CHEF_QUEUE, [])[0]
        self.assertFalse(entree["recu"])
        self.assertEqual(entree["texte"], "message persistant")
        self.echec = None
        self.assertEqual(agents.chef_flush_queue(), 1)
        self.assertTrue(store.read_json(agents.CHEF_QUEUE, [])[0]["recu"])
        nombre = len(self.commandes)
        self.assertTrue(agents.chef_inject("message persistant", message_id="transport-codex"))
        self.assertEqual(len(self.commandes), nombre)


if __name__ == "__main__":
    unittest.main()
