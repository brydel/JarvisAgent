"""Création d'une commande."""
from .notifications import envoyer_courriel


def creer_commande(base, client, lignes):
    """Enregistre la commande puis prévient le client. Appelée pendant la requête HTTP."""
    numero = base.enregistrer(client, lignes)
    envoyer_courriel(client["email"], f"Commande {numero}", "Merci pour ta commande.")
    return numero
