"""Plans proposés par le chef et validés par toi (Telegram, cockpit ou terminal).

Un plan liste des lancements précis : (projet, issue Linear, agent), avec le rôle, le modèle et
la taille de chaque tâche. Le chef ne peut lancer QUE ce qui figure dans un plan approuvé, une
seule fois par élément, avec le modèle que tu as validé.
Un « plan de nuit » est un plan plus long, validé avant de dormir.
"""

from __future__ import annotations

import re
import time

from . import store

PLANS_FILE = "plans.json"
AGENTS = {"claude": "claude", "cc": "claude", "codex": "codex", "cx": "codex", "auto": "auto"}
VALIDITE = {"vague": 24 * 3600, "nuit": 16 * 3600}  # durée de validité après approbation

# projet:ISSUE:agent[/modèle][@rôle][+taille][%jetons][:description]
_ITEM_RE = re.compile(
    r"^(?P<projet>[\w.-]+):(?P<issue>[A-Za-z]+-\d+):(?P<agent>[a-z]+)"
    r"(?:/(?P<modele>[A-Za-z0-9._-]+))?(?:@(?P<role>[a-z-]+))?(?:\+(?P<taille>[SMLsml]))?"
    r"(?:%(?P<jetons>\d+(?:[.,]\d+)?[kKmM]?))?"
    r"(?::(?P<desc>.+))?$")


def lire_jetons(texte: str) -> int:
    """« 800k » → 800 000 ; « 2.5M » → 2 500 000 ; « 120000 » → 120 000."""
    t = texte.strip().lower().replace(",", ".")
    mult = {"k": 1_000, "m": 1_000_000}.get(t[-1:], 1)
    try:
        n = int(float(t.rstrip("km")) * mult)
    except ValueError:
        raise PlanError(f"plafond de jetons illisible « {texte} » (ex. 800k, 2M)") from None
    if not 10_000 <= n <= 100_000_000:
        raise PlanError(f"plafond de jetons hors bornes : {n} (entre 10k et 100M)")
    return n


_DESC_REVUE = re.compile(r"^(revue|relecture)(-pr-\d+)?$")


class PlanError(ValueError):
    pass


class BudgetError(PlanError):
    """Lancement refusé faute de jetons chez le fournisseur prévu."""


def parse_item(spec: str) -> dict:
    """« repriceo:BIS-71:auto@devops+M:pipeline CI » → élément de plan (pas encore routé).

    L'agent vaut claude, codex ou auto (le routeur choisit). Facultatifs : /modèle pour imposer un
    modèle du catalogue, @rôle pour la spécialité, +S/+M/+L pour la taille.
    """
    m = _ITEM_RE.match(spec.strip())
    if not m:
        raise PlanError(f"élément invalide « {spec} » "
                        "(attendu projet:ISSUE:agent[/modèle][@rôle][+taille][%jetons][:description])")
    agent = AGENTS.get(m["agent"])
    if not agent:
        raise PlanError(f"agent inconnu « {m['agent']} » dans « {spec} » (claude, codex ou auto)")
    return {
        "projet": m["projet"],
        "issue": m["issue"].upper(),
        "agent": agent,
        "modele": (m["modele"] or "").lower(),
        "role": (m["role"] or "").lower(),
        "taille": (m["taille"] or "M").upper(),
        "desc": (m["desc"] or "").strip(),
        "jetons_max": lire_jetons(m["jetons"]) if m["jetons"] else 0,
        "lance": False,
        "lance_ts": None,
    }


