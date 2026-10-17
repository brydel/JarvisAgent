"""Migration de l'état JSON vers SQLite (et retour), sans perte et vérifiée.

`migrer` : importe chaque fichier d'état *.json (sauf lourdes/, que le bac à sable de Codex doit pouvoir écrire)
dans jarvis.db, relit chaque valeur et la compare à l'original, puis seulement bascule le réglage
stockage.backend = "sqlite". Une copie des JSON est gardée dans sauvegardes/. Les journaux en ajout seul (*.jsonl),
dont le journal d'audit chaîné, ne sont pas convertis : ils restent des fichiers, intacts.
`revenir` : réécrit les JSON depuis la base (après sauvegarde des JSON présents), vérifie, rebascule en json.
Refusé tant qu'un démon tient le bail d'orchestrateur : arrête-le d'abord (rien ne doit écrire pendant la copie).
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import bail, config, store


class StockageError(RuntimeError):
    pass


def _fichiers_etat() -> list[Path]:
    racine = config.STATE_DIR
    out = []
    for p in sorted(racine.rglob("*.json")):
        rel = p.relative_to(racine).as_posix()
        if rel.startswith(("lourdes/", "sauvegardes/")) or not p.is_file():
            continue
        out.append(p)
    return out


def _sans_demon() -> None:
    b = bail.lire()
    if b and b["titulaire"] != bail.identite():
        raise StockageError(f"un démon tient le bail ({b['titulaire']}) : arrête-le (jarvis start le relancera) puis recommence")


def _regler(valeur: str) -> None:
    s = config.settings()
    s.setdefault("stockage", {})["backend"] = valeur
    config.save_settings(s)


def migrer(par: str = "humain") -> dict:
    if store.backend() == "sqlite":
        raise StockageError("le stockage est déjà en SQLite")
    _sans_demon()
    racine = config.STATE_DIR
    sauvegarde = racine / "sauvegardes" / f"json-{time.strftime('%Y%m%d-%H%M%S')}"
    importes, ignores = {}, []
    with store.locked("stockage"):
        for p in _fichiers_etat():
            rel = p.relative_to(racine).as_posix()
            try:
                importes[rel] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                ignores.append(f"{rel} ({exc})")
            dest = sauvegarde / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        with store.transaction() as c:
            for nom, valeur in importes.items():
                c.execute("INSERT INTO etat (nom, valeur, maj) VALUES (?, ?, ?) ON CONFLICT(nom) DO UPDATE SET "
                          "valeur = excluded.valeur, maj = excluded.maj", (nom, json.dumps(valeur, ensure_ascii=False),
                                                                           time.time()))
        relus = dict(store.connexion().execute("SELECT nom, valeur FROM etat").fetchall())
        ecarts = [n for n, v in importes.items() if n not in relus or json.loads(relus[n]) != v]
        if ecarts:
            raise StockageError("vérification échouée, rien n'est basculé : " + ", ".join(ecarts[:10]))
        _regler("sqlite")
    _journal(par, "migre", f"{len(importes)} état(s), sauvegarde {sauvegarde}")
    return {"importes": len(importes), "ignores": ignores, "sauvegarde": str(sauvegarde), "base": str(store.db_path())}


def revenir(par: str = "humain") -> dict:
    if store.backend() != "sqlite":
        raise StockageError("le stockage est déjà en JSON")
    _sans_demon()
    racine = config.STATE_DIR
    sauvegarde = racine / "sauvegardes" / f"json-avant-retour-{time.strftime('%Y%m%d-%H%M%S')}"
    with store.locked("stockage"):
        lignes = dict(store.connexion().execute("SELECT nom, valeur FROM etat").fetchall())
        for p in _fichiers_etat():
            dest = sauvegarde / p.relative_to(racine)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        for nom, valeur in lignes.items():
            chemin = store.state_path(nom)
            tmp = chemin.with_suffix(chemin.suffix + ".tmp")
            tmp.write_text(json.dumps(json.loads(valeur), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(chemin)
        ecarts = [n for n, v in lignes.items() if json.loads(store.state_path(n).read_text(encoding="utf-8")) != json.loads(v)]
        if ecarts:
            raise StockageError("vérification échouée, le stockage reste en SQLite : " + ", ".join(ecarts[:10]))
        _regler("json")
    _journal(par, "retour_json", f"{len(lignes)} état(s)")
    return {"exportes": len(lignes), "sauvegarde": str(sauvegarde)}


def etat() -> dict:
    out = {"backend": store.backend(), "base": str(store.db_path()), "base_existe": store.db_path().exists()}
    if out["base_existe"]:
        out["lignes"] = store.connexion().execute("SELECT COUNT(*) FROM etat").fetchone()[0]
        out["taille_ko"] = round(store.db_path().stat().st_size / 1024)
    out["fichiers_json"] = len(_fichiers_etat())
    return out


def _journal(acteur: str, decision: str, raison: str) -> None:
    try:
        from . import journal
        journal.ecrire("systeme", acteur=acteur, objet="stockage", decision=decision, raison=raison)
    except Exception:  # noqa: BLE001
        pass
