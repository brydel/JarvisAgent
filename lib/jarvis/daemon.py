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
    "/usine — les ateliers : quel spécialiste travaille sur quoi\n"
    "/livrables — vidéos, visuels et rapports produits\n"
    "/modeles — catalogue des modèles et propositions à valider\n"
    "/bilan — ce que l'usine a produit cette semaine\n"
    "/sante — état du PC (mémoire, disque, Docker, batterie)\n"
    "/pause — bloque tout nouveau lancement\n"
    "/reprendre — lève ta pause (les causes automatiques restent)\n"
    "/pauses — causes de pause et réservations en cours\n"
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

    from . import admission, taches, usage
    try:
        closes = taches.synchroniser(agents, usage.task_tokens)
        _lancements_avortes([t for t in closes if t.get("jamais_demarre")], agents)
    except Exception as exc:  # noqa: BLE001 — le registre est un plus : la surveillance continue sans lui
        store.feed_add("erreur", f"registre des tâches : {exc}")
    try:
        admission.reconcilier(agents)  # réservations démarrées ou expirées (place rendue, plan relançable)
    except Exception as exc:  # noqa: BLE001
        store.feed_add("erreur", f"réservations : {exc}")
    fiches = taches.toutes()
    chef_up = ag.chef_running()
    for i, (kind, msg, a) in enumerate(events):
        fiche = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", "")) if a else None
        if fiche:
            msg = _avec_role(msg, fiche)
            events[i] = (kind, msg, a)
        store.feed_add(kind, msg, agent=(ag.target(a) if a else None))
        if kind in ("agent_done", "agent_waiting") and a:
            suite = _suite_pour_chef(fiche) if kind == "agent_done" else ""
            injected = chef_up and ag.chef_inject(
                f"[JARVIS événement] {msg}. Cible workmux : {ag.target(a)}. "
                "Lis sa sortie (jarvis voir) et son issue Linear, puis décide de la suite." + suite)
            if not injected and kind == "agent_waiting":
                # Personne pour lui répondre : on prévient l'humain directement.
                notify.alert("question", f"{msg} et le chef n'est pas lancé", windows=True)
    store.write_json(WATCH_STATE, {k: {"status": a["status"]} for k, a in cur.items()})
    return [{"type": k, "texte": m} for k, m, _ in events]


def _lancements_avortes(fiches: list[dict], agents: list[dict]) -> None:
    """Un lancement interrompu avant l'apparition de l'agent (commande coupée, délai dépassé) ne doit pas
    consommer son élément de plan en silence : il est rendu relançable et le chef est prévenu."""
    fenetres = {a["worktree"] for a in agents}
    for t in fiches:
        if t["worktree"] in fenetres:
            continue  # une fenêtre porte ce nom : on ne libère rien, au risque de lancer deux fois
        libere = False
        if t.get("plan"):
            try:
                plans.release(t["plan"], t["projet"], t["issue"], t["agent"])
                libere = True
            except plans.PlanError:
                pass
        if t.get("reservation"):
            from . import admission
            admission.liberer(t["reservation"], "tâche jamais démarrée", acteur="demon")
        msg = (f"{t['projet']} {t['issue']} ({t['agent']}) n'a jamais démarré"
               + (f" : l'élément est de nouveau lançable dans {t['plan']}" if libere else ""))
        store.feed_add("erreur", msg)
        ag.chef_inject(f"[JARVIS] {msg}. Vérifie « jarvis etat », puis relance-le si le plan est encore valide.")


def _avec_role(msg: str, fiche: dict) -> str:
    from . import modeles, roles
    r = roles.ou_defaut(fiche["role"])
    return f"{r['emoji']} {r['titre']} — {msg} [{modeles.libelle(fiche['agent'], fiche['modele'], fiche['effort'])}]"


