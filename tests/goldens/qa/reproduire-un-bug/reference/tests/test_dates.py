import unittest
from datetime import date

from dates import lire_date


class TestLireDate(unittest.TestCase):
    def test_jour_avant_mois(self):
        self.assertEqual(lire_date("03/04/2026"), date(2026, 4, 3))
