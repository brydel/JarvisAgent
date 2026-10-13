"""Démon Jarvis : surveille les agents, prévient le chef et fait le pont avec Telegram."""

from __future__ import annotations

import threading
import time

from . import agents as ag
from . import config, notify, plans, report, store
from .telegram import Bot, TelegramError

WATCH_STATE = "watch.json"
TG_STATE = "telegram.json"

AIDE = (
    "Commandes Jarvis :\n"
    "/etat — état des agents et des plans\n"
    "/plans — plans à valider (avec boutons)\n"
    "/jetons — consommation Claude et Codex (5 h et semaine)\n"
    "/sante — état du PC (mémoire, disque, Docker, batterie)\n"
    "/pause — bloque tout nouveau lancement\n"
    "/reprendre — lève la pause\n"
    "/aide — cette aide\n\n"
    "Tout autre message est transmis directement au chef d'orchestre. "
    "Tu peux aussi lui envoyer une image (maquette, direction artistique) ou un fichier, avec une légende."
)


# --- Surveillance des agents -------------------------------------------------

def watch_once(first: bool = False) -> list[dict]:
    """Compare l'état courant au précédent et réagit aux changements. Renvoie les événements."""
    agents, err = ag.status_all()
    if agents is None:
        return []  # observation impossible : on ne conclut rien (fail closed)
    from . import poste
    poste.save_snapshot(agents)  # sert à reprendre les agents après un redémarrage du PC
    prev = store.read_json(WATCH_STATE, {})
    cur = {f"{a['project']}:{a['worktree']}": a for a in agents}
    events = []
    if not first:
        for key, a in cur.items():
            old = prev.get(key, {}).get("status")
            if old == a["status"]:
                continue
            label = f"{a['project']}/{a['worktree']} ({ag.kind_label(a['kind'])})"
            if a["status"] == "done":
                events.append(("agent_done", f"{label} a terminé", a))
            elif a["status"] == "waiting":
                events.append(("agent_waiting", f"{label} attend une réponse", a))
            elif a["status"] == "working" and old is None:
                events.append(("agent_working", f"{label} a démarré", a))
        for key in prev.keys() - cur.keys():
            events.append(("agent_gone", f"{key.replace(':', '/')} n'est plus suivi", None))

    chef_up = ag.chef_running()
    for kind, msg, a in events:
        store.feed_add(kind, msg, agent=(ag.target(a) if a else None))
        if kind in ("agent_done", "agent_waiting") and a:
            injected = chef_up and ag.chef_inject(
                f"[JARVIS événement] {msg}. Cible workmux : {ag.target(a)}. "
                "Lis sa sortie (jarvis voir) et son issue Linear, puis décide de la suite.")
            if not injected and kind == "agent_waiting":
                # Personne pour lui répondre : on prévient l'humain directement.
                notify.alert("question", f"{msg} et le chef n'est pas lancé", windows=True)
    store.write_json(WATCH_STATE, {k: {"status": a["status"]} for k, a in cur.items()})
    return [{"type": k, "texte": m} for k, m, _ in events]


BUDGET_STATE = "budget.json"
VEILLE_STATE = "veille.json"
STOP_MSG = ("[JARVIS] La limite de jetons de ton abonnement est presque atteinte. Termine l'étape en cours, "
            "committe ton travail (préfixe WIP si c'est inachevé), pousse ta branche, commente l'état dans "
            "l'issue Linear (❓ ou ✅), puis arrête-toi : n'entame rien d'autre.")


def _pct(u: dict) -> str:
    parts = [f"{k} {u[k]['used']:.0f} %" for k in ("5h", "semaine") if u.get(k)]
    return ", ".join(parts) or "?"