def _suite_pour_chef(fiche: dict | None) -> str:
    """Ce que le chef doit faire d'une tâche terminée, selon son rôle : c'est la porte qualité de l'usine."""
    if not fiche:
        return ""
    from . import livrables, roles
    r = roles.ou_defaut(fiche["role"])
    autre = "codex" if fiche["agent"] == "claude" else "claude"
    if fiche.get("revue") or r["nom"] == "revue":
        return (f" C'est une contre-relecture : lis son verdict, puis enregistre-le avec « jarvis verdict "
                f"{fiche['projet']} {fiche['issue']} pret|corrections \"résumé\" ».")
    suite = ""
    if r["livrable"] != "pr":
        d = livrables.dossier(fiche["projet"], fiche["issue"], creer=False)
        suite += (f" Ses livrables sont dans {d} : contrôle chaque fichier (jarvis studio verifier, regarde la "
                  f"planche-contact), puis envoie ce qui est bon avec « jarvis livrer ».")
    if r["revue"] == "croisee":
        suite += (f" Travail produit par {fiche['agent']} : prévois sa contre-relecture par {autre} "
                  f"(élément {fiche['projet']}:{fiche['issue']}:{autre}@revue) avant de le déclarer prêt.")
    return suite


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
    st = store.read_json(BUDGET_STATE, {"niveaux": {}})
    from . import pauses
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
                from . import taches
                fiches = taches.toutes()
                for a in agents_now or []:
                    if a["status"] in ("working", "untracked", "silent") and p in (a["kind"] or "").lower():
                        ok, _ = ag.send(ag.target(a), STOP_MSG)
                        store.feed_add("systeme", f"arrêt demandé à {a['project']}/{a['worktree']} (jetons {name})")
                        fiche = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
                        if fiche:
                            # Arrêt pour quota : ce n'est pas un échec de l'agent, l'essai ne compte pas.
                            taches.classer(fiche["id"], "quota", source="auto", par="demon",
                                           note=f"jetons {name} épuisés", remplacer=False)
        elif old == "epuise":
            events.append(f"{name} rétabli")
            notify.alert("plan_ok", f"Jetons {name} rétablis ({_pct(u)}) : il peut reprendre du travail.",
                         title="JARVIS · jetons")
            ag.chef_inject(f"[JARVIS jetons] {name} est de nouveau disponible ({_pct(u)}).")

    both_out = all(s[p]["niveau"] == "epuise" for p in usage.PROVIDERS)
    # Cause « quota », indépendante des autres : la lever ne touche ni à ta pause ni à celle de la batterie.
    if both_out and cfg.get("pause_auto", True):
        if pauses.poser("quota", "Claude et Codex épuisés", par="demon"):
            events.append("pause auto")
            notify.alert("systeme", "Pause automatique (quota) : Claude et Codex sont épuisés. Reprise dès qu'un "
                                    "abonnement se libère.", title="JARVIS · jetons")
    elif not both_out and pauses.lever("quota", par="demon"):
        events.append("reprise auto")
        restantes = pauses.actives()
        notify.alert("plan_ok", "Fin de la pause quota : un abonnement a des jetons."
                     + (f" Jarvis reste en pause ({', '.join(sorted(restantes))})." if restantes else ""),
                     title="JARVIS · jetons")
        if not restantes:
            ag.chef_inject("[JARVIS jetons] Pause quota levée : reprends ta boucle en tenant compte des marges "
                           "(jarvis jetons).")
    store.write_json(BUDGET_STATE, st)
    return events


PREVISION_STATE = "prevision.json"
PREVISION_SEUIL_MIN = 45  # prévenir quand l'épuisement est prévu dans moins de N minutes


def prevision_check(now: float | None = None) -> list[str]:
    """Prévient avant l'épuisement : au rythme actuel, un abonnement tombera avant sa remise à zéro."""
    from . import usage
    now = now or time.time()
    s = usage.summary(now)
    usage.enregistrer_historique(s, now)
    st = store.read_json(PREVISION_STATE, {})
    events = []
    for p in usage.PROVIDERS:
        u = s[p]
        prev = u.get("prevision") or {}
        reset = (u.get("5h") or {}).get("resets_at") or 0
        proche = (prev.get("avant_reset") and prev.get("minutes") is not None
                  and prev["minutes"] <= PREVISION_SEUIL_MIN and u["niveau"] != "epuise")
        if not proche:
            continue
        if st.get(p) == reset:
            continue  # déjà signalé pour cette fenêtre
        st[p] = reset
        name = p.capitalize()
        events.append(f"{name} prévision")
        texte = (f"Au rythme actuel ({prev['rythme']:.0f} %/h), {name} atteindra son seuil d'arrêt dans "
                 f"{usage.fmt_duree(prev['minutes'])}, avant sa remise à zéro ({usage.fmt_reset(reset)}).")
        notify.alert("question", texte, title="JARVIS · jetons")
        ag.chef_inject(f"[JARVIS jetons] {texte} Ne lui confie plus de nouvelle tâche d'ici là et bascule ce qui "
                       f"peut l'être vers l'autre fournisseur.")
    store.write_json(PREVISION_STATE, st)
    return events


BLOCAGE_STATE = "blocage.json"


