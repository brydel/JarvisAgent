"""Sous-commandes Python de `jarvis` (appelées par bin/jarvis)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import re
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
        plans.resoudre(items)  # rôle, fournisseur, modèle et secours de chaque tâche
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


def _capacite(agents: list[dict]) -> tuple[int, dict]:
    """(agents occupés, capacité du poste)."""
    from . import poste
    busy = sum(1 for x in agents if x["status"] in ag.BUSY)
    return busy, poste.capacite(busy)


def _fiche_shell(fiche: dict) -> str:
    """Affectation d'un lancement, une « clé=valeur » par ligne, lue par bin/jarvis."""
    keys = ("agent", "modele", "modele_id", "effort", "repli", "role", "taille", "raison", "reservation", "classe",
            "jetons_max")
    lines = [f"{k}={' '.join(str(fiche.get(k) or '').split())}" for k in keys]
    lines.append(f"par_secours={'1' if fiche.get('par_secours') else '0'}")
    return "\n".join(lines)


# Code de sortie par motif de refus, lu par bin/jarvis et le chef.
_CODES_REFUS = {"pause": 3, "budget": 5, "capacite": 2, "lourde": 2, "doublon": 2, "plan": 2, "observation": 2,
                "config": 6, "origine": 2, "budget_jetons": 8, "escalade": 9, "meme_approche": 9}


def _acteur() -> str:
    if os.environ.get("JARVIS_ROLE") == "chef":
        return "chef"
    if os.environ.get("JARVIS_METIER"):
        return f"agent:{os.environ['JARVIS_METIER']}"
    return "humain" if sys.stdin.isatty() and sys.stdout.isatty() else "cli"


def cmd_plan_verifier(a) -> int:
    """Utilisé par `jarvis task` : passe par l'admission commune (pauses, observation, capacité,
    réservations, opérations lourdes, doublons, jetons, plan) puis marque le lancement.

    Affiche l'affectation à lancer (fournisseur, modèle, effort, rôle, réservation), une « clé=valeur » par ligne.
    """
    from . import admission
    try:
        adm = admission.demander(origine="plan", projet=a.projet, issue=a.issue, agent=a.agent, worktree=a.worktree or "",
                                 plan=a.id, relecture=a.revue, acteur=_acteur(), consignes_empreinte=a.consignes_empreinte or "")
    except admission.Refus as exc:
        _prevenir_chef_refus(exc, a.projet, a.issue)
        return _err(exc.raison, _CODES_REFUS.get(exc.code, 2))
    fiche = dict(adm["fiche"])
    fiche["reservation"], fiche["classe"], fiche["jetons_max"] = adm["reservation"], adm["classe"], adm["jetons_max"]
    for av in adm["avertissements"]:
        print(f"Attention : {av}", file=sys.stderr)
    print(_fiche_shell(fiche))
    return 0


def cmd_admission(a) -> int:
    """`jarvis admission demander|liberer|etat` : le point d'admission, pour un lancement manuel ou l'affichage."""
    from . import admission
    if a.action == "etat":
        print(admission.texte_etat())
        return 0
    if a.action == "liberer":
        return 0 if admission.liberer(a.id, " ".join(a.raison), acteur=_acteur()) else _err(f"réservation {a.id} inconnue ou déjà close")
    forcer = bool(a.forcer)
    if forcer and _acteur() != "humain":
        return _err("--forcer est réservé à l'humain devant un terminal.", 4)
    try:
        adm = admission.demander(origine=a.origine, projet=a.projet, issue=a.issue, agent=a.agent, worktree=a.worktree or "",
                                 role=a.role or "", classe=a.classe or "", acteur=_acteur(), forcer=forcer,
                                 taille=(a.taille or "M").upper(), consignes_empreinte=a.consignes_empreinte or "")
    except admission.Refus as exc:
        _prevenir_chef_refus(exc, a.projet, a.issue)
        return _err(exc.raison, _CODES_REFUS.get(exc.code, 2))
    for av in adm["avertissements"]:
        print(f"Attention : {av}", file=sys.stderr)
    print(f"reservation={adm['reservation']}\nclasse={adm['classe']}\njetons_max={adm['jetons_max']}")
    return 0


def _prevenir_chef_refus(exc, projet: str, issue: str) -> None:
    """Plafond de jetons ou escalade : le chef en est informé même si ce n'est pas lui qui a lancé."""
    if exc.code not in ("budget_jetons", "escalade"):
        return
    store.feed_add("erreur", f"{projet} {issue} : lancement refusé ({exc.code})")
    if os.environ.get("JARVIS_ROLE") != "chef":
        ag.chef_inject(f"[JARVIS {exc.code}] {exc.raison}")


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
    busy, cap = _capacite(agents)
    limit = cap["max"]
    pourquoi = f" (plafond réduit : {' ; '.join(cap['raisons'])})" if cap["raisons"] else ""
    if busy >= limit:
        return _err(f"{busy}/{limit} agents déjà occupés{pourquoi} : attends qu'un agent termine.", 1)
    print(f"{busy}/{limit} agents occupés{pourquoi}")
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
    try:  # la note alimente aussi la mémoire cherchable (titre = première ligne)
        from . import memoire
        premiere = text.splitlines()[0]
        memoire.noter(titre=premiere[:160], corps=text, source="note")
    except Exception:  # noqa: BLE001 — le journal reste la référence ; la mémoire est un plus
        pass
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


# --- Noeud GPU (Jetson) -------------------------------------------------------

def cmd_noeud_config(a) -> int:
    refused = _human_only("brancher le noeud GPU")
    if refused is not None:
        return refused
    from . import noeud
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}@[A-Za-z0-9.-]{1,253}", a.cible or ""):
        return _err("cible attendue sous la forme utilisateur@adresse (ex. moi@192.168.1.20)")
    pub = noeud.creer_cle(config.settings()["noeud"])
    try:
        noeud.sante({**config.settings()["noeud"], "cible": a.cible}, hote_connu=False)
    except noeud.NoeudError:
        print("Le noeud ne répond pas encore à la clé de Jarvis. Sur la Jetson, depuis services/noeud_jetson :\n")
        print(f"  echo '{pub}' > jarvis_noeud.pub")
        print("  bash installer_noeud.sh --cle-jarvis jarvis_noeud.pub\n")
        print(f"puis relance : jarvis noeud config {a.cible}")
        return 1
    try:
        r = noeud.brancher(a.cible, par="humain")
    except (noeud.NoeudError, ValueError, OSError) as exc:
        return _err(f"branchement impossible : {exc}")
    print(f"✓ Noeud GPU branché : connexion « {r['connexion']} », outils autorisés, mandat {r['mandat']} pour le Board.")
    print("  L'audio déposé sur le Board sera transcrit sur le noeud. Pour couper : jarvis regler noeud.actif false")
    return 0


def cmd_noeud_etat(a) -> int:
    from . import noeud
    ok, raison = noeud.active()
    if not ok:
        print(f"○ {raison}")
        return 0
    try:
        s = noeud.sante()
    except noeud.NoeudError as exc:
        print(f"✗ Activé mais {exc} : l'audio du Board garde ses seules métadonnées.")
        return 1
    m = s.get("mesures") or {}
    r = noeud.reglages()
    print(f"● Noeud GPU {r['cible']} (connexion {r['connexion']}) : modèle {s.get('modele')}, "
          f"{'occupé' if s.get('occupe') else 'libre'}")
    print(f"  mémoire {m.get('memoire_dispo_mo', '?')}/{m.get('memoire_totale_mo', '?')} Mo libres · "
          f"GPU {m.get('gpu_c', '?')} °C · CPU {m.get('cpu_c', '?')} °C · audio {s.get('duree_max_s')} s au plus")
    return 0


# --- Réglages -----------------------------------------------------------------

def cmd_regler(a) -> int:
    refused = _human_only("modifier les réglages")
    if refused is not None:
        return refused
    data = config.settings()
    section, _, key = a.cle.partition(".")
    if not key or section not in data or section == "telegram":
        return _err("clé inconnue. Exemples : general.max_agents, general.poll_seconds, notifications.windows")
    if section == "noeud" and key not in ("actif", "langue", "delai_s"):
        return _err("cible, clé, connexion et mandat du noeud se règlent avec « jarvis noeud config »")
    current = data[section].get(key)
    value: object = a.valeur
    allowed = {"codex.mode": ("bac-a-sable", "complet"), "plans.validation": ("humain", "auto"),
               "noeud.langue": config.LANGUES_NOEUD}.get(a.cle)
    if current is None:
        return _err(f"clé inconnue « {a.cle} » (voir le tableau des réglages du README)")
    if allowed and a.valeur not in allowed:
        return _err(f"{a.cle} accepte : {', '.join(allowed)}")
    if isinstance(current, bool):
        value = a.valeur.lower() in ("1", "true", "oui", "vrai", "on")
    elif isinstance(current, int) and config._BORNES.get((section, key), (int,))[0] is not float:
        try:
            value = int(a.valeur)
        except ValueError:
            return _err(f"{a.cle} attend un nombre entier")
    elif isinstance(current, (int, float)):
        try:
            value = float(a.valeur.replace(",", "."))
        except ValueError:
            return _err(f"{a.cle} attend un nombre")
    data[section][key] = value
    erreurs = config.valider(data)
    if erreurs:
        # Un réglage invalide fermerait l'admission : on le refuse plutôt que de l'écrire.
        return _err("réglage refusé : " + " ; ".join(erreurs))
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


def cmd_fermer(a) -> int:
    """Ferme la fenêtre d'agents terminés. Refuse tout agent qui travaille encore."""
    found, err = ag.status_all()
    if found is None:
        return _err(f"impossible de lire l'état des agents ({err})", 2)
    if a.termines:
        cibles = [x for x in found if x["status"] in ag.CLOSABLE]
        if not cibles:
            print("Aucune fenêtre d'agent terminé à fermer.")
            return 0
    else:
        if not a.cible:
            return _err("précise une cible (projet:worktree) ou --termines")
        agent = ag.find(a.cible)
        if not agent:
            return _err(f"agent « {a.cible} » introuvable (jarvis etat)")
        cibles = [agent]
    rc = 0
    for agent in cibles:
        ok, msg = ag.close(agent)
        print(("✓ " if ok else "✗ ") + msg)
        if ok:
            store.feed_add("systeme", msg + " (worktree conservé)")
        else:
            rc = 1
    return rc


def cmd_reprendre(a) -> int:
    from . import poste
    if not poste.reprise_en_attente():
        print("Rien à reprendre : aucun agent interrompu par un redémarrage.")
        return 0
    if not a.essai and not os.environ.get("TMUX"):
        return _err("lance « jarvis reprendre » depuis la session Jarvis (jarvis start, puis Ctrl+B c).")
    lignes = poste.reprendre(dry_run=a.essai)
    for ln in lignes:
        print(ln)
    if not a.essai:
        repris = sum(1 for ln in lignes if ln.startswith("repris"))
        notify.alert("systeme", f"Jarvis relancé après un redémarrage du PC : {repris} agent(s) repris.",
                     title="JARVIS · redémarrage", windows=False)
    return 0


def cmd_reprise_preparer(a) -> int:
    from . import poste
    snap = poste.preparer_reprise()
    if snap:
        print(json.dumps({"agents": len(snap.get("agents", [])), "chef": bool(snap.get("chef"))}))
    return 0


def cmd_sante(a) -> int:
    from . import poste
    print(poste.texte())
    return 0


def cmd_reparer_git(a) -> int:
    from . import poste
    p = config.projects().get(a.projet)
    if not p:
        return _err(f"projet inconnu « {a.projet} » (jarvis projet liste)")
    ok, lignes = poste.reparer_git(Path(p["chemin"]))
    for ln in lignes:
        print(ln)
    store.feed_add("systeme" if ok else "erreur", f"réparation git de {a.projet} : {'dépôt sain' if ok else 'à vérifier'}")
    return 0 if ok else 1


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


# --- Rôles et modèles -----------------------------------------------------------------------

def cmd_role_liste(a) -> int:
    from . import roles
    print(roles.texte())
    return 0


def cmd_role_voir(a) -> int:
    from . import roles
    r = roles.get(a.nom)
    if not r:
        return _err(f"rôle inconnu « {a.nom} » (jarvis role liste)")
    print(f"{r['emoji']} {r['titre']} — équipe {r['equipe']} · niveau {r['niveau']} · {r['fournisseur']}\n")
    print(r["corps"])
    return 0


def cmd_role_version(a) -> int:
    """Briefs candidats : proposer, lister, décider (toi), retirer, promouvoir (toi)."""
    from . import versions_roles as vr
    try:
        if a.action == "candidats":
            if a.cible:
                p = vr.get(a.cible)
                if not p:
                    return _err(f"proposition {a.cible} introuvable")
                print(vr.diff_complet(p))
                return 0
            print(vr.texte())
            return 0
        if a.action == "proposer":
            try:
                texte = Path(a.fichier).read_text(encoding="utf-8")
            except OSError as exc:
                return _err(f"candidat illisible : {exc}")
            # Aucun score par la ligne de commande : seuls ceux mesurés par l'optimiseur sont affichés.
            p = vr.proposer(a.cible, texte, a.pourquoi, par=_acteur(), source=a.fichier)
            print(f"{p['id']} proposé pour {p['role']} : ton humain décide (Telegram). Rien ne change avant.")
            return 0
        if a.action == "retirer":
            p = vr.retirer(a.cible, par=_acteur(), raison=a.pourquoi)
            print(f"{p['id']} retiré : le rôle {p['role']} reprend son brief stable.")
            return 0
        refused = _human_only(f"{a.action} un brief de rôle")
        if refused is not None:
            return refused
        if a.action in ("approuver", "refuser"):
            p = vr.decider(a.cible, a.action == "approuver", par="humain")
            print(f"{p['id']} en essai sur {p['pct']} % des tâches {p['role']}." if p["statut"] == "canari"
                  else f"{p['id']} refusé.")
            return 0
        p = vr.promouvoir(a.cible, par="humain")
        print(f"{p['id']} promu : brief du rôle {p['role']} écrit dans {p['ecrit']}.")
        return 0
    except vr.VersionError as exc:
        return _err(str(exc))