def budget_check() -> list[str]:
    """Réagit aux changements de niveau de jetons (alerte, épuisé, rétabli). Renvoie les événements."""
    from . import usage
    s = usage.summary()
    st = store.read_json(BUDGET_STATE, {"niveaux": {}, "pause_budget": False})
    cfg = config.settings()["jetons"]
    events = []
    agents_now, _ = ag.status_all()
    for p in usage.PROVIDERS:
        u, lvl = s[p], s[p]["niveau"]
        old = st["niveaux"].get(p, "inconnu")
        st["niveaux"][p] = lvl
        if lvl == old or lvl == "inconnu":
            continue
        name = p.capitalize()
        if lvl == "alerte" and old in ("ok", "inconnu"):
            events.append(f"{name} alerte")
            notify.alert("question", f"Jetons {name} à {_pct(u)} : passe en mode économe.", title="JARVIS · jetons")
            ag.chef_inject(f"[JARVIS jetons] {name} a dépassé le seuil d'alerte ({_pct(u)}). "
                           f"Privilégie l'autre agent pour les prochaines tâches et allège les vagues.")
        elif lvl == "epuise":
            events.append(f"{name} épuisé")
            reprise = usage.fmt_reset(u.get("reprise")) or "la remise à zéro"
            notify.alert("erreur", f"Jetons {name} épuisés ({_pct(u)}) jusqu'à {reprise}. "
                                   f"Ses agents committent leur travail et s'arrêtent.", title="JARVIS · jetons")
            ag.chef_inject(f"[JARVIS jetons] {name} ÉPUISÉ jusqu'à {reprise} : ne lui assigne plus aucune tâche "
                           f"(jarvis task la refusera). Ses agents en cours ont reçu l'ordre de committer et de s'arrêter.")
            if cfg.get("arret_agents", True):
                for a in agents_now or []:
                    if a["status"] in ("working", "untracked") and p in (a["kind"] or "").lower():
                        ok, _ = ag.send(ag.target(a), STOP_MSG)
                        store.feed_add("systeme", f"arrêt demandé à {a['project']}/{a['worktree']} (jetons {name})")
        elif old == "epuise":
            events.append(f"{name} rétabli")
            notify.alert("plan_ok", f"Jetons {name} rétablis ({_pct(u)}) : il peut reprendre du travail.",
                         title="JARVIS · jetons")
            ag.chef_inject(f"[JARVIS jetons] {name} est de nouveau disponible ({_pct(u)}).")

    both_out = all(s[p]["niveau"] == "epuise" for p in usage.PROVIDERS)
    if both_out and cfg.get("pause_auto", True) and not store.paused():
        store.set_paused(True)
        st["pause_budget"] = True
        events.append("pause auto")
        notify.alert("systeme", "Pause automatique : Claude et Codex sont épuisés. Reprise dès qu'un abonnement "
                                "se libère.", title="JARVIS · jetons")
    elif st.get("pause_budget") and not both_out:
        st["pause_budget"] = False
        if store.paused():
            store.set_paused(False)
            events.append("reprise auto")
            notify.alert("plan_ok", "Fin de la pause automatique : un abonnement a des jetons.", title="JARVIS · jetons")
            ag.chef_inject("[JARVIS jetons] Pause automatique levée : reprends ta boucle en tenant compte des marges "
                           "(jarvis jetons).")
    store.write_json(BUDGET_STATE, st)
    return events


def veille_check(now: float | None = None) -> str | None:
    """Rappelle au chef la veille concurrentielle d'un projet quand elle est due. Renvoie le projet."""
    days = int(config.settings()["veille"].get("jours", 7))
    if days <= 0 or not ag.chef_running():
        return None
    now = now or time.time()
    st = store.read_json(VEILLE_STATE, {"fait": {}, "dernier_rappel": 0})
    if now - st.get("dernier_rappel", 0) < 6 * 3600:
        return None  # au plus un rappel toutes les 6 h
    from . import usage
    if usage.summary()["claude"]["niveau"] == "epuise":
        return None  # le chef lui-même consomme des jetons Claude
    projs = sorted(config.projects().items(), key=lambda kv: (kv[1]["priorite"], kv[0]))
    for name, p in projs:
        if not p["actif"]:
            continue
        last = st["fait"].get(name, 0)
        if now - last < days * 86400:
            continue
        ago = "jamais faite" if not last else f"dernière il y a {int((now - last) // 86400)} j"
        ag.chef_inject(f"[JARVIS veille] Veille concurrentielle due pour « {name} » ({ago}). Quand ta boucle le "
                       f"permet et si la marge Claude dépasse 30 %, applique la procédure « Veille concurrentielle » "
                       f"de ton rôle, puis lance « jarvis veille fait {name} ».")
        st["dernier_rappel"] = now
        store.write_json(VEILLE_STATE, st)
        store.feed_add("chef", f"veille concurrentielle demandée pour {name}")
        return name
    return None


