"""Envoi des courriels de notification."""
import smtplib
from email.message import EmailMessage


def envoyer_courriel(destinataire, sujet, corps, hote="localhost"):
    """Envoie un courriel et attend la réponse du serveur (jusqu'à 3 secondes)."""
    message = EmailMessage()
    message["To"], message["Subject"] = destinataire, sujet
    message.set_content(corps)
    with smtplib.SMTP(hote, timeout=3) as serveur:
        serveur.send_message(message)
