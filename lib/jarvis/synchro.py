"""Synchronisation des quatre parties de Jarvis : le Board, Telegram, le chef et la mémoire collective.

Un seul fil d'information, dans les deux sens :
- Board → Telegram : chaque élément contextualisé et chaque livrable arrive sur ton Telegram, avec des boutons
  « Lancer » / « Écarter » pour les actions proposées (mêmes règles que le panneau : une action lancée crée une
  mission L1 de préparation, rien d'externe).
- Telegram → Board : un lien, un fichier ou un message « #projet … » envoyé au chef est aussi déposé sur le Board du
  projet, où il est contextualisé ; une conversation ordinaire reste une conversation avec le chef.
- Board ↔ chef : le chef est prévenu de ce qui arrive sur le Board, et le lit ou l'alimente avec `jarvis board`.
- Mémoire collective : analyses, livrables et décisions du Board sont notés dans la mémoire du chef
  (memoire.jsonl, la même que `jarvis memoire`), et chaque analyse du Board part avec ce que cette mémoire sait
  déjà du sujet. Ce qui vient de la mémoire est une DONNÉE de contexte, jamais une consigne.

Toutes ces fonctions sont des effets APRÈS coup : une erreur (Telegram injoignable, chef arrêté) est notée dans le
fil d'activité et n'annule jamais ce que le moteur a enregistré.
"""

from __future__ import annotations

import json
import queue
import shutil
import re
import threading

from . import config, store

NATURES = {"inspire": "inspire", "alimente": "alimente", "utilise": "utilise", "depend": "dépend de"}
URL = re.compile(r"https?://\S+")
PROJET = re.compile(r"^#([\w.-]{1,40})\s*", re.U)
MEMOIRE_PROMPT = 5


def _reglage(nom: str, defaut: bool = True) -> bool:
    try:
        return bool(config.settings().get("board", {}).get(nom, defaut))
    except Exception:  # noqa: BLE001 — réglages illisibles : comportement par défaut
        return defaut


def _local(tenant_id: str) -> bool:
    """La mémoire et Telegram sont ceux de CE poste : seul le tenant local y écrit (aucune fuite entre tenants)."""
    from . import missions
    return tenant_id == missions.tenant_local()


def _effet(nom: str, f, *args, **kw):
    try:
        return f(*args, **kw)
    except Exception as exc:  # noqa: BLE001 — un effet de synchronisation ne casse jamais le moteur
        try:
            store.feed_add("erreur", f"synchro {nom} : {exc}")
        except Exception:  # noqa: BLE001
            pass
        return None


def _objet(tenant_id: str, objet_id: str) -> dict | None:
    from . import missions
    c = missions._connecter(tenant_id)
    try:
        o = c.execute("SELECT * FROM board_objets WHERE id=? AND tenant_id=?", (objet_id, tenant_id)).fetchone()
        return {**dict(o), "meta": json.loads(o["meta"] or "{}")} if o else None
    finally:
        c.close()


def _titre(o: dict) -> str:
    return str(o["meta"].get("titre") or (o["contenu"] or o["type"]).split("\n")[0])[:120]


def _nom_espace(espace: str) -> str:
    return "Accueil" if espace == "accueil" else espace


# --- mémoire collective -------------------------------------------------------------------------------------

def memoire_pour(tenant_id: str, requete: str, espace: str) -> list[str]:
    """Ce que la mémoire collective sait déjà du sujet (projet du Board d'abord), en lignes courtes."""
    if not _local(tenant_id):
        return []
    from . import memoire
    projet = "" if espace == "accueil" else espace
    sortie = []
    for r in memoire.chercher(requete, projet=projet, limite=MEMOIRE_PROMPT):
        e = r["entree"]
        details = "; ".join((e.get("decisions") or []) + (e.get("lecons") or []))[:240] or str(e.get("corps") or "")[:240]
        sortie.append(f"{e['id']} {e['titre'][:120]} — {details}")
    return sortie


