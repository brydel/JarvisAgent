"""Exécutants déclarés : les machines qui peuvent faire tourner des agents, avec leur capacité mesurée.

Aujourd'hui un seul exécutant réel : « local », ce poste, déclaré et tenu à jour par le démon (signe de vie
toutes les minutes, capacité mesurée : cœurs, mémoire, agents au maximum). `jarvis executant declarer` en
ajoute d'autres pour préparer la station. L'admission continue de n'utiliser que le poste local : répartir le
travail sur plusieurs machines demandera un état partagé (serveur) — conçu, voir docs/autonomy/architecture.md.
"""

from __future__ import annotations

import os
import re
import socket
import time

from . import store

FILE = "executants.json"
ACTIF_S = 300
NOM_OK = re.compile(r"^[a-z0-9][a-z0-9._-]{0,40}$")


class ExecutantError(ValueError):
    pass


def mesurer() -> dict:
    """Capacité de ce poste : cœurs, mémoire totale et disponible, agents au maximum (réglage et santé)."""
    from . import diagnostic, poste
    mem = diagnostic.memoire()
    try:
        agents_max = int(poste.capacite().get("max", 0))
    except Exception:  # noqa: BLE001 — mesure de confort : jamais bloquante
        agents_max = 0
    return {"coeurs": os.cpu_count() or 0, "memoire_mo": mem.get("total_mo"),
            "memoire_dispo_mo": mem.get("disponible_mo"), "agents_max": agents_max}


def declarer(nom: str, *, hote: str = "", capacite: dict | None = None, par: str = "humain",
             now: float | None = None) -> dict:
    nom = nom.strip().lower()
    if not NOM_OK.match(nom):
        raise ExecutantError(f"nom d'exécutant invalide « {nom} »")
    now = now or time.time()
    cap = capacite if capacite is not None else (mesurer() if nom == "local" else {})

    def _set(data):
        e = data.get(nom) or {"declare": now, "par": par}
        e.update(hote=hote or e.get("hote") or (socket.gethostname() if nom == "local" else ""), capacite=cap, vu=now)
        data[nom] = e
        return dict(e)

    return store.update_json(FILE, {}, _set)


def signe_de_vie(nom: str = "local", now: float | None = None, intervalle: float = 60) -> bool:
    """Tenu par le démon pour « local » : remesure et horodate, au plus une fois par minute."""
    now = now or time.time()
    e = store.read_json(FILE, {}).get(nom)
    if e and now - e.get("vu", 0) < intervalle:
        return False
    declarer(nom, par="demon", now=now)
    return True


def retirer(nom: str) -> bool:
    def _del(data):
        return data.pop(nom.lower(), None) is not None
    return bool(store.update_json(FILE, {}, _del))


def liste(now: float | None = None) -> list[dict]:
    now = now or time.time()
    out = []
    for nom, e in sorted(store.read_json(FILE, {}).items()):
        out.append({"nom": nom, **e, "actif": now - e.get("vu", 0) < ACTIF_S})
    return out


def texte(now: float | None = None) -> str:
    from . import bail
    b = bail.lire(now)
    lignes = [f"Orchestrateur : {b['titulaire']} (bail n° {b['numero']}, depuis "
              f"{time.strftime('%d/%m %H:%M', time.localtime(b['depuis']))})" if b else "Orchestrateur : aucun démon actif"]
    for e in liste(now):
        c = e.get("capacite") or {}
        vu = time.strftime("%d/%m %H:%M", time.localtime(e.get("vu", 0)))
        lignes.append(f"{'●' if e['actif'] else '○'} {e['nom']:<12} {e.get('hote') or '?':<18} "
                      f"{c.get('coeurs', '?')} cœurs · {c.get('memoire_mo', '?')} Mo · {c.get('agents_max', '?')} agents max"
                      f" — vu {vu}")
    if len(lignes) == 1:
        lignes.append("Aucun exécutant déclaré (le démon déclare « local » à son démarrage).")
    return "\n".join(lignes)
