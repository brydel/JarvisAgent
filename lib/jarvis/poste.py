"""Le poste de travail : reprise après un redémarrage, santé du PC et réparation git."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import agents as ag
from . import config, store

# --- Reprise après un redémarrage --------------------------------------------------

SNAPSHOT = "agents_actifs.json"      # tenu à jour par le démon
REPRISE = "reprise.json"             # agents interrompus détectés au démarrage de la session
NOTE_CHEF = "redemarrage.json"       # résumé transmis au chef dans son message de démarrage
REPRISE_MAX_AGE = 24 * 3600          # au-delà, l'instantané est trop vieux pour être repris
REPRISE_MSG = ("[JARVIS] Le PC a redémarré pendant ton travail. Vérifie l'état de ton worktree (git status, "
               "git log) puis reprends ta tâche là où tu t'es arrêté, en suivant ton protocole.")


def boot_id() -> str:
    """Identifiant du démarrage courant de Linux : il change à chaque redémarrage du PC (ou de WSL)."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def save_snapshot(agents: list[dict]) -> None:
    """Mémorise les agents qui travaillent : ce sont eux qu'on relancera après un redémarrage."""
    actifs = [{k: a.get(k, "") for k in ("project", "worktree", "kind", "status", "workdir")}
              for a in agents if a["status"] in ("working", "waiting", "untracked", "silent")]
    store.write_json(SNAPSHOT, {"ts": time.time(), "boot": boot_id(), "chef": ag.chef_running(), "agents": actifs})


def preparer_reprise(now: float | None = None) -> dict | None:
    """Appelé quand la session tmux n'existait plus : transforme le dernier instantané en reprise.

    Seulement après un vrai redémarrage (identifiant de démarrage différent) : si tu as arrêté tmux
    toi-même, rien n'est relancé. Doit passer AVANT le démon, qui réécrirait l'instantané.
    """
    now = now or time.time()
    snap = store.read_json(SNAPSHOT, {})
    store.supprimer(SNAPSHOT)
    if not snap or now - snap.get("ts", 0) > REPRISE_MAX_AGE:
        return None
    if snap.get("boot") and snap["boot"] == boot_id():
        return None  # même démarrage : arrêt volontaire de tmux, pas un redémarrage
    if not snap.get("agents") and not snap.get("chef"):
        return None
    snap["detecte"] = now
    store.write_json(REPRISE, snap)
    return snap


def reprise_en_attente(now: float | None = None) -> dict | None:
    data = store.read_json(REPRISE, {})
    if data and (now or time.time()) - data.get("detecte", 0) > REPRISE_MAX_AGE:
        store.supprimer(REPRISE)  # trop vieux : on ne relance plus rien
        return None
    return data or None