def blocage_check(now: float | None = None) -> list[str]:
    """Signale au chef les agents qui « travaillent » sans rien afficher, ou depuis trop longtemps."""
    cfg = config.settings()["general"]
    silence_max = int(cfg.get("blocage_min", 45)) * 60
    duree_max = int(cfg.get("duree_max_min", 240)) * 60
    if silence_max <= 0 and duree_max <= 0:
        return []
    found, _ = ag.status_all()
    if found is None:
        return []
    idle = ag.window_idle()
    st = store.read_json(BLOCAGE_STATE, {})
    encore: dict[str, list[str]] = {}
    events = []
    from . import taches
    fiches = None
    for a in found:
        if a["status"] == "waiting" and silence_max > 0 and a["elapsed"] >= silence_max:
            # Attend une réponse depuis longtemps : l'essai est « bloqué » (attend l'humain ou le chef).
            fiches = taches.toutes() if fiches is None else fiches
            fiche = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
            if fiche and not fiche.get("echec"):
                taches.classer(fiche["id"], "bloque", source="auto", par="demon",
                               note=f"attend une réponse depuis {ag.fmt_elapsed(a['elapsed'])}", remplacer=False)
        if a["status"] != "working":
            continue
        key = ag.target(a)
        deja = st.get(key, [])
        motifs = []
        silence = idle.get(a["window"])
        if silence_max > 0 and silence is not None and silence >= silence_max:
            motifs.append(("silence", f"n'affiche plus rien depuis {ag.fmt_elapsed(silence)}"))
        if duree_max > 0 and a["elapsed"] >= duree_max:
            motifs.append(("duree", f"travaille depuis {ag.fmt_elapsed(a['elapsed'])}"))
        encore[key] = [m for m, _ in motifs]
        nouveaux = [texte for m, texte in motifs if m not in deja]
        if not nouveaux:
            continue
        msg = f"{a['project']}/{a['worktree']} ({ag.kind_label(a['kind'])}) {' et '.join(nouveaux)}"
        events.append(key)
        store.feed_add("agent_bloque", msg, agent=key)
        if not ag.chef_inject(f"[JARVIS blocage] {msg}. Cible workmux : {key}. Lis sa sortie (jarvis voir) : s'il "
                              f"tourne en rond ou est figé, donne-lui une consigne corrective ; après deux échecs, "
                              f"demande-lui de s'arrêter et préviens ton humain."):
            notify.alert("question", f"{msg} et le chef n'est pas lancé")
    store.write_json(BLOCAGE_STATE, encore)
    return events


CHEF_STATE = "chef_garde.json"
CHEF_RELANCES_MAX = 3  # par heure : au-delà, c'est une panne à montrer à l'humain, pas à masquer
# Le chef a-t-il tourné sous les yeux de CE démon ? En mémoire, pas sur disque : après un redémarrage
# du PC ou un « jarvis start » sans « jarvis chef », personne ne doit lancer le chef à ta place.
_chef_vu = False


def chef_check(now: float | None = None) -> str | None:
    """Relance le chef s'il s'est arrêté alors qu'il reste du travail. Renvoie l'action faite."""
    import subprocess
    global _chef_vu
    now = now or time.time()
    if ag.chef_running():
        _chef_vu = True
        return None
    if not _chef_vu:
        return None  # jamais vu tourner par ce démon : ce n'est pas une panne
    found, _ = ag.status_all()
    occupes = sum(1 for a in found or [] if a["status"] in ag.BUSY)
    restant = sum(1 for p in plans.active() for i in p["items"] if not i["lance"])
    if not occupes and not restant and not plans.pending():
        _chef_vu = False  # arrêté sans rien laisser en cours : arrêt normal
        return None
    st = store.read_json(CHEF_STATE, {"alerte": 0})
    from . import admission
    # Aucune relance automatique en pause (quelle que soit la cause) : l'arrêt voulu par l'humain,
    # une maintenance ou un incident ne doivent jamais être contournés par le démon.
    auto = config.settings()["general"].get("chef_relance_auto", True) and not store.paused()
    if auto and admission.relance_autorisee("chef", CHEF_RELANCES_MAX, now)[0]:
        try:
            res = subprocess.run([str(config.JARVIS_HOME / "bin" / "jarvis"), "chef-lancer"],
                                 capture_output=True, text=True, timeout=120)
            ok = res.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            ok = False
        if ok:
            notify.alert("systeme", f"Le chef s'était arrêté ({occupes} agent(s) en cours, {restant} tâche(s) à "
                                    "lancer) : je l'ai relancé.", title="JARVIS · chef", windows=False)
            return "relance"
    if now - st.get("alerte", 0) > 3600:
        st["alerte"] = now
        store.write_json(CHEF_STATE, st)
        notify.alert("erreur", f"Le chef est arrêté alors qu'il reste du travail ({occupes} agent(s) en cours, "
                               f"{restant} tâche(s) approuvée(s) à lancer). Sur ton PC : jarvis chef",
                     title="JARVIS · chef")
        return "alerte"
    return None


MODELES_STATE = "modeles_garde.json"
_verif_en_cours = threading.Lock()


def modeles_check(now: float | None = None) -> bool:
    """Essaie les modèles du catalogue quand c'est dû (jamais essayés, ou essai trop ancien).

    Dans un fil à part : un essai prend plusieurs secondes par modèle. Renvoie True s'il est lancé.
    """
    from . import modeles, usage
    dus = modeles.a_verifier(now)
    if not dus or not _verif_en_cours.acquire(blocking=False):
        return False
    tous = len(dus) == sum(1 for m in modeles.catalogue().values() if m["actif"] and m["id"])

    def _run():
        try:
            avant = {k: (v or {}).get("ok") for k, v in modeles.etat_verif().items() if not k.startswith("_")}
            res = modeles.verifier(None if tous else dus, usage_resume=usage.summary())
            perdus = [n for n, r in res.items() if r["ok"] is False and avant.get(n) is not False]
            gagnes = [n for n, r in res.items() if r["ok"] is True and avant.get(n) is not True]
            if gagnes:
                store.feed_add("modele", f"modèles disponibles avec tes abonnements : {', '.join(gagnes)}")
            if perdus:
                notify.alert("question", f"Modèle(s) indisponible(s) avec tes abonnements : {', '.join(perdus)}. "
                                         "Le routeur utilise les autres. Détail : jarvis modele",
                             title="JARVIS · modèles", windows=False)
                ag.chef_inject(f"[JARVIS modèles] Indisponible(s) : {', '.join(perdus)}. Le routeur les ignore ; "
                               f"profite de ta prochaine veille des modèles pour proposer leur remplaçant.")
        except Exception as exc:  # noqa: BLE001
            store.feed_add("erreur", f"essai des modèles : {exc}")
        finally:
            _verif_en_cours.release()

    threading.Thread(target=_run, name="modeles", daemon=True).start()
    return True


