def creer_utilisateur(email, age):
    if not isinstance(email, str) or "@" not in email.strip():
        raise ValueError("adresse électronique invalide")
    if isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 150:
        raise ValueError("âge invalide : entier entre 0 et 150 attendu")
    return {"email": email.strip().lower(), "age": age}