BATTEMENT_STATE = "battement.json"
BATTEMENT_MAX = 4 * 3600  # sans résultat, l'intervalle double jusqu'à 4 h (économie de jetons)


def battement_check(now: float | None = None) -> bool:
    """Réveille le chef quand tout est calme alors qu'il reste de la place et des jetons.

    Sans battement, le chef ne se réveille que sur un événement : une nuit peut rester vide
    alors que les abonnements ont de la marge. Renvoie True si le chef a été réveillé.
    """
    base = int(config.settings()["general"].get("battement_min", 30)) * 60
    if base <= 0 or store.paused() or not ag.chef_running():
        return False
    now = now or time.time()
    st = store.read_json(BATTEMENT_STATE, {"dernier": 0, "intervalle": base, "plans": 0})
    nb_plans = len(plans.all_plans())
    if nb_plans != st.get("plans"):
        st.update(intervalle=base, plans=nb_plans)  # le chef a proposé quelque chose : rythme normal
    interval = max(base, min(int(st.get("intervalle", base)), BATTEMENT_MAX))
    idle = ag.chef_idle_secs()
    if idle is None or idle < base or now - st.get("dernier", 0) < interval:
        store.write_json(BATTEMENT_STATE, st)
        return False
    if plans.pending() or store.read_json(ag.CHEF_QUEUE, []) or ag.chef_has_dialog():
        store.write_json(BATTEMENT_STATE, st)
        return False  # il attend ton humain, ou un message est déjà en route
    found, _ = ag.status_all()
    if found is None:
        return False
    busy = sum(1 for a in found if a["status"] in ag.BUSY)
    limit = int(config.settings()["general"].get("max_agents", 3))
    from . import usage
    s = usage.summary()
    if busy >= limit or s["claude"]["niveau"] == "epuise" or \
            all(s[p]["niveau"] == "epuise" for p in usage.PROVIDERS):
        store.write_json(BATTEMENT_STATE, st)
        return False
    ag.chef_inject(
        f"[JARVIS battement] Calme depuis {idle // 60} min : {busy}/{limit} agents occupés, jetons Claude "
        f"{_pct(s['claude'])}, Codex {_pct(s['codex'])}. S'il existe du travail utile et prioritaire (corrections "
        f"de PR, revues, backlog Linear des projets actifs), propose un plan. Sinon, termine ton tour en une ligne "
        f"sans rien lancer.")
    store.feed_add("chef", f"battement : chef réveillé ({busy}/{limit} agents occupés)")
    st.update(dernier=now, intervalle=min(interval * 2, BATTEMENT_MAX), plans=nb_plans)
    store.write_json(BATTEMENT_STATE, st)
    return True


def menage_check() -> list[str]:
    """Ferme les fenêtres des agents terminés depuis longtemps (worktree et branche restent)."""
    minutes = int(config.settings()["general"].get("fermeture_auto_min", 60))
    if minutes <= 0:
        return []
    found, _ = ag.status_all()
    closed = []
    for a in found or []:
        if a["status"] in ag.CLOSABLE and a["elapsed"] >= minutes * 60:
            ok, _msg = ag.close(a)
            if ok:
                closed.append(ag.target(a))
                store.feed_add("systeme", f"fenêtre de {a['project']}/{a['worktree']} fermée (terminé depuis "
                                          f"{ag.fmt_elapsed(a['elapsed'])}, worktree conservé)")
    return closed


SANTE_STATE = "sante.json"
SANTE_PERIODE = 5 * 60


def sante_check(now: float | None = None) -> list[str]:
    """Surveille le PC et prévient l'humain quand un indicateur se dégrade ou se rétablit."""
    if not config.settings()["sante"].get("active", True):
        return []
    now = now or time.time()
    st = store.read_json(SANTE_STATE, {"ts": 0, "niveaux": {}})
    if now - st.get("ts", 0) < SANTE_PERIODE:
        return []
    from . import poste
    events = []
    for item in poste.checks(now):
        old = st["niveaux"].get(item["cle"], "ok")
        st["niveaux"][item["cle"]] = item["niveau"]
        if item["niveau"] == old:
            continue
        if item["niveau"] == "ok":
            store.feed_add("systeme", f"poste : {item['texte']}")
            continue
        events.append(item["cle"])
        kind = "erreur" if item["niveau"] == "critique" else "question"
        notify.alert(kind, item["texte"], title="JARVIS · santé du PC")
        if item["cle"] in ("docker", "disque"):
            ag.chef_inject(f"[JARVIS santé] {item['texte']}. Tiens-en compte pour les tâches à lancer.")
    st["ts"] = now
    store.write_json(SANTE_STATE, st)
    return events