def resoudre(items: list[dict], usage_resume: dict | None = None) -> list[dict]:
    """Route chaque élément : fournisseur, modèle, effort et secours. Lève PlanError si impossible.

    Fait à la création du plan : tu valides une affectation précise, pas un « auto ».
    """
    from . import modeles, taches
    vus: set[tuple] = set()
    for it in items:
        # Compatibilité avec l'ancienne écriture « projet:ISSUE:codex:revue-pr-12 », et elle seule :
        # « date-prevue » ou « revue-de-presse » ne sont pas des relectures.
        if not it.get("role") and _DESC_REVUE.match(it.get("desc", "").strip().lower()):
            it["role"] = "revue"
    # La production d'abord : une relecture « auto » doit connaître le fournisseur qu'elle relit.
    for it in sorted(items, key=lambda i: i.get("role") == "revue"):
        role = it.get("role") or ""
        auteur = ""
        if role == "revue" and it["agent"] == "auto":
            auteur = next((o["agent"] for o in items if o is not it and o["issue"] == it["issue"]
                           and o["projet"] == it["projet"] and o.get("role") != "revue"), "")
            auteur = auteur or taches.dernier_auteur(it["projet"], it["issue"])
        try:
            choix = modeles.choisir(role or None, it.get("taille") or "M", it["agent"], it.get("modele") or "",
                                    usage_resume=usage_resume, auteur=auteur)
        except modeles.RoutageError as exc:
            raise PlanError(f"{it['projet']}:{it['issue']} — {exc}") from exc
        it.update(agent=choix["agent"], modele=choix["modele"], modele_id=choix["modele_id"],
                  effort=choix["effort"], repli=choix["repli"], role=choix["role"], taille=choix["taille"],
                  raison=choix["raison"], secours=choix["secours"])
        if not it.get("jetons_max"):
            # Plafond de l'unité de travail, fixé et affiché au moment où l'humain valide le plan.
            from . import couts
            it["jetons_max"], it["jetons_source"] = couts.plafond_defaut(it["role"], it["taille"])
        else:
            it["jetons_source"] = "imposé par le plan"
        key = (it["projet"], it["issue"], it["agent"])
        if key in vus:
            raise PlanError(f"{it['projet']}:{it['issue']} apparaît deux fois pour {it['agent']} : "
                            "un élément par agent et par issue")
        vus.add(key)
    return items


def _empty() -> dict:
    return {"seq": 0, "plans": []}


def create(titre: str, items: list[dict], mode: str = "vague", resume: str = "", origine: str = "chef") -> dict:
    if not items:
        raise PlanError("un plan doit contenir au moins un élément")
    if mode not in VALIDITE:
        raise PlanError("mode inconnu (vague ou nuit)")

    def _add(data):
        data["seq"] += 1
        plan = {
            "id": f"P-{data['seq']:04d}",
            "titre": titre.strip() or "Plan sans titre",
            "mode": mode,
            "resume": resume.strip(),
            "statut": "en_attente",
            "origine": origine,
            "cree": time.time(),
            "decide": None,
            "par": None,
            "raison": "",
            "items": items,
        }
        data["plans"].append(plan)
        data["plans"] = data["plans"][-200:]
        return plan

    plan = store.update_json(PLANS_FILE, _empty(), _add)
    store.feed_add("plan_new", f"{plan['id']} proposé : {plan['titre']} ({len(items)} tâche(s), {mode})", plan=plan["id"])
    return plan


def all_plans() -> list[dict]:
    return store.read_json(PLANS_FILE, _empty())["plans"]


def get(plan_id: str) -> dict | None:
    plan_id = plan_id.upper()
    return next((p for p in all_plans() if p["id"] == plan_id), None)


def pending() -> list[dict]:
    return [p for p in all_plans() if p["statut"] == "en_attente"]


def active() -> list[dict]:
    """Plans approuvés, encore valides, avec des éléments non lancés."""
    now = time.time()
    return [
        p for p in all_plans()
        if p["statut"] == "approuve" and now - (p["decide"] or 0) < VALIDITE[p["mode"]]
    ]


def decide(plan_id: str, ok: bool, par: str, raison: str = "") -> dict:
    """Approuve ou refuse un plan, puis prévient le chef. Renvoie le plan mis à jour."""
    plan_id = plan_id.upper()

    def _decide(data):
        for p in data["plans"]:
            if p["id"] == plan_id:
                if p["statut"] != "en_attente":
                    deja = {"approuve": "approuvé", "refuse": "refusé", "termine": "terminé"}
                    raise PlanError(f"{plan_id} est déjà {deja.get(p['statut'], p['statut'])}")
                p["statut"] = "approuve" if ok else "refuse"
                p["decide"] = time.time()
                p["par"] = par
                p["raison"] = raison
                return dict(p)
        raise PlanError(f"plan {plan_id} introuvable")

    plan = store.update_json(PLANS_FILE, _empty(), _decide)
    if ok:
        store.feed_add("plan_ok", f"{plan_id} approuvé ({par})", plan=plan_id)
        msg = (f"[JARVIS] Plan {plan_id} APPROUVÉ par ton humain ({par}). "
               f"Lance ses tâches maintenant avec : jarvis task --plan {plan_id} --projet <projet> <ISSUE> <agent> [desc].")
    else:
        store.feed_add("plan_no", f"{plan_id} refusé ({par})" + (f" : {raison}" if raison else ""), plan=plan_id)
        msg = (f"[JARVIS] Plan {plan_id} REFUSÉ par ton humain ({par})."
               + (f" Raison : {raison}." if raison else "")
               + " Remets-toi en question, puis propose un plan corrigé.")
    from . import agents  # import tardif : évite une boucle d'imports
    agents.chef_inject(msg)
    return plan