def _noter(tenant_id: str, **entree) -> None:
    if _local(tenant_id):
        from . import memoire
        memoire.noter(source="board", **entree)


# --- Telegram ---------------------------------------------------------------------------------------------------

def boutons(objet_id: str, propositions: list[dict]) -> list[list[tuple[str, str]]]:
    """Une ligne par action encore proposée : « ▶ Lancer n » / « ✕ n ». Données courtes (64 octets max)."""
    lignes = []
    for i, p in enumerate(propositions[:5]):
        if p.get("statut") == "proposee":
            lignes.append([(f"▶ {i + 1}. {'Lancer' if p['niveau'] == 'L1' else 'Préparer'}", f"bpl:{objet_id}:{i}"),
                           (f"✕ {i + 1}", f"bpe:{objet_id}:{i}")])
    return lignes


_file: "queue.Queue | None" = None
_verrou = threading.Lock()


def _en_fond(nom: str, f, *args) -> None:
    """Telegram et le chef passent par le réseau ou tmux : un envoi lent (réseau coupé, nouvelles tentatives) ne doit
    jamais retenir l'exécutant de missions. Une seule file, un seul fil, dans l'ordre d'arrivée."""
    global _file
    with _verrou:
        if _file is None:
            _file = queue.Queue(maxsize=200)

            def vider():
                while True:
                    n, g, a = _file.get()
                    _effet(n, g, *a)

            threading.Thread(target=vider, name="synchro", daemon=True).start()
    try:
        _file.put_nowait((nom, f, args))
    except queue.Full:  # file saturée (Telegram injoignable depuis longtemps) : on perd la notification, pas le travail
        _effet(nom, lambda: (_ for _ in ()).throw(RuntimeError("file de notifications pleine")))


def _envoyer_telegram(texte: str, boutons_=None) -> None:
    from . import notify
    notify.telegram(texte[:3900], boutons_ or None)


def _telegram(texte: str, boutons_=None) -> None:
    if _reglage("telegram"):
        _en_fond("telegram", _envoyer_telegram, texte, boutons_)


def _chef(texte: str) -> None:
    if _reglage("chef"):
        from . import agents
        _en_fond("chef", agents.chef_inject, texte)


def texte_analyse(o: dict) -> str:
    m = o["meta"]
    lignes = [f"🧠 Jarvis · Board {_nom_espace(o['espace'])}", f"« {_titre(o)} »"]
    if m.get("jarvis_resume"):
        lignes += ["", m["jarvis_resume"]]
    props = m.get("propositions") or []
    if props:
        lignes += ["", "Actions :"]
        for i, p in enumerate(props[:5]):
            etat = {"lancee": " — ▶ lancée" + (" par Jarvis" if str(p.get("par", "")).startswith("jarvis") else ""),
                    "ecartee": " — écartée"}.get(p.get("statut"), "")
            lignes.append(f"{i + 1}. [{p['niveau']}] {p['titre']}{etat}")
    return "\n".join(lignes)


# --- effets appelés par le moteur ---------------------------------------------------------------------------------

def apres_contextualisation(tenant_id: str, objet_id: str, liens: int = 0) -> None:
    o = _objet(tenant_id, objet_id)
    if o is None or o["supprime"]:
        return
    m, titre = o["meta"], _titre(o)
    props = m.get("propositions") or []
    _effet("mémoire", _noter, tenant_id, titre=f"Board {_nom_espace(o['espace'])} : {titre}",
           corps=str(m.get("jarvis_resume") or ""), decisions=[f"Lancé par Jarvis : {p['titre']}" for p in props
                                                               if str(p.get("par", "")).startswith("jarvis")],
           projet="" if o["espace"] == "accueil" else o["espace"], etiquettes=["board", o["type"]])
    if not _local(tenant_id):
        return
    texte = texte_analyse(o) + (f"\n\n🔗 {liens} lien(s) tracé(s) vers d'autres cartes du projet." if liens else "")
    _effet("telegram", _telegram, texte, boutons(objet_id, props))
    if o["auteur"] != "chef":  # le chef sait déjà ce qu'il a déposé lui-même
        lance = next((p["titre"] for p in props if p.get("statut") == "lancee"), "")
        _effet("chef", _chef, f"[BOARD {_nom_espace(o['espace'])}] « {titre} » analysé par Jarvis : "
               f"{str(m.get('jarvis_resume') or '')[:220]} — {len(props)} action(s) proposée(s)"
               + (f", lancée seule : {lance}" if lance else "")
               + f". Détails : jarvis board voir --espace {o['espace']}")