def watch_loop(stop: threading.Event) -> None:
    first = True
    while not stop.is_set():
        for step in (lambda: watch_once(first=first), ag.chef_flush_queue, budget_check, veille_check,
                     menage_check, battement_check):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 — le démon ne doit jamais mourir sur une erreur ponctuelle
                store.feed_add("erreur", f"surveillance : {exc}")
        first = False
        stop.wait(int(config.settings()["general"].get("poll_seconds", 20)))


def sante_loop(stop: threading.Event) -> None:
    """Fil séparé : PowerShell et Docker peuvent mettre des secondes à répondre."""
    while not stop.is_set():
        try:
            sante_check()
        except Exception as exc:  # noqa: BLE001
            store.feed_add("erreur", f"santé du poste : {exc}")
        stop.wait(60)


# --- Pont Telegram -----------------------------------------------------------

def handle_update(bot: Bot, chat_id: str, upd: dict) -> None:
    owner = str(chat_id)

    cb = upd.get("callback_query")
    if cb:
        from_chat = str(cb.get("message", {}).get("chat", {}).get("id", ""))
        # Conversation privée appairée : l'expéditeur doit être la même personne que la conversation.
        if from_chat != owner or str(cb.get("from", {}).get("id", owner)) != owner:
            bot.answer(cb["id"], "Accès refusé")
            return
        action, _, plan_id = (cb.get("data") or "").partition(":")
        try:
            plan = plans.decide(plan_id, action == "ok", par="Telegram")
            verdict = "✅ Approuvé" if plan["statut"] == "approuve" else "✋ Refusé"
            bot.answer(cb["id"], verdict)
            msg = cb.get("message", {})
            if msg.get("message_id"):
                bot.edit(owner, msg["message_id"], f"{msg.get('text', '')}\n\n{verdict}")
        except plans.PlanError as exc:
            bot.answer(cb["id"], str(exc))
        return

    msg = upd.get("message") or {}
    text = (msg.get("text") or msg.get("caption") or "").strip()
    fichier = _piece_jointe(msg)
    if not text and not fichier:
        return
    if str(msg.get("chat", {}).get("id", "")) != owner or str(msg.get("from", {}).get("id", owner)) != owner:
        bot.send(msg["chat"]["id"], "⛔ Ce Jarvis est privé.")
        return
    if fichier:
        _transmettre_fichier(bot, owner, fichier, text)
        return

    cmd = text.split()[0].split("@")[0].lower()
    if cmd in ("/start", "/aide", "/help"):
        bot.send(owner, AIDE)
    elif cmd in ("/etat", "/status"):
        bot.send(owner, report.text(detail=False))
    elif cmd in ("/jetons", "/tokens"):
        from . import usage
        bot.send(owner, "Jetons\n\n" + usage.text())
    elif cmd in ("/sante", "/santé"):
        from . import poste
        bot.send(owner, "Santé du PC\n\n" + poste.texte())
    elif cmd == "/plans":
        pend = plans.pending()
        if not pend:
            bot.send(owner, "Aucun plan à valider.")
        for p in pend:
            bot.send(owner, plans.format_plan(p), notify.plan_buttons(p["id"]))
    elif cmd == "/pause":
        store.set_paused(True)
        store.feed_add("systeme", "pause activée depuis Telegram")
        ag.chef_inject("[JARVIS] Ton humain a mis Jarvis en PAUSE : ne lance plus aucune tâche jusqu'à nouvel ordre.")
        bot.send(owner, "⏸ Pause activée : plus aucun nouveau lancement.")
    elif cmd == "/reprendre":
        store.set_paused(False)
        store.feed_add("systeme", "pause levée depuis Telegram")
        ag.chef_inject("[JARVIS] Pause levée par ton humain : tu peux reprendre ta boucle.")
        bot.send(owner, "▶ C'est reparti.")
    else:
        store.feed_add("toi", f"(Telegram) {text}")
        if ag.chef_inject(f"[Message de ton humain via Telegram] {text}"):
            bot.send(owner, "✔ Transmis au chef.")
        else:
            bot.send(owner, "⚠ Le chef n'est pas lancé. Sur ton PC : jarvis chef")


