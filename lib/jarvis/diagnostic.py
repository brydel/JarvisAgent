"""Diagnostic léger du poste : ce que Linux (WSL) voit, ce que Windows alloue, et ce qu'on ne sait pas.

`jarvis diagnostic` produit un rapport EXPURGÉ (aucun nom d'utilisateur, chemin personnel, adresse ni
jeton) enregistré sous DATA_DIR/diagnostics/. Il sert à régler les profils (laptop-conservative…) à
partir de mesures, pas d'hypothèses. Une mesure absente est affichée « inconnu » : jamais devinée.

Mesures : mémoire totale/disponible/swap et pression PSI (WSL), processeur (modèle, cœurs, charge),
disque Linux et C:, mémoire Windows totale et libre (PowerShell, si disponible), température (zones
thermiques Linux si exposées — rarement sous WSL), processus par famille (agents, navigateurs,
compilations, rendus, conteneurs), limites imposables (cgroup v2, systemd --user, nice/ionice).
Bibliothèque standard uniquement ; les commandes externes sont bornées dans le temps.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config

INCONNU = "inconnu"
FAMILLES = {
    "agents": ("claude", "codex", "node"),  # Claude Code et Codex tournent sous node
    "navigateurs": ("chrome", "chromium", "msedge", "headless_shell", "firefox"),
    "compilations": ("tsc", "esbuild", "webpack", "vite", "cargo", "rustc", "gcc", "g++", "clang", "make", "ninja", "javac", "go"),
    "tests": ("pytest", "jest", "vitest", "playwright"),
    "rendus": ("ffmpeg", "ffprobe"),
    "conteneurs": ("dockerd", "containerd", "docker-proxy", "runc"),
    "python": ("python", "python3"),
}


def _lire(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _cmd(cmd: list[str], timeout: int = 10) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout if res.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def memoire() -> dict:
    mem: dict[str, int] = {}
    for line in _lire("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if v.split():
            mem[k] = int(v.split()[0])
    out = {"total_mo": round(mem["MemTotal"] / 1024) if mem.get("MemTotal") else INCONNU,
           "disponible_mo": round(mem["MemAvailable"] / 1024) if mem.get("MemAvailable") else INCONNU,
           "swap_total_mo": round(mem.get("SwapTotal", 0) / 1024) if "SwapTotal" in mem else INCONNU,
           "swap_libre_mo": round(mem.get("SwapFree", 0) / 1024) if "SwapFree" in mem else INCONNU,
           "pression_psi": INCONNU}
    psi = _lire("/proc/pressure/memory")
    if psi:
        m = re.search(r"some avg10=([\d.]+) avg60=([\d.]+) avg300=([\d.]+)", psi)
        if m:
            out["pression_psi"] = {"avg10": float(m[1]), "avg60": float(m[2]), "avg300": float(m[3])}
    return out


def processeur() -> dict:
    cpuinfo = _lire("/proc/cpuinfo")
    modele = next((ln.split(":", 1)[1].strip() for ln in cpuinfo.splitlines() if ln.startswith("model name")), INCONNU)
    coeurs = os.cpu_count() or INCONNU
    try:
        l1, l5, l15 = os.getloadavg()
        charge = {"1min": round(l1, 2), "5min": round(l5, 2), "15min": round(l15, 2),
                  "par_coeur_1min": round(l1 / coeurs, 2) if isinstance(coeurs, int) else INCONNU}
    except (OSError, AttributeError):
        charge = INCONNU
    psi = _lire("/proc/pressure/cpu")
    m = re.search(r"some avg10=([\d.]+) avg60=([\d.]+)", psi) if psi else None
    return {"modele": modele, "coeurs_logiques_wsl": coeurs, "charge": charge,
            "pression_psi": {"avg10": float(m[1]), "avg60": float(m[2])} if m else INCONNU,
            "frequence_mhz": _frequence()}


def _frequence():
    f = _lire("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").strip()
    if f.isdigit():
        return round(int(f) / 1000)
    m = re.search(r"cpu MHz\s*:\s*([\d.]+)", _lire("/proc/cpuinfo"))
    return round(float(m[1])) if m else INCONNU


def temperature() -> dict:
    """Zones thermiques Linux. Sous WSL2 elles ne sont généralement pas exposées : « inconnu », pas une estimation."""
    zones = {}
    for z in sorted(Path("/sys/class/thermal").glob("thermal_zone*")) if Path("/sys/class/thermal").is_dir() else []:
        t = _lire(str(z / "temp")).strip()
        typ = _lire(str(z / "type")).strip() or z.name
        if t.lstrip("-").isdigit():
            zones[typ] = round(int(t) / 1000, 1)
    hwmon = {}
    for h in sorted(Path("/sys/class/hwmon").glob("hwmon*")) if Path("/sys/class/hwmon").is_dir() else []:
        nom = _lire(str(h / "name")).strip() or h.name
        for f in sorted(h.glob("temp*_input")):
            t = _lire(str(f)).strip()
            if t.lstrip("-").isdigit():
                hwmon[f"{nom}/{f.name}"] = round(int(t) / 1000, 1)
    return {"zones_c": zones or INCONNU, "hwmon_c": hwmon or INCONNU,
            "limitation_thermique": INCONNU,
            "note": "aucune source fiable sous WSL : laisser « inconnu » ; ne pas déduire une température de la charge"}


def disques() -> dict:
    out = {}
    for nom, chemin in (("linux", config.HOME), ("windows_c", Path("/mnt/c"))):
        try:
            if chemin.is_dir():
                u = shutil.disk_usage(chemin)
                out[nom] = {"total_go": round(u.total / 1e9), "libre_go": round(u.free / 1e9)}
        except OSError:
            out[nom] = INCONNU
    return out


def _processus() -> list[tuple[int, int, str, int]]:
    """[(pid, ppid, comm, rss_ko)] d'après /proc."""
    out = []
    for e in os.listdir("/proc"):
        if not e.isdigit():
            continue
        stat = _lire(f"/proc/{e}/stat")
        if not stat:
            continue
        nom = stat[stat.find("(") + 1:stat.rfind(")")]
        reste = stat[stat.rfind(")") + 2:].split()
        ppid = int(reste[1]) if len(reste) > 1 and reste[1].isdigit() else 0
        rss = 0
        for ln in _lire(f"/proc/{e}/status").splitlines():
            if ln.startswith("VmRSS:"):
                rss = int(ln.split()[1])
                break
        out.append((int(e), ppid, nom, rss))
    return out


