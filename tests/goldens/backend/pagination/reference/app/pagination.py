def paginer(elements, page, taille):
    if taille < 1 or page < 1:
        raise ValueError("page et taille doivent valoir au moins 1")
    debut = (page - 1) * taille
    return list(elements[debut:debut + taille])