def _open_windows() -> set[str]:
    try:
        res = subprocess.run(["tmux", "list-windows", "-a", "-F", "#{window_name}"],
                             capture_output=True, text=True, timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return set()
    return set(res.stdout.split())


def reprendre(dry_run: bool = False) -> list[str]:
    """Rouvre seulement les agents qui travaillaient, en reprenant leur conversation. Renvoie un compte rendu."""
    data = reprise_en_attente()
    if not data:
        return []
    projs = config.projects()
    ouvertes = _open_windows()
    lignes, repris, echecs, refuses = [], [], [], []
    from . import admission, taches
    fiches = taches.toutes()
    for a in data.get("agents", []):
        label = f"{a['project']}/{a['worktree']}"
        proj = projs.get(a["project"])
        if not proj:
            lignes.append(f"ignoré : {label} (projet inconnu)")
            continue
        if a.get("workdir") and not Path(a["workdir"]).is_dir():
            lignes.append(f"ignoré : {label} (worktree supprimé)")
            continue
        if ag.WINDOW_PREFIX + a["worktree"] in ouvertes:
            lignes.append(f"déjà ouvert : {label}")
            continue
        if dry_run:
            lignes.append(f"à reprendre : {label} ({ag.kind_label(a['kind'])})")
            continue
        # Une reprise est un départ comme un autre : même admission (pauses, capacité, jetons). Une
        # vieille vague n'est pas relancée en bloc si le poste ne le permet plus ; le reste attend.
        fiche = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
        agent = (a.get("kind") or (fiche or {}).get("agent") or "").lower() or "claude"
        try:
            adm = admission.demander(origine="reprise", projet=a["project"], issue=(fiche or {}).get("issue") or a["worktree"],
                                     agent=agent, worktree=a["worktree"], role=(fiche or {}).get("role", ""), acteur="reprise",
                                     taille=(fiche or {}).get("taille") or "M",
                                     jetons_max=int((fiche or {}).get("jetons_max") or 0))
        except admission.Refus as exc:
            refuses.append(a)
            lignes.append(f"en attente : {label} — {exc.raison}")
            continue
        try:
            res = subprocess.run(["workmux", "open", a["worktree"], "--continue", "-p", REPRISE_MSG],
                                 cwd=proj["chemin"], capture_output=True, text=True, timeout=60)
            ok = res.returncode == 0
            err = (res.stderr or res.stdout).strip().splitlines()[-1:] if not ok else []
        except (subprocess.TimeoutExpired, OSError) as exc:
            ok, err = False, [str(exc)]
        if ok:
            repris.append(label)
            lignes.append(f"repris : {label} ({ag.kind_label(a['kind'])})")
            store.feed_add("task", f"{label} repris après le redémarrage")
            taches.reouvrir(a["project"], a["worktree"])
            if fiche:
                admission.confirmer(adm["reservation"], fiche["id"], a["worktree"])
        else:
            admission.liberer(adm["reservation"], "workmux open a échoué", acteur="reprise")
            echecs.append(a)
            lignes.append(f"ÉCHEC : {label} — {' '.join(err) or 'workmux open a échoué'}")
            store.feed_add("erreur", f"reprise impossible de {label}")
    if not dry_run:
        restants = echecs + refuses
        if restants:  # on garde ceux qui n'ont pas repris : « jarvis reprendre » pourra réessayer
            store.write_json(REPRISE, {**data, "agents": restants})
        else:
            store.supprimer(REPRISE)
        heure = time.strftime("%H:%M", time.localtime(data.get("ts", time.time())))
        store.write_json(NOTE_CHEF, {"ts": time.time(), "texte": (
            f"Le PC a redémarré (dernier état connu à {heure}). "
            + (f"Agents repris automatiquement avec leur conversation : {', '.join(repris)}. " if repris else
               "Aucun agent n'a été repris. ")
            + (f"Reprise impossible pour : {', '.join(x['project'] + '/' + x['worktree'] for x in echecs)}. "
               if echecs else "")
            + (f"En attente (admission refusée : pause, capacité ou jetons) : "
               f"{', '.join(x['project'] + '/' + x['worktree'] for x in refuses)} — « jarvis reprendre » réessaie. "
               if refuses else "")
            + "Vérifie en priorité leur état, le travail non commité dans les worktrees et les plans en cours.")})
    return lignes


def note_redemarrage() -> str:
    """Résumé du redémarrage pour le message de démarrage du chef (lu une seule fois)."""
    data = store.read_json(NOTE_CHEF, {})
    store.supprimer(NOTE_CHEF)
    if time.time() - data.get("ts", 0) > 3 * 3600:
        return ""  # vieille note (chef relancé bien plus tard) : plus d'actualité
    return data.get("texte", "")


# --- Santé du poste -----------------------------------------------------------------

WIN_CACHE = "sante_windows.json"
WIN_TTL = 30 * 60

_PS_SCRIPT = r"""
$b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
$keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired',
          'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
$pending = $false; foreach ($k in $keys) { if (Test-Path $k) { $pending = $true } }
[pscustomobject]@{
  batterie = if ($b) { [int]$b.EstimatedChargeRemaining } else { $null }
  secteur  = if ($b) { @(1, 4, 5) -notcontains [int]$b.BatteryStatus } else { $true }
  redemarrage = $pending
} | ConvertTo-Json -Compress
"""


BATTERIE_TTL_SECTEUR = 10 * 60   # sur secteur : un débranchement est vu en dix minutes au plus
BATTERIE_TTL_BATTERIE = 2 * 60   # sur batterie : niveau relu toutes les deux minutes
BATTERIE_CACHE_MAX = 20 * 60     # au-delà, une mesure ne prouve plus rien : on ne restreint pas sur sa foi


def _windows_info(now: float, rafraichir: bool = True, max_age: float = WIN_TTL) -> dict | None:
    """Batterie et redémarrage en attente. `rafraichir=False` : cache seulement (jamais de PowerShell)."""
    cache = store.read_json(WIN_CACHE, {})
    if cache and now - cache.get("ts", 0) < max_age:
        return cache.get("info")
    if not rafraichir:
        return None
    ps = shutil.which("powershell.exe")
    if not ps:
        return None
    try:
        res = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                             capture_output=True, text=True, timeout=40)
        info = json.loads(res.stdout.strip() or "null")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        info = None
    store.write_json(WIN_CACHE, {"ts": now, "info": info})
    return info