def processus() -> dict:
    procs = _processus()
    familles = {f: {"nb": 0, "rss_mo": 0} for f in FAMILLES}
    for _pid, _ppid, nom, rss in procs:
        base = nom.lower()
        for fam, noms in FAMILLES.items():
            if base in noms or any(base.startswith(n) for n in noms if len(n) > 4):
                familles[fam]["nb"] += 1
                familles[fam]["rss_mo"] += rss // 1024
                break
    # Descendants des volets d'agents tmux : combien de processus chaque agent entraîne.
    agents = []
    try:
        from . import agents as ag
        enfants: dict[int, list[int]] = {}
        for pid, ppid, _n, _r in procs:
            enfants.setdefault(ppid, []).append(pid)
        rss_par_pid = {pid: rss for pid, _p, _n, rss in procs}
        for w in ag.tmux_agent_windows():
            if not w.get("pid"):
                continue
            a_voir, total, mo = [w["pid"]], 0, 0
            while a_voir:
                p = a_voir.pop()
                for c in enfants.get(p, []):
                    total += 1
                    mo += rss_par_pid.get(c, 0) // 1024
                    a_voir.append(c)
            agents.append({"fenetre": w["window"], "descendants": total, "rss_mo": mo})
    except Exception:  # noqa: BLE001 — le diagnostic ne doit jamais planter sur tmux
        pass
    conteneurs = _cmd(["docker", "ps", "-q"], timeout=8)
    return {"total": len(procs), "familles": familles, "agents_tmux": agents,
            "conteneurs_docker": len(conteneurs.split()) if conteneurs else (0 if shutil.which("docker") else INCONNU)}


