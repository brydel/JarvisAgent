"""Sous-commandes Python de `jarvis` (appelées par bin/jarvis)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import sys
import time
from pathlib import Path

from . import agents as ag
from . import config, notify, plans, report, store
from .telegram import Bot, TelegramError


def _err(msg: str, code: int = 1) -> int:
    print(f"Erreur : {msg}", file=sys.stderr)
    return code


# --- etat / fil ---------------------------------------------------------------

def cmd_etat(a) -> int:
    snap = report.snapshot()
    if a.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    else:
        print(report.text(snap))
    return 0


def cmd_fil(a) -> int:
    for e in store.feed_tail(a.n):
        print(f"{time.strftime('%H:%M', time.localtime(e['ts']))} {e.get('icone', '•')} {e['texte']}")
    return 0


# --- plans --------------------------------------------------------------------

def cmd_plan_nouveau(a) -> int:
    try:
        items = [plans.parse_item(s) for s in a.item]
        known = config.projects()
        for it in items:
            if it["projet"] not in known:
                return _err(f"projet inconnu « {it['projet']} » (jarvis projet liste)")
        plan = plans.create(a.titre, items, mode="nuit" if a.nuit else "vague", resume=a.pourquoi, origine="chef")
    except plans.PlanError as exc:
        return _err(str(exc))
    if config.settings()["plans"].get("validation") == "auto":
        # Validation automatique choisie par l'humain : il est prévenu, les autres garde-fous restent actifs.
        plan = plans.decide(plan["id"], True, par="auto")
        notify.telegram(f"📋 Plan approuvé automatiquement\n\n{plans.format_plan(plan)}")
        print(plans.format_plan(plan))
        print(f"\n{plan['id']} approuvé automatiquement (réglage plans.validation = auto). Tu peux lancer ses tâches.")
        return 0
    notify.telegram(f"📋 Nouveau plan à valider\n\n{plans.format_plan(plan)}", notify.plan_buttons(plan["id"]))
    notify.toast("JARVIS · plan à valider", f"{plan['id']} : {plan['titre']}")
    print(plans.format_plan(plan))
    print(f"\n{plan['id']} envoyé à ton humain. Attends sa décision : elle te sera transmise ici.")
    return 0


def cmd_plan_liste(a) -> int:
    items = plans.all_plans() if a.tous else plans.pending() + plans.active()
    if not items:
        print("Aucun plan." if a.tous else "Aucun plan en attente ni en cours.")
    for p in items[-20:]:
        print(plans.format_plan(p))
        print()
    return 0


def cmd_plan_voir(a) -> int:
    p = plans.get(a.id)
    if not p:
        return _err(f"plan {a.id} introuvable")
    print(plans.format_plan(p))
    return 0


def _human_only(action: str) -> int | None:
    """Les décisions humaines exigent un vrai terminal : l'outil Bash d'un agent n'en a pas.

    Le cockpit et Telegram appellent plans.decide directement, sans passer par ici.
    """
    if os.environ.get("JARVIS_ROLE") == "chef" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _err(f"{action} est réservé à l'humain (terminal interactif, cockpit ou Telegram).", 4)
    return None


def cmd_plan_decision(a, ok: bool) -> int:
    refused = _human_only("approuver ou refuser un plan")
    if refused is not None:
        return refused
    try:
        p = plans.decide(a.id, ok, par="terminal", raison=" ".join(getattr(a, "raison", []) or []))
    except plans.PlanError as exc:
        return _err(str(exc))
    print(plans.format_plan(p, detail=False))
    return 0


def cmd_plan_verifier(a) -> int:
    """Utilisé par `jarvis task` : vérifie pause, capacité et plan, puis marque le lancement."""
    if store.paused():
        return _err("Jarvis est en PAUSE : aucun nouveau lancement autorisé.", 3)
    from . import usage
    kind = plans.AGENTS.get(a.agent, a.agent)
    u = usage.summary().get(kind)
    if u and u["niveau"] == "epuise":
        other = "codex" if kind == "claude" else "claude"
        reprise = usage.fmt_reset(u.get("reprise")) or "sa remise à zéro"
        return _err(f"jetons {kind} épuisés jusqu'à {reprise} : assigne la tâche à {other} "
                    f"(nouveau plan) ou attends.", 5)
    agents, err = ag.status_all()
    if agents is None:
        return _err(f"impossible de compter les agents ({err})", 2)
    busy = sum(1 for x in agents if x["status"] in ag.BUSY)
    limit = int(config.settings()["general"].get("max_agents", 3))
    try:
        plans.authorize_launch(a.id, a.projet, a.issue, a.agent, busy=busy,
                               visible={x["worktree"] for x in agents}, max_agents=limit)
    except plans.PlanError as exc:
        return _err(str(exc), 2)
    return 0


def cmd_plan_relacher(a) -> int:
    try:
        plans.release(a.id, a.projet, a.issue, a.agent)
    except plans.PlanError as exc:
        return _err(str(exc), 2)
    return 0


def cmd_capacite(a) -> int:
    """Code 0 s'il reste une place pour un agent, 1 sinon."""
    agents, err = ag.status_all()
    if agents is None:
        return _err(f"impossible de compter les agents ({err})", 2)
    busy = sum(1 for x in agents if x["status"] in ag.BUSY)
    limit = int(config.settings()["general"].get("max_agents", 3))
    if busy >= limit:
        return _err(f"{busy}/{limit} agents déjà occupés : attends qu'un agent termine.", 1)
    print(f"{busy}/{limit} agents occupés")
    return 0


