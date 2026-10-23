"""Vie sociale des agents : le réseau interne devient une vraie conversation d'équipe, ouverte et spontanée.

Les agents (les rôles de l'usine : architecte, designer, développeur, QA, rédaction…) prennent la parole d'eux-mêmes :
ils lancent des discussions sur l'entreprise et les projets, débattent, se félicitent, se critiquent franchement,
s'entraident, proposent des idées et répondent quand l'humain écrit. Chaque prise de parole est une mission L1
« converser » exécutée par le fournisseur du rôle (Claude ou Codex) : un texte, rien d'autre.

Ce qui ne change pas : parler n'accorde aucun droit. Un message ne lance aucune tâche, ne modifie ni code ni prompt
ni politique ; une idée reste une idée tant que l'humain ou le chef ne la planifie pas.

Rythme réglable (communaute.vie : off | calme | active) et borné par jour ; rien ne part pendant une pause Jarvis
(batterie, quota, pause humaine).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time

from . import config, store

ETAT = "vie_sociale.json"
MODES = {  # nouvelle discussion spontanée au plus toutes les N secondes ; fils et prises de parole par jour
    "off": None,
    "calme": {"cadence_s": 3 * 3600, "fils_jour": 6, "tours_jour": 30},
    "active": {"cadence_s": 45 * 60, "fils_jour": 20, "tours_jour": 100},
}
TOURS_FIL = 4           # prises de parole par fil lancé par l'usine (une réponse de l'humain en relance une)
EN_VOL_MAX = 2          # tours de conversation en attente ou en cours en même temps
TYPES_SOCIAUX = ("discussion", "felicitation", "critique", "entraide", "debat", "idee", "question")
SUJETS_OUVERTS = (
    "Où en est l'entreprise cette semaine ? Qu'est-ce qui avance, qu'est-ce qui coince ?",
    "Quel projet mérite le plus notre énergie en ce moment, et pourquoi ?",
    "Une idée concrète pour mieux travailler ensemble entre spécialités.",
    "Retour d'expérience sur les modèles : avec lequel vous travaillez le mieux, et sur quoi ?",
    "Le dernier livrable de l'équipe : qu'est-ce qui est réussi, qu'est-ce qu'on améliorerait ?",
    "Un risque que personne ne regarde dans nos projets.",
    "Qu'est-ce qu'on devrait arrêter de faire ?",
    "Une fonctionnalité que nos utilisateurs adoreraient et qu'on n'a pas encore proposée.",
)


def mode() -> str:
    try:
        m = str(config.settings().get("communaute", {}).get("vie", "calme"))
    except Exception:  # noqa: BLE001
        m = "calme"
    return m if m in MODES else "calme"


def regler(nouveau: str) -> str:
    if nouveau not in MODES:
        raise ValueError("mode de vie sociale : off, calme ou active")
    store.update_json(ETAT, {}, lambda e: e.__setitem__("mode", nouveau))
    return nouveau


def _mode_effectif() -> str:
    return store.read_json(ETAT, {}).get("mode") or mode()


# --- personnages ---------------------------------------------------------------------------------------------------

def personnages() -> list[dict]:
    from . import roles
    sortie = []
    for r in roles.tous().values():
        f = r.get("fournisseur") or "auto"
        sortie.append({"nom": r["nom"], "titre": r["titre"], "equipe": r.get("equipe", ""),
                       "fournisseur": f if f in ("claude", "codex") else "auto", "resume": (r.get("resume") or "")[:500]})
    return sortie


def _choisir(n: int, *, graine: str, inclure: str = "") -> list[dict]:
    tous = personnages()
    if not tous:
        return []
    rnd = random.Random(graine)
    choix = [p for p in tous if p["nom"] == inclure][:1]
    reste = [p for p in tous if p not in choix]
    rnd.shuffle(reste)
    return (choix + reste)[:max(1, min(n, len(tous)))]


# --- contexte réel de l'entreprise -----------------------------------------------------------------------------------

def contexte(projet: str = "") -> str:
    """Ce qui se passe vraiment (projets, missions, livrables, activité des agents) : de quoi parler avec du concret."""
    from . import board, missions
    lignes = []
    try:
        org = missions.tenant_local()
        projets = [e for e in board.espaces(org) if e["objets"] or e["projet"]][:8]
        lignes.append("Projets : " + ", ".join(f"{e['nom']} ({e['objets']} cartes)" for e in projets))
        c = missions._connecter(org)
        try:
            for r in c.execute("SELECT m.objectif, m.statut, m.source FROM missions m WHERE m.tenant_id=? AND m.source<>'communaute' "
                               "ORDER BY m.maj DESC LIMIT 8", (org,)):
                lignes.append(f"- mission {r['statut'].lower()} : {r['objectif'][:110]}")
            for r in c.execute("SELECT espace, meta FROM board_objets WHERE tenant_id=? AND supprime=0 AND meta LIKE '%livrable_de%' "
                               "ORDER BY cree DESC LIMIT 3", (org,)):
                lignes.append(f"- livrable récent ({r['espace']}) : {json.loads(r['meta']).get('titre', '')[:110]}")
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — pas de contexte plutôt qu'une conversation bloquée
        pass
    try:
        from . import taches
        for t in taches.toutes()[-5:]:
            lignes.append(f"- tâche {t['projet']} {t['issue']} ({t.get('role', '')}, {t.get('modele') or t.get('agent', '')}) : "
                          f"{t.get('statut', '')}{' · verdict ' + t['verdict'] if t.get('verdict') else ''}")
    except Exception:  # noqa: BLE001
        pass
    if projet:
        lignes.insert(0, f"Discussion propre au projet : {projet}")
    return "\n".join(lignes)[:3000]


# --- lancer une prise de parole --------------------------------------------------------------------------------------

def _en_vol(org: str) -> int:
    from . import missions
    c = missions._connecter(org)
    try:
        return c.execute("SELECT COUNT(*) AS n FROM taches WHERE tenant_id=? AND type='converser' AND statut NOT IN "
                         "('SUCCEEDED','FAILED','CANCELLED','EXPIRED')", (org,)).fetchone()["n"]
    finally:
        c.close()


def _fil_recent(fil_id: str | None, projet: str) -> list[dict]:
    if not fil_id:
        return []
    from . import communaute, missions
    try:
        f = communaute.fil(projet, fil_id, limite=40, tenant_id=missions.tenant_local())
    except Exception:  # noqa: BLE001
        return []
    msgs = [f["fil"]] + [m for m in f["messages"] if m["id"] != f["fil"]["id"]]
    return [{"auteur": m["auteur"], "type": m["type"], "contenu": m["contenu"][:600]} for m in msgs[-8:]]


def lancer_tour(*, sujet: str, persona: dict, participants: list[dict], projet: str = "", salon: str = "general",
                fil_id: str | None = None, tour: int = 1, max_tours: int = TOURS_FIL, raison: str = "",
                now: float | None = None) -> str | None:
    """Une prise de parole d'un agent (mission L1 « converser »). Renvoie l'identifiant de mission, ou None si la
    vie sociale est coupée, en pause, saturée ou au plafond du jour."""
    from . import missions, pauses
    now = now or time.time()
    reglage = MODES.get(_mode_effectif())
    if reglage is None or pauses.active():
        return None
    org = missions.tenant_local()
    jour = time.strftime("%Y-%m-%d", time.localtime(now))
    etat = store.read_json(ETAT, {})
    tours = etat.get("tours", {}).get(jour, 0)
    if tours >= reglage["tours_jour"] or _en_vol(org) >= EN_VOL_MAX:
        return None
    c = missions._connecter(org)
    try:  # le fournisseur du rôle s'il est connecté sur ce poste, sinon le routeur choisit (aucune attente sans fin)
        connectes = {r["fournisseur"] for r in c.execute("SELECT fournisseur FROM connexions WHERE tenant_id=?", (org,))}
    finally:
        c.close()
    fournisseur = persona["fournisseur"] if persona["fournisseur"] in connectes else "auto"
    travail = {"persona": persona, "participants": [p["nom"] for p in participants], "sujet": sujet[:600],
               "projet": projet, "salon": salon, "fil_id": fil_id, "tour": tour, "max_tours": max_tours,
               "fil": _fil_recent(fil_id, projet), "contexte": contexte(projet), "raison": raison[:200]}
    cle = "converser:" + hashlib.sha256(f"{fil_id or sujet}|{tour}|{persona['nom']}|{jour}".encode()).hexdigest()[:20]
    m = missions.creer_mission(org, f"Conversation : {persona['titre']} — {sujet[:80]}",
                               [{"type": "converser", "niveau": "L1", "capacites": ["analyse"],
                                 "fournisseur": fournisseur, "travail": travail, "delai_s": 300}],
                               source="communaute", demandeur="vie_sociale", cle_idempotence=cle, now=now)

    def compter(e):
        e.setdefault("tours", {})
        e["tours"] = {jour: e["tours"].get(jour, 0) + 1}
    store.update_json(ETAT, {}, compter)
    return m["mission_id"]


def lancer_debat(sujet: str, *, projet: str = "", salon: str = "general", participants: int = 3,
                 now: float | None = None) -> dict:
    """Débat demandé (humain, chef ou événement) : 3 agents, 4 prises de parole."""
    sujet = " ".join(str(sujet or "").split())[:600]
    if len(sujet) < 5:
        raise ValueError("sujet de débat trop court")
    equipe = _choisir(participants, graine=f"{sujet}|{time.time() // 3600}")
    if len(equipe) < 2:
        raise ValueError("au moins deux rôles sont nécessaires pour débattre")
    mid = lancer_tour(sujet=sujet, persona=equipe[0], participants=equipe, projet=projet, salon=salon, tour=1, now=now)
    if mid is None:
        raise ValueError("vie sociale coupée, en pause ou au plafond du jour (réglage : " + _mode_effectif() + ")")
    _noter_fil(now)
    return {"mission_id": mid, "participants": [p["titre"] for p in equipe]}


def _noter_fil(now: float | None = None) -> None:
    now = now or time.time()
    jour = time.strftime("%Y-%m-%d", time.localtime(now))

    def maj(e):
        e["dernier_fil"] = now
        e["fils"] = {jour: (e.get("fils") or {}).get(jour, 0) + 1}
    store.update_json(ETAT, {}, maj)


def signaler(evenement: str, texte: str, *, projet: str = "") -> None:
    """Un fait réel (livrable prêt, mission réussie ou échouée…) devient un sujet : l'équipe en parle au prochain passage."""
    store.update_json(ETAT, {}, lambda e: e.__setitem__("sujets", ((e.get("sujets") or []) + [
        {"evenement": evenement, "texte": texte[:400], "projet": projet, "ts": time.time()}])[-10:]))