def veille_modeles_check(now: float | None = None) -> bool:
    """Rappelle au chef la veille des modèles (nouveautés Claude et Codex) quand elle est due."""
    days = int(config.settings()["veille"].get("modeles_jours", 14))
    if days <= 0 or not ag.chef_running():
        return False
    now = now or time.time()
    st = store.read_json(VEILLE_STATE, {"fait": {}, "dernier_rappel": 0})
    if now - st.get("modeles", 0) < days * 86400:
        return False
    from . import usage
    if usage.summary()["claude"]["niveau"] != "ok":
        return False  # la veille consomme des jetons Claude : seulement quand il y a de la marge
    ag.chef_inject("[JARVIS veille] Veille des modèles due. Applique la procédure « Veille des modèles » de ton "
                   "rôle : nouveautés de Claude Code et de Codex (sources officielles), puis « jarvis modele "
                   "proposer » pour chaque changement utile au catalogue.")
    store.update_json(VEILLE_STATE, {"fait": {}, "dernier_rappel": 0}, lambda d: d.__setitem__("modeles", now))
    store.feed_add("chef", "veille des modèles demandée")
    return True


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
    from . import poste, usage
    limit = poste.capacite(busy)["max"]
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


BATTERIE_MSG = ("[JARVIS] La batterie du PC est presque vide et il n'est pas branché. Termine l'étape en cours, "
                "committe ton travail (préfixe WIP si c'est inachevé), pousse ta branche, puis arrête-toi : "
                "le PC peut s'éteindre d'une minute à l'autre.")


BATTERIE_STATE = "batterie.json"


def batterie_check(now: float | None = None) -> list[str]:
    """Batterie critique : les agents mettent leur travail à l'abri et Jarvis se met en pause.

    Appelé chaque minute par le fil de santé, avec une mesure fraîche (deux minutes au plus sur batterie).
    """
    if not config.settings()["sante"].get("active", True):
        return []
    from . import poste
    now = now or time.time()
    from . import pauses
    pct = poste.batterie_critique(now, rafraichir=True)
    if pct is not None:
        if not pauses.poser("batterie", f"{pct} %, PC non branché", par="demon"):
            return []  # déjà posée : rien de neuf
        found, _ = ag.status_all()
        for a in found or []:
            if a["status"] in ("working", "untracked", "silent"):
                ag.send(ag.target(a), BATTERIE_MSG)
        notify.alert("erreur", f"Batterie à {pct} % et PC non branché : les agents committent leur travail et "
                               "Jarvis se met en pause. Branche le PC.", title="JARVIS · batterie")
        ag.chef_inject(f"[JARVIS santé] Batterie à {pct} % : pause. Les agents ont reçu l'ordre de committer. "
                       "Ne lance plus rien tant que le PC n'est pas rebranché.")
        return ["batterie"]
    if "batterie" in pauses.actives():
        b = poste.batterie(now)
        if b and b["secteur"]:
            # Seule la cause « batterie » est levée : ta pause, une maintenance ou un quota restent.
            pauses.lever("batterie", par="demon")
            restantes = pauses.actives()
            notify.alert("plan_ok", "PC rebranché : fin de la pause batterie."
                         + (f" Jarvis reste en pause ({', '.join(sorted(restantes))})." if restantes else ""),
                         title="JARVIS · batterie")
            if not restantes:
                ag.chef_inject("[JARVIS santé] PC rebranché : pause levée, reprends ta boucle.")
            return ["batterie rétablie"]
    return []


JETONS_STATE = "jetons_garde.json"
PLAFOND_MSG = ("[JARVIS] Ta tâche a atteint son plafond de jetons. Termine l'étape en cours, committe ton travail "
               "(préfixe WIP si c'est inachevé), pousse ta branche, commente l'état dans l'issue Linear (ce qui est "
               "fait, ce qui reste, pourquoi c'est plus long que prévu), puis arrête-toi.")


