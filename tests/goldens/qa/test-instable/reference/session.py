import time


class Session:
    DUREE = 30 * 60

    def __init__(self, horloge=time.time):
        self.horloge = horloge
        self.debut = horloge()

    def expiree(self):
        return self.horloge() - self.debut >= self.DUREE
