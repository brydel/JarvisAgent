"""Résumé d'un texte par un modèle, derrière un drapeau, avec repli sans IA."""
import json
import os


def _repli(texte):
    """Première phrase du texte (jusqu'au premier point inclus), ou tout le texte."""
    propre = texte.strip()
    point = propre.find(".")
    return propre if point < 0 else propre[:point + 1]


def _actif(actif):
    return os.environ.get("RESUME_IA") == "1" if actif is None else bool(actif)


def _valide(brut, texte):
    """Le résumé si la sortie du fournisseur respecte le schéma, sinon None."""
    try:
        donnees = json.loads(brut)
    except (TypeError, ValueError):
        return None
    resume = donnees.get("resume") if isinstance(donnees, dict) else None
    if not isinstance(resume, str) or not resume.strip() or len(resume) > len(texte):
        return None
    return resume


def resumer(texte, fournisseur, actif=None):
    """{"resume": …, "source": "ia" | "repli"}. Le fournisseur n'est appelé que si le drapeau est actif."""
    repli = {"resume": _repli(texte), "source": "repli"}
    if not _actif(actif):
        return repli
    brut = None
    for _essai in range(2):  # un seul nouvel essai
        try:
            brut = fournisseur(texte)
            break
        except Exception:  # noqa: BLE001 — panne du fournisseur : on réessaie une fois, puis repli
            continue
    else:
        return repli
    resume = _valide(brut, texte)
    return {"resume": resume, "source": "ia"} if resume is not None else repli