def jetons_check(now: float | None = None, agents: list[dict] | None = None) -> list[str]:
    """Plafond de jetons pendant le travail : l'agent qui dépasse reçoit l'ordre de committer et de s'arrêter,
    le chef est prévenu. Une seule fois par tâche. Relu toutes les budget_jetons.verification_min minutes."""
    cfg = config.settings().get("budget_jetons", {})
    if not cfg.get("actif", True):
        return []
    now = now or time.time()
    st = store.read_json(JETONS_STATE, {"ts": 0, "signales": []})
    if now - st.get("ts", 0) < 60 * int(cfg.get("verification_min", 5)):
        return []
    st["ts"] = now
    if agents is None:
        agents, _ = ag.status_all()
    if agents is None:
        store.write_json(JETONS_STATE, st)
        return []
    from . import couts, taches
    fiches = taches.toutes()
    signales = set(st.get("signales", []))
    events = []
    for a in agents:
        if a["status"] not in ag.BUSY:
            continue
        fiche = taches.pour_agent(a["project"], a["worktree"], fiches, a.get("workdir", ""))
        if not fiche or fiche["statut"] not in taches.OUVERTS or fiche["id"] in signales:
            continue
        plafond = int(fiche.get("jetons_max") or 0) or couts.plafond_defaut(fiche.get("role", ""), fiche.get("taille", "M"))[0]
        deja = couts.compteur_unite(fiche["projet"], fiche["issue"], fiche.get("role", ""))
        if deja < plafond:
            continue
        signales.add(fiche["id"])
        events.append(fiche["id"])
        from . import evenements
        evenements.sans_echec(fiche["id"], "plafond", jetons=deja, plafond=plafond)
        ag.send(ag.target(a), PLAFOND_MSG)
        msg = (f"{fiche['projet']} {fiche['issue']} ({fiche['id']}) a atteint son plafond : {taches.fmt_jetons(deja)} / "
               f"{taches.fmt_jetons(plafond)} jetons. L'agent committe et s'arrête.")
        store.feed_add("erreur", msg)
        ag.chef_inject(f"[JARVIS jetons] {msg} Lis son compte rendu : découpe la tâche ou change d'approche ; un plafond "
                       f"plus haut passe par un nouveau plan (%…).")
        try:
            from . import journal
            journal.ecrire("budget", acteur="demon", objet=fiche["id"], decision="plafond_jetons",
                           raison=f"{deja}/{plafond}")
        except Exception:  # noqa: BLE001
            pass
    st["signales"] = sorted(signales)[-500:]
    store.write_json(JETONS_STATE, st)
    return events


BILAN_STATE = "bilan_quotidien.json"


def bilan_check(now: float | None = None) -> bool:
    """Envoie le bilan quotidien sur Telegram une fois par jour, à partir de bilan.heure (heure locale)."""
    cfg = config.settings().get("bilan", {})
    if not cfg.get("actif", True) or not config.settings()["telegram"].get("chat_id"):
        return False
    now = now or time.time()
    local = time.localtime(now)
    jour = time.strftime("%Y-%m-%d", local)
    try:
        h, m = (int(x) for x in str(cfg.get("heure", "08:00")).split(":"))
    except ValueError:
        return False
    if (local.tm_hour, local.tm_min) < (h, m):
        return False
    st = store.read_json(BILAN_STATE, {})
    if st.get("dernier") == jour:
        return False
    st["dernier"] = jour
    store.write_json(BILAN_STATE, st)  # écrit d'abord : jamais deux bilans, ni une erreur répétée tout le jour
    from . import bilan
    try:
        texte = bilan.quotidien(now)
    except Exception as exc:  # noqa: BLE001
        store.feed_add("erreur", f"bilan quotidien impossible : {exc}")
        return False
    notify.telegram(texte)
    store.feed_add("note", "bilan quotidien envoyé")
    return True


SKILLS_STATE = "skills_audit.json"


def skills_check(now: float | None = None) -> list[str]:
    """Audit horaire des skills : prévient une seule fois par problème nouveau (skill modifiée après épinglage,
    signature invalide, skill apparue hors registre). Ne désactive rien : la décision reste humaine."""
    now = now or time.time()
    st = store.read_json(SKILLS_STATE, {})
    if now - st.get("ts", 0) < 3600:
        return []
    st["ts"] = now
    store.write_json(SKILLS_STATE, st)
    from . import skills
    pb = skills.problemes()
    cles = {f"{s['nom']}:{s['etat']}:{s.get('empreinte', '')}" for s in pb}
    nouveaux = [s for s in pb if f"{s['nom']}:{s['etat']}:{s.get('empreinte', '')}" not in set(st.get("connus", []))]
    st["connus"] = sorted(cles)
    store.write_json(SKILLS_STATE, st)
    if nouveaux:
        lignes = [f"• {s['nom']} ({s['origine']}) : {s['etat']} — {s.get('detail', '')}" for s in nouveaux[:10]]
        notify.alert("erreur", "Skills à examiner (jarvis skill auditer) :\n" + "\n".join(lignes))
    return [s["nom"] for s in nouveaux]


CANARI_STATE = "canari.json"


def canari_check(now: float | None = None) -> list[dict]:
    """Toutes les heures : retour automatique au brief stable si un candidat en essai régresse."""
    now = now or time.time()
    st = store.read_json(CANARI_STATE, {})
    if now - st.get("ts", 0) < 3600:
        return []
    store.write_json(CANARI_STATE, {"ts": now})
    from . import versions_roles
    return versions_roles.surveiller(now)


OPTIM_STATE = "optimisation.json"


