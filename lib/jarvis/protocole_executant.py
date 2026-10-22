"""Protocole plan de contrôle ↔ exécutant (« runner »), version 1 : enveloppes de tâche et de résultat.

Une enveloppe reçue est une DONNÉE à valider, jamais une instruction : l'exécutant vérifie la version, les
champs, leurs types et leurs bornes avant de faire quoi que ce soit, et le plan de contrôle fait de même pour
un résultat. Le tenant d'une enveloppe n'accorde rien : côté plan de contrôle, le tenant vient de l'identité
authentifiée de l'exécutant (missions.reclamer), jamais de ce que l'exécutant affirme.

Compatibilité : le plan de contrôle refuse une version majeure qu'il ne connaît pas ; un champ inconnu est
ignoré (ajout compatible), un champ obligatoire absent est refusé.
"""

from __future__ import annotations

VERSION = 1
VERSIONS_ACCEPTEES = (1,)
TAILLE_MAX_CONTENU = 200_000
OUTILS_MAX = 10  # outils déclarés par l'exécutant pour une tentative (affichés sur le Board, jamais exécutés)  # caractères d'un artefact renvoyé (borne contre l'épuisement de la base)

CHAMPS_TACHE = {
    "version": int,
    "tenant_id": str,
    "mission_id": str,
    "tache_id": str,
    "tentative_id": str,
    "correlation_id": str,
    "capacites": list,
    "niveau": str,
    "fournisseur": str,
    "travail": dict,
    "delai_s": int,
    "limites": dict,
    "bail_jeton": int,
    "bail_expire": float,
    "cle_idempotence": str,
    "decision_politique": str,
}

CHAMPS_RESULTAT = {
    "version": int,
    "tache_id": str,
    "tentative_id": str,
    "bail_jeton": int,
    "cle_idempotence": str,
    "issue": str,
}

ISSUES = ("reussi", "echec", "fournisseur_indisponible")
NIVEAUX = ("L0", "L1", "L2", "L3", "L4")


class EnveloppeInvalide(ValueError):
    pass


def _verifier(env: object, champs: dict[str, type], quoi: str) -> dict:
    if not isinstance(env, dict):
        raise EnveloppeInvalide(f"{quoi} : un objet est attendu")
    version = env.get("version")
    if version not in VERSIONS_ACCEPTEES:
        raise EnveloppeInvalide(f"{quoi} : version de protocole {version!r} non prise en charge {VERSIONS_ACCEPTEES}")
    for nom, typ in champs.items():
        if nom not in env:
            raise EnveloppeInvalide(f"{quoi} : champ obligatoire « {nom} » absent")
        valeur = env[nom]
        ok = isinstance(valeur, typ) and not (typ is int and isinstance(valeur, bool))
        if typ is float:
            ok = isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
        if not ok:
            raise EnveloppeInvalide(f"{quoi} : « {nom} » doit être de type {typ.__name__}")
    return env


def valider_tache(env: object) -> dict:
    """Validation côté exécutant d'une tâche reçue."""
    env = _verifier(env, CHAMPS_TACHE, "tâche")
    if env["niveau"] not in NIVEAUX:
        raise EnveloppeInvalide(f"tâche : niveau inconnu {env['niveau']!r}")
    if env["delai_s"] <= 0 or env["delai_s"] > 24 * 3600:
        raise EnveloppeInvalide("tâche : délai hors bornes (1 s à 24 h)")
    if not all(isinstance(c, str) for c in env["capacites"]):
        raise EnveloppeInvalide("tâche : capacités mal formées")
    return env


def valider_resultat(env: object) -> dict:
    """Validation côté plan de contrôle d'un résultat renvoyé par un exécutant."""
    env = _verifier(env, CHAMPS_RESULTAT, "résultat")
    if env["issue"] not in ISSUES:
        raise EnveloppeInvalide(f"résultat : issue inconnue {env['issue']!r}")
    contenu = env.get("contenu", "")
    if not isinstance(contenu, str):
        raise EnveloppeInvalide("résultat : « contenu » doit être du texte")
    if len(contenu) > TAILLE_MAX_CONTENU:
        raise EnveloppeInvalide(f"résultat : contenu trop long ({len(contenu)} > {TAILLE_MAX_CONTENU})")
    if env["issue"] == "reussi" and not contenu.strip():
        raise EnveloppeInvalide("résultat : une réussite sans contenu n'est pas une preuve")
    outils = env.get("outils", [])
    if not isinstance(outils, list) or len(outils) > OUTILS_MAX or not all(
            isinstance(o, dict) and set(o) <= {"outil", "detail"} and all(isinstance(v, str) and len(v) <= 200
                                                                         for v in o.values()) for o in outils):
        raise EnveloppeInvalide(f"résultat : « outils » mal formés ({OUTILS_MAX} au plus, textes courts)")
    return env


def resultat(tache: dict, issue: str, *, contenu: str = "", erreur: str = "", fournisseur: str = "",
             factice: bool = False, outils: list | None = None) -> dict:
    """Construit le résultat d'une tentative, lié à son bail (jeton de clôture) et à sa clé d'idempotence."""
    return {
        "version": VERSION,
        "tache_id": tache["tache_id"],
        "tentative_id": tache["tentative_id"],
        "bail_jeton": tache["bail_jeton"],
        "cle_idempotence": tache["cle_idempotence"],
        "issue": issue,
        "contenu": contenu,
        "erreur": erreur[:2000],
        "fournisseur": fournisseur,
        "factice": factice,
        **({"outils": [{k: str(v)[:200] for k, v in o.items() if k in ("outil", "detail")} for o in outils][:OUTILS_MAX]}
           if outils else {}),
    }