def apres_livrable(tenant_id: str, objet_id: str) -> None:
    o = _objet(tenant_id, objet_id)
    if o is None:
        return
    titre = _titre(o).removeprefix("Livrable — ")
    _effet("mémoire", _noter, tenant_id, titre=f"Livrable : {titre}", corps=o["contenu"][:1500],
           projet="" if o["espace"] == "accueil" else o["espace"], etiquettes=["board", "livrable"])
    if not _local(tenant_id):
        return
    extrait = o["contenu"].replace("[FACTICE — aucune IA n'a produit ce texte]", "").strip()[:700]
    _effet("telegram", _telegram, f"✅ Livrable prêt · Board {_nom_espace(o['espace'])}\n« {titre} »\n\n{extrait}"
           + ("…" if len(o["contenu"]) > 700 else "") + "\n\nLa carte est sur le Board, reliée à sa mission.")
    _effet("chef", _chef, f"[BOARD {_nom_espace(o['espace'])}] Livrable prêt : « {titre} » (carte {objet_id}). "
           f"Lis-le avec : jarvis board voir --espace {o['espace']}")


def apres_decision(tenant_id: str, objet_id: str, index: int, decision: str, par: str) -> None:
    o = _objet(tenant_id, objet_id)
    if o is None or par == "jarvis:auto":
        return
    p = (o["meta"].get("propositions") or [{}] * (index + 1))[index]
    verbe = "Lancé" if decision == "lancer" else "Écarté"
    _effet("mémoire", _noter, tenant_id, titre=f"Board {_nom_espace(o['espace'])} : {verbe.lower()} « {p.get('titre', '?')} »",
           decisions=[f"{verbe} par {par} : {p.get('titre', '?')} (élément « {_titre(o)} »)"],
           projet="" if o["espace"] == "accueil" else o["espace"], etiquettes=["board", "decision"])
    if _local(tenant_id) and par != "chef":
        _effet("chef", _chef, f"[BOARD {_nom_espace(o['espace'])}] Ton humain a {verbe.lower()} « {p.get('titre', '?')} » "
               f"pour « {_titre(o)} » ({par}).")


# --- Telegram → Board ----------------------------------------------------------------------------------------------

