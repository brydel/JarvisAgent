import time


class Cache:
    def __init__(self, ttl=None, horloge=time.monotonic):
        self._d = {}
        self.ttl = ttl
        self.horloge = horloge

    def set(self, cle, valeur):
        self._d[cle] = (valeur, self.horloge())

    def get(self, cle):
        if cle not in self._d:
            return None
        valeur, quand = self._d[cle]
        if self.ttl is not None and self.horloge() - quand >= self.ttl:
            del self._d[cle]
            return None
        return valeur
