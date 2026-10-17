def paginer(elements, page, taille):
    debut = page * taille
    return elements[debut:debut + taille]
