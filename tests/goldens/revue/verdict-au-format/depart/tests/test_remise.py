import unittest

from app.remise import remise


class RemiseTest(unittest.TestCase):
    def test_nominal(self):
        self.assertEqual(remise(100, 20), 80)

    def test_pourcentage_negatif(self):
        with self.assertRaises(ValueError):
            remise(100, -5)


if __name__ == "__main__":
    unittest.main()