def optimisation_check(now: float | None = None, lancer=None) -> str | None:
    """Optimisation hebdomadaire d'un brief (réglage optimisation.hebdo, désactivé par défaut) : un rôle par
    semaine, à tour de rôle, la nuit choisie. Lancée en arrière-plan ; chaque mesure passe par l'admission (pauses,
    quota, capacité) et un candidat n'est jamais appliqué sans ta décision. Renvoie le rôle lancé."""
    cfg = config.settings().get("optimisation", {})
    if not cfg.get("hebdo") or store.paused():
        return None
    now = now or time.time()
    local = time.localtime(now)
    try:
        h, m = (int(x) for x in str(cfg.get("heure", "02:00")).split(":"))
        jour = int(cfg.get("jour", 7))
    except ValueError:
        return None
    if local.tm_wday + 1 != jour or (local.tm_hour, local.tm_min) < (h, m) or local.tm_hour >= 6:
        return None
    semaine = time.strftime("%G-%V", local)
    st = store.read_json(OPTIM_STATE, {})
    if st.get("semaine") == semaine:
        return None
    liste = [r.strip() for r in str(cfg.get("roles", "")).split(",") if r.strip()]
    if not liste:
        return None
    role = liste[int(st.get("index", 0)) % len(liste)]
    store.write_json(OPTIM_STATE, {"semaine": semaine, "index": int(st.get("index", 0)) + 1, "role": role, "ts": now})
    import subprocess
    import sys
    journal_dir = config.DATA_DIR / "optimisation"
    journal_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(config.JARVIS_HOME / "outils" / "optimiser_prompts.py"), "--role", role,
           "--mode", "abonnement", "--confirmer", "--appliquer"]
    if lancer:
        lancer(cmd)
    else:
        with open(journal_dir / f"hebdo-{semaine}-{role}.log", "a", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=journal_dir,
                                    env={k: v for k, v in __import__("os").environ.items() if k != "JARVIS_ROLE"})
        store.update_json(OPTIM_STATE, {}, lambda d: d.update(pid=proc.pid))
    store.feed_add("systeme", f"optimisation hebdomadaire du brief {role} lancée (résultat soumis à ta décision)")
    return role


RESSOURCES_STATE = "ressources.json"


def pression_memoire() -> float | None:
    """PSI mémoire « some avg60 » en % (Linux ≥ 4.20, souvent présent sous WSL2), ou None si indisponible."""
    try:
        with open("/proc/pressure/memory", encoding="utf-8") as fh:
            for ligne in fh:
                if ligne.startswith("some"):
                    for champ in ligne.split():
                        if champ.startswith("avg60="):
                            return float(champ[6:])
    except (OSError, ValueError):
        return None
    return None


def ressources_check(now: float | None = None, pression: float | None = None, libre_mo: float | None = None) -> str | None:
    """Pause « ressources » quand la pression mémoire reste élevée, levée avec hystérésis et délai.

    Mesures soutenues : la cause se pose après deux lectures consécutives au-dessus du seuil (deux
    minutes), et se lève après `hysterese_min` minutes sous la moitié du seuil. Une mesure absente ne pose
    ni ne lève rien. Renvoie "posee", "levee" ou None.
    """
    if not config.settings()["sante"].get("active", True):
        return None
    now = now or time.time()
    cfg = config.settings()["admission"]
    seuil = float(cfg.get("pression_memoire_pct", 25))
    hyst = 60 * int(cfg.get("hysterese_min", 5))
    from . import pauses, poste
    pression = pression_memoire() if pression is None else pression
    if libre_mo is None:
        mem = poste._meminfo()
        libre_mo = mem["MemAvailable"] / 1024 if mem.get("MemAvailable") else None
    reserve = float(cfg.get("memoire_reserve_mo", 1500))
    st = store.read_json(RESSOURCES_STATE, {"haut": 0, "bas_depuis": 0})
    mauvais = (pression is not None and pression >= seuil) or (libre_mo is not None and libre_mo < reserve / 2)
    bon = (pression is None or pression < seuil / 2) and (libre_mo is None or libre_mo >= reserve)
    if pression is None and libre_mo is None:
        return None  # rien de mesurable : on ne conclut rien
    resultat = None
    if mauvais:
        st["haut"] = st.get("haut", 0) + 1
        st["bas_depuis"] = 0
        if st["haut"] >= 2 and "ressources" not in pauses.actives():
            detail = (f"pression mémoire {pression:.0f} %" if pression is not None and pression >= seuil
                      else f"mémoire libre {libre_mo:.0f} Mo")
            pauses.poser("ressources", detail, par="demon")
            notify.alert("question", f"PC sous pression ({detail}) : aucun nouveau lancement jusqu'au retour au calme. "
                                     "Les agents en cours continuent.", title="JARVIS · ressources", windows=False)
            ag.chef_inject(f"[JARVIS santé] PC sous pression ({detail}) : pause « ressources », ne lance rien de plus.")
            resultat = "posee"
    elif bon:
        st["haut"] = 0
        st["bas_depuis"] = st.get("bas_depuis") or now
        if "ressources" in pauses.actives() and now - st["bas_depuis"] >= hyst:
            pauses.lever("ressources", par="demon")
            if not pauses.actives():
                ag.chef_inject("[JARVIS santé] Pression retombée : pause « ressources » levée, reprends ta boucle.")
            resultat = "levee"
    else:
        st["haut"] = 0  # zone intermédiaire : ni assez haut pour poser, ni assez bas pour lever
        st["bas_depuis"] = 0
    store.write_json(RESSOURCES_STATE, st)
    return resultat