# --- chef → humain --------------------------------------------------------------

def cmd_demander(a) -> int:
    question = " ".join(a.texte).strip()
    if not question:
        return _err("question vide")
    notify.alert("question", question, title="JARVIS · question du chef")
    print("Question envoyée à ton humain (Telegram + notification). Sa réponse arrivera dans cette session.")
    return 0


def cmd_note(a) -> int:
    text = " ".join(a.texte).strip()
    if not text:
        return _err("note vide")
    journal = store.state_path("journal.md")
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {time.strftime('%Y-%m-%d %H:%M')}\n\n{text}\n")
    store.feed_add("note", text if len(text) < 160 else text[:157] + "…")
    if a.envoyer:
        notify.telegram(f"📝 Bilan du chef\n\n{text}")
    print("Noté dans le journal.")
    return 0


def cmd_journal(a) -> int:
    journal = store.state_path("journal.md")
    if not journal.exists():
        print("Journal vide.")
        return 0
    content = journal.read_text(encoding="utf-8")
    print(content[-a.caracteres:])
    return 0


# --- projets --------------------------------------------------------------------

def cmd_projet_ajouter(a) -> int:
    path = Path(a.chemin).expanduser().resolve()
    if not (path / ".git").exists():
        return _err(f"{path} n'est pas un dépôt git")
    projs = config.projects()
    projs[a.nom] = {
        "chemin": str(path),
        "linear": a.linear or "",
        "description": a.description or "",
        "verification": a.verification or "",
        "priorite": a.priorite,
        "actif": True,
    }
    config.save_projects(projs)
    print(f"Projet « {a.nom} » enregistré ({path}).")
    return 0


def cmd_projet_liste(a) -> int:
    projs = config.projects()
    if not projs:
        print("Aucun projet. Ajoute-en un : jarvis projet ajouter <nom> <chemin> --linear \"<projet Linear>\"")
    for name, p in sorted(projs.items(), key=lambda kv: (kv[1]["priorite"], kv[0])):
        state = "" if p["actif"] else "  (en pause)"
        print(f"P{p['priorite']}  {name:<16} {p['chemin']}{state}")
        if p["linear"]:
            print(f"     Linear : {p['linear']}")
        if p["description"]:
            print(f"     {p['description']}")
    return 0


def cmd_projet_chemin(a) -> int:
    p = config.projects().get(a.nom)
    if not p:
        return _err(f"projet inconnu « {a.nom} » (jarvis projet liste)")
    print(p["chemin"])
    return 0


# --- Telegram -------------------------------------------------------------------

