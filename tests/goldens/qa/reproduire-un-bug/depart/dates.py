from datetime import date


def lire_date(texte):
    a, b, annee = (int(x) for x in texte.split("/"))
    return date(annee, a, b)
