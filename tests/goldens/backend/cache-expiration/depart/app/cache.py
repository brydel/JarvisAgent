class Cache:
    def __init__(self):
        self._d = {}

    def set(self, cle, valeur):
        self._d[cle] = valeur

    def get(self, cle):
        return self._d.get(cle)
