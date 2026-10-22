"""Comptes et adhésions : qui peut se connecter, et à quelles organisations (avec quel rôle).

Mots de passe hachés par scrypt (bibliothèque standard), sel aléatoire, comparaison à temps constant. Création et
adhésions : rôle propriétaire (administration). Vérification d'une connexion : rôle jarvis_app, par la fonction
jarvis_compte_connexion — l'application ne lit jamais la table des comptes directement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time

import psycopg
from psycopg.rows import dict_row

ROLES = ("proprietaire", "membre", "lecteur")
N, R, P = 2 ** 14, 8, 1
COURRIEL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CompteError(Exception):
    pass


def hacher(mot_de_passe: str, *, sel: bytes | None = None) -> str:
    if len(mot_de_passe) < 12:
        raise CompteError("mot de passe trop court (12 caractères au moins)")
    sel = sel or secrets.token_bytes(16)
    h = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${base64.b64encode(sel).decode()}${base64.b64encode(h).decode()}"


def verifier_empreinte(mot_de_passe: str, empreinte: str) -> bool:
    try:
        _, n, r, p, sel, h = empreinte.split("$")
        calcule = hashlib.scrypt(mot_de_passe.encode(), salt=base64.b64decode(sel), n=int(n), r=int(r), p=int(p),
                                 dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calcule, base64.b64decode(h))


def creer(dsn_admin: str, courriel: str, nom: str, mot_de_passe: str) -> str:
    courriel = courriel.strip().lower()
    if not COURRIEL.match(courriel):
        raise CompteError(f"courriel invalide : {courriel}")
    cid = f"CO-{secrets.token_hex(6)}"
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        try:
            conn.execute("INSERT INTO comptes (id, courriel, nom, mdp_empreinte, cree) VALUES (%s,%s,%s,%s,%s)",
                         (cid, courriel, nom, hacher(mot_de_passe), time.time()))
        except psycopg.errors.UniqueViolation:
            raise CompteError(f"un compte existe déjà pour {courriel}") from None
    return cid


def adherer(dsn_admin: str, compte_id: str, tenant_id: str, role: str) -> None:
    if role not in ROLES:
        raise CompteError(f"rôle inconnu : {role} ({', '.join(ROLES)})")
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute("INSERT INTO adhesions VALUES (%s,%s,%s,%s) ON CONFLICT (compte_id, tenant_id) "
                     "DO UPDATE SET role = excluded.role", (compte_id, tenant_id, role, time.time()))


def connexion(dsn_app: str, courriel: str, mot_de_passe: str) -> dict:
    """Vérifie un couple courriel / mot de passe. Renvoie le compte et ses organisations, ou lève CompteError
    (même message que le compte existe ou non)."""
    with psycopg.connect(dsn_app, autocommit=True, row_factory=dict_row) as conn:
        c = conn.execute("SELECT * FROM jarvis_compte_connexion(%s)", (courriel.strip(),)).fetchone()
        empreinte = c["mdp_empreinte"] if c else hacher("leurre-pour-un-temps-constant!")
        ok = verifier_empreinte(mot_de_passe, empreinte)
        if not c or not ok or c["desactive"]:
            raise CompteError("courriel ou mot de passe incorrect")
        adhesions = conn.execute("SELECT * FROM jarvis_adhesions(%s)", (c["id"],)).fetchall()
    return {"id": c["id"], "nom": c["nom"], "organisations": adhesions}