def _meminfo() -> dict[str, int]:
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, val = line.partition(":")
            out[key] = int(val.split()[0]) if val.split() else 0
    except OSError:
        pass
    return out


def checks(now: float | None = None, windows: bool = True) -> list[dict]:
    """État du poste : [{cle, niveau: ok|alerte|critique, texte}]."""
    now = now or time.time()
    cfg = config.settings()["sante"]
    out: list[dict] = []

    mem = _meminfo()
    if mem.get("MemTotal"):
        pct = 100 * mem.get("MemAvailable", 0) / mem["MemTotal"]
        lvl = "critique" if pct < cfg["memoire_min_pct"] / 2 else ("alerte" if pct < cfg["memoire_min_pct"] else "ok")
        out.append({"cle": "memoire", "niveau": lvl,
                    "texte": f"Mémoire libre : {pct:.0f} % de {mem['MemTotal'] / 1048576:.1f} Go"})

    # Sous WSL, le disque Linux est virtuel : c'est le disque Windows (C:) qui le contient qui compte.
    disques = [("disque", config.HOME, "Disque Linux")]
    if is_wsl() and Path("/mnt/c").is_dir():
        disques.append(("disque_windows", Path("/mnt/c"), "Disque Windows C:"))
    for cle, chemin, nom in disques:
        try:
            free = shutil.disk_usage(chemin).free / 1e9
        except OSError:
            continue
        lvl = "critique" if free < cfg["disque_min_go"] / 2 else ("alerte" if free < cfg["disque_min_go"] else "ok")
        out.append({"cle": cle, "niveau": lvl, "texte": f"{nom} : {free:.0f} Go libres"})

    if shutil.which("docker"):
        try:
            res = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                                 capture_output=True, text=True, timeout=15)
            up = res.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            up = False
        out.append({"cle": "docker", "niveau": "ok" if up else "alerte",
                    "texte": "Docker répond" if up else "Docker ne répond pas : ouvre Docker Desktop (tests de base de données bloqués)"})

    if windows:
        info = _windows_info(now)
        if info:
            if info.get("batterie") is not None and not info.get("secteur", True):
                b = info["batterie"]
                out.append({"cle": "batterie", "niveau": "critique" if b < 20 else "alerte",
                            "texte": f"PC sur batterie ({b} %) : branche-le, sinon il s'arrêtera pendant la nuit"})
            else:
                out.append({"cle": "batterie", "niveau": "ok", "texte": "PC sur secteur"})
            if info.get("redemarrage"):
                out.append({"cle": "redemarrage", "niveau": "alerte",
                            "texte": "Windows attend un redémarrage pour une mise à jour : redémarre toi-même "
                                     "à un moment choisi, ou règle les heures d'activité pour la nuit"})
            else:
                out.append({"cle": "redemarrage", "niveau": "ok", "texte": "Aucun redémarrage Windows en attente"})

    try:
        up_h = float(Path("/proc/uptime").read_text().split()[0]) / 3600
        out.append({"cle": "uptime", "niveau": "ok", "texte": f"Linux allumé depuis {up_h:.0f} h"})
    except (OSError, ValueError, IndexError):
        pass
    return out


# --- Capacité adaptée au poste ------------------------------------------------------------------

MEMOIRE_RESERVE_MO = 1500  # valeur de repli ; le réglage admission.memoire_reserve_mo fait foi
CHARGE_MAX = 2.5           # valeur de repli ; le réglage admission.charge_max_par_coeur fait foi