def cmd_modele_liste(a) -> int:
    from . import modeles
    print(modeles.texte())
    en_attente = modeles.propositions()
    if en_attente:
        print("\nPROPOSITIONS À VALIDER")
        for i in en_attente:
            print(modeles.format_proposition(i))
    return 0


def cmd_modele_choisir(a) -> int:
    """Montre (ou fournit à bin/jarvis) l'affectation que le routeur choisirait."""
    from . import modeles, taches
    auteur = ""
    if a.relit:
        projet, _, issue = a.relit.partition(":")
        auteur = taches.dernier_auteur(projet, issue)
    try:
        fiche = modeles.choisir(a.role or None, a.taille, a.agent, a.modele or "", auteur=auteur)
    except modeles.RoutageError as exc:
        return _err(str(exc))
    if a.shell:
        print(_fiche_shell(fiche))
        return 0
    print(f"→ {modeles.libelle(fiche['agent'], fiche['modele'], fiche['effort'])}")
    print(f"  {fiche['raison']}")
    if fiche["secours"]:
        s = fiche["secours"]
        print(f"  secours : {modeles.libelle(s['agent'], s['modele'], s['effort'])}")
    return 0


def cmd_modele_verifier(a) -> int:
    from . import modeles, usage
    print("Essai des modèles du catalogue avec tes abonnements (une courte requête par modèle)…")
    res = modeles.verifier(a.noms or None, usage.summary())
    if not res:
        print("Aucun modèle à essayer.")
    for nom, r in res.items():
        mark = {True: "✓", False: "✗", None: "?"}[r["ok"]]
        print(f"  {mark} {nom} : {r['detail']}")
    return 0


def cmd_modele_proposer(a) -> int:
    from . import modeles
    champs = {"fournisseur": a.fournisseur, "id": a.id, "niveau": a.niveau, "cout": a.cout, "effort": a.effort,
              "atouts": a.atouts, "repli": a.repli, "note": a.note}
    if a.retirer:
        champs["actif"] = False
    try:
        item = modeles.proposer(a.nom, champs, a.pourquoi or "", a.source or "")
    except modeles.RoutageError as exc:
        return _err(str(exc))
    notify.telegram(f"🧬 Proposition sur le catalogue des modèles\n\n{modeles.format_proposition(item)}",
                    notify.proposition_buttons(item["id"]))
    notify.toast("JARVIS · modèle à valider", f"{item['id']} : {item['nom']}")
    print(modeles.format_proposition(item))
    print(f"\n{item['id']} envoyé à ton humain. Sa décision te sera transmise ici.")
    return 0


def cmd_modele_decision(a, ok: bool) -> int:
    refused = _human_only("modifier le catalogue des modèles")
    if refused is not None:
        return refused
    from . import modeles
    try:
        item = modeles.decider(a.id, ok, par="terminal")
    except modeles.RoutageError as exc:
        return _err(str(exc))
    print(modeles.format_proposition(item))
    return 0


# --- Registre des tâches, bilan, usine ------------------------------------------------------------

def cmd_prompt_construire(a) -> int:
    """Écrit le prompt d'un agent : mission, brief de son rôle, poste de travail, consignes du chef."""
    from . import livrables, roles
    role = roles.ou_defaut(a.role)
    issue = a.issue.upper()
    dossier = livrables.dossier(a.projet, issue)
    out = [f"Tu travailles dans l'usine Jarvis en tant que **{role['titre']}** (équipe {role['equipe']}).", ""]
    out.append("## Mission")
    if a.revue:
        out += [f"Mission de RELECTURE uniquement : relis la PR #{a.revue} liée à l'issue Linear {issue}.",
                "Ne modifie aucun fichier, ne crée aucun commit, n'ouvre aucune PR.",
                "Vérifie point par point les critères d'acceptation de l'issue, la sécurité, les tests et la lisibilité.",
                f"Publie tes remarques avec « gh pr review {a.revue} --comment --body-file <fichier> »,",
                "puis résume ton verdict dans l'issue Linear (commentaire « ✅ REVUE » ou « ❓ REVUE »)."]
    elif role["nom"] == "revue":
        out += [f"Mission de RELECTURE uniquement : relis le travail livré pour l'issue Linear {issue}.",
                "Ne modifie aucun fichier, ne crée aucun commit, n'ouvre aucune PR.",
                f"Ce travail est soit une PR liée à l'issue, soit des fichiers déposés dans `{dossier}` : l'issue et son "
                "commentaire ✅ TERMINÉ te disent lesquels. Pour une vidéo ou un visuel, lance le contrôle "
                "(`jarvis studio verifier <fichier>`), regarde la planche-contact avec ton outil de lecture d'image, "
                "et vérifie chaque affirmation contre le produit réel.",
                "Publie ton verdict dans l'issue Linear (commentaire « ✅ REVUE » ou « ❓ REVUE »)."]
    else:
        out += [f"Traite l'issue Linear {issue}. Lis-la en entier via l'outil Linear avant de commencer,",
                f"puis suis à la lettre le protocole décrit dans {a.regles} (statut, commentaires ❓/✅, PR).",
                "Ne fusionne jamais dans main."]
        if role["livrable"] != "pr":
            out += ["Ton livrable principal est un ensemble de fichiers, pas du code : dépose-les dans le dossier des "
                    "livrables ci-dessous. La PR ne contient que les sources utiles à versionner (scénarios, "
                    "storyboards, textes) ; s'il n'y en a aucune, ne crée pas de PR et dis-le dans ton commentaire final."]
    from . import versions_roles
    version, corps_candidat = versions_roles.choisir(role["nom"], a.projet, issue)  # essai progressif d'un brief
    if getattr(a, "brief_sortie", ""):
        Path(a.brief_sortie).write_text(version, encoding="utf-8")  # la fiche de tâche notera la version reçue
    corps = corps_candidat if corps_candidat is not None else role["corps"]
    if corps:
        out += ["", f"## Ton rôle : {role['titre']}", "", corps]
    out += ["", "## Ton poste", "",
            f"- Projet : {a.projet} · issue : {issue} · branche : {a.branche}",
            f"- Livrables hors dépôt (captures, vidéos, rapports) : `{dossier}` (variable `$JARVIS_LIVRABLES`). "
            "Ne les committe jamais.",
            f"- Outils de l'usine : `{config.JARVIS_HOME}` (variable `$JARVIS_HOME`), dont le studio "
            "`skills/jarvis-studio/`.",
            "- Ton commentaire final dans Linear cite ton rôle et liste les fichiers déposés dans les livrables.",
            "- Tu ne livres rien toi-même à l'humain : le chef d'orchestre contrôle puis envoie."]
    if a.consignes:
        try:
            texte = Path(a.consignes).read_text(encoding="utf-8")
        except OSError as exc:
            return _err(f"consignes illisibles : {exc}")
        out += ["", "## Consignes du chef d'orchestre", "", texte.rstrip()]
    from . import specifications
    spec = specifications.pour_prompt(role=role["nom"], projet=a.projet, issue=issue, branche=a.branche)
    out += ["", "## Contrat commun de la session", "",
            "Ce contrat décrit le profil et les livrables. Il n'accorde aucun outil ni mandat supplémentaire.",
            "```json", json.dumps(spec, ensure_ascii=False, sort_keys=True), "```"]
    from . import communaute_runtime
    out += ["", communaute_runtime.contexte(a.projet)]
    print("\n".join(out))
    return 0


def cmd_tache_enregistrer(a) -> int:
    from . import taches
    fiche = taches.enregistrer(projet=a.projet, issue=a.issue, agent=a.agent, worktree=a.worktree, chemin=a.chemin,
                               role=a.role, modele=a.modele, modele_id=a.modele_id, effort=a.effort, repli=a.repli,
                               taille=a.taille, plan=a.plan, revue=a.revue, raison=a.raison, secours=a.secours,
                               classe=a.classe, reservation=a.reservation, jetons_max=int(a.jetons_max or 0),
                               consignes_empreinte=a.consignes_empreinte, base=a.base, brief=a.brief)
    if a.reservation:
        from . import admission
        admission.confirmer(a.reservation, fiche["id"], a.worktree)
    print(fiche["id"])
    return 0


def cmd_tache_annuler(a) -> int:
    from . import taches
    taches.annuler(a.id)
    return 0


def cmd_lancement_args(a) -> int:
    """Pour bin/jarvis-claude et bin/jarvis-codex : options du modèle et environnement du worktree courant.

    Une ligne « arg<TAB>valeur » par argument du CLI, « env<TAB>NOM=valeur » par variable.
    """
    from . import livrables, modeles, taches
    if os.environ.get("JARVIS_METIER") or os.environ.get("JARVIS_ROLE"):
        # Réservé aux lanceurs, qui l'appellent AVANT de démarrer l'agent : un agent ou le chef qui l'appellerait
        # depuis le worktree d'un autre rôle lirait ses secrets.
        return _err("lancement-args est réservé aux lanceurs de Jarvis.", 4)
    fiche = taches.par_chemin(os.getcwd())
    if not fiche:
        return 0  # worktree inconnu du registre (lancé à la main) : réglages par défaut du CLI
    args: list[str] = []
    cat = modeles.catalogue()
    verif = modeles.etat_verif()
    m = cat.get(fiche.get("modele") or "")
    ident = fiche.get("modele_id") or ""
    if ident and not (m and m["id"] == ident and modeles.utilisable(m, verif)):
        # Retiré, modifié ou devenu indisponible depuis la validation du plan : un identifiant qui n'est
        # plus celui d'un modèle vérifié ferait échouer le démarrage. Le modèle par défaut prend le relais.
        store.feed_add("erreur", f"modèle {fiche.get('modele') or ident} indisponible : {fiche['projet']} "
                                 f"{fiche['issue']} démarre avec le modèle par défaut")
        ident = ""
    surs = {x["id"] for x in cat.values() if x["fournisseur"] == a.agent and x["id"] and modeles.utilisable(x, verif)}
    effort = fiche.get("effort") or ""
    if a.agent == "claude":
        if ident:
            args += ["--model", ident]
            replis = [x for x in (fiche.get("repli") or "").split(",") if x and x != ident and x in surs]
            if replis:
                args += ["--fallback-model", ",".join(replis)]
        if effort:
            args += ["--effort", effort]
    else:
        if ident:
            args += ["--model", ident]
        if effort:
            args += ["-c", f'model_reasoning_effort="{effort}"']
    for x in args:
        print(f"arg\t{x}")
    env = {"JARVIS_PROJET": fiche["projet"], "JARVIS_ISSUE": fiche["issue"], "JARVIS_METIER": fiche["role"],
           "JARVIS_LIVRABLES": str(livrables.dossier(fiche["projet"], fiche["issue"]))}
    for k, v in env.items():
        print(f"env\t{k}={v}")
    # Secrets minimaux : seulement ceux du rôle de la tâche. Les valeurs ne passent que par ce canal
    # (lu par le lanceur), jamais par un fichier, un journal ou le prompt. Les noms seuls sont tracés.
    from . import secrets
    try:
        injectes = secrets.pour_tache(fiche["projet"], fiche["role"])
    except secrets.SecretsError as exc:
        store.feed_add("erreur", f"secrets de {fiche['projet']} non injectés : {exc}")
        injectes = {}
    for k, v in injectes.items():
        print(f"secret\t{k}={v}")
    if injectes:
        store.feed_add("systeme", f"{fiche['projet']} {fiche['issue']} [{fiche['role']}] : secrets injectés : "
                                  + ", ".join(sorted(injectes)))
    return 0


def cmd_tache_liste(a) -> int:
    from . import modeles, roles, taches
    if a.quoi and a.quoi[0] in ("voir", "echec", "relancer"):
        return _cmd_tache_action(a)
    nombres = [x for x in a.quoi if x != "liste"]
    if len(nombres) > 1 or any(not x.isdigit() or int(x) < 1 for x in nombres):
        return _err("usage : jarvis tache [n]  (n = nombre de tâches à afficher)")
    fiches = taches.toutes()[-(int(nombres[0]) if nombres else 20):]
    if not fiches:
        print("Aucune tâche enregistrée.")
    for t in fiches:
        r = roles.ou_defaut(t["role"])
        quand = time.strftime("%d/%m %H:%M", time.localtime(t["cree"]))
        ligne = (f"{t['id']} {quand} {t['projet']} {t['issue']} [{r['sigle']} {r['titre']}] "
                 f"{modeles.libelle(t['agent'], t['modele'], t['effort'])} — {taches.STATUTS.get(t['statut'], t['statut'])}")
        if t.get("jetons"):
            ligne += f" · {taches.fmt_jetons(t['jetons'].get('total', 0))} jetons"
        if t.get("verdict"):
            ligne += f" · relecture : {taches.VERDICTS[t['verdict']]}"
        if t.get("echec"):
            ligne += f" · échec : {t['echec']['classe']}"
        print(ligne)
    return 0


