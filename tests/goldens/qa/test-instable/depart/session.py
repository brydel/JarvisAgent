import time


class Session:
    DUREE = 30 * 60

    def __init__(self):
        self.debut = time.time()

    def expiree(self):
        return time.time() - self.debut >= self.DUREE