RECENT_LAUNCH = 300  # s : un agent tout juste lancé peut mettre ce temps à apparaître dans workmux


def _est_relecture(item: dict) -> bool:
    return item.get("role") == "revue"


def _selectionner(p: dict, plan_id: str, projet: str, issue: str, agent: str, epuises: set[str],
                  relecture: bool = False) -> tuple[dict, bool]:
    """Élément du plan à lancer pour (projet, issue, agent) et s'il part avec son secours.

    Une issue peut porter deux éléments : la production, puis sa contre-relecture par l'autre
    fournisseur. Sans indication, c'est la production qui part d'abord ; la relecture part quand
    elle est demandée (`relecture`, c'est-à-dire « jarvis task --revue … ») ou quand il ne reste qu'elle.
    Ainsi le secours d'une production ne peut jamais être confondu avec l'élément de relecture.
    """
    prevus = [i for i in p["items"] if (i["projet"], i["issue"]) == (projet, issue)]
    if not prevus:
        raise PlanError(f"{projet}:{issue} ne fait pas partie de {plan_id}")
    libres = [i for i in prevus if not i["lance"]]
    if relecture:
        choix = [i for i in libres if _est_relecture(i)] or [i for i in libres if not i.get("role")]
        if not choix:
            raise PlanError(f"aucune contre-relecture à lancer pour {issue} dans {plan_id}")
    else:
        choix = [i for i in libres if not _est_relecture(i)] or libres

    def _secours(i) -> str:
        return (i.get("secours") or {}).get("agent", "")

    if agent == "auto":
        # « auto » : l'élément restant de cette issue, avec son secours si son fournisseur est épuisé.
        if not choix:
            raise PlanError(f"{issue} a déjà été lancé avec {plan_id}")
        if len(choix) > 1:
            qui = ", ".join(i["agent"] for i in choix)
            raise PlanError(f"{issue} a plusieurs éléments à lancer dans {plan_id} ({qui}) : précise l'agent")
        item = choix[0]
        if item["agent"] in epuises:
            if _secours(item) and _secours(item) not in epuises:
                return item, True
            raise BudgetError(f"jetons {item['agent']} épuisés et aucun secours disponible pour {issue} : attends "
                              "la remise à zéro ou propose un nouveau plan")
        return item, False

    exact = [i for i in choix if i["agent"] == agent]
    if exact:
        item = exact[0]
        if agent in epuises:
            autre = _secours(item)
            conseil = (f"lance-la avec son secours : jarvis task --plan {plan_id} --projet {projet} {issue} auto"
                       if autre and autre not in epuises else "attends la remise à zéro ou propose un nouveau plan")
            raise BudgetError(f"jetons {agent} épuisés : {conseil}")
        return item, False
    par_secours = [i for i in choix if _secours(i) == agent]
    if par_secours:
        item = par_secours[0]
        if item["agent"] not in epuises:
            raise PlanError(f"{projet}:{issue} est prévu pour {item['agent']} dans {plan_id} : le secours "
                            f"({agent}) ne sert que si {item['agent']} est épuisé")
        return item, True
    if any(i["agent"] == agent or i.get("lance_par") == agent for i in prevus):
        raise PlanError(f"{issue} ({agent}) a déjà été lancé avec {plan_id}")
    qui = ", ".join(sorted({i["agent"] for i in prevus}))
    raise PlanError(f"{projet}:{issue}:{agent} ne fait pas partie de {plan_id} (prévu pour {qui})")