# --- résultat d'une prise de parole -----------------------------------------------------------------------------------

def lire_message(contenu: str) -> dict:
    """Message d'un agent : bloc JSON {type, titre, contenu} si présent, sinon le texte brut (discussion)."""
    m = re.search(r"\{.*\}", contenu, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and str(d.get("contenu") or "").strip():
                t = str(d.get("type") or "discussion").lower()
                return {"type": t if t in TYPES_SOCIAUX else "discussion", "titre": str(d.get("titre") or "")[:160],
                        "contenu": str(d["contenu"]).strip()[:4000]}
        except json.JSONDecodeError:
            pass
    return {"type": "discussion", "titre": "", "contenu": contenu.strip()[:4000]}


def apres_tour(tenant_id: str, travail: dict, contenu: str) -> None:
    """Publie la prise de parole dans le réseau, puis passe la parole au participant suivant du fil."""
    from . import communaute, missions
    if tenant_id != missions.tenant_local():
        return
    msg = lire_message(contenu)
    persona = travail["persona"]
    titre = msg["titre"] or travail["sujet"][:150]
    publie = communaute.publier(travail.get("projet", ""), msg["contenu"], auteur=f"agent:{persona['nom']}",
                                type=msg["type"], titre="" if travail.get("fil_id") else titre,
                                salon=travail.get("salon", "general"), parent_id=travail.get("fil_id"),
                                operation_id=f"converser:{travail.get('fil_id') or 'racine'}:{travail['tour']}:{persona['nom']}"[:150],
                                tenant_id=tenant_id)
    fil_id = travail.get("fil_id") or publie.get("fil_id") or publie["id"]
    if travail["tour"] >= travail.get("max_tours", TOURS_FIL):
        return
    noms = travail.get("participants") or []
    tous = {p["nom"]: p for p in personnages()}
    suivant = tous.get(noms[travail["tour"] % len(noms)]) if noms else None
    if suivant is None or suivant["nom"] == persona["nom"] and len(noms) > 1:
        suivant = tous.get(noms[(travail["tour"] + 1) % len(noms)]) if noms else None
    if suivant:
        lancer_tour(sujet=travail["sujet"], persona=suivant, participants=[tous[n] for n in noms if n in tous],
                    projet=travail.get("projet", ""), salon=travail.get("salon", "general"), fil_id=fil_id,
                    tour=travail["tour"] + 1, max_tours=travail.get("max_tours", TOURS_FIL))


# --- passage du démon ------------------------------------------------------------------------------------------------

def passage(now: float | None = None) -> str | None:
    """Toutes les 20 s : répondre à l'humain, parler des faits récents, ou ouvrir un sujet quand c'est le moment."""
    from . import communaute, missions
    now = now or time.time()
    reglage = MODES.get(_mode_effectif())
    if reglage is None or not missions.backend().existe():
        return None
    org = missions.tenant_local()
    etat = store.read_json(ETAT, {})
    # 1) l'humain (ou le chef) a écrit : un agent lui répond dans le fil
    curseur = etat.get("curseur")
    if curseur is None:  # première mise en route : on ne répond pas à l'historique
        lot = communaute.actualites(apres=0, limite=100, tenant_id=org)
        while lot.get("encore"):
            lot = communaute.actualites(apres=lot["suivant"], limite=100, tenant_id=org)
        store.update_json(ETAT, {}, lambda e: e.__setitem__("curseur", lot["suivant"]))
        return None
    lot = communaute.actualites(apres=curseur, limite=20, tenant_id=org)
    for m in lot["messages"]:
        if not str(m["auteur"]).startswith("agent:") and m["auteur"] != "systeme":
            equipe = _choisir(2, graine=m["id"])
            fil = m.get("fil_id") or m["id"]
            lancer_tour(sujet=m.get("titre") or m["contenu"][:200], persona=equipe[0], participants=equipe,
                        projet=m.get("projet", ""), salon=m.get("salon", "general"), fil_id=fil, tour=1, max_tours=2,
                        raison=f"réponse à {m['auteur']}", now=now)
    store.update_json(ETAT, {}, lambda e: e.__setitem__("curseur", lot["suivant"]))
    # 2) un fait réel attend ; 3) sinon un sujet ouvert, au rythme choisi
    jour = time.strftime("%Y-%m-%d", time.localtime(now))
    if (etat.get("fils") or {}).get(jour, 0) >= reglage["fils_jour"] or now - etat.get("dernier_fil", 0) < reglage["cadence_s"] / 3:
        return None
    sujets = etat.get("sujets") or []
    if sujets:
        s = sujets[0]
        store.update_json(ETAT, {}, lambda e: e.__setitem__("sujets", (e.get("sujets") or [])[1:]))
        sujet = {"livrable": f"Livrable terminé : {s['texte']} — qu'en pensez-vous ? Bravo, critiques, améliorations ?",
                 }.get(s["evenement"], s["texte"])
        try:
            lancer_debat(sujet, projet=s.get("projet", ""), salon="atelier", now=now)
            return sujet
        except ValueError:
            return None
    if now - etat.get("dernier_fil", 0) < reglage["cadence_s"]:
        return None
    sujet = random.Random(int(now // 3600)).choice(SUJETS_OUVERTS)
    try:
        lancer_debat(sujet, salon="general", now=now)
        return sujet
    except ValueError:
        return None


def verifier(now: float | None = None) -> None:
    try:
        passage(now)
    except Exception as exc:  # noqa: BLE001 — la vie sociale ne doit jamais gêner le démon
        store.feed_add("erreur", f"vie sociale des agents : {exc}")