def _cmd_tache_action(a) -> int:
    """jarvis tache voir <T-id> · tache echec <T-id> <classe> [note] · tache relancer <T-id> --autoriser."""
    from . import couts, roles, taches, usage
    action, reste = a.quoi[0], a.quoi[1:]
    if not reste:
        return _err(f"usage : jarvis tache {action} <T-xxxxx>" + (" <classe> [note]" if action == "echec" else ""))
    t = taches.get(reste[0])
    if not t:
        return _err(f"tâche {reste[0]} introuvable")
    if action == "voir":
        unite = taches.unite(t["projet"], t["issue"], t.get("role", ""))
        comptes = taches._essais_comptes(unite)
        maxi = taches.ESSAIS_AUTO + taches.autorisations(t["projet"], t["issue"], t.get("role", ""))
        c = couts.cout_fiche(t)
        cpt = usage.compteur_tache(t["id"]) or {}
        r = roles.ou_defaut(t.get("role"))
        print(f"{t['id']} — {t['projet']} {t['issue']} [{r['titre']}, taille {t.get('taille', 'M')}] · {t['agent']} "
              f"{t.get('modele') or ''} · {taches.STATUTS.get(t['statut'], t['statut'])}")
        print(f"  essai {t.get('essai') or '?'} · essais comptés pour cette unité : {len(comptes)}/{maxi}")
        if t.get("brief", "stable") != "stable":
            print(f"  brief reçu : {t['brief']} (essai d'un brief candidat, jarvis role candidats)")
        if t.get("echec"):
            e = t["echec"]
            print(f"  échec : {e['classe']} ({taches.CLASSES_ECHEC[e['classe']]}, {'constaté' if e['source'] == 'auto' else 'déclaré'}"
                  + (f" par {e['par']}" if e.get("par") else "") + ")" + (f" — {e['note']}" if e.get("note") else ""))
        print(f"  jetons de l'unité : {taches.fmt_jetons(cpt.get('jetons', 0))} / plafond {taches.fmt_jetons(cpt.get('plafond', 0))}"
              + (" — PLAFOND ATTEINT" if cpt.get("depasse") else ""))
        print(f"  cette tâche : {taches.fmt_jetons(c['jetons'])} jetons · équivalent API {couts.monnaie(c['usd'])}"
              + (" (estimation)" if c["estimation"] else ""))
        for x in unite:
            if x["id"] != t["id"]:
                print(f"  autre essai : {x['id']} {taches.STATUTS.get(x['statut'], x['statut'])}"
                      + (f" · échec {x['echec']['classe']}" if x.get("echec") else ""))
        return 0
    if action == "echec":
        if len(reste) < 2:
            return _err(f"usage : jarvis tache echec <T-xxxxx> <classe> [note] (classes : {', '.join(taches.CLASSES_ECHEC)})")
        if os.environ.get("JARVIS_METIER"):
            return _err("un agent ne classe pas son propre échec : le chef ou ton humain le fait.", 4)
        try:
            taches.classer(t["id"], reste[1], source="declare", par=_acteur(), note=" ".join(reste[2:]))
        except ValueError as exc:
            return _err(str(exc))
        print(f"{t['id']} classé : {reste[1]} ({taches.CLASSES_ECHEC[reste[1]]})")
        return 0
    # relancer --autoriser : un humain débloque un essai après une escalade
    if not a.autoriser:
        return _err("ajoute --autoriser : débloquer un essai après escalade est une décision humaine.")
    refused = _human_only("débloquer un essai après escalade")
    if refused is not None:
        return refused
    total = taches.autoriser_essai(t["projet"], t["issue"], t.get("role", ""), par="humain", note=" ".join(reste[1:]))
    print(f"Un essai de plus autorisé pour {t['projet']} {t['issue']} [{t.get('role')}] ({total} au total). "
          "Le chef peut relancer avec un plan.")
    ag.chef_inject(f"[JARVIS] Ton humain a débloqué un essai de plus pour {t['projet']} {t['issue']} [{t.get('role')}]. "
                   "Change d'approche par rapport aux essais précédents.")
    return 0


def cmd_budget_jetons(a) -> int:
    """jarvis budget-jetons voir <T-id> | defaut [--role R --taille M]"""
    from . import couts, taches, usage
    if a.action == "voir":
        if not a.quoi:
            return _err("usage : jarvis budget-jetons voir <T-xxxxx>")
        c = usage.compteur_tache(a.quoi[0])
        if not c:
            return _err(f"tâche {a.quoi[0]} introuvable")
        t = taches.get(c["tache"])
        print(f"{t['projet']} {t['issue']} [{t.get('role')}] : {taches.fmt_jetons(c['jetons'])} jetons consommés "
              f"(relances comprises) / plafond {taches.fmt_jetons(c['plafond'])} · reste {taches.fmt_jetons(c['reste'])}"
              + (" — PLAFOND ATTEINT : aucune relance" if c["depasse"] else ""))
        return 1 if c["depasse"] else 0
    plafond, source = couts.plafond_defaut(a.role or "", a.taille or "M")
    print(f"Plafond par défaut [{a.role or 'generaliste'}, taille {(a.taille or 'M').upper()}] : "
          f"{taches.fmt_jetons(plafond)} jetons — {source}")
    return 0


def cmd_cout(a) -> int:
    from . import couts, taches
    note = couts.note_monnaie()
    entete = "Équivalent API (tarifs publics) : ce que ces tâches auraient coûté hors abonnement, pas une dépense."
    if a.action == "tache":
        if not a.quoi:
            return _err("usage : jarvis cout tache <T-xxxxx>")
        t = taches.get(a.quoi[0])
        if not t:
            return _err(f"tâche {a.quoi[0]} introuvable")
        c = couts.cout_fiche(t)
        tf = couts.tarif(t["agent"], t.get("modele", ""))
        print(entete)
        print(f"{t['id']} {t['projet']} {t['issue']} · {t['agent']} {t.get('modele') or 'défaut'} · "
              f"{taches.fmt_jetons(c['jetons'])} jetons → {couts.monnaie(c['usd'])}"
              + (f" (estimation : {c['raison']})" if c["estimation"] else ""))
        if tf.get("prix_in") is not None:
            print(f"  tarif {tf['modele']} : entrée {tf['prix_in']:g} $, sortie {tf['prix_out']:g} $ par million de jetons")
    elif a.action == "projet":
        if not a.quoi:
            return _err("usage : jarvis cout projet <nom> [--periode 7j]")
        try:
            r = couts.par_projet(a.quoi[0], a.periode)
        except ValueError as exc:
            return _err(str(exc))
        print(entete)
        print(f"{r['projet']} sur {r['periode']} : {len(r['lignes'])} tâche(s), {taches.fmt_jetons(r['jetons'])} jetons, "
              f"{couts.monnaie(r['usd'])}" + (" (contient des estimations)" if r["estimation"] else "")
              + (f", {r['inconnus']} tâche(s) sans mesure" if r["inconnus"] else ""))
        for x in sorted(r["lignes"], key=lambda x: -(x["usd"] or 0))[:15]:
            print(f"  {x['id']} {x['issue']:<10} {x['role']:<12} {x['modele']:<14} {taches.fmt_jetons(x['jetons']):>7} "
                  f"{couts.monnaie(x['usd'])}{' *' if x['estimation'] else ''}")
    else:
        r = couts.semaine(a.n)
        print(entete)
        print(f"7 derniers jours : {taches.fmt_jetons(r['jetons'])} jetons, {couts.monnaie(r['usd'])}"
              + (" (contient des estimations, marquées *)" if r["estimation"] else ""))
        for p, usd in sorted(r["projets"].items(), key=lambda kv: -kv[1]):
            print(f"  {p:<16} {couts.monnaie(usd)}")
        if r["lignes"]:
            print("Tâches les plus coûteuses :")
            for x in r["lignes"]:
                print(f"  {x['id']} {x['projet']} {x['issue']:<10} {x['role']:<12} {x['modele']:<14} "
                      f"{taches.fmt_jetons(x['jetons']):>7} {couts.monnaie(x['usd'])}{' *' if x['estimation'] else ''}")
    if note:
        print(note)
    return 0


def cmd_verdict(a) -> int:
    from . import taches
    if a.projet not in config.projects():
        return _err(f"projet inconnu « {a.projet} »")
    try:
        fiche = taches.noter_verdict(a.projet, a.issue, a.verdict, " ".join(a.note))
    except ValueError as exc:
        return _err(str(exc))
    if not fiche:
        return _err(f"aucune tâche de production trouvée pour {a.projet} {a.issue.upper()}")
    store.feed_add("note", f"relecture de {a.projet} {fiche['issue']} : {taches.VERDICTS[a.verdict]}")
    print(f"Verdict enregistré pour {fiche['id']} ({a.projet} {fiche['issue']}) : {taches.VERDICTS[a.verdict]}.")
    return 0


def cmd_bilan(a) -> int:
    from . import taches
    if a.quoi == "quotidien":
        from . import bilan
        texte = bilan.quotidien()
        print(texte)
        if a.envoyer:
            print("Envoyé sur Telegram." if notify.telegram(texte) else "Telegram non configuré ou injoignable.")
        return 0
    b = taches.bilan(a.jours)
    if a.json:
        print(json.dumps(b, ensure_ascii=False, indent=2, default=str))
    else:
        print(taches.texte_bilan(b))
    return 0


def cmd_usine(a) -> int:
    print(report.usine())
    return 0


# --- Studio et livrables --------------------------------------------------------------------------

def cmd_studio_verifier(a) -> int:
    from . import studio
    rapport = studio.verifier(a.fichier, duree_min=a.duree_min, duree_max=a.duree_max)
    if a.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
    else:
        print(studio.texte(rapport))
    return 0 if rapport["verdict"] == "PRÊT" else 1


def cmd_livrer(a) -> int:
    from . import livrables, studio
    interactif = sys.stdin.isatty() and sys.stdout.isatty()
    if os.environ.get("JARVIS_METIER") or not (os.environ.get("JARVIS_ROLE") == "chef" or interactif):
        # Un agent de l'usine dépose ses fichiers ; c'est le chef qui contrôle, fait relire, puis livre.
        # (Garde-fou contre l'erreur, pas barrière de sécurité : la destination reste ton seul Telegram.)
        return _err("la livraison revient au chef d'orchestre : dépose ton fichier dans $JARVIS_LIVRABLES "
                    "et cite-le dans ton commentaire ✅ TERMINÉ.", 4)
    if a.forcer and (os.environ.get("JARVIS_ROLE") == "chef" or not interactif):
        return _err("envoyer un fichier qui échoue au contrôle qualité est réservé à l'humain, dans son terminal.", 4)
    try:
        item = livrables.livrer(a.fichier, a.titre or "", a.legende or "", forcer=a.forcer)
    except livrables.LivrableError as exc:
        return _err(str(exc))
    print(studio.texte(item["rapport"]))
    if item["envoye"]:
        print(f"\n{item['id']} envoyé à ton humain sur Telegram.")
    else:
        print(f"\n{item['id']} enregistré mais NON envoyé : {item['erreur']}. Fichier : {item['fichier']}")
    return 0 if item["envoye"] else 6