def cmd_telegram_config(a) -> int:
    print("Configuration du bot Telegram de Jarvis\n")
    print("1. Dans Telegram, ouvre @BotFather et envoie /newbot.")
    print("2. Choisis un nom (ex. Jarvis Brydel) puis un identifiant finissant par « bot ».")
    print("3. BotFather te donne un jeton qui ressemble à 123456789:ABC-def…\n")
    token = getpass.getpass("Colle le jeton ici (il ne s'affiche pas) : ").strip()
    if not token:
        return _err("aucun jeton saisi")
    try:
        bot = Bot(token)
        me = bot.me()
    except TelegramError as exc:
        return _err(f"jeton refusé par Telegram : {exc}")
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    # Le démon met sa lecture Telegram en pause pendant l'appairage (sinon il « avalerait » le code).
    pairing = store.state_path("telegram_pairing")
    pairing.write_text(str(time.time()), encoding="utf-8")
    try:
        return _pair(bot, me, token, code)
    finally:
        pairing.unlink(missing_ok=True)


def _pair(bot: Bot, me: dict, token: str, code: str) -> int:
    print(f"\n✓ Bot reconnu : @{me.get('username')}")
    print(f"Ouvre la conversation avec @{me.get('username')} dans Telegram et envoie-lui ce code : {code}")
    print("J'attends ton message (5 minutes maximum)…")

    offset = None
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            ups = bot.updates(offset, wait=20)
        except TelegramError as exc:
            return _err(str(exc))
        for u in ups:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if (msg.get("text") or "").strip() == code:
                if msg.get("chat", {}).get("type") != "private":
                    bot.send(msg["chat"]["id"], "⛔ Appaire Jarvis dans une conversation privée avec le bot, pas dans un groupe.")
                    continue
                chat_id = str(msg["chat"]["id"])
                data = config.settings()
                data["telegram"]["token"] = token
                data["telegram"]["chat_id"] = chat_id
                config.save_settings(data)
                store.write_json("telegram.json", {"offset": offset})
                bot.send(chat_id, "✅ Jarvis est connecté. Envoie /aide pour voir les commandes.")
                print(f"\n✓ Appairé avec ta conversation ({chat_id}). Réglages enregistrés dans {config.SETTINGS_FILE}")
                print("Relance le démon pour l'activer : il tourne dans la fenêtre « daemon » (jarvis start).")
                return 0
    return _err("délai dépassé : code non reçu. Relance « jarvis telegram config ».")


def cmd_telegram_test(a) -> int:
    if notify.telegram("🔔 Test Jarvis : la liaison Telegram fonctionne."):
        print("✓ Message de test envoyé.")
        return 0
    return _err("Telegram non configuré ou injoignable (jarvis telegram config)")


# --- Réglages -----------------------------------------------------------------

def cmd_regler(a) -> int:
    refused = _human_only("modifier les réglages")
    if refused is not None:
        return refused
    data = config.settings()
    section, _, key = a.cle.partition(".")
    if not key or section not in data or section == "telegram":
        return _err("clé inconnue. Exemples : general.max_agents, general.poll_seconds, notifications.windows")
    current = data[section].get(key)
    value: object = a.valeur
    if isinstance(current, bool):
        value = a.valeur.lower() in ("1", "true", "oui", "vrai", "on")
    elif isinstance(current, int):
        try:
            value = int(a.valeur)
        except ValueError:
            return _err(f"{a.cle} attend un nombre")
    data[section][key] = value
    config.save_settings(data)
    print(f"{a.cle} = {value}")
    return 0


def cmd_reglage_lire(a) -> int:
    section, _, key = a.cle.partition(".")
    value = config.settings().get(section, {}).get(key, "")
    if (section, key) == ("telegram", "token"):
        value = "configuré" if value else ""  # le jeton ne s'affiche jamais
    print(str(value).lower() if isinstance(value, bool) else value)
    return 0


def cmd_jetons(a) -> int:
    from . import usage
    s = usage.summary()
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(usage.text(s))
    return 0