def battement_demon() -> None:
    """Preuve de vie du démon, lue par le cockpit et « jarvis etat »."""
    import os
    store.write_json(report.DEMON_FILE, {"ts": time.time(), "pid": os.getpid()})


_BAIL: dict | None = None   # bail d'orchestrateur tenu par ce démon (posé par run)


_BAIL_ERREURS = 0


def bail_check() -> bool:
    """Renouvelle le bail. False si un autre orchestrateur l'a pris (ou 5 erreurs de stockage d'affilée) : ce
    démon doit s'arrêter, et sortir en erreur pour que « jarvis start » le relance proprement."""
    global _BAIL, _BAIL_ERREURS
    if _BAIL is None:
        return True
    from . import bail
    try:
        return _bail_renouveler(bail)
    except Exception as exc:  # noqa: BLE001 — base occupée, disque plein… : passager, sauf s'il dure
        _BAIL_ERREURS += 1
        store.feed_add("erreur", f"bail d'orchestrateur : {exc} ({_BAIL_ERREURS}/5)")
        return _BAIL_ERREURS < 5


def _bail_renouveler(bail) -> bool:
    global _BAIL, _BAIL_ERREURS
    # Expiré pendant une veille du PC mais libre : on le reprend (nouveau numéro). Pris par un autre : perdu.
    b = bail.renouveler(_BAIL["titulaire"], _BAIL["numero"]) or bail.acquerir(_BAIL["titulaire"])
    if not b:
        notify.alert("erreur", "Bail d'orchestrateur perdu : un autre démon Jarvis a pris la main, celui-ci s'arrête.")
        return False
    _BAIL, _BAIL_ERREURS = b, 0
    return True


def executant_check() -> None:
    from . import executants
    executants.signe_de_vie("local")


def missions_check() -> None:
    """Jarvis Next : baux expirés, nouveaux essais, fournisseurs revenus. Rien tant que la base n'existe pas."""
    from . import missions
    if (config.STATE_DIR / missions.FICHIER).exists():
        missions.recuperer()


def watch_loop(stop: threading.Event) -> None:
    first = True
    while not stop.is_set():
        if not bail_check():
            stop.set()
            break
        for step in (battement_demon, lambda: watch_once(first=first), ag.chef_flush_queue, budget_check,
                     prevision_check, blocage_check, jetons_check, chef_check, modeles_check, veille_check,
                     veille_modeles_check, menage_check, battement_check, bilan_check, skills_check, executant_check,
                     canari_check, optimisation_check, missions_check):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 — le démon ne doit jamais mourir sur une erreur ponctuelle
                store.feed_add("erreur", f"surveillance : {exc}")
        first = False
        stop.wait(int(config.settings()["general"].get("poll_seconds", 20)))


