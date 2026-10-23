"""Le chef dessine le Board : formats, position, taille, couleur, vignette, rangement, réduction, dossiers."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import unittest
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
import test_board_v2

from jarvis import board, cli, dessin_board, missions as mi  # noqa: E402


class DessinTest(test_board_v2.Base):
    def chef(self, *args):
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"JARVIS_ROLE": "chef"}), contextlib.redirect_stdout(sortie):
            code = cli.main(["board", *args])
        return code, sortie.getvalue()

    def carte(self, oid, espace="dessin"):
        return next(o for o in board.objets(self.org, espace)["objets"] if o["id"] == oid)

    def test_poser_dans_le_format_et_a_l_endroit_voulus(self):
        code, texte = self.chef("deposer", "--espace", "dessin", "--format", "texte", "--titre", "Feuille de route",
                                "--x", "100", "--y", "200", "--largeur", "300", "--hauteur", "120", "--couleur", "violet",
                                "--tags", "q4,produit", "--priorite", "P2", "Objectifs du trimestre")
        self.assertEqual(code, 0, texte)
        o = self.carte(texte.split()[0])
        self.assertEqual((o["type"], o["x"], o["y"], o["largeur"], o["hauteur"], o["priorite"]), ("texte", 100, 200, 300, 120, "P2"))
        self.assertEqual((o["meta"]["titre"], o["meta"]["couleur"], o["meta"]["tags"], o["auteur"]),
                         ("Feuille de route", "violet", ["q4", "produit"], "chef"))
        self.assertIsNone(o["mission_id"], "le dessin du chef ne déclenche pas d'analyse (sauf --analyser)")
        code, texte = self.chef("deposer", "--espace", "dessin", "--compact", "Rappel : démo vendredi")
        o = self.carte(texte.split()[0])
        self.assertEqual((o["meta"]["compact"], o["largeur"], o["hauteur"]), (True, 240, 96))
        self.assertEqual(self.chef("deposer", "--espace", "dessin", "--couleur", "fluo", "x")[0], 1, "couleur inconnue refusée")
        self.assertEqual(self.chef("deposer", "--espace", "dessin", "--format", "mission", "x")[0], 1,
                         "une carte de mission ne se dessine pas : elle vient du moteur de missions")

    def test_fichier_copie_et_dossier(self):
        f = self.tmp / "maquette.png"
        f.write_bytes(test_board_v2.png(40, 30))
        code, texte = self.chef("deposer", "--espace", "dessin", "--fichier", str(f))
        self.assertEqual(code, 0, texte)
        o = self.carte(texte.split()[0])
        self.assertEqual((o["type"], o["meta"]["titre"]), ("image", "maquette"))
        self.assertTrue(f.exists(), "le fichier du chef est copié, pas déplacé")
        a = self.chef("deposer", "--espace", "dessin", "A")[1].split()[0]
        b = self.chef("deposer", "--espace", "dessin", "B")[1].split()[0]
        code, texte = self.chef("grouper", "--espace", "dessin", "--titre", "Idées", "--couleur", "jaune", a, b)
        self.assertEqual(code, 0, texte)
        d = texte.split()[-1]
        self.assertEqual((self.carte(a)["parent_id"], self.carte(b)["parent_id"]), (d, d))
        self.assertEqual((self.carte(d)["type"], self.carte(d)["meta"]["couleur"]), ("dossier", "jaune"))

    def test_modifier_deplacer_redimensionner_compacter(self):
        oid = self.chef("deposer", "--espace", "dessin", "--titre", "Note", "Du texte")[1].split()[0]
        self.assertEqual(self.chef("modifier", oid, "--x", "50", "--y", "60", "--largeur", "500", "--couleur", "rose")[0], 0)
        o = self.carte(oid)
        self.assertEqual((o["x"], o["y"], o["largeur"], o["meta"]["couleur"], o["meta"]["titre"]), (50, 60, 500, "rose", "Note"))
        self.chef("modifier", oid, "--compact")
        o = self.carte(oid)
        self.assertEqual((o["meta"]["compact"], o["largeur"], o["hauteur"]), (True, 240, 96))
        self.chef("modifier", oid, "--normal", "--largeur", "408", "--hauteur", "320")
        self.assertFalse(self.carte(oid)["meta"]["compact"])
        self.assertEqual(self.chef("modifier", oid)[0], 1, "rien à modifier")
        board.mettre_a_jour(self.org, oid, {"verrouille": True}, par="humain")
        self.assertEqual(self.chef("modifier", oid, "--x", "0")[0], 1, "une carte verrouillée par l'humain ne bouge pas")

    def test_ranger_reduire(self):
        ids = [self.chef("deposer", "--espace", "dessin", "--x", str(i * 13), "--y", "7", f"carte {i}")[1].split()[0]
               for i in range(5)]
        code, texte = self.chef("ranger", "--espace", "dessin", "--disposition", "grille", "--colonnes", "2")
        self.assertEqual(code, 0, texte)
        pos = sorted((self.carte(i)["y"], self.carte(i)["x"]) for i in ids)
        self.assertEqual(len({p[0] for p in pos}), 3, "5 cartes sur 2 colonnes : 3 lignes")
        # flux : une source avant ce qu'elle alimente
        board.lier(self.org, "dessin", ids[4], ids[0], par="humain")
        board.lier(self.org, "dessin", ids[0], ids[2], par="humain")
        self.chef("ranger", "--espace", "dessin", "--disposition", "flux")
        self.assertLess(self.carte(ids[4])["x"], self.carte(ids[0])["x"])
        self.assertLess(self.carte(ids[0])["x"], self.carte(ids[2])["x"])
        avant = self.carte(ids[1])["largeur"]
        self.assertEqual(self.chef("reduire", "--espace", "dessin", "--echelle", "0.5", ids[1])[0], 0)
        self.assertEqual(self.carte(ids[1])["largeur"], round(avant * 0.5))
        self.chef("reduire", "--espace", "dessin", "--compact")
        self.assertTrue(all(self.carte(i)["meta"].get("compact") for i in ids))
        self.assertEqual(self.chef("reduire", "--espace", "dessin", "--echelle", "9")[0], 1)
        with self.assertRaises(mi.MissionError):
            dessin_board.ranger(self.org, "dessin", disposition="spirale", par="chef")

    def test_par_le_vrai_lanceur(self):
        racine = test_jarvis.ROOT
        r = subprocess.run([str(racine / "bin" / "jarvis"), "board", "deposer", "--espace", "dessin", "--couleur", "cyan",
                            "--compact", "Posé par le lanceur"], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "JARVIS_ROLE": "chef"})
        self.assertEqual(r.returncode, 0, r.stderr)
        r2 = subprocess.run([str(racine / "bin" / "jarvis"), "board", "ranger", "--espace", "dessin", "--disposition", "ligne"],
                            capture_output=True, text=True, timeout=60, env={**os.environ, "JARVIS_ROLE": "chef"})
        self.assertIn("rangée(s) en ligne", r2.stdout, r2.stderr)


if __name__ == "__main__":
    unittest.main()