def cmd_veille_liste(a) -> int:
    from . import daemon
    st = store.read_json(daemon.VEILLE_STATE, {"fait": {}})
    days = int(config.settings()["veille"].get("jours", 7))
    now = time.time()
    for name in config.projects():
        last = st.get("fait", {}).get(name)
        if last:
            age = int((now - last) // 86400)
            due = "due" if days and now - last >= days * 86400 else f"prochaine dans {days - age} j"
            print(f"{name:<16} dernière il y a {age} j — {due}")
        else:
            print(f"{name:<16} jamais faite — due")
    return 0


def cmd_veille_fait(a) -> int:
    from . import daemon
    if a.projet not in config.projects():
        return _err(f"projet inconnu « {a.projet} »")
    store.update_json(daemon.VEILLE_STATE, {"fait": {}, "dernier_rappel": 0},
                      lambda st: st.setdefault("fait", {}).__setitem__(a.projet, time.time()))
    store.feed_add("note", f"veille concurrentielle faite pour {a.projet}")
    print(f"Veille de {a.projet} enregistrée.")
    return 0


def cmd_installer_statusline(a) -> int:
    """Branche bin/jarvis-statusline dans ~/.claude/settings.json sans écraser un réglage existant."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    settings_path = (Path(base) if base else config.HOME / ".claude") / "settings.json"
    command = str(config.JARVIS_HOME / "bin" / "jarvis-statusline")
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    except json.JSONDecodeError:
        return _err(f"{settings_path} est illisible : statusLine non installée", 2)
    current = (data.get("statusLine") or {}).get("command", "")
    if current == command:
        print("déjà installée")
        return 0
    if current:
        print(f"une barre d'état existe déjà ({current}) : je n'y touche pas")
        return 3
    data["statusLine"] = {"type": "command", "command": command}
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = settings_path.with_suffix(".jarvis-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(settings_path)
    print("installée")
    return 0


def cmd_voir(a) -> int:
    """Sortie récente d'un agent, même s'il n'est pas (encore) suivi par workmux."""
    print(ag.capture(a.cible, lines=a.lignes))
    return 0


def cmd_preparer_worktree(a) -> int:
    from . import trust
    done = trust.prepare(a.agent, a.chemin)
    if done:
        print(", ".join(done))
    return 0


def cmd_evenement(a) -> int:
    store.feed_add(a.type, " ".join(a.texte))
    return 0


CHEF_KICKOFF = (
    "Nouvelle session. Applique ta boucle : relis « jarvis journal », puis « jarvis etat » et "
    "« jarvis projet liste », consulte Linear pour les projets actifs, reprends les agents en cours, "
    "puis propose la prochaine vague (ou explique pourquoi il n'y a rien à lancer)."
)


def _rule_path(path: Path) -> str:
    """Chemin au format des règles de permission Claude Code (~/… ou //…)."""
    try:
        return "~/" + str(path.resolve().relative_to(config.HOME.resolve()))
    except ValueError:
        return "/" + str(path.resolve())


def cmd_chef_preparer(a) -> int:
    """Prépare le dossier de travail du chef (rôle + permissions) et affiche son chemin."""
    chef_dir = config.DATA_DIR / "chef"
    (chef_dir / "consignes").mkdir(parents=True, exist_ok=True)
    (chef_dir / ".claude").mkdir(exist_ok=True)

    role = chef_dir / "CLAUDE.md"
    source = config.JARVIS_HOME / "chef" / "CLAUDE.md"
    if role.is_symlink():
        role.unlink()
    elif role.exists():
        backup = role.with_name(f"CLAUDE.md.bak.{time.strftime('%Y%m%d-%H%M%S')}")
        role.rename(backup)  # on ne détruit jamais un fichier modifié à la main
    role.symlink_to(source)  # lien : un « git pull » de JarvisAgent met le rôle à jour

    # Dossiers que le chef ne doit jamais modifier avec ses outils : le code des projets
    # (et leurs worktrees), et tout ce qui porte les garde-fous de Jarvis.
    protected = {Path(config.settings()["general"]["workspace"]).expanduser()}
    for p in config.projects().values():
        root = Path(p["chemin"])
        protected |= {root, root.parent / f"{root.name}__worktrees"}
    protected |= {config.STATE_DIR, config.CONFIG_DIR, config.JARVIS_HOME, chef_dir / ".claude"}
    deny_paths = []
    for d in sorted({_rule_path(x) for x in protected}):
        deny_paths += [f"Edit({d}/**)", f"Write({d}/**)"]
    secrets = []
    for d in sorted({_rule_path(x) for x in protected if x not in (config.STATE_DIR, config.CONFIG_DIR)}):
        secrets += [f"Read({d}/**/.env)", f"Read({d}/**/.env.*)"]

    settings = {
        "permissions": {
            "allow": [
                "Bash(jarvis etat *)", "Bash(jarvis etat)", "Bash(jarvis projet liste)", "Bash(jarvis fil *)",
                "Bash(jarvis plan nouveau *)", "Bash(jarvis plan liste *)", "Bash(jarvis plan liste)",
                "Bash(jarvis plan voir *)", "Bash(jarvis task *)", "Bash(jarvis capacite)",
                "Bash(jarvis demander *)", "Bash(jarvis note *)", "Bash(jarvis journal *)", "Bash(jarvis journal)",
                "Bash(jarvis voir *)", "Bash(jarvis jetons)", "Bash(jarvis jetons *)",
                "Bash(jarvis veille)", "Bash(jarvis veille *)",
                # Veille concurrentielle : recherche web (lecture seule).
                "WebSearch", "WebFetch",
                "Bash(workmux status)", "Bash(workmux status *)", "Bash(workmux capture *)",
                "Bash(workmux send *)", "Bash(workmux wait *)",
                "Bash(gh pr view *)", "Bash(gh pr diff *)", "Bash(gh pr checks *)", "Bash(gh pr list *)",
                "mcp__linear-server__*",
            ],
            "deny": deny_paths + secrets + [
                # Décisions et réglages réservés à l'humain.
                "Bash(jarvis plan ok *)", "Bash(jarvis plan non *)", "Bash(jarvis plan verifier *)",
                "Bash(jarvis plan relacher *)", "Bash(jarvis regler *)", "Bash(jarvis telegram *)",
                "Bash(jarvis reglage-lire *)", "Bash(jarvis preparer-worktree *)", "Bash(jarvis chef-preparer *)",
                # Contournements de « jarvis task » et accès directs au noyau.
                "Bash(workmux add *)", "Bash(workmux run *)", "Bash(python *)", "Bash(python3 *)",
                "Bash(env *)", "Bash(script *)",
                # Le chef dirige : il ne fusionne, ne pousse et ne supprime rien.
                "Bash(workmux merge *)", "Bash(workmux remove *)", "Bash(workmux rm *)",
                "Bash(gh pr merge)", "Bash(gh pr merge *)", "Bash(git push)", "Bash(git push *)",
                "Bash(git merge *)", "Bash(git reset *)", "Bash(git -C *)", "Bash(rm *)",
            ],
        }
    }
    (chef_dir / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                                                        encoding="utf-8")
    print(chef_dir)
    return 0


def cmd_chef_message(a) -> int:
    print(CHEF_KICKOFF)
    return 0


# --- Analyseur ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis", description="Poste de pilotage des agents IA")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("etat", help="état des agents, plans et projets")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_etat)

    s = sub.add_parser("fil", help="derniers événements")
    s.add_argument("n", nargs="?", type=int, default=30)
    s.set_defaults(fn=cmd_fil)

    plan = sub.add_parser("plan", help="plans proposés par le chef").add_subparsers(dest="action", required=True)
    s = plan.add_parser("nouveau", help="proposer un plan à valider")
    s.add_argument("--titre", required=True)
    s.add_argument("--item", action="append", default=[], required=True, metavar="projet:ISSUE:agent[:desc]")
    s.add_argument("--pourquoi", default="", help="justification courte (2-3 phrases)")
    s.add_argument("--nuit", action="store_true", help="plan de nuit, valable 16 h")
    s.set_defaults(fn=cmd_plan_nouveau)
    s = plan.add_parser("liste")
    s.add_argument("--tous", action="store_true")
    s.set_defaults(fn=cmd_plan_liste)
    s = plan.add_parser("voir")
    s.add_argument("id")
    s.set_defaults(fn=cmd_plan_voir)
    s = plan.add_parser("ok", help="approuver")
    s.add_argument("id")
    s.set_defaults(fn=lambda a: cmd_plan_decision(a, True))
    s = plan.add_parser("non", help="refuser")
    s.add_argument("id")
    s.add_argument("raison", nargs="*")
    s.set_defaults(fn=lambda a: cmd_plan_decision(a, False))
    s = plan.add_parser("verifier", help=argparse.SUPPRESS)
    s.add_argument("id")
    s.add_argument("projet")
    s.add_argument("issue")
    s.add_argument("agent")
    s.set_defaults(fn=cmd_plan_verifier)
    s = plan.add_parser("relacher", help=argparse.SUPPRESS)
    s.add_argument("id")
    s.add_argument("projet")
    s.add_argument("issue")
    s.add_argument("agent")
    s.set_defaults(fn=cmd_plan_relacher)

    s = sub.add_parser("capacite", help="reste-t-il une place pour un agent ?")
    s.set_defaults(fn=cmd_capacite)

    s = sub.add_parser("demander", help="poser une question à l'humain (Telegram + notification)")
    s.add_argument("texte", nargs="+")
    s.set_defaults(fn=cmd_demander)

    s = sub.add_parser("note", help="écrire un bilan dans le journal du chef")
    s.add_argument("texte", nargs="+")
    s.add_argument("--envoyer", action="store_true", help="envoyer aussi le bilan sur Telegram")
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("journal", help="relire la fin du journal du chef")
    s.add_argument("--caracteres", type=int, default=6000)
    s.set_defaults(fn=cmd_journal)

    projet = sub.add_parser("projet", help="registre des projets").add_subparsers(dest="action", required=True)
    s = projet.add_parser("ajouter")
    s.add_argument("nom")
    s.add_argument("chemin")
    s.add_argument("--linear", help="nom du projet ou de l'équipe Linear")
    s.add_argument("--description")
    s.add_argument("--verification", help="commandes de vérification (lint, tests)")
    s.add_argument("--priorite", type=int, default=3)
    s.set_defaults(fn=cmd_projet_ajouter)
    s = projet.add_parser("liste")
    s.set_defaults(fn=cmd_projet_liste)
    s = projet.add_parser("chemin")
    s.add_argument("nom")
    s.set_defaults(fn=cmd_projet_chemin)

    tg = sub.add_parser("telegram", help="liaison Telegram").add_subparsers(dest="action", required=True)
    tg.add_parser("config").set_defaults(fn=cmd_telegram_config)
    tg.add_parser("test").set_defaults(fn=cmd_telegram_test)

    s = sub.add_parser("regler", help="modifier un réglage (ex. general.max_agents 4)")
    s.add_argument("cle")
    s.add_argument("valeur")
    s.set_defaults(fn=cmd_regler)

    s = sub.add_parser("jetons", help="consommation Claude et Codex (5 h et semaine)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_jetons)
    veille_p = sub.add_parser("veille", help="veille concurrentielle")
    veille_p.set_defaults(fn=cmd_veille_liste)  # « jarvis veille » seul = la liste
    veille = veille_p.add_subparsers(dest="action")
    veille.add_parser("liste").set_defaults(fn=cmd_veille_liste)
    s = veille.add_parser("fait")
    s.add_argument("projet")
    s.set_defaults(fn=cmd_veille_fait)
    sub.add_parser("installer-statusline", help=argparse.SUPPRESS).set_defaults(fn=cmd_installer_statusline)
    s = sub.add_parser("voir", help="sortie récente d'un agent (projet:worktree)")
    s.add_argument("cible")
    s.add_argument("-n", "--lignes", type=int, default=80)
    s.set_defaults(fn=cmd_voir)
    s = sub.add_parser("preparer-worktree", help=argparse.SUPPRESS)
    s.add_argument("agent")
    s.add_argument("chemin")
    s.set_defaults(fn=cmd_preparer_worktree)
    s = sub.add_parser("reglage-lire", help=argparse.SUPPRESS)
    s.add_argument("cle")
    s.set_defaults(fn=cmd_reglage_lire)
    s = sub.add_parser("evenement", help=argparse.SUPPRESS)
    s.add_argument("type")
    s.add_argument("texte", nargs="+")
    s.set_defaults(fn=cmd_evenement)
    sub.add_parser("chef-preparer", help=argparse.SUPPRESS).set_defaults(fn=cmd_chef_preparer)
    sub.add_parser("chef-message", help=argparse.SUPPRESS).set_defaults(fn=cmd_chef_message)

    sub.add_parser("daemon", help="surveillance + Telegram").set_defaults(fn=lambda a: _daemon())
    sub.add_parser("cockpit", help="interface plein écran").set_defaults(fn=lambda a: _cockpit())
    return p


def _daemon() -> int:
    from . import daemon
    daemon.run()
    return 0


def _cockpit() -> int:
    from . import cockpit
    return cockpit.main()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