def sante_loop(stop: threading.Event) -> None:
    """Fil séparé : PowerShell et Docker peuvent mettre des secondes à répondre."""
    while not stop.is_set():
        for step in (batterie_check, ressources_check, sante_check):
            try:
                step()
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
        if action in ("mok", "mnon"):
            from . import modeles
            try:
                item = modeles.decider(plan_id, action == "mok", par="Telegram")
                verdict = "✅ Accepté" if item["statut"] == "acceptee" else "✋ Refusé"
                bot.answer(cb["id"], verdict)
                msg = cb.get("message", {})
                if msg.get("message_id"):
                    bot.edit(owner, msg["message_id"], f"{msg.get('text', '')}\n\n{verdict}")
            except modeles.RoutageError as exc:
                bot.answer(cb["id"], str(exc))
            return
        if action in ("rbok", "rbnon"):
            from . import rollback
            try:
                r = rollback.decider(plan_id, action == "rbok", par="Telegram")
                verdict = f"↩ Revert fait ({len(r.get('commits', []))} commit(s))" if r["execute"] else "Gardé tel quel"
            except rollback.RollbackError as exc:
                verdict = f"⚠ {exc}"
            bot.answer(cb["id"], verdict[:190])
            msg = cb.get("message", {})
            if msg.get("message_id"):
                bot.edit(owner, msg["message_id"], f"{msg.get('text', '')}\n\n{verdict}")
            return
        if action in ("skok", "sknon"):
            from . import skills
            try:
                nom, _, jeton = plan_id.partition(":")
                r = skills.decider(nom, action == "skok", par="Telegram", jeton_attendu=jeton or "?")
                verdict = "✅ Skill activée" if r["active"] else "✋ Skill refusée (copie supprimée)"
            except (skills.SkillError, OSError) as exc:
                verdict = f"⚠ {exc}"
            bot.answer(cb["id"], verdict[:190])
            msg = cb.get("message", {})
            if msg.get("message_id"):
                bot.edit(owner, msg["message_id"], f"{msg.get('text', '')}\n\n{verdict}")
            return
        if action in ("rlok", "rlnon"):
            from . import versions_roles
            try:
                r = versions_roles.decider(plan_id, action == "rlok", par="Telegram")
                verdict = (f"✅ Essai sur {r['pct']} % des tâches {r['role']}" if r["statut"] == "canari"
                           else "✋ Brief refusé")
            except versions_roles.VersionError as exc:
                verdict = f"⚠ {exc}"
            bot.answer(cb["id"], verdict[:190])
            msg = cb.get("message", {})
            if msg.get("message_id"):
                bot.edit(owner, msg["message_id"], f"{msg.get('text', '')}\n\n{verdict}")
            return
        if action not in ("ok", "non"):
            bot.answer(cb["id"], "Bouton inconnu")
            return
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
    elif cmd == "/usine":
        bot.send(owner, report.usine())
    elif cmd == "/livrables":
        from . import livrables
        bot.send(owner, "Livrables\n\n" + livrables.texte())
    elif cmd in ("/modeles", "/modèles"):
        from . import modeles
        bot.send(owner, "Modèles\n\n" + modeles.texte())
        for i in modeles.propositions():
            bot.send(owner, modeles.format_proposition(i), notify.proposition_buttons(i["id"]))
    elif cmd == "/bilan":
        from . import taches
        bot.send(owner, taches.texte_bilan())
    elif cmd == "/plans":
        pend = plans.pending()
        from . import modeles
        props = modeles.propositions()
        if not pend and not props:
            bot.send(owner, "Aucun plan à valider.")
        for p in pend:
            bot.send(owner, plans.format_plan(p), notify.plan_buttons(p["id"]))
        for i in props:
            bot.send(owner, modeles.format_proposition(i), notify.proposition_buttons(i["id"]))
    elif cmd == "/pause":
        store.set_paused(True)
        store.feed_add("systeme", "pause activée depuis Telegram")
        ag.chef_inject("[JARVIS] Ton humain a mis Jarvis en PAUSE : ne lance plus aucune tâche jusqu'à nouvel ordre.")
        bot.send(owner, "⏸ Pause activée : plus aucun nouveau lancement.")
    elif cmd == "/reprendre":
        from . import pauses
        store.set_paused(False)
        store.feed_add("systeme", "pause humaine levée depuis Telegram")
        restantes = pauses.actives()
        if restantes:
            bot.send(owner, "▶ Ta pause est levée, mais Jarvis reste en pause : " + pauses.texte(restantes)
                     + "\nCes causes se lèvent seules (batterie, quota, ressources) ou avec « jarvis pause lever <cause> ».")
        else:
            ag.chef_inject("[JARVIS] Pause levée par ton humain : tu peux reprendre ta boucle.")
            bot.send(owner, "▶ C'est reparti.")
    elif cmd == "/pauses":
        from . import admission, pauses
        bot.send(owner, pauses.texte() + "\n\n" + admission.texte_etat())
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
    global _BAIL
    from . import bail
    _BAIL = bail.acquerir()
    if not _BAIL:
        b = bail.lire() or {}
        print(f"Un autre démon Jarvis tient le bail d'orchestrateur ({b.get('titulaire', '?')}, jusqu'à "
              f"{time.strftime('%H:%M:%S', time.localtime(b.get('expire', 0)))}). Un seul démon à la fois : rien n'est lancé.")
        raise SystemExit(1)
    stop = threading.Event()
    threads = [
        threading.Thread(target=watch_loop, args=(stop,), name="surveillance", daemon=True),
        threading.Thread(target=telegram_loop, args=(stop,), name="telegram", daemon=True),
        threading.Thread(target=sante_loop, args=(stop,), name="sante", daemon=True),
    ]
    web_cfg = config.settings()["web"]
    if web_cfg.get("actif", True):
        from . import web
        threads.append(threading.Thread(target=web.serve, args=(stop, int(web_cfg.get("port", 7717))),
                                        name="web", daemon=True))
    for t in threads:
        t.start()
    store.feed_add("systeme", "démon Jarvis démarré")
    tg = "configuré" if config.settings()["telegram"].get("chat_id") else "non configuré (jarvis telegram config)"
    print(f"JARVIS · démon actif — surveillance toutes les {config.settings()['general']['poll_seconds']} s, Telegram {tg}.")
    if web_cfg.get("actif", True):
        print(f"Tableau de bord : http://localhost:{int(web_cfg.get('port', 7717))} (lecture seule, ce PC uniquement)")
    print("Laisse cette fenêtre ouverte. Ctrl+C pour arrêter.")
    import signal

    def _terminer(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminer)
    signal.signal(signal.SIGHUP, _terminer)   # fenêtre tmux fermée : on rend le bail
    perdu = False
    try:
        while not stop.is_set():
            stop.wait(3600)
        perdu = True
        print("Bail d'orchestrateur perdu ou stockage indisponible : ce démon s'arrête.")
    except KeyboardInterrupt:
        stop.set()
        store.feed_add("systeme", "démon Jarvis arrêté")
    finally:
        try:
            bail.liberer(_BAIL["titulaire"])
        except Exception:  # noqa: BLE001
            pass
    if perdu:
        raise SystemExit(1)
