"""Le noeud GPU (Jetson) est visible du chef et de /etat : « est-ce que tu vois la Jetson ? » a une réponse."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé

from jarvis import noeud, report  # noqa: E402

ACTIF = {"actif": True, "cible": "brydel@10.0.0.44", "connexion": "jetson-test", "mandat_board": "MA-x"}
SANTE = {"modele": "small", "occupe": False, "duree_max_s": 1800,
         "mesures": {"memoire_dispo_mo": 5482, "memoire_totale_mo": 7619, "gpu_c": 49, "cpu_c": 50}}


class NoeudVisibleTest(unittest.TestCase):
    def setUp(self):
        noeud._dernier_etat = (0.0, None, "")

    def test_non_configure(self):
        with mock.patch.object(noeud, "reglages", return_value={}):
            joignable, texte = noeud.texte_etat(cache_s=0)
        self.assertIsNone(joignable)
        self.assertIn("désactivé", texte)

    def test_joignable_puis_cache(self):
        with mock.patch.object(noeud, "reglages", return_value=ACTIF), \
             mock.patch.object(noeud, "sante", return_value=SANTE) as sante:
            joignable, texte = noeud.texte_etat()
            self.assertTrue(joignable)
            self.assertIn("audio small, libre", texte)
            self.assertIn("5482/7619 Mo", texte)
            noeud.texte_etat()
            self.assertEqual(sante.call_count, 1, "/etat ne relance pas SSH à chaque affichage")
            noeud.texte_etat(cache_s=0)
            self.assertEqual(sante.call_count, 2, "la commande explicite mesure toujours")

    def test_modele_texte_distinct_du_modele_audio(self):
        sante = {**SANTE, "modeles": {"audio": "small", "moteur_audio": "whisper", "llm": "qwen3.5:4b",
                                      "contexte": 8192, "charge": None}}
        with mock.patch.object(noeud, "reglages", return_value=ACTIF), \
             mock.patch.object(noeud, "sante", return_value=sante):
            _, texte = noeud.texte_etat(cache_s=0)
        self.assertIn("audio whisper:small · texte/image qwen3.5:4b (contexte 8192), libre", texte)

    def test_injoignable(self):
        with mock.patch.object(noeud, "reglages", return_value=ACTIF), \
             mock.patch.object(noeud, "sante", side_effect=noeud.NoeudError("noeud injoignable (TimeoutExpired)")):
            joignable, texte = noeud.texte_etat(cache_s=0)
        self.assertFalse(joignable)
        self.assertIn("injoignable", texte)

    def test_etat_affiche_la_jetson(self):
        with mock.patch.object(noeud, "texte_etat", return_value=(True, "● Noeud GPU brydel@10.0.0.44 : modèle small, libre")):
            self.assertIn("NOEUD GPU (JETSON)", report.text())
        with mock.patch.object(noeud, "texte_etat", return_value=(None, "○ noeud GPU désactivé")):
            self.assertNotIn("NOEUD GPU", report.text(), "rien à montrer quand aucun noeud n'est configuré")

    def test_le_chef_sait_comment_repondre(self):
        consignes = (test_jarvis.ROOT / "chef" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("jarvis noeud etat", consignes)
        self.assertIn("si tu vois la Jetson", consignes)
        self.assertTrue(Path(test_jarvis.ROOT / "bin" / "jarvis").exists())


if __name__ == "__main__":
    unittest.main()