def capacite(busy: int = 0, now: float | None = None) -> dict:
    """Nombre d'agents que le PC peut porter maintenant.

    Renvoie {"max": plafond effectif, "base": max_agents, "raisons": [pourquoi il est réduit]}.
    Le plafond ne descend jamais sous le nombre d'agents déjà occupés : on n'arrête personne ici,
    on évite seulement d'en lancer de nouveaux sur un PC qui n'a plus la place.
    """
    now = now or time.time()
    s = config.settings()
    base = int(s["general"].get("max_agents", 3))
    cfg = s["sante"]
    adm = s.get("admission", {})
    reserve = float(adm.get("memoire_reserve_mo", MEMOIRE_RESERVE_MO))
    charge_max = float(adm.get("charge_max_par_coeur", CHARGE_MAX))
    out = {"max": base, "base": base, "raisons": []}
    if not cfg.get("capacite_auto", True):
        return out

    def _plafonner(n: int, raison: str) -> None:
        n = max(busy, n)
        if n < out["max"]:
            out["max"] = n
            out["raisons"].append(raison)

    mem = _meminfo()
    if mem.get("MemAvailable"):
        libre = mem["MemAvailable"] / 1024
        par_agent = max(200, int(cfg.get("memoire_par_agent_mo", 1200)))
        places = int(max(0.0, libre - reserve) // par_agent)
        _plafonner(busy + places, f"mémoire libre {libre / 1024:.1f} Go")
    try:
        free = shutil.disk_usage(config.HOME).free / 1e9
        if free < cfg["disque_min_go"] / 2:
            _plafonner(busy, f"disque presque plein ({free:.0f} Go libres)")
    except OSError:
        pass
    try:
        charge = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
        if charge > charge_max:
            _plafonner(busy, f"processeur saturé (charge {charge:.1f} par cœur)")
    except (OSError, AttributeError):
        pass
    info = _windows_info(now, rafraichir=False, max_age=BATTERIE_CACHE_MAX)
    if info and info.get("batterie") is not None and not info.get("secteur", True):
        if info["batterie"] < int(cfg.get("batterie_min_pct", 30)):
            _plafonner(busy, f"PC sur batterie ({info['batterie']} %)")
    return out


def batterie(now: float | None = None, rafraichir: bool = False) -> dict | None:
    """{"pct", "secteur"} ou None si inconnu. Avec `rafraichir`, la mesure est relue quand elle a vieilli :
    toutes les deux minutes sur batterie, toutes les dix sur secteur (appel réservé au démon : PowerShell est lent)."""
    now = now or time.time()
    cache = (store.read_json(WIN_CACHE, {}) or {}).get("info") or {}
    sur_batterie = cache.get("batterie") is not None and not cache.get("secteur", True)
    age = BATTERIE_TTL_BATTERIE if sur_batterie else BATTERIE_TTL_SECTEUR
    info = _windows_info(now, rafraichir=rafraichir, max_age=age if rafraichir else BATTERIE_CACHE_MAX)
    if not info or info.get("batterie") is None:
        return None
    return {"pct": int(info["batterie"]), "secteur": bool(info.get("secteur", True))}


def batterie_critique(now: float | None = None, rafraichir: bool = False) -> int | None:
    """Pourcentage de batterie si le PC est sur batterie sous le seuil d'arrêt, sinon None."""
    b = batterie(now, rafraichir)
    if not b or b["secteur"]:
        return None
    seuil = int(config.settings()["sante"].get("batterie_arret_pct", 12))
    return b["pct"] if b["pct"] <= seuil else None


ICONES = {"ok": "🟢", "alerte": "🟠", "critique": "🔴"}


def texte(items: list[dict] | None = None) -> str:
    items = checks() if items is None else items
    return "\n".join(f"{ICONES.get(i['niveau'], '•')} {i['texte']}" for i in items) or "Aucune mesure disponible."


# --- Réparation git après un arrêt brutal -----------------------------------------------

_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_LOOSE = re.compile(r"^[0-9a-f]{38}([0-9a-f]{24})?$")


def _git(path: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=timeout)


def _objet_absent(path: Path, sha: str) -> bool:
    res = _git(path, "cat-file", "-e", sha + "^{object}", timeout=20)
    # Seul « objet introuvable » compte ; une autre erreur (droits, safe.directory) ne supprime rien.
    return res.returncode != 0 and not res.stderr.strip().startswith(("fatal: detected dubious", "fatal: not a git"))


def reparer_git(path: Path) -> tuple[bool, list[str]]:
    """Répare les dégâts typiques d'un arrêt brutal, sans jamais toucher au code ni aux branches locales.

    1. refus si un agent du projet travaille (il partage ce .git) ;
    2. sauvegarde complète de .git ;
    3. suppression des objets libres vides (illisibles de toute façon) ;
    4. suppression des références DISTANTES cassées (origin/…), que le fetch recrée ;
    5. git fetch --all, puis git fsck.
    """
    gitdir = path / ".git"
    if not gitdir.is_dir():
        return False, [f"{path} n'est pas un dépôt git (ou .git n'est pas un dossier)"]
    check = _git(path, "rev-parse", "--git-dir", timeout=20)
    if check.returncode != 0:
        return False, [f"git ne peut pas lire ce dépôt : {check.stderr.strip()}"]
    projet = config.project_for_path(path)
    found, _ = ag.status_all()
    actifs = [a["worktree"] for a in found or [] if a["status"] in ag.BUSY and a["project"] == projet]
    if actifs:
        return False, [f"des agents travaillent dans ce dépôt ({', '.join(actifs)}) : attends qu'ils aient fini"]

    log: list[str] = []
    dest = config.STATE_DIR / "sauvegardes" / f"{path.name}-git-{time.strftime('%Y%m%d-%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(gitdir, dest, symlinks=True)
    log.append(f"sauvegarde : {dest}")

    vides = [f for f in (gitdir / "objects").glob("??/*")
             if _LOOSE.match(f.name) and f.parent.name != "pack" and f.is_file() and f.stat().st_size == 0]
    for f in vides:
        f.unlink()
    log.append(f"objets vides supprimés : {len(vides)}")

    cassees = []
    remotes = gitdir / "refs" / "remotes"
    for ref in (remotes.rglob("*") if remotes.is_dir() else []):
        if not ref.is_file() or ref.name.endswith(".lock"):
            continue
        sha = ref.read_text(errors="replace").strip()
        if sha.startswith("ref: "):
            continue  # origin/HEAD : référence symbolique
        if not _SHA.match(sha) or set(sha) == {"0"} or _objet_absent(path, sha):
            ref.unlink()
            cassees.append(str(ref.relative_to(gitdir)))
    packed = gitdir / "packed-refs"
    if packed.is_file():
        lines = packed.read_text(errors="replace").splitlines()
        keep = [ln for ln in lines if not (len(ln.split()) == 2 and ln.split()[1].startswith("refs/remotes/")
                                           and _objet_absent(path, ln.split()[0]))]
        if len(keep) != len(lines):
            # Protocole de git : on prend packed-refs.lock, puis on remplace le fichier d'un coup.
            lock = gitdir / "packed-refs.lock"
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                return False, log + ["packed-refs est verrouillé par une autre commande git : réessaie plus tard"]
            with os.fdopen(fd, "w") as fh:
                fh.write("\n".join(keep) + "\n")
            os.replace(lock, packed)
            cassees += [ln.split()[1] for ln in lines if ln not in keep]
    log.append("références distantes recréées : " + (", ".join(cassees) if cassees else "aucune"))

    fetch = _git(path, "fetch", "--all", "--prune", timeout=300)
    log.append("git fetch : " + ("ok" if fetch.returncode == 0 else (fetch.stderr.strip().splitlines() or ["échec"])[-1]))
    fsck = _git(path, "fsck", "--no-dangling", timeout=600)
    problemes = [ln for ln in (fsck.stdout + fsck.stderr).splitlines()
                 if ln.strip() and not ln.startswith(("Checking", "dangling"))]
    if problemes:
        log.append("git fsck signale encore :")
        log += [f"  {ln}" for ln in problemes[:30]]
    else:
        log.append("git fsck : dépôt sain")
    return fetch.returncode == 0 and not problemes, log


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False
