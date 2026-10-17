def remise(prix, pct):
    if not 0 <= pct <= 100:
        raise ValueError("pourcentage hors de 0..100")
    return round(prix * (100 - pct) / 100, 2)