def authorize_launch(plan_id: str, projet: str, issue: str, agent: str, *,
                     busy: int | None = None, visible: set[str] | None = None,
                     max_agents: int | None = None, epuises: set[str] | None = None,
                     relecture: bool = False) -> dict:
    """Vérifie qu'un lancement figure dans un plan approuvé et le marque comme lancé.

    Si `max_agents` est donné, la capacité est vérifiée sous le même verrou : agents occupés
    (`busy`) + lancements récents pas encore visibles dans workmux (`visible` = worktrees vus).
    `epuises` : fournisseurs sans jetons. Un élément dont le fournisseur prévu est épuisé peut être
    lancé avec son secours (l'autre fournisseur, validé avec le plan).
    `relecture` : le lancement demandé est une contre-relecture (« jarvis task --revue »).
    Renvoie l'élément avec son affectation effective. Lève PlanError avec une explication sinon.
    """
    plan_id, issue, agent = plan_id.upper(), issue.upper(), AGENTS.get(agent, agent)
    visible = {v.lower() for v in (visible or set())}
    epuises = epuises or set()

    def _check(data):
        if max_agents is not None:
            now = time.time()
            pending_start = sum(
                1 for p in data["plans"] for i in p["items"]
                if i["lance"] and now - (i["lance_ts"] or 0) < RECENT_LAUNCH
                and not any(w.startswith(i["issue"].lower()) for w in visible)
            )
            total = (busy or 0) + pending_start
            if total >= max_agents:
                raise PlanError(f"{total}/{max_agents} agents occupés (dont {pending_start} en démarrage) : "
                                "attends qu'un agent termine.")
        for p in data["plans"]:
            if p["id"] != plan_id:
                continue
            if p["statut"] == "en_attente":
                raise PlanError(f"{plan_id} attend encore la validation de ton humain")
            if p["statut"] == "refuse":
                raise PlanError(f"{plan_id} a été refusé")
            if p["statut"] == "termine":
                raise PlanError(f"{plan_id} est terminé : toutes ses tâches ont été lancées")
            if time.time() - (p["decide"] or 0) > VALIDITE[p["mode"]]:
                raise PlanError(f"{plan_id} a expiré : propose un nouveau plan")
            item, par_secours = _selectionner(p, plan_id, projet, issue, agent, epuises, relecture)
            item["lance"] = True
            item["lance_ts"] = time.time()
            effectif = dict(item)
            if par_secours:
                item["lance_par"] = item["secours"]["agent"]
                effectif.update(item["secours"])
                effectif["par_secours"] = True
                effectif["raison"] = (f"secours : {item['agent']} épuisé ; " + (item.get("raison") or "")).rstrip(" ;")
            if all(i["lance"] for i in p["items"]):
                p["statut"] = "termine"
            return effectif
        raise PlanError(f"plan {plan_id} introuvable")

    return store.update_json(PLANS_FILE, _empty(), _check)


def release(plan_id: str, projet: str, issue: str, agent: str) -> None:
    """Rend un élément relançable après un échec technique du lancement (workmux add)."""
    plan_id, issue, agent = plan_id.upper(), issue.upper(), AGENTS.get(agent, agent)

    def _release(data):
        for p in data["plans"]:
            if p["id"] != plan_id:
                continue
            lances = [i for i in p["items"] if (i["projet"], i["issue"]) == (projet, issue) and i["lance"]
                      and i.get("lance_par", i["agent"]) == agent]
            if not lances:
                break
            # Le lancement qui vient d'échouer est le plus récent : une issue peut avoir deux éléments
            # lancés par le même fournisseur (production, puis relecture partie avec son secours).
            item = max(lances, key=lambda i: i.get("lance_ts") or 0)
            item["lance"], item["lance_ts"] = False, None
            item.pop("lance_par", None)
            if p["statut"] == "termine":
                p["statut"] = "approuve"
            return
        raise PlanError(f"{projet}:{issue}:{agent} introuvable dans {plan_id}")

    store.update_json(PLANS_FILE, _empty(), _release)


def affectation(item: dict) -> str:
    """« Codex · sol · high » pour un élément routé, « codex » pour un ancien plan."""
    if not item.get("modele"):
        return item["agent"]
    from . import modeles
    return modeles.libelle(item["agent"], item["modele"], item.get("effort", ""))


def format_plan(p: dict, detail: bool = True) -> str:
    statut = {"en_attente": "⏳ en attente", "approuve": "✅ approuvé", "refuse": "✋ refusé", "termine": "🏁 terminé"}
    lines = [f"{p['id']} — {p['titre']}  [{p['mode']}, {statut.get(p['statut'], p['statut'])}]"]
    if detail:
        if p.get("resume"):
            lines.append(f"  Pourquoi : {p['resume']}")
        from . import roles
        for i in p["items"]:
            mark = "✓" if i["lance"] else "·"
            desc = f" — {i['desc']}" if i["desc"] else ""
            ligne = f"  {mark} {i['projet']} {i['issue']} → {affectation(i)}"
            if i.get("role"):
                r = roles.ou_defaut(i["role"])
                ligne += f"  [{r['emoji']} {r['titre']}, taille {i.get('taille', 'M')}]"
            if i.get("jetons_max"):
                from . import taches
                ligne += f"  ≤ {taches.fmt_jetons(i['jetons_max'])} jetons"
            lines.append(ligne + desc)
            if i.get("secours") and not i["lance"]:
                s = i["secours"]
                from . import modeles
                lines.append(f"      secours si {i['agent']} est épuisé : {modeles.libelle(s['agent'], s['modele'], s.get('effort', ''))}")
            if i.get("lance_par") and i["lance_par"] != i["agent"]:
                lines.append(f"      lancé avec le secours ({i['lance_par']})")
    return "\n".join(lines)
