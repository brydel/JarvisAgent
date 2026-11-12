"""Petits outils de texte."""


def tronquer(texte, longueur):
    """Coupe `texte` à `longueur` caractères au plus. Un texte coupé se termine par « … », compté dans la longueur."""
    if longueur < 1:
        raise ValueError("longueur inférieure à 1")
    if len(texte) > longueur:
        return texte[:longueur - 1] + "…"
    return texte


def slug(titre):
    r = ""
    for c in titre.lower():
        if c.isalnum(): r += c
        elif r and r[-1] != "-": r += "-"
    return r.strip("-")