def limites() -> dict:
    """Mécanismes de plafonnement réellement disponibles ici (à valider sous WSL, pas supposés)."""
    cg = Path("/sys/fs/cgroup")
    v2 = (cg / "cgroup.controllers").is_file()
    controleurs = _lire(str(cg / "cgroup.controllers")).split() if v2 else []
    # Un cgroup délégué à l'utilisateur est inscriptible sans root : c'est lui qui permettrait de plafonner.
    delegue = ""
    for cand in (Path(f"/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice"), cg):
        try:
            if cand.is_dir() and os.access(cand, os.W_OK):
                delegue = str(cand).replace(str(config.HOME), "~")
                break
        except OSError:
            continue
    systemd_user = bool(_cmd(["systemctl", "--user", "is-system-running"], timeout=5).strip()) if shutil.which("systemctl") else False
    return {
        "cgroup_v2": v2, "controleurs": controleurs, "cgroup_inscriptible_sans_root": delegue or False,
        "systemd_run_user": systemd_user, "nice": bool(shutil.which("nice")), "ionice": bool(shutil.which("ionice")),
        "prlimit": bool(shutil.which("prlimit")),
        "verdict": ("plafonds CPU/mémoire imposables par cgroup délégué" if delegue and {"cpu", "memory"} <= set(controleurs)
                    else "aucun plafond CPU/mémoire imposable sans root ici : seules la priorité (nice) et "
                         "l'admission s'appliquent ; les commandes des agents ne sont pas bornées"),
    }


_PS_WINDOWS = r"""
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
[pscustomobject]@{
  memoire_totale_mo = [int]($os.TotalVisibleMemorySize / 1024)
  memoire_libre_mo  = [int]($os.FreePhysicalMemory / 1024)
  modele_pc = ($cs.Manufacturer + ' ' + $cs.Model).Trim()
  processeur = $cpu.Name
  coeurs = $cpu.NumberOfCores
  threads = $cpu.NumberOfLogicalProcessors
  version = $os.Caption
} | ConvertTo-Json -Compress
"""


def windows(interroger: bool = True) -> dict:
    """Ce que Windows alloue ou garde : mémoire totale/libre côté Windows, modèle, processeur. Rien de personnel."""
    from . import poste
    if not poste.is_wsl():
        return {"wsl": False}
    out: dict = {"wsl": True, "distribution": os.environ.get("WSL_DISTRO_NAME") or INCONNU,
                 "wslconfig": _wslconfig()}
    ps = shutil.which("powershell.exe")
    if not interroger or not ps:
        out["windows"] = INCONNU
        return out
    try:
        res = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", _PS_WINDOWS],
                             capture_output=True, text=True, timeout=40)
        out["windows"] = json.loads(res.stdout.strip() or "null") or INCONNU
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        out["windows"] = INCONNU
    return out


def _wslconfig() -> dict | str:
    """Limites déclarées dans %UserProfile%\\.wslconfig (memory, processors, swap), sans le chemin ni le nom."""
    out = _cmd(["cmd.exe", "/c", "echo %UserProfile%"], timeout=8).strip()
    if not out:
        return INCONNU
    chemin = _cmd(["wslpath", out], timeout=5).strip()
    texte = _lire(str(Path(chemin) / ".wslconfig")) if chemin else ""
    if not texte:
        return "absent (valeurs par défaut de WSL : 50 % de la RAM, tous les cœurs)"
    vals = {}
    for ln in texte.splitlines():
        m = re.match(r"\s*(memory|processors|swap)\s*=\s*(\S+)", ln, re.I)
        if m:
            vals[m[1].lower()] = m[2]
    return vals or "présent sans limite mémoire/processeur"


def collecter(windows_: bool = True, **_ignore) -> dict:
    s = config.settings()
    return {
        "ts": time.time(), "date": time.strftime("%Y-%m-%d %H:%M"),
        "environnement": {"noyau": _lire("/proc/version").split("(")[0].strip() or INCONNU,
                          "python": ".".join(map(str, __import__('sys').version_info[:3])),
                          "ce_pc_est_la_cible": True},
        "memoire": memoire(), "processeur": processeur(), "temperature": temperature(), "disques": disques(),
        "processus": processus(), "limites": limites(), "windows": windows(windows_),
        "reglages": {"profil": s["admission"].get("profil") or "aucun", "max_agents": s["general"]["max_agents"],
                     "operations_lourdes_max": s["admission"]["operations_lourdes_max"],
                     "memoire_reserve_mo": s["admission"]["memoire_reserve_mo"],
                     "configuration_valide": not config.valider(s)},
    }


