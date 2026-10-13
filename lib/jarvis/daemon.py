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
    "/pause — bloque tout nouveau lancement\n"
    "/reprendre — lève la pause\n"
    "/aide — cette aide\n\n"
    "Tout autre message est transmis directement au chef d'orchestre."
)


# --- Surveillance des agents -------------------------------------------------

def watch_once(first: bool = False) -> list[dict]:
    """Compare l'état courant au précédent et réagit aux changements. Renvoie les événements."""
    agents, err = ag.status_all()
    if agents is None:
        return []  # observation impossible : on ne conclut rien (fail closed)
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
                "Lis sa sortie (workmux capture) et son issue Linear, puis décide de la suite.")
            if not injected and kind == "agent_waiting":
                # Personne pour lui répondre : on prévient l'humain directement.
                notify.alert("question", f"{msg} et le chef n'est pas lancé", windows=True)
    store.write_json(WATCH_STATE, {k: {"status": a["status"]} for k, a in cur.items()})
    return [{"type": k, "texte": m} for k, m, _ in events]


def watch_loop(stop: threading.Event) -> None:
    first = True
    while not stop.is_set():
        try:
            watch_once(first=first)
            first = False
            ag.chef_flush_queue()
        except Exception as exc:  # noqa: BLE001 — le démon ne doit jamais mourir sur une erreur ponctuelle
            store.feed_add("erreur", f"surveillance : {exc}")
        stop.wait(int(config.settings()["general"].get("poll_seconds", 20)))


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
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if str(msg.get("chat", {}).get("id", "")) != owner or str(msg.get("from", {}).get("id", owner)) != owner:
        bot.send(msg["chat"]["id"], "⛔ Ce Jarvis est privé.")
        return

    cmd = text.split()[0].split("@")[0].lower()
    if cmd in ("/start", "/aide", "/help"):
        bot.send(owner, AIDE)
    elif cmd in ("/etat", "/status"):
        bot.send(owner, report.text(detail=False))
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