def cmd_livrables(a) -> int:
    from . import livrables
    if a.projet and a.issue:
        if a.projet not in config.projects():
            return _err(f"projet inconnu « {a.projet} »")
        try:
            print(livrables.dossier(a.projet, a.issue))
        except livrables.LivrableError as exc:
            return _err(str(exc))
        return 0
    print(livrables.texte())
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
    # Vague 3 : skills actives, quarantaine, briefs candidats, rapports d'optimisation, dossiers lus par les agents.
    from . import skills as _skills
    protected |= {config.DATA_DIR / d for d in ("skills", "skills-quarantaine", "roles-candidats", "optimisation")}
    protected |= set(_skills.liens_dirs())
    deny_paths = []
    for d in sorted({_rule_path(x) for x in protected}):
        deny_paths += [f"Edit({d}/**)", f"Write({d}/**)"]
    secrets = []
    for d in sorted({_rule_path(x) for x in protected if x not in (config.STATE_DIR, config.CONFIG_DIR)}):
        secrets += [f"Read({d}/**/.env)", f"Read({d}/**/.env.*)"]
    secrets.append(f"Read({_rule_path(config.CONFIG_DIR / 'secrets')}/**)")  # secrets par rôle (vague 1)

    settings = {
        "permissions": {
            "allow": [
                "Bash(jarvis etat *)", "Bash(jarvis etat)", "Bash(jarvis projet liste)", "Bash(jarvis fil *)",
                "Bash(jarvis plan nouveau *)", "Bash(jarvis plan liste *)", "Bash(jarvis plan liste)",
                "Bash(jarvis plan voir *)", "Bash(jarvis task *)", "Bash(jarvis capacite)",
                "Bash(jarvis demander *)", "Bash(jarvis note *)", "Bash(jarvis journal *)", "Bash(jarvis journal)",
                "Bash(jarvis voir *)", "Bash(jarvis jetons)", "Bash(jarvis jetons *)",
                "Bash(jarvis veille)", "Bash(jarvis veille *)",
                "Bash(jarvis fermer *)", "Bash(jarvis sante)", "Bash(jarvis reparer-git *)",
                "Bash(jarvis reprendre --essai)", "Bash(jarvis admission etat)", "Bash(jarvis pause)",
                "Bash(jarvis pause etat)", "Bash(jarvis pause poser incident *)", "Bash(jarvis lourd liste)",
                "Bash(jarvis audit)", "Bash(jarvis audit *)", "Bash(jarvis profil liste)", "Bash(jarvis profil voir *)",
                "Bash(jarvis diagnostic)", "Bash(jarvis diagnostic *)", "Bash(jarvis politique)", "Bash(jarvis politique *)",
                "Bash(jarvis budget)", "Bash(jarvis budget *)", "Bash(jarvis fournisseurs)", "Bash(jarvis fournisseurs *)",
                "Bash(jarvis proposition *)", "Bash(jarvis memoire)", "Bash(jarvis memoire *)",
                "Bash(jarvis cout)", "Bash(jarvis cout *)", "Bash(jarvis budget-jetons *)",
                "Bash(jarvis secrets verifier *)", "Bash(jarvis rejouer *)", "Bash(jarvis traces)", "Bash(jarvis traces *)",
                "Bash(jarvis rollback proposer *)", "Bash(jarvis rollback demander *)", "Bash(jarvis eval liste*)",
                "Bash(jarvis eval verifier*)", "Bash(jarvis eval resultats*)", "Bash(jarvis proxy)", "Bash(jarvis proxy voir)",
                "Bash(jarvis skill)", "Bash(jarvis skill liste)", "Bash(jarvis skill auditer)", "Bash(jarvis skill installer *)",
                "Bash(jarvis stockage)", "Bash(jarvis stockage etat)", "Bash(jarvis executant)", "Bash(jarvis executant liste)",
                # Usine : rôles, routeur, registre, bilan, studio et livrables.
                "Bash(jarvis role)", "Bash(jarvis role *)", "Bash(jarvis modele)", "Bash(jarvis modele liste)",
                "Bash(jarvis modele choisir *)", "Bash(jarvis modele proposer *)",
                "Bash(jarvis tache)", "Bash(jarvis tache *)", "Bash(jarvis verdict *)",
                "Bash(jarvis bilan)", "Bash(jarvis bilan *)", "Bash(jarvis usine)",
                "Bash(jarvis studio verifier *)", "Bash(jarvis livrer *)",
                "Bash(jarvis livrables)", "Bash(jarvis livrables *)",
                # Veille concurrentielle : recherche web (lecture seule).
                "WebSearch", "WebFetch",
                "Bash(jarvis os diagnostic)", "Bash(jarvis os schemas)", "Bash(jarvis os preflight *)",
                "Bash(jarvis os communaute *)", "Bash(jarvis os outils *)",
                "Bash(jarvis os runtime *)", "Bash(jarvis os modele voir)", "Bash(jarvis os modele verifier)",
                "Bash(jarvis os oauth liste)",
                "Bash(jarvis os connexions liste)", "Bash(jarvis os connexions decouvrir *)",
                "Bash(workmux status)", "Bash(workmux status *)", "Bash(workmux capture *)",
                "Bash(workmux send *)", "Bash(workmux wait *)",
                "Bash(gh pr view *)", "Bash(gh pr diff *)", "Bash(gh pr checks *)", "Bash(gh pr list *)",
                "mcp__linear-server__*",
            ],
            "deny": deny_paths + secrets + [
                # Décisions et réglages réservés à l'humain.
                "Bash(jarvis os mandat creer*)", "Bash(jarvis os mandat revoquer*)",
                "Bash(jarvis os connexions creer*)", "Bash(jarvis os connexions revoquer*)",
                "Bash(jarvis os modele configurer*)", "Bash(jarvis os oauth configurer*)",
                "Bash(jarvis os oauth commencer*)", "Bash(jarvis os oauth revoquer*)",
                "Bash(jarvis plan ok *)", "Bash(jarvis plan non *)", "Bash(jarvis plan verifier *)",
                "Bash(jarvis plan relacher *)", "Bash(jarvis regler *)", "Bash(jarvis telegram *)",
                "Bash(jarvis reglage-lire *)", "Bash(jarvis preparer-worktree *)", "Bash(jarvis chef-preparer *)",
                "Bash(jarvis autostart)", "Bash(jarvis autostart *)", "Bash(jarvis reprise-preparer)",
                "Bash(jarvis reprise-preparer *)", "Bash(jarvis reprendre)",
                "Bash(jarvis modele ok *)", "Bash(jarvis modele non *)", "Bash(jarvis modele verifier)",
                "Bash(jarvis modele verifier *)", "Bash(jarvis livrer * --forcer*)", "Bash(jarvis livrer --forcer*)",
                "Bash(jarvis tache-enregistrer *)", "Bash(jarvis tache-annuler *)", "Bash(jarvis lancement-args *)",
                "Bash(jarvis prompt-construire *)", "Bash(jarvis chef-lancer)", "Bash(jarvis chef-lancer *)", "Bash(jarvis chef-etat)",
                "Bash(jarvis web)", "Bash(jarvis web *)", "Bash(jarvis relancer)", "Bash(jarvis relancer *)",
                "Bash(jarvis pause lever *)", "Bash(jarvis pause poser humain*)", "Bash(jarvis pause poser maintenance*)",
                "Bash(jarvis pause poser batterie*)", "Bash(jarvis pause poser quota*)", "Bash(jarvis pause poser ressources*)",
                "Bash(jarvis profil appliquer *)", "Bash(jarvis admission demander *)", "Bash(jarvis admission liberer *)",
                "Bash(jarvis lourd debut *)", "Bash(jarvis lourd exec *)", "Bash(jarvis lourd fin *)",
                "Bash(jarvis politique appliquer *)", "Bash(jarvis politique deleguer *)", "Bash(jarvis budget definir *)",
                "Bash(jarvis tache relancer *)", "Bash(jarvis execution *)", "Bash(jarvis rollback executer *)",
                "Bash(jarvis eval lancer *)", "Bash(jarvis proxy config*)", "Bash(jarvis skill approuver *)",
                "Bash(jarvis skill refuser *)", "Bash(jarvis skill epingler *)",
                "Bash(jarvis role approuver *)", "Bash(jarvis role refuser *)", "Bash(jarvis role promouvoir *)",
                "Bash(jarvis stockage migrer*)", "Bash(jarvis stockage revenir*)", "Bash(jarvis executant declarer *)",
                "Bash(jarvis executant retirer *)",
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


def cmd_chef_etat(a) -> int:
    """Pour bin/jarvis : 0 = le chef tourne, 1 = pas de fenêtre, 2 = fenêtre ouverte sur un simple shell."""
    etat = ag.chef_etat()
    print(etat)
    return {"actif": 0, "absent": 1}.get(etat, 2)


def cmd_chef_message(a) -> int:
    from . import poste
    note = poste.note_redemarrage()
    print(CHEF_KICKOFF + (f" IMPORTANT : {note}" if note else ""))
    return 0


# --- Analyseur ------------------------------------------------------------------

def cmd_pause(a) -> int:
    from . import admission, pauses
    if a.action == "etat":
        print(pauses.texte())
        print(admission.texte_etat())
        return 0
    cause = a.cause
    if cause not in pauses.CAUSES:
        return _err(f"cause inconnue « {cause} » (valeurs : {', '.join(pauses.CAUSES)})")
    acteur = _acteur()
    # Un agent (le chef compris) peut POSER une pause incident : jamais en lever une, ni poser une autre.
    # Même garde que les approbations (terminal interactif) : garde-fou applicatif, pas une barrière
    # (docs/autonomy/securite.md).
    if not (a.action == "poser" and cause == "incident"):
        refused = _human_only("poser ou lever une pause (un agent peut seulement poser « incident »)")
        if refused is not None:
            return refused
    note = " ".join(a.note)
    if a.action == "poser":
        if pauses.poser(cause, note, par=acteur):
            print(f"⏸ Pause « {cause} » posée." + (f" {note}" if note else ""))
            ag.chef_inject(f"[JARVIS] Pause « {cause} » posée par {acteur} : ne lance plus aucune tâche jusqu'à nouvel ordre.")
        else:
            print(f"La pause « {cause} » était déjà posée.")
    else:
        if not pauses.lever(cause, par=acteur):
            print(f"La pause « {cause} » n'était pas posée.")
        restantes = pauses.actives()
        if restantes:
            print(f"▶ « {cause} » levée. Jarvis reste en pause : {pauses.texte(restantes)}")
        else:
            print("▶ Plus aucune pause : Jarvis peut relancer.")
            ag.chef_inject(f"[JARVIS] Pause levée par {acteur} : tu peux reprendre ta boucle.")
    return 0


def cmd_profil(a) -> int:
    profs = config.profils()
    if a.action == "liste":
        actuel = config.settings()["admission"].get("profil") or ""
        for nom, p in profs.items():
            marque = " (appliqué)" if nom == actuel else ""
            print(f"{nom}{marque} — {p['description']}")
        if not actuel:
            print("Aucun profil appliqué : réglages par défaut ou personnalisés (jarvis profil appliquer <nom>).")
        return 0
    if not a.nom:
        return _err("précise le nom du profil (jarvis profil liste)")
    if a.action == "voir":
        p = profs.get(a.nom)
        if not p:
            return _err(f"profil inconnu « {a.nom} »")
        print(f"{a.nom} — {p['description']}")
        for table, vals in p["reglages"].items():
            for k, v in vals.items():
                print(f"  {table}.{k} = {v}")
        return 0
    refused = _human_only("appliquer un profil")
    if refused is not None:
        return refused
    try:
        regl, sauvegarde = config.appliquer_profil(a.nom)
    except ValueError as exc:
        return _err(str(exc))
    from . import journal
    journal.ecrire("profil", acteur="humain", objet=a.nom, decision="applique",
                   raison=f"sauvegarde : {sauvegarde.name if sauvegarde else 'aucune (pas de settings.toml)'}")
    n = sum(len(v) for v in regl.values())
    print(f"Profil « {a.nom} » appliqué ({n} réglages)." + (f" Ancien settings.toml : {sauvegarde}" if sauvegarde else ""))
    print("Les valeurs valent pour les PROCHAINS lancements ; aucun agent en cours n'est arrêté. Vérifie : jarvis capacite")
    return 0


def cmd_lourd(a) -> int:
    from . import admission
    acteur = _acteur()
    if a.action == "liste":
        ops = admission.lourdes_en_cours()
        print("Aucune opération lourde déclarée." if not ops else "\n".join(
            f"{o['id']} {o['classe']} {o.get('worktree') or ''} {o.get('desc') or ''}" for o in ops))
        return 0
    if a.action == "fin":
        if not a.quoi:
            return _err("usage : jarvis lourd fin <L-xxxxx>")
        return 0 if admission.lourde_fin(a.quoi[0], acteur=acteur) else _err(f"opération {a.quoi[0]} inconnue ou déjà close")
    if not a.quoi:
        return _err("usage : jarvis lourd debut <classe> [desc] | jarvis lourd exec <classe> -- commande…")
    classe = a.quoi[0]
    worktree = a.worktree or os.environ.get("JARVIS_ISSUE", "")
    if a.action == "debut":
        try:
            # Sans PID : le wrapper bash qui nous appelle disparaît aussitôt ; seule la durée fait foi (jarvis lourd fin).
            o = admission.lourde_debut(classe, worktree=worktree, desc=" ".join(a.quoi[1:]), pid=None,
                                       duree_min=a.duree, acteur=acteur)
        except admission.Refus as exc:
            return _err(exc.raison, _CODES_REFUS.get(exc.code, 2))
        print(o["id"])
        return 0
    # exec : attend une place (bornée), lance la commande avec une priorité réduite, libère à la fin.
    import shutil
    import subprocess
    cmd = a.quoi[1:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        return _err("usage : jarvis lourd exec <classe> -- commande…")
    limite = time.time() + 60 * max(0, a.attente)
    while True:
        try:
            o = admission.lourde_debut(classe, worktree=worktree, desc=" ".join(cmd)[:120], pid=os.getpid(),
                                       duree_min=a.duree, acteur=acteur)
            break
        except admission.Refus as exc:
            if exc.code != "lourde" or time.time() >= limite:
                return _err(exc.raison, _CODES_REFUS.get(exc.code, 2))
            print(f"… {exc.raison} (nouvel essai dans 15 s)", file=sys.stderr)
            time.sleep(15)
    prefixe = ["nice", "-n", "10"] if shutil.which("nice") else []
    try:
        rc = subprocess.call(prefixe + cmd)
    finally:
        admission.lourde_fin(o["id"], acteur=acteur)
    return rc


def cmd_audit(a) -> int:
    from . import journal
    if a.verifier:
        ok, msg = journal.verifier()
        print(("✔ " if ok else "⚠ ") + msg)
        return 0 if ok else 1
    print(journal.texte(journal.lire(a.n, a.type_)))
    return 0


def cmd_diagnostic(a) -> int:
    from . import diagnostic
    rapport = diagnostic.collecter(windows_=not a.sans_windows)
    chemin = diagnostic.enregistrer(rapport)
    if a.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2, default=str))
    else:
        print(diagnostic.texte(rapport))
    print(f"\nRapport expurgé enregistré : {chemin}", file=sys.stderr)
    return 0


def cmd_politique(a) -> int:
    from . import politique
    try:
        if a.action == "voir":
            print(politique.texte())
        elif a.action == "exceptions":
            print(politique.texte_exceptions())
        elif a.action == "verifier":
            if not a.quoi:
                return _err("usage : jarvis politique verifier <action> [--projet P] [--montant N] [--detail …]")
            d = politique.autoriser(a.quoi[0], acteur=_acteur(), projet=a.projet or "", montant=float(a.montant or 0),
                                    detail=" ".join(a.quoi[1:]), categorie=a.categorie or "depense")
            print(f"{d['decision']} (niveau {d['niveau']}) — {d['raison']}")
            return 0 if d["decision"] == "admis" else 1
        elif a.action == "deleguer":
            refused = _human_only("déléguer une action")
            if refused is not None:
                return refused
            if not a.quoi or not a.perimetre:
                return _err("usage : jarvis politique deleguer <action> --perimetre \"…\" [--plafond N] [--jours N] [--projet P]")
            d = politique.deleguer(a.quoi[0], perimetre=a.perimetre, plafond=float(a.plafond or 0), jours=a.jours or 7,
                                   projet=a.projet or "")
            print(f"{d['id']} : {d['action']} délégué ({d['perimetre']}, plafond {d['plafond']:g}, "
                  f"jusqu'au {time.strftime('%d/%m %H:%M', time.localtime(d['expire']))}).")
        elif a.action == "revoquer":
            refused = _human_only("révoquer une délégation")
            if refused is not None:
                return refused
            if not a.quoi:
                return _err("usage : jarvis politique revoquer <D-xxxx>")
            print("révoquée" if politique.revoquer(a.quoi[0]) else "délégation inconnue ou déjà close")
        elif a.action == "exception":
            refused = _human_only("décider d'une exception")
            if refused is not None:
                return refused
            if len(a.quoi) < 2:
                return _err("usage : jarvis politique exception <E-xxxx> accordee|refusee")
            ok = politique.clore_exception(a.quoi[0], a.quoi[1])
            print("décision enregistrée" if ok else "exception inconnue ou déjà close")
            if ok and a.quoi[1] == "accordee":
                print("Note : accorder une exception ne lance rien et ne crée pas de délégation durable ; "
                      "pour une autorisation répétée : jarvis politique deleguer.")
        elif a.action == "appliquer":
            refused = _human_only("appliquer la politique")
            if refused is not None:
                return refused
            pol = politique.charger()
            from . import journal
            journal.ecrire("politique", acteur="humain", objet=f"v{pol['version']}", decision="appliquee",
                           raison=f"{len(pol['actions'])} actions" + (f" ; ignorées : {len(pol['ignorees'])}" if pol["ignorees"] else ""))
            print(politique.texte(pol))
    except politique.PolitiqueError as exc:
        return _err(str(exc))
    return 0


def cmd_budget(a) -> int:
    from . import budgets
    try:
        if a.action == "voir":
            print(budgets.texte())
        elif a.action == "verifier":
            if len(a.quoi) < 2:
                return _err("usage : jarvis budget verifier <catégorie> <montant> [--projet P]")
            ok, raison = budgets.verifier(a.quoi[0], float(a.quoi[1]), projet=a.projet or "")
            print(("admis — " if ok else "refusé — ") + raison)
            return 0 if ok else 1
        elif a.action == "definir":
            refused = _human_only("définir un budget")
            if refused is not None:
                return refused
            if len(a.quoi) < 2:
                return _err("usage : jarvis budget definir <catégorie> <plafond> [--projet P] [--periode mois|semaine|jour|unique] [--note …]")
            e = budgets.definir(a.quoi[0], float(a.quoi[1]), periode=a.periode or "mois", projet=a.projet or "",
                                note=" ".join(a.quoi[2:]))
            print(f"{e['id']} : {e['categorie']} {e['plafond']:g} par {e['periode']}" + (f" pour {e['projet']}" if e["projet"] else ""))
        elif a.action == "engager":
            if len(a.quoi) < 2:
                return _err("usage : jarvis budget engager <catégorie> <montant> [libellé] [--projet P] [--estime]")
            d = politique_depense(a)
            if d is not None:
                return d
            budgets.engager(a.quoi[0], float(a.quoi[1]), projet=a.projet or "", libelle=" ".join(a.quoi[2:]),
                            par=_acteur(), estime=bool(a.estime))
            print("dépense enregistrée")
        elif a.action == "encaisser":
            refused = _human_only("enregistrer un encaissement")
            if refused is not None:
                return refused
            if len(a.quoi) < 1 or not a.projet:
                return _err("usage : jarvis budget encaisser <montant> [libellé] --projet P")
            budgets.encaisser(float(a.quoi[0]), projet=a.projet, libelle=" ".join(a.quoi[1:]))
            print("encaissement enregistré")
    except ValueError as exc:
        return _err(str(exc))
    return 0


def politique_depense(a) -> int | None:
    """Une dépense réelle (non estimée) engagée par un agent passe par la politique : refus sans enveloppe/délégation."""
    if a.estime or _acteur() == "humain":
        return None
    from . import politique
    d = politique.autoriser("depense", acteur=_acteur(), projet=a.projet or "", montant=float(a.quoi[1]),
                            detail=" ".join(a.quoi[2:]), categorie=a.quoi[0])
    if d["decision"] != "admis":
        return _err(f"dépense refusée ({d['decision']}) : {d['raison']}", 7)
    return None


def cmd_fournisseurs(a) -> int:
    from . import fournisseurs
    caps = fournisseurs.capacites()
    print(json.dumps(caps, ensure_ascii=False, indent=2, default=str) if a.json else fournisseurs.texte(caps))
    return 0


def cmd_proposition(a) -> int:
    from . import travaux
    try:
        if a.action == "liste":
            print(travaux.texte(travaux.tous(a.statut)))
        elif a.action == "voir":
            t = travaux.get(a.quoi[0]) if a.quoi else None
            if not t:
                return _err("usage : jarvis proposition voir <W-xxxxx>")
            print(json.dumps(t, ensure_ascii=False, indent=2))
        elif a.action == "soumettre":
            if not a.titre:
                return _err("usage : jarvis proposition soumettre --source dot --titre … [--fichier contenu.md] [--type T] [--projet P]")
            contenu = Path(a.fichier).read_text(encoding="utf-8", errors="replace") if a.fichier else " ".join(a.quoi)
            t = travaux.soumettre(source=a.source or _acteur(), titre=a.titre, contenu=contenu, type_=a.type_ or "autre",
                                  projet=a.projet or "", par=_acteur())
            print(f"{t['id']}" + (" (doublon : proposition déjà connue)" if t["doublon"] else " soumise"))
        elif a.action in ("accepter", "rejeter"):
            if not a.quoi:
                return _err(f"usage : jarvis proposition {a.action} <W-xxxxx> [raison]")
            t = travaux.decider(a.quoi[0], a.action == "accepter", par=_acteur(), raison=" ".join(a.quoi[1:]))
            print(f"{t['id']} {t['statut']}." + (" Rien n'est lancé : propose un plan pour ce travail." if t["statut"] == "acceptee" else ""))
        elif a.action == "confier":
            if len(a.quoi) < 2:
                return _err("usage : jarvis proposition confier <W-xxxxx> local:claude|local:codex|codex-cloud [T-xxxxx|id cloud]")
            t = travaux.confier(a.quoi[0], a.quoi[1], a.quoi[2] if len(a.quoi) > 2 else "", par=_acteur())
            print(f"{t['id']} confié à {t['executant']}")
        elif a.action == "terminer":
            if len(a.quoi) < 2:
                return _err("usage : jarvis proposition terminer <W-xxxxx> <preuve> [--echec] [note]")
            t = travaux.terminer(a.quoi[0], preuve=a.quoi[1], verifie_par=_acteur(), ok=not a.echec, note=" ".join(a.quoi[2:]))
            print(f"{t['id']} {t['statut']}")
        elif a.action == "importer":
            depot = a.quoi[0] if a.quoi else config.settings().get("propositions", {}).get("github_depot", "")
            if not depot:
                return _err("usage : jarvis proposition importer <owner/depot> (ou réglage propositions.github_depot)")
            n = travaux.importer_github(depot)
            print(f"{len(n)} nouvelle(s) proposition(s) importée(s) depuis {depot}" + ("".join(f"\n  {t['id']} {t['titre']}" for t in n)))
    except travaux.TravauxError as exc:
        return _err(str(exc))
    except OSError as exc:
        return _err(str(exc))
    return 0


def cmd_eval(a) -> int:
    from . import evaluation
    try:
        if a.action == "liste":
            for c in evaluation.cas_tous(a.role or None):
                print(f"{c['nom']:<36} {c['titre']}")
            return 0
        if a.action == "verifier":
            res = evaluation.controle(a.role or None)
            for r in res:
                etat = "✔" if r["ok"] else "✘"
                motifs = []
                if not r["depart_refuse"]:
                    motifs.append("la vérification accepte le départ")
                if not r["reference_acceptee"]:
                    motifs.append("la vérification refuse la référence : " + r["detail"][:200])
                if r["exigences_manquantes"]:
                    motifs.append("brief du rôle sans : " + ", ".join(r["exigences_manquantes"]))
                print(f"{etat} {r['cas']}" + (f" — {' ; '.join(motifs)}" if motifs else ""))
            ko = sum(1 for r in res if not r["ok"])
            print(f"{len(res) - ko}/{len(res)} cas sains.")
            return 1 if ko else 0
        if a.action == "resultats":
            res = evaluation.resultats(a.n)
            if not res:
                print("Aucune évaluation réelle lancée (jarvis eval lancer <rôle>/<cas> --agent claude --confirmer).")
            for r in res:
                quand = time.strftime("%d/%m %H:%M", time.localtime(r["ts"]))
                print(f"{quand} {'✔' if r['ok'] else '✘'} {r['cas']:<34} {r['agent']}/{r['modele']:<12} brief {r['brief']} "
                      f"· {r['duree_s']:.0f} s")
            return 0
        if a.action == "promptfoo":
            print(evaluation.promptfoo_config())
            return 0
        # lancer : un vrai agent consomme le quota de l'abonnement
        if os.environ.get("JARVIS_METIER") or os.environ.get("JARVIS_ROLE"):
            return _err("une évaluation réelle se lance par ton humain, pas par un agent ni par le chef.", 4)
        if not a.confirmer:
            return _err("une évaluation réelle consomme ton quota : ajoute --confirmer.")
        if not a.quoi:
            return _err("usage : jarvis eval lancer <rôle>/<cas> [--agent claude|codex] [--modele M] --confirmer")
        from . import admission
        try:
            r = evaluation.lancer(a.quoi[0], a.agent, a.modele or "", acteur=_acteur(), garder=a.garder)
        except admission.Refus as exc:
            return _err(exc.raison, _CODES_REFUS.get(exc.code, 2))
        if a.sortie_brute:
            # promptfoo (fournisseur exec:) : la sortie est jugée par l'assertion ; un code non nul serait une erreur.
            print("VERDICT: OK" if r["ok"] and not r["suspect"] else "VERDICT: ECHEC\n" + r["detail"])
            return 0
        else:
            print(f"{'✔ réussi' if r['ok'] else '✘ échoué'} — {r['cas']} par {r['agent']}/{r['modele']} en {r['duree_s']:.0f} s"
                  f" (brief {r['brief']})")
            if not r["ok"]:
                print(r["detail"])
            if r["suspect"]:
                print("⚠ Suspect : la sortie de l'agent mentionne les cas d'évaluation (références ou vérifications). "
                      "Résultat à ne pas compter avant relecture.")
            if r.get("dossier"):
                print(f"Projet conservé : {r['dossier']}")
        return 0 if r["ok"] else 1
    except evaluation.EvalError as exc:
        return _err(str(exc))


def cmd_execution(a) -> int:
    """`jarvis execution lancer` : appelé par bin/jarvis pour démarrer un agent sur le backend du projet."""
    from . import admission, execution
    if os.environ.get("JARVIS_METIER"):
        return _err("un agent ne lance pas d'autre agent : propose la tâche au chef d'orchestre.", 4)
    # Seul un départ admis peut partir, une seule fois : réservation confirmée (fiche de tâche créée), active,
    # pour ce projet et ce worktree, jamais utilisée.
    if not admission.marquer_lance(a.reservation, a.projet, a.branche):
        return _err("aucune réservation d'admission confirmée et inutilisée pour ce lancement : passe par « jarvis task ».", 4)
    try:
        backend = execution.pour_projet(a.projet)
        r = backend.lancer(projet=a.projet, chemin=os.getcwd(), branche=a.branche, profil=a.agent, prompt=a.prompt)
    except execution.NonDisponible as exc:
        return _err(str(exc), 1)
    if backend.nom != "workmux":
        print(f"backend={r['backend']} cible={r['cible']}")
    return 0


def cmd_rejouer(a) -> int:
    from . import evenements
    try:
        evs = evenements.chronologie(a.tache)
    except ValueError as exc:
        return _err(str(exc))
    print(f"Chronologie de {a.tache.upper()} (reconstruction à partir des registres ; rien n'est réexécuté)")
    print(evenements.texte(evs, a.depuis))
    return 0


def cmd_traces(a) -> int:
    from . import observabilite
    if a.action == "exporter":
        print(f"Traces OpenTelemetry (JSON) écrites : {observabilite.exporter_fichier(a.jours)}")
        return 0
    if a.action == "envoyer":
        ok, msg = observabilite.envoyer(a.jours)
        print(("✔ " if ok else "✘ ") + msg)
        return 0 if ok else 1
    from . import couts, taches
    for r in observabilite.dernieres_executions(a.n):
        print(f"{r['id']} {r['projet']} {r['issue']:<10} {r['role']:<12} {r['modele']:<14} "
              f"{taches.STATUTS.get(r['statut'], r['statut']):<12} {r['duree_min']:>6.1f} min "
              f"{taches.fmt_jetons(r['jetons']):>7} {couts.monnaie(r['usd'])}{' *' if r['estimation'] else ''}"
              + (f" · échec {r['echec']}" if r["echec"] else ""))
    return 0


def cmd_proxy(a) -> int:
    from . import proxy
    if a.action == "config":
        chemin = proxy.ecrire()
        r = proxy.reglages()
        print(f"Configuration LiteLLM écrite : {chemin}")
        print("Pour les fonctions IA des PRODUITS seulement (jamais pour les agents, qui sont sur abonnement).")
        print("État : " + ("activé dans ton catalogue" if r["actif"] else "désactivé (proxy.actif = false)")
              + f". Lancer toi-même : litellm --config {chemin} --port {r['port']} (installation et clés d'API à ta charge).")
        return 0
    print(json.dumps(proxy.configuration(), ensure_ascii=False, indent=2))
    return 0


def cmd_skill(a) -> int:
    """Registre des skills : audit, installation en quarantaine, décision humaine, épinglage."""
    from . import skills
    try:
        if a.action in ("liste", "auditer"):
            audit = skills.auditer()
            print(skills.texte(audit))
            pb = skills.problemes(audit)
            if pb and a.action == "auditer":
                print(f"\n⚠ {len(pb)} skill(s) à examiner : modifiées, non épinglées ou hors registre.")
                return 1
            return 0
        if not a.quoi:
            return _err(f"jarvis skill {a.action} : précise la skill (ou la source)")
        if a.action == "installer":
            r = skills.installer(a.quoi, par=_acteur())
            print(f"Skill « {r['nom']} » en quarantaine : {r['quarantaine']}")
            print(f"{r['fichiers']} fichier(s), empreinte {r['empreinte']}, signature : {r['signature']}.")
            print("Rien n'est actif. Activation : bouton Telegram ou « jarvis skill approuver " + r["nom"] + " » au terminal."
                  if r["envoye"] else "Telegram injoignable : approuve au terminal avec « jarvis skill approuver " + r["nom"] + " ».")
            return 0
        refused = _human_only(f"{a.action} une skill")
        if refused is not None:
            return refused
        if a.action in ("approuver", "refuser"):
            r = skills.decider(a.quoi, a.action == "approuver", par="humain")
            print(f"Skill « {r['nom']} » activée : {r['chemin']}" if r["active"] else f"Skill « {r['nom']} » refusée, copie supprimée.")
            return 0
        lock = skills.epingler(a.quoi, version=a.version, auteur=a.auteur, cle=a.signer)
        print(f"« {lock['nom']} » épinglée : {lock['empreinte']}" + (" (signée)" if lock.get("signature") else " (non signée)"))
        return 0
    except skills.SkillError as exc:
        return _err(str(exc))


def cmd_stockage(a) -> int:
    """État du stockage ; migration JSON → SQLite et retour (toi seulement, démon arrêté)."""
    from . import stockage
    if a.action == "etat":
        e = stockage.etat()
        print(f"Stockage : {e['backend']} · base {e['base']} "
              + (f"({e['lignes']} états, {e['taille_ko']} Ko)" if e["base_existe"] else "(pas encore créée)")
              + f" · {e['fichiers_json']} fichier(s) JSON")
        return 0
    refused = _human_only("changer le stockage")
    if refused is not None:
        return refused
    try:
        if a.action == "migrer":
            r = stockage.migrer(par="humain")
            print(f"{r['importes']} état(s) importés dans {r['base']} et vérifiés ; stockage basculé en SQLite.")
            print(f"Copie des JSON : {r['sauvegarde']}. Retour possible : jarvis stockage revenir.")
            for i in r["ignores"]:
                print(f"⚠ ignoré (illisible) : {i}")
        else:
            r = stockage.revenir(par="humain")
            print(f"{r['exportes']} état(s) réécrits en JSON et vérifiés ; stockage rebasculé en JSON ({r['sauvegarde']}).")
        return 0
    except stockage.StockageError as exc:
        return _err(str(exc))


def cmd_executant(a) -> int:
    from . import executants
    try:
        if a.action == "liste":
            print(executants.texte())
            return 0
        refused = _human_only("déclarer ou retirer un exécutant")
        if refused is not None:
            return refused
        if not a.nom:
            return _err("précise le nom de l'exécutant")
        if a.action == "retirer":
            return 0 if executants.retirer(a.nom) else _err(f"exécutant « {a.nom} » inconnu")
        cap = {"coeurs": a.coeurs, "memoire_mo": a.memoire_mo, "agents_max": a.agents_max} if a.nom != "local" else None
        e = executants.declarer(a.nom, hote=a.hote, capacite=cap, par="humain")
        print(f"Exécutant « {a.nom} » déclaré ({e.get('hote') or 'hôte inconnu'}). L'admission n'utilise encore que ce poste.")
        return 0
    except executants.ExecutantError as exc:
        return _err(str(exc))


def cmd_rollback(a) -> int:
    from . import rollback
    try:
        if a.action == "proposer":
            print(rollback.texte(rollback.proposer(a.tache)))
        elif a.action == "demander":
            p = rollback.demander(a.tache, par=_acteur())
            print(rollback.texte(p))
            if p.get("envoye"):
                print("\nEnvoyé à ton humain sur Telegram (boutons Revert / Garder). Rien n'est fait sans son clic.")
            else:
                print("\n⚠ Telegram injoignable ou non configuré : rien n'est parti. La demande est notée ; ton humain peut "
                      "exécuter « jarvis rollback executer " + p["tache"] + " » dans son terminal.")
                return 1
        else:
            refused = _human_only("exécuter un rollback")
            if refused is not None:
                return refused
            r = rollback.executer(a.tache, par="humain", autorise_terminal=True)
            print(f"↩ {len(r['commits'])} commit(s) défaits par revert dans le worktree de {r['tache']}.")
    except rollback.RollbackError as exc:
        return _err(str(exc))
    return 0


def cmd_secrets(a) -> int:
    from . import secrets
    if not a.projet:
        return _err("usage : jarvis secrets verifier --projet <nom>")
    try:
        print("\n".join(secrets.verifier(a.projet)))
    except secrets.SecretsError as exc:
        return _err(str(exc))
    return 0


def _identite_coureur() -> Path:
    return config.STATE_DIR / "coureur" / "identite.json"


def cmd_mission(a) -> int:
    """Jarvis Next (M1) : missions durables sur ce poste, tenant local unique."""
    from . import adaptateurs, coureur, missions
    org = missions.tenant_local()
    try:
        if a.action == "liste":
            for m in missions.missions(org):
                print(f"{m['id']}  {m['statut']:<9} {m['source']:<6} {m['objectif'][:80]}")
            return 0
        if a.action == "voir":
            print(missions.texte_mission(missions.mission(org, a.cible)))
            return 0
        if a.action == "evenements":
            for e in missions.evenements(org, apres=a.apres):
                print(f"{e['seq']:>6} {time.strftime('%H:%M:%S', time.localtime(e['ts']))} {e['type']:<16} "
                      f"{e['tache_id'] or e['mission_id'] or ''} {json.dumps(e['donnees'], ensure_ascii=False)}")
            return 0
        if a.action == "approbations":
            for p in missions.approbations_en_attente(org):
                print(f"{p['id']}  {p['niveau']} {p['type']} ({p['tache_id']}, mission {p['mission_id']})\n"
                      f"    travail : {p['travail'][:300]}")
            return 0
        if a.action == "board":
            texte = " ".join([a.cible, *a.texte]).strip()
            if texte:
                o = missions.board_ajouter(org, a.espace, a.type, texte, auteur=getpass.getuser())
                print(f"Objet {o['objet_id']} ajouté." + (f" Mission d'analyse {o['mission_id']} créée." if
                                                          o["mission_id"] else ""))
                return 0
            for o in missions.board(org, a.espace):
                print(f"{o['id']} [{o['type']}] {o['contenu'][:70]!r} → {o.get('mission_statut') or '—'}")
                for art in o.get("artefacts", []):
                    marque = " FACTICE" if art["factice"] else ""
                    print(f"    ▸ {art['id']} ({art['fournisseur']}{marque}) {art['contenu'][:200]!r}")
            return 0
        if a.action == "creer":
            texte = Path(a.fichier).read_text(encoding="utf-8") if a.fichier else " ".join(a.texte)
            m = missions.creer_mission(
                org, a.cible or "Analyser un document",
                [{"type": "analyse_document", "niveau": a.niveau, "capacites": ["analyse"],
                  "fournisseur": a.fournisseur, "travail": {"document": texte}}],
                source="cli", demandeur=f"cli:{getpass.getuser()}")
            print(missions.texte_mission(missions.mission(org, m["mission_id"])))
            return 0
        if a.action == "recuperer":
            print(missions.recuperer())
            return 0
        refused = _human_only(f"« jarvis mission {a.action} »")
        if refused is not None:
            return refused
        if a.action in ("approuver", "refuser"):
            r = missions.decider_approbation(org, a.cible, a.action == "approuver", acteur=getpass.getuser(),
                                             acteur_type="humain")
            print(f"Approbation {a.cible} : {r}.")
            return 0
        if a.action == "annuler":
            print(f"{missions.annuler_mission(org, a.cible, par=getpass.getuser())} tâche(s) annulée(s).")
            return 0
        if a.action == "connexion":
            missions.declarer_connexion(org, a.cible, a.mode)
            print(f"Connexion « {a.cible} » ({a.mode}) déclarée. Aucun identifiant n'est stocké par Jarvis.")
            return 0
        if a.action == "arret":
            missions.arret_urgence(org, a.cible != "off", par=getpass.getuser())
            print("Arrêt d'urgence " + ("levé." if a.cible == "off" else "posé : plus aucune tâche n'est confiée."))
            return 0
        if a.action == "enroler":
            fournisseurs = [f for f in a.fournisseurs.split(",") if f]
            rid, secret = missions.enroler_executant(org, a.cible or "local", capacites=["analyse"],
                                                     fournisseurs=fournisseurs, profil="PERSONAL_LOCAL")
            chemin = _identite_coureur()
            chemin.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump({"id": rid, "secret": secret}, fh)
            print(f"Exécutant {rid} enrôlé ({', '.join(fournisseurs)}). Identité dans {chemin} (600).")
            return 0
        if a.action == "studio":
            from . import studio_api, web
            valeur = studio_api.jeton(nouveau=a.nouveau_jeton)
            try:
                httpd = studio_api.serveur(a.port)
            except OSError as exc:
                return _err(f"port {a.port} indisponible ({exc}) : jarvis mission studio --port 7719")
            url = studio_api.lien(a.port, valeur)
            url_v2 = f"http://localhost:{a.port}/v2/connexion#{valeur}"
            v2 = (studio_api.DOSSIER_V2 / "index.html").exists()
            print(f"Jarvis Studio : {url}" + (f"\nBoard V2     : {url_v2}" if v2 else "")
                  + "\n(ces liens contiennent ton jeton d'accès : ne les partage pas). Ctrl+C pour arrêter.")
            web._ouvrir(url_v2 if v2 else url)
            import signal
            import threading
            precedents = {}
            def interrompre_studio(*_):
                raise KeyboardInterrupt
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM, signal.SIGHUP):
                    precedents[sig] = signal.signal(sig, interrompre_studio)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                for sig in precedents:
                    signal.signal(sig, signal.SIG_IGN)
                httpd.arret.set()
                try:
                    httpd.server_close()
                finally:
                    for sig, ancien in precedents.items():
                        signal.signal(sig, ancien)
            return 0
        if a.action == "executer":
            try:
                ident = json.loads(_identite_coureur().read_text())
            except (OSError, json.JSONDecodeError):
                return _err("aucun exécutant enrôlé : jarvis mission enroler --fournisseurs claude")
            verrou = coureur.prendre_verrou(ident["id"])
            if verrou is None:
                return _err("cet exécutant tourne déjà (dans le démon Jarvis ou un autre terminal) : "
                            "les missions avancent seules, rien à lancer")
            disponibles = {**adaptateurs.par_defaut(), "factice": adaptateurs.Factice()}
            cr = coureur.Coureur(coureur.TransportLocal(ident["id"], ident["secret"]), disponibles)
            for i in range(a.fois):
                missions.recuperer()
                r = cr.tour()
                print(json.dumps(r, ensure_ascii=False))
                if r["etat"] in ("vide", "arret") and i + 1 < a.fois:
                    time.sleep(a.attente)
            return 0
        return _err(f"action inconnue : {a.action}")
    except missions.MissionError as exc:
        return _err(str(exc))


def cmd_memoire(a) -> int:
    from . import memoire
    try:
        if a.action == "noter":
            if not a.titre:
                return _err("usage : jarvis memoire noter --titre \"…\" [--decisions \"a ; b\"] [--echecs …] [--lecons …] [--projet P] [corps]")
            e = memoire.noter(titre=a.titre, corps=" ".join(a.quoi), decisions=a.decisions, echecs=a.echecs,
                              lecons=a.lecons, projet=a.projet or "", etiquettes=a.etiquettes, source=_acteur())
            print(f"{e['id']} noté : {e['titre']}")
        elif a.action == "chercher":
            if not a.quoi:
                return _err("usage : jarvis memoire chercher <mots…> [--projet P] [--jours 90]")
            print(memoire.texte(memoire.chercher(" ".join(a.quoi), jours=a.jours, projet=a.projet or "", limite=a.n), a.jours))
        else:
            entrees = memoire.toutes()[-a.n:]
            if not entrees:
                print("Mémoire vide. À la fin de chaque vague : jarvis memoire noter --titre … --lecons …")
            for e in entrees:
                quand = time.strftime("%d/%m/%Y", time.localtime(e.get("ts", 0)))
                print(f"{e['id']} [{quand}{', ' + e['projet'] if e.get('projet') else ''}] {e['titre']}")
    except ValueError as exc:
        return _err(str(exc))
    return 0


def cmd_board(a) -> int:
    """Le Board partagé (même source que le Studio et Telegram) : le chef le lit et l'alimente."""
    from . import board, missions, synchro
    org = missions.tenant_local()
    espace = board.nom_espace(a.espace)
    acteur = _acteur()
    try:
        if a.action == "voir":
            print(synchro.texte_board(org, espace, detail=True))
        elif a.action == "espaces":
            for e in board.espaces(org):
                print(f"{e['nom']:<24} {e['objets']:>4} carte(s){'  (projet)' if e['projet'] else ''}")
        elif a.action == "deposer":
            texte = " ".join(a.quoi).strip()
            if not texte:
                return _err('usage : jarvis board deposer --espace P [--titre "…"] [--analyser] <texte ou lien>')
            x, y = synchro.position_libre(org, espace)
            lien = synchro.URL.fullmatch(texte)
            o = missions.board_ajouter(org, espace, "lien" if lien else "note", texte, auteur=acteur, x=x, y=y,
                                       largeur=434 if lien else 408, hauteur=356 if lien else 320,
                                       meta={"titre": (a.titre or texte.split(chr(10))[0])[:80], "source": acteur},
                                       analyser=False, contextualiser=a.analyser)
            print(f"{o['objet_id']} déposé sur le Board {espace}" + (" (analyse lancée)" if o.get("mission_id") else ""))
        elif a.action == "commenter":
            if len(a.quoi) < 2:
                return _err("usage : jarvis board commenter BO-… <texte>")
            print(board.commenter(org, a.quoi[0], " ".join(a.quoi[1:]), auteur=acteur))
        elif a.action == "lier":
            if len(a.quoi) != 2 or a.nature not in synchro.NATURES:
                return _err("usage : jarvis board lier BO-source BO-cible --nature inspire|alimente|utilise|depend")
            o = synchro._objet(org, a.quoi[0])
            if o is None:
                return _err(f"objet inconnu : {a.quoi[0]}")
            # une relation posée par le chef ou un agent porte l'auteur « jarvis » : visible et retirable sur le Board
            print(board.lier(org, o["espace"], a.quoi[0], a.quoi[1], libelle=synchro.NATURES[a.nature], style=a.nature,
                             par="jarvis:" + acteur if acteur != "humain" else "humain"))
        elif a.action == "decider":
            if len(a.quoi) != 3 or a.quoi[2] not in ("lancer", "ecarter") or not a.quoi[1].isdigit():
                return _err("usage : jarvis board decider BO-… <numéro d'action> lancer|ecarter")
            r = missions.decider_proposition(org, a.quoi[0], int(a.quoi[1]) - 1, a.quoi[2], par=acteur)
            print(f"mission {r['mission_id']} créée (préparation L1)" if r.get("mission_id") else "action écartée")
    except missions.MissionError as exc:
        return _err(str(exc))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis", description="Poste de pilotage des agents IA")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("os", help="contrats, diagnostic de capacités et mandats personnels")
    s.add_argument("arguments", nargs=argparse.REMAINDER)
    def os_commande(a):
        from . import os_cli
        return os_cli.main(a.arguments)
    s.set_defaults(fn=os_commande)

    s = sub.add_parser("etat", help="état des agents, plans et projets")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_etat)

    s = sub.add_parser("fil", help="derniers événements")
    s.add_argument("n", nargs="?", type=int, default=30)
    s.set_defaults(fn=cmd_fil)

    plan = sub.add_parser("plan", help="plans proposés par le chef").add_subparsers(dest="action", required=True)
    s = plan.add_parser("nouveau", help="proposer un plan à valider")
    s.add_argument("--titre", required=True)
    s.add_argument("--item", action="append", default=[], required=True, metavar="projet:ISSUE:agent[/modèle][@rôle][+taille][:desc]",
                   help="agent : claude, codex ou auto (le routeur choisit) ; taille S, M ou L")
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
    s.add_argument("--revue", action="store_true")
    s.add_argument("--worktree", default="")
    s.add_argument("--consignes-empreinte", default="")
    s.set_defaults(fn=cmd_plan_verifier)
    s = plan.add_parser("relacher", help=argparse.SUPPRESS)
    s.add_argument("id")
    s.add_argument("projet")
    s.add_argument("issue")
    s.add_argument("agent")
    s.set_defaults(fn=cmd_plan_relacher)

    s = sub.add_parser("capacite", help="reste-t-il une place pour un agent ?")
    s.set_defaults(fn=cmd_capacite)

    adm = sub.add_parser("admission", help="point d'admission commun des lancements").add_subparsers(dest="action", required=True)
    s = adm.add_parser("etat", help="réservations et opérations lourdes en cours")
    s.set_defaults(fn=cmd_admission)
    s = adm.add_parser("demander", help=argparse.SUPPRESS)
    s.add_argument("projet")
    s.add_argument("issue")
    s.add_argument("agent")
    s.add_argument("--origine", default="cli", choices=("cli", "reprise", "relance", "sous-agent"))
    s.add_argument("--worktree", default="")
    s.add_argument("--role", default="")
    s.add_argument("--classe", default="")
    s.add_argument("--taille", default="M")
    s.add_argument("--consignes-empreinte", default="")
    s.add_argument("--forcer", action="store_true", help="passer outre la capacité (humain seulement, jamais les pauses)")
    s.set_defaults(fn=cmd_admission)
    s = adm.add_parser("liberer", help=argparse.SUPPRESS)
    s.add_argument("id")
    s.add_argument("raison", nargs="*")
    s.set_defaults(fn=cmd_admission)

    s = sub.add_parser("pause", help="pauses par cause : humain, batterie, quota, ressources, incident, maintenance")
    s.add_argument("action", nargs="?", default="etat", choices=("etat", "poser", "lever"))
    s.add_argument("cause", nargs="?", default="humain")
    s.add_argument("note", nargs="*")
    s.set_defaults(fn=cmd_pause)

    s = sub.add_parser("profil", help="profils de poste (laptop-conservative, workstation)")
    s.add_argument("action", nargs="?", default="liste", choices=("liste", "voir", "appliquer"))
    s.add_argument("nom", nargs="?")
    s.set_defaults(fn=cmd_profil)

    s = sub.add_parser("lourd", help="déclarer une opération lourde (compilation, tests, navigateur, vidéo)")
    s.add_argument("action", choices=("debut", "fin", "exec", "liste"))
    s.add_argument("quoi", nargs="*", help="debut <classe> [desc] · fin <L-xxxxx> · exec <classe> -- commande… "
                                           "(les options --duree/--attente/--worktree se placent AVANT la classe)")
    s.add_argument("--worktree", default="")
    s.add_argument("--duree", type=int, default=120, help="durée maximale prévue en minutes (défaut 120)")
    s.add_argument("--attente", type=int, default=30, help="exec : minutes d'attente maximales d'une place (défaut 30)")
    s.set_defaults(fn=cmd_lourd)

    s = sub.add_parser("audit", help="journal d'audit (admissions, pauses, politique, budgets)")
    s.add_argument("n", nargs="?", type=int, default=40)
    s.add_argument("--type", dest="type_", default=None)
    s.add_argument("--verifier", action="store_true", help="contrôler la chaîne d'empreintes")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("politique", help="politique de délégation (niveaux 1/2/3), délégations et exceptions")
    s.add_argument("action", nargs="?", default="voir",
                   choices=("voir", "verifier", "deleguer", "revoquer", "exceptions", "exception", "appliquer"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--projet", default="")
    s.add_argument("--montant", type=float, default=0.0)
    s.add_argument("--categorie", default="depense", help="catégorie de budget du montant (depense, services, acquisition…)")
    s.add_argument("--perimetre", default="")
    s.add_argument("--plafond", type=float, default=0.0)
    s.add_argument("--jours", type=int, default=7)
    s.set_defaults(fn=cmd_politique)

    s = sub.add_parser("budget", help="enveloppes de dépense (non renseignée = zéro) et mouvements")
    s.add_argument("action", nargs="?", default="voir", choices=("voir", "verifier", "definir", "engager", "encaisser"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--projet", default="")
    s.add_argument("--periode", default="mois")
    s.add_argument("--estime", action="store_true", help="dépense estimée (comparée au réel plus tard)")
    s.set_defaults(fn=cmd_budget)

    s = sub.add_parser("fournisseurs", help="capacités déclarées de Claude et Codex (modèles, quotas, fraîcheur)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_fournisseurs)

    s = sub.add_parser("proposition", help="file de travaux partagée (dot, GitHub, humain) : propositions → travaux vérifiés")
    s.add_argument("action", nargs="?", default="liste",
                   choices=("liste", "voir", "soumettre", "accepter", "rejeter", "confier", "terminer", "importer"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--source", default="")
    s.add_argument("--titre", default="")
    s.add_argument("--fichier", default="")
    s.add_argument("--type", dest="type_", default="")
    s.add_argument("--projet", default="")
    s.add_argument("--statut", default=None)
    s.add_argument("--echec", action="store_true")
    s.set_defaults(fn=cmd_proposition)

    s = sub.add_parser("diagnostic", help="inventaire léger du poste (rapport expurgé)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--sans-windows", action="store_true", help="ne pas interroger PowerShell")
    s.set_defaults(fn=cmd_diagnostic)

    s = sub.add_parser("demander", help="poser une question à l'humain (Telegram + notification)")
    s.add_argument("texte", nargs="+")
    s.set_defaults(fn=cmd_demander)

    s = sub.add_parser("note", help="écrire un bilan dans le journal du chef")
    s.add_argument("texte", nargs="+")
    s.add_argument("--envoyer", action="store_true", help="envoyer aussi le bilan sur Telegram")
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("eval", help="harnais d'évaluation des rôles (cas fixes jugés par scripts)")
    s.add_argument("action", nargs="?", default="liste", choices=("liste", "verifier", "lancer", "resultats", "promptfoo"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--role", default="")
    s.add_argument("--agent", default="claude", choices=("claude", "codex"))
    s.add_argument("--modele", default="")
    s.add_argument("--confirmer", action="store_true", help="lancer : accepter de consommer du quota")
    s.add_argument("--garder", action="store_true", help="lancer : conserver le projet produit par l'agent")
    s.add_argument("--sortie-brute", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("-n", type=int, default=30)
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("rejouer", help="chronologie d'une tâche (plan, admission, tours, verdict, fin)")
    s.add_argument("tache")
    s.add_argument("--depuis", type=int, default=1)
    s.set_defaults(fn=cmd_rejouer)

    s = sub.add_parser("traces", help="observabilité : dernières exécutions, export OpenTelemetry")
    s.add_argument("action", nargs="?", default="liste", choices=("liste", "exporter", "envoyer"))
    s.add_argument("--jours", type=float, default=7)
    s.add_argument("-n", type=int, default=20)
    s.set_defaults(fn=cmd_traces)

    s = sub.add_parser("proxy", help="configuration LiteLLM pour les fonctions IA des produits (désactivé)")
    s.add_argument("action", nargs="?", default="voir", choices=("voir", "config"))
    s.set_defaults(fn=cmd_proxy)

    s = sub.add_parser("rollback", help="défaire par revert les commits d'une tâche (toujours avec ton accord)")
    s.add_argument("action", choices=("proposer", "demander", "executer"))
    s.add_argument("tache")
    s.set_defaults(fn=cmd_rollback)

    s = sub.add_parser("skill", help="registre des skills : audit, quarantaine, approbation, épinglage")
    s.add_argument("action", nargs="?", default="liste", choices=("liste", "auditer", "installer", "approuver", "refuser", "epingler"))
    s.add_argument("quoi", nargs="?", default="")
    s.add_argument("--version", default="")
    s.add_argument("--auteur", default="")
    s.add_argument("--signer", default="", metavar="CLE_SSH", help="epingler : signer avec cette clé (ssh-keygen -Y sign)")
    s.set_defaults(fn=cmd_skill)

    s = sub.add_parser("stockage", help="stockage de l'état : JSON (défaut) ou SQLite, migration vérifiée")
    s.add_argument("action", nargs="?", default="etat", choices=("etat", "migrer", "revenir"))
    s.set_defaults(fn=cmd_stockage)

    s = sub.add_parser("executant", help="exécutants déclarés (machines) et bail d'orchestrateur")
    s.add_argument("action", nargs="?", default="liste", choices=("liste", "declarer", "retirer"))
    s.add_argument("nom", nargs="?", default="")
    s.add_argument("--hote", default="")
    s.add_argument("--coeurs", type=int, default=0)
    s.add_argument("--memoire-mo", type=int, default=0)
    s.add_argument("--agents-max", type=int, default=0)
    s.set_defaults(fn=cmd_executant)

    s = sub.add_parser("mission", help="Jarvis Next (M1) : missions durables, Board, exécutant local")
    s.add_argument("action", nargs="?", default="liste",
                   choices=("liste", "voir", "evenements", "approbations", "board", "creer", "recuperer",
                            "approuver", "refuser", "annuler", "connexion", "arret", "enroler", "executer",
                            "studio"))
    s.add_argument("cible", nargs="?", default="", help="identifiant, objectif, fournisseur ou on/off selon l'action")
    s.add_argument("texte", nargs="*", help="texte à ajouter au Board ou document à analyser")
    s.add_argument("--espace", default="accueil")
    s.add_argument("--type", default="note")
    s.add_argument("--niveau", default="L1", choices=("L0", "L1", "L2", "L3", "L4"))
    s.add_argument("--fournisseur", default="auto")
    s.add_argument("--fichier", default="")
    s.add_argument("--mode", default="abonnement", choices=("abonnement", "api", "factice"))
    s.add_argument("--fournisseurs", default="claude,codex")
    s.add_argument("--apres", type=int, default=0)
    s.add_argument("--fois", type=int, default=1)
    s.add_argument("--attente", type=float, default=5.0)
    s.add_argument("--port", type=int, default=7718, help="studio : port local (127.0.0.1)")
    s.add_argument("--nouveau-jeton", action="store_true", help="studio : remplace le jeton et ferme les sessions")
    s.set_defaults(fn=cmd_mission)

    s = sub.add_parser("execution", help=argparse.SUPPRESS)
    s.add_argument("action", choices=("lancer",))
    s.add_argument("--projet", required=True)
    s.add_argument("--branche", required=True)
    s.add_argument("--agent", required=True, choices=("cc", "cx"))
    s.add_argument("--prompt", required=True)
    s.add_argument("--reservation", default="")
    s.set_defaults(fn=cmd_execution)

    s = sub.add_parser("secrets", help="secrets minimaux par rôle : ce que recevrait chaque agent (noms seuls)")
    s.add_argument("action", choices=("verifier",))
    s.add_argument("--projet", default="")
    s.set_defaults(fn=cmd_secrets)

    s = sub.add_parser("board", help="le Board partagé : voir, déposer, commenter, relier, décider (chef compris)")
    s.add_argument("action", nargs="?", default="voir", choices=("voir", "espaces", "deposer", "commenter", "lier", "decider"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--espace", default="accueil", help="Board du projet (accueil par défaut)")
    s.add_argument("--titre", default="")
    s.add_argument("--nature", default="alimente")
    s.add_argument("--analyser", action="store_true", help="faire contextualiser la carte déposée")
    s.set_defaults(fn=cmd_board)

    s = sub.add_parser("memoire", help="mémoire du chef : décisions, échecs, leçons (recherche pondérée)")
    s.add_argument("action", nargs="?", default="liste", choices=("noter", "chercher", "liste"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--titre", default="")
    s.add_argument("--decisions", default="")
    s.add_argument("--echecs", default="")
    s.add_argument("--lecons", default="")
    s.add_argument("--etiquettes", default="")
    s.add_argument("--projet", default="")
    s.add_argument("--jours", type=int, default=90)
    s.add_argument("-n", type=int, default=8)
    s.set_defaults(fn=cmd_memoire)

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

    nd = sub.add_parser("noeud", help="noeud GPU (Jetson) : outils sous mandat").add_subparsers(dest="action", required=True)
    s = nd.add_parser("config")
    s.add_argument("cible", help="utilisateur@adresse du noeud")
    s.set_defaults(fn=cmd_noeud_config)
    nd.add_parser("etat").set_defaults(fn=cmd_noeud_etat)

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
    s = sub.add_parser("fermer", help="fermer la fenêtre d'un agent terminé (worktree conservé)")
    s.add_argument("cible", nargs="?")
    s.add_argument("--termines", action="store_true", help="toutes les fenêtres d'agents terminés")
    s.set_defaults(fn=cmd_fermer)
    s = sub.add_parser("reprendre", help="relancer les agents interrompus par un redémarrage")
    s.add_argument("--essai", action="store_true", help="afficher sans rien relancer")
    s.set_defaults(fn=cmd_reprendre)
    sub.add_parser("reprise-preparer", help=argparse.SUPPRESS).set_defaults(fn=cmd_reprise_preparer)
    sub.add_parser("sante", help="état du PC").set_defaults(fn=cmd_sante)
    s = sub.add_parser("reparer-git", help="réparer le dépôt git d'un projet après un arrêt brutal")
    s.add_argument("projet")
    s.set_defaults(fn=cmd_reparer_git)
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
    sub.add_parser("chef-etat", help=argparse.SUPPRESS).set_defaults(fn=cmd_chef_etat)

    # --- Rôles, modèles, registre des tâches ---
    role = sub.add_parser("role", help="rôles spécialisés de l'usine")
    role.set_defaults(fn=cmd_role_liste)
    role_sub = role.add_subparsers(dest="action")
    role_sub.add_parser("liste").set_defaults(fn=cmd_role_liste)
    s = role_sub.add_parser("voir")
    s.add_argument("nom")
    s.set_defaults(fn=cmd_role_voir)
    s = role_sub.add_parser("candidats", help="briefs candidats et essais en cours ; avec RB-… : diff complet")
    s.add_argument("cible", nargs="?", default="", metavar="RB-0001")
    s.set_defaults(fn=cmd_role_version, action="candidats")
    s = role_sub.add_parser("proposer", help="proposer un brief candidat (ton humain décide)")
    s.add_argument("cible", metavar="role")
    s.add_argument("--fichier", required=True)
    s.add_argument("--pourquoi", required=True)
    s.set_defaults(fn=cmd_role_version, action="proposer")
    for act in ("approuver", "refuser", "retirer", "promouvoir"):
        s = role_sub.add_parser(act)
        s.add_argument("cible", metavar="RB-0001")
        s.add_argument("--pourquoi", default="")
        s.set_defaults(fn=cmd_role_version, action=act)

    modele = sub.add_parser("modele", help="catalogue des modèles et routeur")
    modele.set_defaults(fn=cmd_modele_liste)
    modele_sub = modele.add_subparsers(dest="action")
    modele_sub.add_parser("liste").set_defaults(fn=cmd_modele_liste)
    s = modele_sub.add_parser("choisir", help="affectation que le routeur choisirait")
    s.add_argument("--role", default="")
    s.add_argument("--taille", default="M")
    s.add_argument("--agent", default="auto")
    s.add_argument("--modele", default="")
    s.add_argument("--relit", default="", metavar="projet:ISSUE", help="contre-relecture : l'autre fournisseur")
    s.add_argument("--shell", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_modele_choisir)
    s = modele_sub.add_parser("verifier", help="essayer les modèles avec tes abonnements")
    s.add_argument("noms", nargs="*")
    s.set_defaults(fn=cmd_modele_verifier)
    s = modele_sub.add_parser("proposer", help="proposer un ajout ou une modification du catalogue")
    s.add_argument("nom")
    s.add_argument("--fournisseur", choices=("claude", "codex"))
    s.add_argument("--id", help="identifiant passé au CLI (--model)")
    s.add_argument("--niveau", type=int, choices=(1, 2, 3, 4))
    s.add_argument("--cout", type=int, choices=(1, 2, 3, 4, 5))
    s.add_argument("--effort", choices=("low", "medium", "high", "xhigh"))
    s.add_argument("--atouts", help="rôles séparés par des virgules")
    s.add_argument("--repli", help="Claude : modèles de repli séparés par des virgules")
    s.add_argument("--note")
    s.add_argument("--retirer", action="store_true", help="proposer de retirer ce modèle du routage")
    s.add_argument("--source", required=True, help="URL de la source (documentation officielle, annonce)")
    s.add_argument("--pourquoi", required=True)
    s.set_defaults(fn=cmd_modele_proposer)
    s = modele_sub.add_parser("ok", help="accepter une proposition")
    s.add_argument("id")
    s.set_defaults(fn=lambda a: cmd_modele_decision(a, True))
    s = modele_sub.add_parser("non", help="refuser une proposition")
    s.add_argument("id")
    s.set_defaults(fn=lambda a: cmd_modele_decision(a, False))

    s = sub.add_parser("tache", help="registre des tâches : liste, voir, echec, relancer")
    s.add_argument("quoi", nargs="*", metavar="[liste] [n] | voir <T> | echec <T> <classe> [note] | relancer <T> --autoriser",
                   help="nombre de tâches à afficher (20 par défaut), ou une action sur une tâche")
    s.add_argument("--autoriser", action="store_true", help="relancer : débloquer un essai après escalade (humain)")
    s.set_defaults(fn=cmd_tache_liste)
    s = sub.add_parser("budget-jetons", help="plafond de jetons d'une unité de travail")
    s.add_argument("action", choices=("voir", "defaut"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--role", default="")
    s.add_argument("--taille", default="M")
    s.set_defaults(fn=cmd_budget_jetons)
    s = sub.add_parser("cout", help="équivalent API des tâches (tâche, projet, semaine)")
    s.add_argument("action", nargs="?", default="semaine", choices=("tache", "projet", "semaine"))
    s.add_argument("quoi", nargs="*")
    s.add_argument("--periode", default="7j")
    s.add_argument("-n", type=int, default=10)
    s.set_defaults(fn=cmd_cout)
    s = sub.add_parser("tache-enregistrer", help=argparse.SUPPRESS)
    for opt in ("projet", "issue", "agent", "worktree"):
        s.add_argument(f"--{opt}", required=True)
    for opt in ("chemin", "role", "modele", "modele-id", "effort", "repli", "plan", "revue", "raison", "classe", "reservation",
                "jetons-max", "consignes-empreinte", "base", "brief"):
        s.add_argument(f"--{opt}", default="")
    s.add_argument("--taille", default="M")
    s.add_argument("--secours", action="store_true")
    s.set_defaults(fn=cmd_tache_enregistrer)
    s = sub.add_parser("tache-annuler", help=argparse.SUPPRESS)
    s.add_argument("id")
    s.set_defaults(fn=cmd_tache_annuler)
    s = sub.add_parser("lancement-args", help=argparse.SUPPRESS)
    s.add_argument("agent", choices=("claude", "codex"))
    s.set_defaults(fn=cmd_lancement_args)
    s = sub.add_parser("prompt-construire", help=argparse.SUPPRESS)
    for opt in ("projet", "issue", "branche", "regles"):
        s.add_argument(f"--{opt}", required=True)
    for opt in ("role", "revue", "consignes", "brief-sortie"):
        s.add_argument(f"--{opt}", default="")
    s.set_defaults(fn=cmd_prompt_construire)
    s = sub.add_parser("verdict", help="enregistrer le verdict d'une contre-relecture")
    s.add_argument("projet")
    s.add_argument("issue")
    s.add_argument("verdict", choices=("pret", "corrections"))
    s.add_argument("note", nargs="*")
    s.set_defaults(fn=cmd_verdict)
    s = sub.add_parser("bilan", help="ce que l'usine a produit ; « quotidien » : le bilan du matin")
    s.add_argument("quoi", nargs="?", choices=("quotidien",))
    s.add_argument("--envoyer", action="store_true", help="quotidien : l'envoyer aussi sur Telegram")
    s.add_argument("--jours", type=float, default=7)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_bilan)
    sub.add_parser("usine", help="les ateliers : qui travaille sur quoi").set_defaults(fn=cmd_usine)

    # --- Studio et livrables ---
    studio = sub.add_parser("studio", help="studio : contrôle des vidéos et visuels").add_subparsers(
        dest="action", required=True)
    s = studio.add_parser("verifier", help="contrôle technique + planche-contact")
    s.add_argument("fichier")
    s.add_argument("--duree-min", type=float)
    s.add_argument("--duree-max", type=float)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_studio_verifier)
    s = sub.add_parser("livrer", help="contrôler un livrable puis l'envoyer à l'humain (Telegram)")
    s.add_argument("fichier")
    s.add_argument("--titre")
    s.add_argument("--legende")
    s.add_argument("--forcer", action="store_true", help="envoyer malgré un contrôle en échec (humain seulement)")
    s.set_defaults(fn=cmd_livrer)
    s = sub.add_parser("livrables", help="livrables récents, ou dossier d'une issue")
    s.add_argument("projet", nargs="?")
    s.add_argument("issue", nargs="?")
    s.set_defaults(fn=cmd_livrables)

    s = sub.add_parser("web", help="tableau de bord dans le navigateur (lecture seule)")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=lambda a: _web(a))
    sub.add_parser("daemon", help="surveillance + Telegram").set_defaults(fn=lambda a: _daemon())
    sub.add_parser("cockpit", help="interface plein écran").set_defaults(fn=lambda a: _cockpit())
    return p


def _web(a) -> int:
    from . import web
    return web.main(a.port)


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