def _expurger(obj):
    """Retire ce qui pourrait identifier : chemins personnels, nom d'utilisateur, adresses."""
    home = str(config.HOME)
    user = os.environ.get("USER") or Path(home).name
    if isinstance(obj, dict):
        return {k: _expurger(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expurger(v) for v in obj]
    if isinstance(obj, str):
        s = obj.replace(home, "~")
        if user and len(user) > 2 and user not in ("root", "user", "ubuntu", "admin"):
            s = re.sub(rf"(?<![\w-]){re.escape(user)}(?![\w-])", "<utilisateur>", s)
        s = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<ip>", s)
        return s
    return obj


def enregistrer(rapport: dict) -> Path:
    dossier = config.DATA_DIR / "diagnostics"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"diagnostic-{time.strftime('%Y%m%d-%H%M%S')}.json"
    chemin.write_text(json.dumps(_expurger(rapport), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for ancien in sorted(dossier.glob("diagnostic-*.json"))[:-30]:
        ancien.unlink(missing_ok=True)
    return chemin


def texte(r: dict) -> str:
    r = _expurger(r)
    m, c, t, l, w = r["memoire"], r["processeur"], r["temperature"], r["limites"], r["windows"]
    out = [f"DIAGNOSTIC DU POSTE — {r['date']} (mesuré sur CE PC ; un rapport venu d'ailleurs ne vaut pas pour lui)",
           "",
           f"Linux/WSL : {r['environnement']['noyau']} · distribution {w.get('distribution', '-') if w.get('wsl') else 'hors WSL'}",
           f"Processeur : {c['modele']} · {c['coeurs_logiques_wsl']} cœurs logiques vus par WSL · charge 1 min "
           f"{c['charge']['1min'] if isinstance(c['charge'], dict) else c['charge']} "
           f"({c['charge']['par_coeur_1min'] if isinstance(c['charge'], dict) else '?'} par cœur) · fréquence {c['frequence_mhz']} MHz",
           f"Mémoire WSL : {m['total_mo']} Mo total, {m['disponible_mo']} Mo disponibles, swap {m['swap_libre_mo']}/{m['swap_total_mo']} Mo · "
           f"pression PSI 60 s : {m['pression_psi']['avg60'] if isinstance(m['pression_psi'], dict) else m['pression_psi']}"]
    if isinstance(w.get("windows"), dict):
        ww = w["windows"]
        out.append(f"Windows : {ww.get('modele_pc', '?')} · {ww.get('processeur', '?')} ({ww.get('coeurs', '?')} cœurs / "
                   f"{ww.get('threads', '?')} threads) · mémoire {ww.get('memoire_libre_mo', '?')}/{ww.get('memoire_totale_mo', '?')} Mo libre")
    elif w.get("wsl"):
        out.append("Windows : inconnu (PowerShell indisponible ou non interrogé)")
    if w.get("wsl"):
        out.append(f".wslconfig : {w.get('wslconfig')}")
    temp = t["zones_c"] if t["zones_c"] != INCONNU else INCONNU
    out.append(f"Température : {temp} · limitation thermique : {t['limitation_thermique']}")
    for nom, d in r["disques"].items():
        out.append(f"Disque {nom} : {d['libre_go']}/{d['total_go']} Go libres" if isinstance(d, dict) else f"Disque {nom} : inconnu")
    p = r["processus"]
    fam = ", ".join(f"{k} {v['nb']} ({v['rss_mo']} Mo)" for k, v in p["familles"].items() if v["nb"])
    out.append(f"Processus : {p['total']} au total · {fam or 'aucune famille connue'} · conteneurs Docker : {p['conteneurs_docker']}")
    for a in p["agents_tmux"]:
        out.append(f"  agent {a['fenetre']} : {a['descendants']} processus descendants, {a['rss_mo']} Mo")
    out.append(f"Plafonds imposables : {l['verdict']} (cgroup v2 : {l['cgroup_v2']}, délégué : {l['cgroup_inscriptible_sans_root']}, "
               f"systemd --user : {l['systemd_run_user']}, nice : {l['nice']})")
    rg = r["reglages"]
    out.append(f"Réglages : profil {rg['profil']} · max_agents {rg['max_agents']} · opérations lourdes {rg['operations_lourdes_max']} · "
               f"réserve mémoire {rg['memoire_reserve_mo']} Mo · configuration {'valide' if rg['configuration_valide'] else 'INVALIDE'}")
    return "\n".join(out)
