import unittest

from texte import slug, tronquer


class TexteTest(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slug("Bonjour le Monde !"), "bonjour-le-monde")

    def test_texte_court_inchange(self):
        self.assertEqual(tronquer("abc", 5), "abc")


if __name__ == "__main__":
    unittest.main()
