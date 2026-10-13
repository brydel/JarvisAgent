"""Livrables : ce que l'usine produit en dehors du code (vidéos, visuels, dossiers de campagne, rapports).

Les agents déposent leurs fichiers dans ~/.local/share/jarvis/livrables/<projet>/<ISSUE>/.
`jarvis livrer` contrôle le fichier, l'enregistre et l'envoie à l'humain sur Telegram.
Rien ne sort d'ici vers un tiers : la diffusion publique reste une décision humaine.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from . import config, notify, store, studio
from .telegram import TelegramError

FILE = "livrables.json"
RACINE = config.DATA_DIR / "livrables"
PHOTO_MAX = 10 * 1024 * 1024  # au-delà, Telegram exige un envoi en document


class LivrableError(ValueError):
    pass


_ISSUE = re.compile(r"^[A-Za-z]+-\d+$")
_PROJET = re.compile(r"^[\w.-]+$")


def dossier(projet: str, issue: str, creer: bool = True) -> Path:
    if not _PROJET.match(projet) or projet in (".", "..") or not _ISSUE.match(issue):
        raise LivrableError(f"dossier de livrables invalide : {projet} {issue} (attendu : projet et ISSUE, ex. BIS-82)")
    d = RACINE / projet / issue.upper()
    if creer:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _vide() -> dict:
    return {"seq": 0, "items": []}


def tous() -> list[dict]:
    return store.read_json(FILE, _vide())["items"]


def recents(n: int = 10) -> list[dict]:
    return tous()[-n:]


def _resoudre(fichier: str) -> tuple[Path, str, str]:
    """Chemin réel du fichier, qui doit se trouver sous livrables/<projet>/<ISSUE>/. Renvoie aussi projet et issue."""
    try:
        path = Path(fichier).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LivrableError(f"fichier introuvable : {fichier}") from exc
    if not path.is_file():
        raise LivrableError(f"{fichier} n'est pas un fichier")
    racine = RACINE.resolve()
    try:
        rel = path.relative_to(racine)
    except ValueError as exc:
        raise LivrableError(f"seuls les fichiers déposés dans {racine}/<projet>/<ISSUE>/ peuvent être livrés") from exc
    if len(rel.parts) < 3:
        raise LivrableError(f"range le fichier dans {racine}/<projet>/<ISSUE>/")
    if any(part.startswith(".") for part in rel.parts) or not studio.genre(path):
        raise LivrableError(f"type de fichier non livrable : {path.name}")
    return path, rel.parts[0], rel.parts[1]


def chemin_servi(cible: str) -> Path | None:
    """Chemin réel d'un fichier du registre s'il est toujours un livrable valide, sinon None.

    Revérifié à chaque lecture : un fichier inscrit peut avoir été remplacé depuis par un lien
    vers autre chose (les réglages, une clé…). Seul ce qui vit réellement sous livrables/ est servi.
    """
    try:
        path, _projet, _issue = _resoudre(cible)
    except LivrableError:
        return None
    return path


def livrer(fichier: str, titre: str = "", legende: str = "", forcer: bool = False) -> dict:
    """Contrôle, enregistre et envoie un livrable sur Telegram. Renvoie sa fiche (avec le rapport).

    Une vidéo qui échoue au contrôle technique n'est pas envoyée (sauf `forcer`, réservé à l'humain).
    """
    path, projet, issue = _resoudre(fichier)
    if projet not in config.projects():
        raise LivrableError(f"projet inconnu « {projet} » (jarvis projet liste)")
    max_mo = float(config.settings()["studio"].get("taille_max_mo", 49))
    rapport = studio.verifier(path, taille_max_mo=max_mo)
    if rapport["verdict"] != "PRÊT" and not forcer:
        raise LivrableError("contrôle qualité non passé, rien n'a été envoyé :\n" + studio.texte(rapport))
    genre = rapport["genre"]
    titre = titre.strip() or path.stem.replace("-", " ").replace("_", " ")
    icone = {"video": "🎬", "image": "🖼", "document": "📄"}[genre]
    texte = f"{icone} {titre}\n{projet} · {issue}"
    if legende.strip():
        texte += f"\n\n{legende.strip()}"

    envoye, erreur = False, ""
    bot, chat = notify.bot_and_chat()
    if bot:
        kind, extra = "document", {}
        if genre == "video" and path.suffix.lower() in (".mp4", ".mov", ".m4v"):
            infos = rapport["infos"]
            kind = "video"
            extra = {"supports_streaming": "true", "width": infos.get("largeur"), "height": infos.get("hauteur"),
                     "duration": int(infos.get("duree") or 0)}
        elif genre == "image" and path.suffix.lower() != ".gif" and path.stat().st_size <= PHOTO_MAX:
            kind = "photo"
        try:
            bot.send_file(chat, path, kind=kind, caption=texte, extra=extra)
            envoye = True
        except TelegramError as exc:
            erreur = str(exc)
            if kind == "photo":
                # Telegram refuse certaines images en « photo » (très hautes, très larges) : en document, elles passent.
                try:
                    bot.send_file(chat, path, kind="document", caption=texte)
                    envoye, erreur = True, ""
                except TelegramError as exc2:
                    erreur = str(exc2)
            if not envoye:
                store.feed_add("erreur", f"Telegram : {erreur}")
    else:
        erreur = "Telegram non configuré (jarvis telegram config)"

    def _add(data):
        champs = {"projet": projet, "issue": issue, "fichier": str(path), "titre": titre, "genre": genre,
                  "octets": path.stat().st_size, "ts": time.time(), "envoye": envoye, "erreur": erreur,
                  "verdict": rapport["verdict"], "infos": rapport["infos"], "planche": rapport.get("planche", "")}
        # Un nouvel essai d'envoi du même fichier met à jour sa fiche au lieu d'en empiler une autre.
        ancien = next((i for i in reversed(data["items"]) if i["fichier"] == str(path) and not i["envoye"]), None)
        if ancien:
            ancien.update(champs)
            return dict(ancien)
        data["seq"] += 1
        item = {"id": f"L-{data['seq']:04d}", **champs}
        data["items"].append(item)
        data["items"] = data["items"][-300:]
        return dict(item)

    item = store.update_json(FILE, _vide(), _add)
    store.feed_add("livrable", f"{item['id']} {titre} ({projet} {issue})"
                   + (" envoyé sur Telegram" if envoye else " prêt, non envoyé"), livrable=item["id"])
    item["rapport"] = rapport
    return item


def fmt_taille(octets: int) -> str:
    return f"{octets / 1e6:.1f} Mo" if octets >= 1e5 else f"{max(1, octets // 1000)} ko"


def texte(items: list[dict] | None = None) -> str:
    items = recents(15) if items is None else items
    if not items:
        return "Aucun livrable pour l'instant."
    icone = {"video": "🎬", "image": "🖼", "document": "📄"}
    lines = []
    for i in reversed(items):
        quand = time.strftime("%d/%m %H:%M", time.localtime(i["ts"]))
        etat = "envoyé" if i["envoye"] else "non envoyé"
        lines.append(f"{icone.get(i['genre'], '•')} {i['id']} {i['titre']} — {i['projet']} {i['issue']} · "
                     f"{fmt_taille(i['octets'])} · {quand} · {etat}")
        lines.append(f"     {i['fichier']}")
    return "\n".join(lines)
