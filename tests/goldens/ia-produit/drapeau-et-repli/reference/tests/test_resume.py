import json
import os
import unittest
from unittest import mock

from resume import resumer

TEXTE = "  Le cours a gagné 4 % cette semaine. Le volume reste faible.  "
REPLI = {"resume": "Le cours a gagné 4 % cette semaine.", "source": "repli"}


class Simule:
    """Fournisseur simulé : rejoue une liste de réponses (une exception est levée)."""

    def __init__(self, *reponses):
        self.reponses, self.appels = list(reponses), 0

    def __call__(self, texte):
        self.appels += 1
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


class ResumeTest(unittest.TestCase):
    def test_drapeau_coupe_par_defaut(self):
        f = Simule(json.dumps({"resume": "Hausse de 4 %."}))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resumer(TEXTE, f), REPLI)
        self.assertEqual(f.appels, 0)

    def test_drapeau_par_l_environnement(self):
        f = Simule(json.dumps({"resume": "Hausse de 4 %."}))
        with mock.patch.dict(os.environ, {"RESUME_IA": "1"}):
            self.assertEqual(resumer(TEXTE, f), {"resume": "Hausse de 4 %.", "source": "ia"})

    def test_panne_un_nouvel_essai_puis_repli(self):
        f = Simule(TimeoutError(), TimeoutError())
        self.assertEqual(resumer(TEXTE, f, actif=True), REPLI)
        self.assertEqual(f.appels, 2)
        f = Simule(TimeoutError(), json.dumps({"resume": "Hausse de 4 %."}))
        self.assertEqual(resumer(TEXTE, f, actif=True)["source"], "ia")

    def test_sortie_hors_schema(self):
        for mauvaise in ("pas du json", "[]", json.dumps({"resume": ""}), json.dumps({"resume": 3}),
                         json.dumps({"autre": "x"}), json.dumps({"resume": "x" * 500})):
            self.assertEqual(resumer(TEXTE, Simule(mauvaise), actif=True), REPLI, mauvaise)

    def test_texte_sans_point(self):
        self.assertEqual(resumer(" Stable ", Simule(), actif=False), {"resume": "Stable", "source": "repli"})


if __name__ == "__main__":
    unittest.main()
