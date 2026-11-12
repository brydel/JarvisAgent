import unittest

from texte import slug, tronquer


class TexteTest(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slug("Bonjour le Monde !"), "bonjour-le-monde")

    def test_texte_court_inchange(self):
        self.assertEqual(tronquer("abc", 5), "abc")

    def test_texte_coupe_compte_les_points_de_suspension(self):
        self.assertEqual(tronquer("abcdefghij", 5), "abcd…")
        self.assertEqual(len(tronquer("abcdefghij", 5)), 5)

    def test_longueur_exacte_et_longueur_invalide(self):
        self.assertEqual(tronquer("abcde", 5), "abcde")
        self.assertEqual(tronquer("abcdef", 1), "…")
        with self.assertRaises(ValueError):
            tronquer("abc", 0)


if __name__ == "__main__":
    unittest.main()
