import unittest

import session


class TestSession(unittest.TestCase):
    def test_expiration(self):
        t = [1000.0]
        s = session.Session(horloge=lambda: t[0])
        t[0] += 29 * 60
        self.assertFalse(s.expiree())
        t[0] += 60
        self.assertTrue(s.expiree())
