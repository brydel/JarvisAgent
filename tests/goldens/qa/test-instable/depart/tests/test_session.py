import time
import unittest

import session


class TestSession(unittest.TestCase):
    def test_expiration(self):
        session.Session.DUREE = 1
        s = session.Session()
        self.assertFalse(s.expiree())
        time.sleep(2)
        self.assertTrue(s.expiree())