def titre_court(texte: str, n: int = 70) -> str:
    """Première ligne, coupée sur un mot (jamais au milieu) avec « … »."""
    ligne = (texte or "").strip().split("\n")[0].strip()
    if len(ligne) <= n:
        return ligne
    coupe = ligne[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (coupe or ligne[:n]) + "…"


def espace_du_message(texte: str) -> tuple[str, str]:
    """« #repriceo texte » → ("repriceo", "texte") si ce Board ou ce projet existe ; sinon ("accueil", texte)."""
    from . import board, missions
    m = PROJET.match(texte or "")
    if m:
        nom = board.nom_espace(m.group(1))
        connus = {e["nom"].lower(): e["nom"] for e in board.espaces(missions.tenant_local())}
        if nom.lower() in connus:
            return connus[nom.lower()], texte[m.end():].strip()
    return "accueil", (texte or "").strip()


def position_libre(tenant_id: str, espace: str, l: float = 434, h: float = 356) -> tuple[float, float]:
    """À droite de ce qui existe déjà, sans recouvrir aucune carte."""
    from . import missions
    c = missions._connecter(tenant_id)
    try:
        r = c.execute("SELECT MAX(x + largeur) AS d, MIN(y) AS h FROM board_objets WHERE tenant_id=? AND espace=? "
                      "AND supprime=0 AND parent_id IS NULL", (tenant_id, espace)).fetchone()
        x0, y0 = ((r["d"] or 0) + 120, r["h"] or 0) if r and r["d"] is not None else (0.0, 0.0)
        return missions.place_libre(c, tenant_id, espace, x0, y0, l, h)
    finally:
        c.close()


def depuis_telegram(texte: str, fichier=None, nom: str = "") -> dict | None:
    """Dépose sur le Board ce qui y a sa place : un fichier, un lien, ou un message adressé à un projet (#projet).
    Renvoie {"objet_id", "espace"} ou None (simple conversation avec le chef)."""
    from . import board, missions
    org = missions.tenant_local()
    espace, reste = espace_du_message(texte)
    adresse = PROJET.match(texte or "") is not None and espace != "accueil"
    meta = {"source": "telegram"}
    if fichier is not None:
        # enregistrer_fichier CONSOMME sa source : le Board reçoit une copie, le chef garde l'original dans sa boîte
        copie = board.fichier_temporaire()
        try:
            shutil.copyfile(fichier, copie)
            a = board.enregistrer_fichier(org, copie, nom or fichier.name, auteur="telegram")
        except (missions.MissionError, OSError, ValueError):
            copie.unlink(missing_ok=True)
            return None  # format non pris en charge par le Board : le chef garde le fichier
        x, y = position_libre(org, espace)
        meta["titre"] = (reste or nom or a["nom"])[:80]
        o = missions.board_ajouter(org, espace, a["famille"] or "document", "", auteur="telegram", x=x, y=y,
                                   asset_id=a["id"], meta=meta, analyser=False, contextualiser=True)
        return {"objet_id": o["objet_id"], "espace": espace}
    url = URL.search(reste or "")
    if not url and not adresse:
        return None
    x, y = position_libre(org, espace)
    if url and reste.strip() == url.group(0):
        meta.update(url=url.group(0), titre=url.group(0).split("/")[2][:80])
        o = missions.board_ajouter(org, espace, "lien", url.group(0), auteur="telegram", x=x, y=y, largeur=434,
                                   hauteur=356, meta=meta, analyser=False, contextualiser=True)
    else:
        meta["titre"] = titre_court(reste) or "Message Telegram"
        o = missions.board_ajouter(org, espace, "note", reste[:50_000] or texte, auteur="telegram", x=x, y=y,
                                   largeur=408, hauteur=320, meta=meta, analyser=False, contextualiser=True)
    return {"objet_id": o["objet_id"], "espace": espace}


def decider_depuis_telegram(donnees: str, lancer: bool) -> str:
    """Bouton d'une notification : « BO-…:index ». Même règle que le panneau du Board."""
    from . import missions
    oid, _, i = donnees.partition(":")
    try:
        r = missions.decider_proposition(missions.tenant_local(), oid, int(i), "lancer" if lancer else "ecarter",
                                         par="telegram:humain")
    except (missions.MissionError, ValueError) as exc:
        return f"⚠ {exc}"
    return "▶ Lancée : mission de préparation créée sur le Board" if r.get("mission_id") else "✕ Écartée"


# --- lecture (Telegram /etat et /board, `jarvis etat`, `jarvis board voir`) ------------------------------------------

EN_COURS = ("LEASED", "RUNNING", "REVIEW")
ATTENTES = {"QUEUED": "en file", "RETRY_SCHEDULED": "nouvel essai prévu", "WAITING_PROVIDER": "fournisseur indisponible",
            "WAITING_APPROVAL": "attend ton accord"}


def _duree(s: float) -> str:
    s = max(0, int(s))
    return f"{s} s" if s < 60 else f"{s // 60} min" if s < 3600 else f"{s // 3600} h {s % 3600 // 60:02d}"


def texte_missions(tenant_id: str, now: float | None = None) -> str:
    """Missions du Board (moteur de missions) : ce qui s'exécute, depuis quand, avec quel fournisseur, et la file.
    Distinct des agents de code (workmux) que le chef lance sur tes projets."""
    import time
    from . import missions
    if not missions.backend().existe():
        return ""
    now = now or time.time()
    c = missions._connecter(tenant_id)
    try:
        cours = c.execute("SELECT t.type, t.fournisseur_choisi AS f, m.objectif, a.debut FROM taches t "
                          "JOIN missions m ON m.id=t.mission_id LEFT JOIN tentatives a ON a.id=t.tentative_id "
                          f"WHERE t.tenant_id=? AND t.statut IN ({','.join('?' * len(EN_COURS))}) ORDER BY a.debut",
                          (tenant_id, *EN_COURS)).fetchall()
        file = {r["statut"]: r["n"] for r in c.execute(
            "SELECT statut, COUNT(*) AS n FROM taches WHERE tenant_id=? GROUP BY statut", (tenant_id,))}
        signe = c.execute("SELECT MAX(dernier_signe) AS s FROM executants WHERE tenant_id=? AND revoque=0",
                          (tenant_id,)).fetchone()["s"]
    finally:
        c.close()
    attentes = [f"{file[k]} {v}" for k, v in ATTENTES.items() if file.get(k)]
    if not cours and not attentes:
        return "MISSIONS DU BOARD : rien en cours."
    vivant = signe and now - signe < 180
    lignes = [f"MISSIONS DU BOARD : {len(cours)} en cours" + (f", {', '.join(attentes)}" if attentes else "")
              + ("" if vivant else f" · ⚠ aucun exécutant actif{' depuis ' + _duree(now - signe) if signe else ''}"
                 " (démon arrêté ? jarvis start)")]
    for r in cours:
        lignes.append(f"  ▶ {r['objectif'][:70]} — {r['f'] or '?'}, depuis {_duree(now - (r['debut'] or now))}")
    return "\n".join(lignes)


# --- lecture (Telegram /board, `jarvis board voir`) ------------------------------------------------------------------

def texte_board(tenant_id: str, espace: str, *, detail: bool = False) -> str:
    from . import board
    etat = board.objets(tenant_id, espace)
    objs = [o for o in etat["objets"] if not o.get("parent_id")]
    if not objs:
        return f"Board {_nom_espace(espace)} : vide."
    par_id = {o["id"]: o for o in objs}
    lignes = [f"Board {_nom_espace(espace)} : {len(objs)} carte(s)"]
    for o in objs:
        m = o["meta"]
        titre = _titre(o) if o["type"] != "mission" else (o.get("mission") or {}).get("objectif", "mission")[:120]
        statut = (o.get("mission") or {}).get("statut", "") if o["type"] == "mission" else ""
        origine = f" (via {m['source']})" if m.get("source") else ""
        lignes.append(f"- {o['id']} [{o['type']}{(' ' + statut) if statut else ''}] {titre}{origine}")
        if detail and o["type"] in ("note", "texte", "lien") and not m.get("livrable_de") and o["contenu"]:
            lignes.append("    contenu : " + o["contenu"][:400].replace("\n", " "))
        if m.get("jarvis_resume"):
            lignes.append(f"    résumé : {m['jarvis_resume'][:300 if detail else 140]}")
        for i, p in enumerate(m.get("propositions") or []):
            if detail or p.get("statut") == "proposee":
                lignes.append(f"    action {i + 1} [{p['niveau']}] {p['titre'][:110]} — {p['statut']}")
        if detail and m.get("livrable_de"):
            lignes.append("    livrable : " + o["contenu"][:600].replace("\n", " "))
    liens = [l for l in etat["liens"] if l["source_id"] in par_id and l["cible_id"] in par_id]
    if liens and detail:
        lignes.append("Relations :")
        for l in liens:
            lignes.append(f"- {_titre(par_id[l['source_id']])[:50]} —{l['libelle'] or l['style']}→ "
                          f"{_titre(par_id[l['cible_id']])[:50]}{' (Jarvis)' if l.get('auteur') == 'jarvis' else ''}")
    return "\n".join(lignes)