BOITE = "boite"  # dossier des fichiers reçus, dans le dossier de travail du chef
MAX_FICHIER = 20 * 1024 * 1024  # limite de téléchargement de l'API Bot


def _piece_jointe(msg: dict) -> dict | None:
    """Photo (la plus grande taille) ou document joint à un message Telegram."""
    if msg.get("photo"):
        best = max(msg["photo"], key=lambda p: p.get("file_size") or p.get("width", 0) * p.get("height", 0))
        return {"file_id": best["file_id"], "nom": "image.jpg", "taille": best.get("file_size") or 0,
                "id": msg.get("message_id", "")}
    doc = msg.get("document")
    if doc and doc.get("file_id"):
        return {"file_id": doc["file_id"], "nom": doc.get("file_name") or "fichier", "taille": doc.get("file_size") or 0,
                "id": msg.get("message_id", "")}
    return None


def _nom_sur(nom: str) -> str:
    import re
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", nom).strip(".-") or "fichier"
    return base[-80:]


def _transmettre_fichier(bot: Bot, owner: str, fichier: dict, legende: str) -> None:
    if fichier["taille"] > MAX_FICHIER:
        bot.send(owner, "⚠ Fichier trop gros (20 Mo maximum via Telegram). Mets-le dans le dépôt et donne le chemin au chef.")
        return
    dest_dir = config.DATA_DIR / "chef" / BOITE
    dest_dir.mkdir(parents=True, exist_ok=True)
    # L'identifiant du message distingue les images d'un même album, envoyées dans la même seconde.
    dest = dest_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{fichier['id']}-{_nom_sur(fichier['nom'])}"
    try:
        bot.download(fichier["file_id"], dest, max_bytes=MAX_FICHIER)
    except TelegramError as exc:
        bot.send(owner, f"⚠ Je n'ai pas pu récupérer le fichier : {exc}")
        return
    store.feed_add("toi", f"(Telegram) fichier {dest.name}" + (f" — {legende}" if legende else ""))
    if ag.chef_inject(f"[Message de ton humain via Telegram] Fichier joint : {dest} (ouvre-le avec l'outil Read). "
                      f"Légende : {legende or '(aucune)'}"):
        bot.send(owner, "✔ Fichier transmis au chef.")
    else:
        bot.send(owner, f"⚠ Fichier enregistré ({dest.name}) mais le chef n'est pas lancé. Sur ton PC : jarvis chef")


def telegram_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            if store.state_path("telegram_pairing").exists():
                stop.wait(5)  # « jarvis telegram config » lit Telegram : on le laisse faire
                continue
            s = config.settings()["telegram"]
            if not (s.get("token") and s.get("chat_id")):
                stop.wait(30)  # pas encore configuré : on revérifie de temps en temps
                continue
            bot = Bot(s["token"])
            offset = store.read_json(TG_STATE, {}).get("offset")
            for upd in bot.updates(offset, wait=25):
                store.write_json(TG_STATE, {"offset": upd["update_id"] + 1})
                try:
                    handle_update(bot, str(s["chat_id"]), upd)
                except Exception as exc:  # noqa: BLE001 — un message mal formé ne doit pas tuer le pont
                    store.feed_add("erreur", f"Telegram : {exc}")
        except Exception as exc:  # noqa: BLE001 — réseau, réglages illisibles… on réessaie plus tard
            store.feed_add("erreur", f"Telegram : {exc}")
            stop.wait(20)


def run() -> None:
    stop = threading.Event()
    threads = [
        threading.Thread(target=watch_loop, args=(stop,), name="surveillance", daemon=True),
        threading.Thread(target=telegram_loop, args=(stop,), name="telegram", daemon=True),
        threading.Thread(target=sante_loop, args=(stop,), name="sante", daemon=True),
    ]
    for t in threads:
        t.start()
    store.feed_add("systeme", "démon Jarvis démarré")
    tg = "configuré" if config.settings()["telegram"].get("chat_id") else "non configuré (jarvis telegram config)"
    print(f"JARVIS · démon actif — surveillance toutes les {config.settings()['general']['poll_seconds']} s, Telegram {tg}.")
    print("Laisse cette fenêtre ouverte. Ctrl+C pour arrêter.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()
        store.feed_add("systeme", "démon Jarvis arrêté")
