#!/usr/bin/env python3
"""Mesure les fondations de données du Board : temps et nombre de requêtes de `board.objets()`, coût d'une
connexion, coût d'un tour de sondage du flux, recherche d'une carte de travail par sa référence.

Tout se passe dans un état TEMPORAIRE (base SQLite neuve sous un dossier jetable) : ton installation n'est ni lue
ni modifiée. Le script ne dépend que de l'API publique du moteur, pour pouvoir être lancé tel quel sur une version
plus ancienne du dépôt et comparer avant / après.

    python3 outils/mesurer_board.py                 # 500 et 5 000 cartes
    python3 outils/mesurer_board.py --cartes 10 500 --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def _isoler() -> Path:
    base = Path(tempfile.mkdtemp(prefix="jarvis-mesure-board-"))
    os.environ["JARVIS_STATE_DIR"] = str(base / "etat")
    os.environ["JARVIS_CONFIG_DIR"] = str(base / "config")
    os.environ["JARVIS_DATA_DIR"] = str(base / "data")
    os.environ.pop("JARVIS_MISSIONS_PG", None)
    sys.path.insert(0, str(RACINE / "lib"))
    return base


class Compteur:
    """Compte les requêtes SQL (trace SQLite) des connexions ouvertes par le moteur pendant un bloc."""

    def __init__(self, mi):
        self.mi, self.n, self.actif = mi, 0, False
        self._origine = mi.BackendSQLite.connecter

        def connecter(backend, tenant_id):
            c = self._origine(backend, tenant_id)
            c.set_trace_callback(self._voir)
            return c
        mi.BackendSQLite.connecter = connecter

    def _voir(self, sql: str) -> None:
        if self.actif and not sql.lstrip().upper().startswith(("PRAGMA", "BEGIN", "COMMIT", "ROLLBACK")):
            self.n += 1

    def compter(self, f) -> int:
        self.n, self.actif = 0, True
        try:
            f()
        finally:
            self.actif = False
        return self.n


def peupler(mi, board, org: str, espace: str, n: int) -> dict:
    """n cartes réalistes : 10 % de cartes mission (avec tâche), 10 % avec fichier, 20 % commentées, n/2 relations,
    quelques cartes de travail du chef (référence)."""
    t0 = time.time()
    with mi.transaction(org) as c:
        for i in range(max(1, n // 10)):
            c.execute("INSERT INTO board_assets (id, tenant_id, sha256, mime, taille, nom, fichier, meta, cree) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (f"AS-{i:012x}", org, f"{i:064x}", "image/png", 1000, f"image {i}.png",
                                                    f"{i:064x}.png", '{"famille": "image", "largeur": 800, "hauteur": 600}', t0))
    ids, missions, refs = [], 0, 0
    for i in range(n):
        kw = {}
        type_, contenu = "note", f"Note de mesure {i}\n- point\n- autre point"
        if i % 10 == 0:
            m = mi.creer_mission(org, f"Mission de mesure {i}", [{"type": "analyse_document", "niveau": "L1",
                                 "capacites": ["analyse"], "travail": {"document": "x"}}], source="mesure", demandeur="mesure")
            type_, contenu, kw = "mission", "", {"mission_id": m["mission_id"]}
            missions += 1
        elif i % 10 == 1:
            type_, contenu, kw = "image", "", {"asset_id": f"AS-{(i // 10) % max(1, n // 10):012x}"}
        elif i % 50 == 2:
            type_, contenu = "tache", ""
            kw = {"meta": {"titre": f"Tâche {i}", "travail_ref": f"tache:T-{i}", "source": "chef"}}
            refs += 1
        o = mi.board_ajouter(org, espace, type_, contenu, auteur="mesure", x=(i % 40) * 460, y=(i // 40) * 380,
                             largeur=420, hauteur=320, analyser=False, **kw)
        ids.append(o["objet_id"])
    for i in range(0, n, 5):
        board.commenter(org, ids[i], f"commentaire {i}", auteur="mesure")
    liens = 0
    for i in range(0, n - 1, 2):
        board.lier(org, espace, ids[i], ids[i + 1], par="mesure")
        liens += 1
    return {"cartes": n, "missions": missions, "liens": liens, "refs": refs, "peuplement_s": round(time.time() - t0, 2), "ids": ids}


def chrono(f, repetitions: int) -> float:
    """Médiane (ms) sur `repetitions` appels."""
    temps = []
    for _ in range(repetitions):
        t = time.perf_counter()
        f()
        temps.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(temps), 3)


def mesurer(n: int, compteur_de, *, verbeux: bool) -> dict:
    from jarvis import board, missions as mi, travail_board
    mi.backend().reinitialiser()
    org = mi.tenant_local()
    espace = "mesure"
    infos = peupler(mi, board, org, espace, n)
    ids = infos.pop("ids")
    compteur = compteur_de(mi)
    r = {"cartes": n, **infos}
    etat = board.objets(org, espace)
    assert len(etat["objets"]) == n, (len(etat["objets"]), n)
    r["objets_requetes"] = compteur.compter(lambda: board.objets(org, espace))
    r["objets_ms"] = chrono(lambda: board.objets(org, espace), 5 if n <= 1000 else 3)
    r["charge_utile_ko"] = round(len(json.dumps(etat, ensure_ascii=False).encode()) / 1024)
    r["connexion_ms"] = chrono(lambda: mi._connecter(org).close(), 200)
    # un tour de sondage du flux quand il n'y a rien de neuf (ce que fait le serveur plusieurs fois par seconde)
    dernier = max((e["seq"] for e in mi.evenements(org, apres=0, limite=1_000_000)), default=0)
    r["sondage_flux_ms"] = chrono(lambda: mi.evenements(org, apres=dernier), 200)
    if hasattr(mi, "LecteurEvenements"):
        lecteur = mi.LecteurEvenements(org, espace=espace)
        lecteur.lire(dernier)
        r["sondage_flux_lecteur_ms"] = chrono(lambda: lecteur.lire(dernier), 2000)
        lecteur.fermer()
    if hasattr(board, "lire"):  # lecture ciblée (delta) : un objet
        r["delta_1_requetes"] = compteur.compter(lambda: board.lire(org, espace, objets=[ids[0]]))
        r["delta_1_ms"] = chrono(lambda: board.lire(org, espace, objets=[ids[0]]), 50)
    c = mi._connecter(org)
    try:
        r["reference_ms"] = chrono(lambda: travail_board._trouver(c, org, espace, "tache:T-2"), 50)
    finally:
        c.close()
    if verbeux:
        print(f"  {n} cartes : objets() {r['objets_ms']} ms, {r['objets_requetes']} requêtes", file=sys.stderr)
    return r


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cartes", type=int, nargs="+", default=[500, 5000])
    p.add_argument("--json", action="store_true", help="sortie JSON seule")
    a = p.parse_args()
    base = _isoler()
    try:
        compteurs: dict = {}

        def compteur_de(mi):
            if "c" not in compteurs:
                compteurs["c"] = Compteur(mi)
            return compteurs["c"]
        resultats = [mesurer(n, compteur_de, verbeux=not a.json) for n in a.cartes]
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if a.json:
        print(json.dumps(resultats, ensure_ascii=False, indent=2))
        return 0
    colonnes = [("cartes", "cartes"), ("objets_ms", "objets() ms"), ("objets_requetes", "requêtes"), ("charge_utile_ko", "réponse Ko"),
                ("connexion_ms", "connexion ms"), ("sondage_flux_ms", "sondage flux ms"),
                ("sondage_flux_lecteur_ms", "sondage (lecteur) ms"), ("delta_1_ms", "delta 1 objet ms"),
                ("delta_1_requetes", "delta requêtes"), ("reference_ms", "référence ms")]
    print(" | ".join(nom for _, nom in colonnes))
    for r in resultats:
        print(" | ".join(str(r.get(cle, "—")) for cle, _ in colonnes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
