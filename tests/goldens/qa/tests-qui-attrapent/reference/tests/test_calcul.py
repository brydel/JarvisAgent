import unittest

from calcul import remise


class TestRemise(unittest.TestCase):
    def test_nominal(self):
        self.assertEqual(remise(200, 25), 150)

    def test_bornes(self):
        self.assertEqual(remise(80, 0), 80)
        self.assertEqual(remise(80, 100), 0)

    def test_arrondi(self):
        self.assertEqual(remise(10, 33), 6.7)

    def test_refus(self):
        for pct in (-1, 101):
            with self.assertRaises(ValueError):
                remise(10, pct)
