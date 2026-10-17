"""Registre privé des skills (compétences des agents), avec confiance.

Une skill est un dossier avec un `SKILL.md`, lu par Claude Code (~/.claude/skills) et Codex (~/.agents/skills).
Une skill exécute du code sur ton poste : on ne l'active jamais sans savoir exactement ce qu'elle contient.

- `skill.lock` (TOML) épingle une skill : nom, version, empreinte SHA-256 de TOUT le dossier (sauf le lock),
  auteur, et une signature facultative (`ssh-keygen -Y sign`, outil d'OpenSSH déjà présent sur Ubuntu).
- `installer(source)` : copie la skill (dossier local ou dépôt git) en **quarantaine**, hors des dossiers lus par
  les agents. Un lock fourni dont l'empreinte ne correspond pas au contenu → **refus**. Toute installation exige
  ensuite ton approbation (bouton Telegram ou `jarvis skill approuver` au terminal) : action de niveau 3.
- `decider(ok)` : contrôle que la quarantaine n'a pas changé depuis la demande, puis active (dossier
  ~/.local/share/jarvis/skills/<nom>, liens pour Claude et Codex, lock écrit) ou supprime la copie.
- `auditer()` : état de chaque skill (épinglée, modifiée, non épinglée, signature invalide, hors registre).

Signature : un fichier `~/.config/jarvis/skills_signataires` au format « allowed_signers » d'OpenSSH liste les
auteurs de confiance. Sans lui (ou sans ssh-keygen), une skill est épinglée par empreinte, marquée « non signée ».
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

from . import config, store

LOCK = "skill.lock"
FILE = "skills.json"
NAMESPACE = "jarvis-skill"
NOM_OK = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")   # 40 car. max : le bouton Telegram tient en 64 octets
INTERDITS = {"__pycache__", ".git"}                   # code compilé ou dépôt imbriqué : jamais relus par un humain
EXTENSIONS_INTERDITES = (".pyc", ".pyo")
TAILLE_MAX = 50_000_000
VALIDITE = 7 * 86400


class SkillError(ValueError):
    pass


def depot_dir() -> Path:
    return config.JARVIS_HOME / "skills"


def installees_dir() -> Path:
    return config.DATA_DIR / "skills"


def quarantaine_dir() -> Path:
    return config.DATA_DIR / "skills-quarantaine"


def signataires() -> Path:
    return config.CONFIG_DIR / "skills_signataires"


def liens_dirs() -> list[Path]:
    """Dossiers lus par les agents (calculés à l'appel : HOME peut changer, en test notamment)."""
    home = Path(os.environ.get("HOME") or Path.home())
    return [home / ".claude" / "skills", home / ".agents" / "skills"]


# --- Empreinte et lock ---------------------------------------------------------------------------

def _fichiers(dossier: Path) -> list[Path]:
    """Tous les fichiers de la skill (seul le lock est exclu de l'empreinte). Du code compilé (.pyc,
    __pycache__) ou un dépôt git imbriqué rendent la skill illisible : rien n'échappe à l'empreinte."""
    out = []
    for p in sorted(dossier.rglob("*")):
        rel = p.relative_to(dossier)
        if rel.as_posix() == LOCK:
            continue
        if any(part in INTERDITS for part in rel.parts) or p.suffix in EXTENSIONS_INTERDITES:
            raise SkillError(f"fichier refusé dans la skill : {rel} (code compilé ou dépôt imbriqué ; supprime-le, "
                             "il serait exécuté sans avoir été relu)")
        if p.is_symlink():
            raise SkillError(f"lien symbolique refusé dans la skill : {rel} (il pourrait pointer n'importe où)")
        if p.is_file():
            out.append(p)
    return out


def empreinte(dossier: Path) -> str:
    """SHA-256 des chemins relatifs et du contenu de chaque fichier (lock exclu). Les droits d'exécution ne
    comptent pas : ils varient selon le système de fichiers (WSL, /mnt/c) sans que le contenu change."""
    h = hashlib.sha256()
    total = 0
    for p in _fichiers(dossier):
        data = p.read_bytes()
        total += len(data)
        if total > TAILLE_MAX:
            raise SkillError("skill trop volumineuse (> 50 Mo)")
        h.update(f"{p.relative_to(dossier).as_posix()}\0{len(data)}\0".encode("utf-8"))
        h.update(data)
    return "sha256:" + h.hexdigest()


def lire_lock(dossier: Path) -> dict | None:
    try:
        with open(dossier / LOCK, "rb") as fh:
            d = tomllib.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SkillError(f"{dossier.name}/{LOCK} illisible : {exc}") from exc
    return d


def _message(lock: dict) -> bytes:
    """Ce qui est signé : l'identité de la skill et son empreinte (pas la signature elle-même)."""
    return f"{lock['nom']}\n{lock.get('version', '')}\n{lock['empreinte']}\n{lock.get('auteur', '')}\n".encode("utf-8")


def _toml(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def ecrire_lock(dossier: Path, *, nom: str, version: str, auteur: str, signature: str = "") -> dict:
    lock = {"nom": nom, "version": version or "0", "empreinte": empreinte(dossier), "auteur": auteur or "inconnu",
            "epingle": time.strftime("%Y-%m-%d")}
    lignes = ["# Épinglage Jarvis : toute modification du dossier change l'empreinte. Ne pas éditer à la main.",
              *(f"{k} = {_toml(v)}" for k, v in lock.items())]
    if signature:
        lignes.append(f'signature = """\n{signature.strip()}\n"""')
        lock["signature"] = signature.strip()
    (dossier / LOCK).write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return lock


def _ssh_keygen() -> str | None:
    return shutil.which("ssh-keygen")


def signer(lock: dict, cle: str) -> str:
    """Signe le lock avec une clé SSH (ssh-keygen -Y sign). Renvoie la signature armurée."""
    outil = _ssh_keygen()
    if not outil:
        raise SkillError("ssh-keygen absent : installe openssh-client pour signer")
    with tempfile.TemporaryDirectory() as d:
        msg = Path(d) / "message"
        msg.write_bytes(_message(lock))
        r = subprocess.run([outil, "-Y", "sign", "-f", cle, "-n", NAMESPACE, str(msg)], capture_output=True, text=True,
                           timeout=60)
        sig = Path(str(msg) + ".sig")
        if r.returncode != 0 or not sig.exists():
            raise SkillError(f"signature impossible : {(r.stderr or r.stdout).strip()[:200]}")
        return sig.read_text(encoding="utf-8")


def verifier_signature(lock: dict) -> tuple[str, str]:
    """("valide"|"invalide"|"absente"|"inverifiable", détail)."""
    sig = (lock.get("signature") or "").strip()
    if not sig:
        return "absente", "non signée"
    outil, autorises = _ssh_keygen(), signataires()
    if not outil or not autorises.is_file():
        return "inverifiable", "ssh-keygen ou ~/.config/jarvis/skills_signataires absent"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "sig"
        f.write_text(sig + "\n", encoding="utf-8")
        r = subprocess.run([outil, "-Y", "verify", "-f", str(autorises), "-I", str(lock.get("auteur", "")),
                            "-n", NAMESPACE, "-s", str(f)], input=_message(lock), capture_output=True, timeout=60)
    if r.returncode == 0:
        return "valide", f"signée par {lock.get('auteur')}"
    return "invalide", "signature invalide ou auteur non autorisé"


def etat(dossier: Path) -> dict:
    """État de confiance d'une skill : epinglee | modifiee | non_epinglee | signature_invalide | illisible."""
    out = {"nom": dossier.name, "chemin": str(dossier), "version": "", "auteur": "", "signature": "absente"}
    try:
        lock = lire_lock(dossier)
        reel = empreinte(dossier)
    except SkillError as exc:
        return {**out, "etat": "illisible", "detail": str(exc)}
    out["empreinte"] = reel
    if not lock:
        return {**out, "etat": "non_epinglee", "detail": "aucun skill.lock"}
    out.update(version=str(lock.get("version", "")), auteur=str(lock.get("auteur", "")))
    if lock.get("nom") != dossier.name:
        return {**out, "etat": "modifiee", "detail": f"le lock est celui de « {lock.get('nom')} »"}
    if lock.get("empreinte") != reel:
        return {**out, "etat": "modifiee", "detail": "le contenu ne correspond plus à l'empreinte épinglée"}
    sig, detail = verifier_signature(lock)
    out["signature"] = sig
    if sig == "invalide":
        return {**out, "etat": "signature_invalide", "detail": detail}
    return {**out, "etat": "epinglee", "detail": detail}


# --- Installation, quarantaine, décision -----------------------------------------------------------

def _nom_skill(dossier: Path, defaut: str) -> str:
    try:
        texte = (dossier / "SKILL.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError("pas de SKILL.md à la racine : ce n'est pas une skill") from exc
    m = re.search(r"^name:\s*([^\n]+)$", texte.split("\n---", 1)[0], re.M) if texte.startswith("---") else None
    nom = (m.group(1).strip().strip("'\"") if m else defaut).lower()
    if not NOM_OK.match(nom):
        raise SkillError(f"nom de skill invalide « {nom} » (minuscules, chiffres, . _ -)")
    return nom


def sans_identifiants(texte: str) -> str:
    """Retire « utilisateur:jeton@ » des URL avant tout affichage, journal ou message."""
    return re.sub(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1", str(texte), flags=re.I)


def _recuperer(source: str, dest: Path) -> None:
    src = Path(source).expanduser()
    if src.is_dir():
        shutil.copytree(src, dest, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        return
    if re.match(r"^(https://|git@|ssh://)", source):
        r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", "--", source, str(dest)], capture_output=True,
                           text=True, timeout=300, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode != 0:
            raise SkillError(f"git clone impossible : {sans_identifiants((r.stderr or r.stdout).strip())[:300]}")
        shutil.rmtree(dest / ".git", ignore_errors=True)
        return
    raise SkillError(f"source introuvable : {source} (dossier local ou URL git https://…)")


def installer(source: str, par: str = "humain") -> dict:
    """Met la skill en quarantaine et demande ton approbation. Rien n'est lu par les agents avant."""
    affichee = sans_identifiants(source)
    q = quarantaine_dir()
    q.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="arrivee-", dir=q))
    try:
        _recuperer(source, tmp / "skill")
        d = tmp / "skill"
        nom = _nom_skill(d, Path(affichee.rstrip("/")).name.removesuffix(".git"))
        attente = store.read_json(FILE, {}).get(nom) or {}
        if attente.get("statut") == "quarantaine" and time.time() - attente.get("ts", 0) <= VALIDITE:
            # Sinon une réinstallation remplacerait la copie que ton bouton désigne.
            raise SkillError(f"« {nom} » attend déjà ta décision : refuse-la d'abord (jarvis skill refuser {nom})")
        reel = empreinte(d)
        lock = lire_lock(d)
        if lock and lock.get("empreinte") != reel:
            raise SkillError(f"« {nom} » refusée : son skill.lock annonce {lock.get('empreinte', '?')[:19]}… mais le "
                             f"contenu donne {reel[:19]}… (modifiée après épinglage)")
        sig, sig_detail = verifier_signature(lock) if lock else ("absente", "non signée")
        if sig == "invalide":
            raise SkillError(f"« {nom} » refusée : {sig_detail}")
        actuelle = installees_dir() / nom
        if (depot_dir() / nom).exists():
            raise SkillError(f"« {nom} » est une skill du dépôt Jarvis : elle se met à jour avec le dépôt")
        cible = q / nom
        shutil.rmtree(cible, ignore_errors=True)
        d.rename(cible)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    demande = {"ts": time.time(), "statut": "quarantaine", "source": affichee, "empreinte": reel, "par": par,
               "version": str((lock or {}).get("version", "")), "auteur": str((lock or {}).get("auteur", "")),
               "signature": sig, "mise_a_jour": actuelle.exists(),
               "fichiers": len(_fichiers(cible))}
    store.update_json(FILE, {}, lambda data: data.update({nom: demande}))
    _journal(par, nom, "quarantaine", f"{affichee} {reel[:19]} ({sig})")
    from . import notify
    texte = (f"🧩 Skill « {nom} » en quarantaine ({'mise à jour' if demande['mise_a_jour'] else 'nouvelle'}) — "
             f"source {affichee}\n{demande['fichiers']} fichier(s), empreinte {reel[:23]}…, {sig_detail}.\n"
             f"Une skill exécute du code sur ton poste. Relis-la avant : {cible}")
    demande["envoye"] = bool(notify.telegram(texte, notify.skill_buttons(nom, jeton(reel))))
    return {"nom": nom, **demande, "quarantaine": str(cible)}


def jeton(empreinte_: str) -> str:
    """Début de l'empreinte, porté par le bouton Telegram : le clic vaut pour CE contenu-là seulement."""
    return empreinte_.removeprefix("sha256:")[:12]


def decider(nom: str, ok: bool, par: str, jeton_attendu: str = "") -> dict:
    """Ta décision sur une skill en quarantaine. `ok` : activation ; sinon la copie est supprimée.
    `jeton_attendu` (bouton Telegram) : la demande doit être celle que le message montrait."""
    nom = nom.lower()
    d = store.read_json(FILE, {}).get(nom)
    if not d or d.get("statut") != "quarantaine":
        raise SkillError(f"aucune skill « {nom} » en attente de décision")
    if jeton_attendu and jeton_attendu != jeton(d["empreinte"]):
        raise SkillError("ce bouton concerne une autre version de la skill : rien n'est fait")
    cible = quarantaine_dir() / nom
    if not ok:
        shutil.rmtree(cible, ignore_errors=True)
        _maj(nom, statut="refusee", decide=time.time(), decide_par=par)
        _journal(par, nom, "refusee")
        return {"nom": nom, "active": False}
    if time.time() - d["ts"] > VALIDITE:
        raise SkillError("demande expirée (7 jours) : réinstalle la skill")
    if not cible.is_dir() or empreinte(cible) != d["empreinte"]:
        raise SkillError("la copie en quarantaine a changé depuis la demande : rien n'est activé, réinstalle-la")
    for lien in liens_dirs():
        if lien.exists() and depot_dir().resolve() in (lien.resolve(), *lien.resolve().parents):
            raise SkillError(f"{lien} pointe dans le dépôt Jarvis : une skill installée n'y est jamais écrite")
        dst = lien / nom
        if (dst.exists() or dst.is_symlink()) and not (dst.is_symlink() and Path(os.readlink(dst)) == installees_dir() / nom):
            raise SkillError(f"{dst} existe déjà et n'est pas géré par Jarvis : déplace-le d'abord (rien n'est écrasé)")
    finale = installees_dir() / nom
    finale.parent.mkdir(parents=True, exist_ok=True)
    if finale.exists():
        sauvegarde = finale.with_name(f"{nom}.bak.{time.strftime('%Y%m%d-%H%M%S')}")
        finale.rename(sauvegarde)
    cible.rename(finale)
    lock = lire_lock(finale)
    if not lock:
        ecrire_lock(finale, nom=nom, version=d.get("version") or "0", auteur=d.get("auteur") or f"approuvée par {par}")
    for lien in liens_dirs():
        lien.mkdir(parents=True, exist_ok=True)
        dst = lien / nom
        if not dst.is_symlink():
            dst.symlink_to(finale)
    _maj(nom, statut="active", decide=time.time(), decide_par=par)
    _journal(par, nom, "approuvee", d["empreinte"][:19])
    store.feed_add("systeme", f"skill « {nom} » activée ({par})")
    return {"nom": nom, "active": True, "chemin": str(finale)}


def _maj(nom: str, **champs) -> None:
    store.update_json(FILE, {}, lambda data: data.setdefault(nom, {}).update(champs))


def _journal(acteur: str, nom: str, decision: str, raison: str = "") -> None:
    try:
        from . import journal
        journal.ecrire("politique", acteur=acteur, objet=f"skill:{nom}", decision=decision, raison=raison,
                       action="protection")
    except Exception:  # noqa: BLE001
        pass


def epingler(nom: str, *, version: str = "", auteur: str = "", cle: str = "") -> dict:
    """Ré-épingle une skill (du dépôt ou installée) après une modification volontaire, éventuellement signée."""
    dossier = next((d / nom for d in (depot_dir(), installees_dir()) if (d / nom).is_dir()), None)
    if not dossier:
        raise SkillError(f"skill « {nom} » introuvable")
    ancien = lire_lock(dossier) or {}
    lock = {"nom": nom, "version": version or str(ancien.get("version") or "1"),
            "empreinte": empreinte(dossier), "auteur": auteur or str(ancien.get("auteur") or "inconnu")}
    signature = signer(lock, cle) if cle else ""
    return ecrire_lock(dossier, nom=nom, version=lock["version"], auteur=lock["auteur"], signature=signature)


def auditer() -> list[dict]:
    """Toutes les skills : dépôt, installées, et ce que lisent les agents sans passer par le registre."""
    out = []
    connus = set()
    for origine, base in (("depot", depot_dir()), ("installee", installees_dir())):
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir() and ".bak." not in p.name):
            out.append({**etat(d), "origine": origine})
            connus.add(d.resolve())
    vus = set()
    for lien in liens_dirs():
        if not lien.is_dir():
            continue
        for p in sorted(lien.iterdir()):
            try:
                reel = p.resolve()
            except OSError:
                continue
            if reel in connus or p.name in vus:
                continue
            vus.add(p.name)
            out.append({"nom": p.name, "chemin": str(p), "origine": "hors_registre", "etat": "hors_registre",
                        "detail": "lue par les agents sans être passée par le registre", "signature": "absente"})
    for nom, d in sorted(store.read_json(FILE, {}).items()):
        if d.get("statut") == "quarantaine":
            out.append({"nom": nom, "chemin": str(quarantaine_dir() / nom), "origine": "quarantaine",
                        "etat": "quarantaine", "detail": f"en attente de ton approbation depuis "
                        f"{time.strftime('%d/%m %H:%M', time.localtime(d['ts']))}", "signature": d.get("signature", "")})
    return out


def problemes(audit: list[dict] | None = None) -> list[dict]:
    return [s for s in (audit if audit is not None else auditer())
            if s["etat"] in ("modifiee", "non_epinglee", "signature_invalide", "illisible", "hors_registre")]


def texte(audit: list[dict]) -> str:
    icones = {"epinglee": "✔", "modifiee": "✘", "non_epinglee": "?", "signature_invalide": "✘", "illisible": "✘",
              "hors_registre": "!", "quarantaine": "⏸"}
    lignes = []
    for s in audit:
        sig = " · signée" if s.get("signature") == "valide" else ""
        lignes.append(f"{icones.get(s['etat'], '•')} {s['nom']:<22} {s['origine']:<13} {s['etat']:<18}"
                      f"{(' v' + s['version']) if s.get('version') else ''}{sig} — {s.get('detail', '')}")
    return "\n".join(lignes) or "Aucune skill."
