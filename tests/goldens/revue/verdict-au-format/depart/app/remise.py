"""Calcul d'une remise."""


def remise(prix, pct):
    """Prix après une remise de `pct` %."""
    if pct < 0:
        raise ValueError("pourcentage négatif")
    return prix - prix * pct / 100
