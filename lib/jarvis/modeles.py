"""Catalogue des modèles et routeur : quel fournisseur et quel modèle pour quelle tâche.

Le choix est déterministe et explicable. Il dépend :
- du rôle (niveau attendu, fournisseur préféré) et de la taille de la tâche (S, M, L) ;
- des atouts de chaque modèle (rôles pour lesquels il est préféré) ;
- de la marge de jetons de chaque abonnement, de sa fenêtre semaine et de sa prévision d'épuisement ;
- de la disponibilité réelle du modèle, vérifiée par un essai avec l'abonnement de l'utilisateur.

Le catalogue évolue par propositions du chef (veille des modèles), validées par l'humain.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

from . import config, roles, store

CATALOGUE_DEFAUT = config.JARVIS_HOME / "config" / "modeles.toml"
CATALOGUE_PERSO = config.CONFIG_DIR / "modeles.toml"
VERIF_FILE = "modeles_verif.json"
PROPOSITIONS_FILE = "modeles_propositions.json"

FOURNISSEURS = ("claude", "codex")
EFFORTS = ("low", "medium", "high", "xhigh")
TAILLES = {"S": -1, "M": 0, "L": 1}
CHAMPS = ("fournisseur", "id", "niveau", "cout", "effort", "repli", "atouts", "note", "actif")
_NOM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\[\]/-]{0,79}$")


class RoutageError(ValueError):
    pass


# --- Catalogue --------------------------------------------------------------------------

_illisibles: dict[str, str] = {}


def _lire(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh).get("modeles", {}) or {}
        _illisibles.pop(str(path), None)
        return data
    except FileNotFoundError:
        _illisibles.pop(str(path), None)
        return {}
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _illisibles[str(path)] = str(exc)  # signalé par « jarvis modele » : un catalogue ignoré doit se voir
        return {}


def catalogue_illisible() -> str:
    """Message si le catalogue personnel existe mais ne peut pas être lu (il est alors ignoré)."""
    _lire(CATALOGUE_PERSO)
    err = _illisibles.get(str(CATALOGUE_PERSO))
    return f"{CATALOGUE_PERSO} est illisible et ignoré ({err}) : corrige-le ou supprime-le" if err else ""


def _normaliser(nom: str, brut: dict) -> dict | None:
    if not isinstance(brut, dict) or brut.get("fournisseur") not in FOURNISSEURS:
        return None

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(brut.get(key, default))))
        except (TypeError, ValueError):
            return default

    effort = str(brut.get("effort") or "").strip().lower()
    return {
        "nom": nom,
        "fournisseur": brut["fournisseur"],
        "id": str(brut.get("id") or "").strip(),
        "niveau": _int("niveau", 2, 1, 4),
        "cout": _int("cout", 3, 1, 5),
        "effort": effort if effort in EFFORTS else "",
        "repli": ",".join(x.strip() for x in str(brut.get("repli") or "").split(",") if x.strip()),
        "atouts": [x.strip().lower() for x in str(brut.get("atouts") or "").split(",") if x.strip()],
        "note": str(brut.get("note") or ""),
        "actif": brut.get("actif", True) is not False,
    }


def catalogue() -> dict[str, dict]:
    """Catalogue du dépôt complété et remplacé, modèle par modèle, par celui de l'utilisateur."""
    brut = {k: dict(v) for k, v in _lire(CATALOGUE_DEFAUT).items() if isinstance(v, dict)}
    for nom, champs in _lire(CATALOGUE_PERSO).items():
        if isinstance(champs, dict):
            brut[nom] = {**brut.get(nom, {}), **champs}
    out = {}
    for nom, champs in brut.items():
        m = _normaliser(nom, champs)
        if m:
            out[nom] = m
    return out


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    # Une seule ligne, sans caractère de contrôle : un retour à la ligne rendrait le fichier illisible.
    propre = " ".join("".join(c if c.isprintable() else " " for c in str(v)).split())
    return '"' + propre.replace("\\", "\\\\").replace('"', '\\"') + '"'


def enregistrer_perso(nom: str, champs: dict) -> None:
    """Ajoute ou modifie un modèle dans le catalogue personnel (~/.config/jarvis/modeles.toml)."""
    perso = {k: dict(v) for k, v in _lire(CATALOGUE_PERSO).items() if isinstance(v, dict)}
    if str(CATALOGUE_PERSO) in _illisibles:
        # On ne réécrit jamais par-dessus un fichier qu'on n'a pas su lire : il est mis de côté.
        CATALOGUE_PERSO.replace(CATALOGUE_PERSO.with_name(f"modeles.toml.illisible.{time.strftime('%Y%m%d-%H%M%S')}"))
    perso[nom] = {**perso.get(nom, {}), **{k: v for k, v in champs.items() if k in CHAMPS and v is not None}}
    lines = ["# Catalogue personnel des modèles : complète et remplace config/modeles.toml de JarvisAgent.", ""]
    for name in sorted(perso):
        lines.append(f"[modeles.{name}]" if _NOM_RE.match(name) and "." not in name else f'[modeles."{name}"]')
        for key in CHAMPS:
            if key in perso[name]:
                lines.append(f"{key} = {_toml(perso[name][key])}")
        lines.append("")
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CATALOGUE_PERSO.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(CATALOGUE_PERSO)


# --- Disponibilité réelle (essai avec l'abonnement) ---------------------------------------

_INDETERMINE = re.compile(r"limit|quota|rate|overload|network|timed? ?out|ENOTFOUND|ECONN|EAI_AGAIN|"
                          r"log ?in|auth|sign in|credential|capacity|503|529|502", re.IGNORECASE)


def etat_verif() -> dict:
    return store.read_json(VERIF_FILE, {})


def exige_verification() -> bool:
    return bool(config.settings()["modeles"].get("verification", True))


def utilisable(m: dict, verif: dict | None = None) -> bool:
    """Un modèle sert au routage s'il est actif et, quand il a un identifiant, si son essai a réussi."""
    if not m.get("actif", True):
        return False
    if not m["id"] or not exige_verification():
        return True
    verif = etat_verif() if verif is None else verif
    v = verif.get(m["nom"]) or {}
    return v.get("ok") is True and v.get("id") == m["id"]


def _env_neutre() -> dict:
    # Hors tmux : les hooks de statut de workmux ne doivent pas prendre cet essai pour un agent.
    return {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "JARVIS_ROLE")}


def _essai_dir() -> Path:
    d = config.STATE_DIR / "essai-modeles"
    d.mkdir(parents=True, exist_ok=True)
    if not (d / ".git").exists() and shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(d)], capture_output=True, timeout=20, check=False)
    return d


def essayer(m: dict, timeout: int = 150) -> tuple[bool | None, str]:
    """Lance une requête minuscule avec ce modèle. (True/False/None = indéterminé, détail)."""
    prompt = "Réponds uniquement par le mot : ok"
    if m["fournisseur"] == "claude":
        if not shutil.which("claude"):
            return None, "claude introuvable"
        cmd = ["claude", "-p", prompt, "--settings", '{"disableAllHooks": true}']
        if m["id"]:
            cmd += ["--model", m["id"]]
    else:
        if not shutil.which("codex"):
            return None, "codex introuvable"
        cmd = ["codex", "exec"]
        if m["id"]:
            cmd += ["-m", m["id"]]
        cmd.append(prompt)
    try:
        res = subprocess.run(cmd, cwd=_essai_dir(), capture_output=True, text=True, timeout=timeout,
                             env=_env_neutre(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, "délai dépassé"
    except OSError as exc:
        return None, str(exc)
    if res.returncode == 0:
        return True, "essai réussi"
    lines = [ln.strip() for ln in (res.stderr + "\n" + res.stdout).splitlines() if ln.strip()]
    detail = (lines[-1] if lines else f"code {res.returncode}")[:200]
    if _INDETERMINE.search(" ".join(lines[-6:])):
        return None, detail  # limite, réseau, connexion : cela ne dit rien du modèle lui-même
    return False, detail


ESSAI_RECUL = 3600          # premier nouvel essai d'un modèle au résultat indéterminé : une heure plus tard
ESSAI_RECUL_MAX = 24 * 3600  # puis le délai double, jusqu'à un essai par jour


def verifier(noms: list[str] | None = None, usage_resume: dict | None = None) -> dict[str, dict]:
    """Essaie les modèles du catalogue qui ont un identifiant. Renvoie {nom: {ok, detail}}.

    Un résultat indéterminé (limite atteinte, réseau, CLI absent ou non connecté) conserve l'état
    précédent ; le modèle sera réessayé plus tard, de moins en moins souvent.
    """
    cat = catalogue()
    out = {}
    complet = noms is None
    for nom, m in cat.items():
        if noms is not None and nom not in noms:
            continue
        if not m["actif"] or not m["id"]:
            continue
        niveau = ((usage_resume or {}).get(m["fournisseur"]) or {}).get("niveau")
        if niveau == "epuise":
            ok, detail = None, "abonnement épuisé : essai reporté"
        else:
            ok, detail = essayer(m)
        out[nom] = {"ok": ok, "detail": detail}

        def _save(data, nom=nom, m=m, ok=ok, detail=detail):
            essais = data.setdefault("_essais", {})
            if ok is None:
                e = essais.get(nom) or {"n": 0}
                essais[nom] = {"n": e["n"] + 1, "ts": time.time(), "id": m["id"], "detail": detail}
            else:
                essais.pop(nom, None)
                data[nom] = {"ok": ok, "id": m["id"], "ts": time.time(), "detail": detail}

        store.update_json(VERIF_FILE, {}, _save)
    if complet:
        store.update_json(VERIF_FILE, {}, lambda data: data.__setitem__("_derniere", {"ts": time.time()}))
    return out


def a_verifier(now: float | None = None) -> list[str]:
    """Modèles à essayer maintenant : jamais essayés (ou identifiant changé), puis tous une fois par période.

    Un modèle dont l'essai n'a rien donné (CLI absent, limite) n'est pas réessayé en boucle : le délai
    double à chaque fois. Les autres modèles ne sont jamais réessayés à cause de lui.
    """
    if not exige_verification():
        return []
    now = now or time.time()
    verif = etat_verif()
    essais = verif.get("_essais") or {}
    cat = catalogue()
    jours = int(config.settings()["modeles"].get("verification_jours", 7))
    derniere = (verif.get("_derniere") or {}).get("ts", 0)
    testables = [m for m in cat.values() if m["actif"] and m["id"]]
    if derniere and jours > 0 and now - derniere > jours * 86400:
        return [m["nom"] for m in testables]
    dus = []
    for m in testables:
        if (verif.get(m["nom"]) or {}).get("id") == m["id"]:
            continue  # déjà essayé avec cet identifiant
        e = essais.get(m["nom"])
        if e and e.get("id") == m["id"]:
            recul = min(ESSAI_RECUL * 2 ** max(0, e.get("n", 1) - 1), ESSAI_RECUL_MAX)
            if now - e.get("ts", 0) < recul:
                continue
        dus.append(m["nom"])
    return dus


def verification_due(now: float | None = None) -> bool:
    return bool(a_verifier(now))


# --- Routeur ----------------------------------------------------------------------------

def effort_pour(m: dict, taille: str) -> str:
    if not m["effort"]:
        return ""
    i = EFFORTS.index(m["effort"]) + TAILLES.get(taille, 0)
    return EFFORTS[max(0, min(len(EFFORTS) - 1, i))]


def _fiche(m: dict, taille: str) -> dict:
    return {"agent": m["fournisseur"], "modele": m["nom"], "modele_id": m["id"],
            "effort": effort_pour(m, taille), "repli": m["repli"]}


def _budget(u: dict | None) -> tuple[float, list[str]]:
    """Points de budget d'un fournisseur et explications. `u` : entrée de usage.summary()."""
    if not u:
        return 0.0, []
    pts, why = 0.0, []
    marge = u.get("marge")
    if marge is not None:
        pts += (marge - 50) / 25
        why.append(f"marge {marge:.0f} %")
    if u.get("niveau") == "alerte":
        pts -= 3
        why.append("en alerte")
    prev = u.get("prevision") or {}
    if prev.get("avant_reset"):
        pts -= 2
        why.append(f"épuisement prévu dans {prev.get('minutes', 0):.0f} min")
    return pts, why


def _score(m: dict, role: dict, cible: int, taille: str, u: dict | None) -> tuple[float, list[str]]:
    why = []
    semaine = ((u or {}).get("semaine") or {}).get("used")
    prudence = float(config.settings()["jetons"].get("semaine_prudence", 70))
    econome = semaine is not None and semaine >= prudence and taille != "L"
    if econome and cible > 3:
        cible = 3  # semaine bien entamée : le niveau maximal est gardé pour les tâches L
    ecart = m["niveau"] - cible
    pts = -1.5 * ecart if ecart >= 0 else -4.0 * (-ecart)  # trop faible coûte plus cher que trop fort
    if role["nom"] in m["atouts"]:
        pts += 3
        why.append(f"atout {role['nom']}")
    if role["fournisseur"] == m["fournisseur"]:
        pts += 2
        why.append(f"{m['fournisseur'].capitalize()} préféré pour ce rôle")
    b, bw = _budget(u)
    pts += b
    why += bw
    if econome:
        why.append(f"semaine à {semaine:.0f} % : modèles coûteux réservés aux grosses tâches")
        if m["cout"] >= 5:
            pts -= 3
    return pts, why


def choisir(role_nom: str | None = None, taille: str = "M", agent: str = "auto", modele: str = "",
            usage_resume: dict | None = None, auteur: str = "") -> dict:
    """Choisit fournisseur + modèle. Lève RoutageError (message pour le chef) si rien ne convient.

    `agent` : claude | codex | auto.  `modele` : nom du catalogue pour forcer un modèle.
    `auteur` : pour une contre-relecture, le fournisseur qui a écrit le travail (l'autre relit).
    """
    role = roles.ou_defaut(role_nom)
    if role_nom and not roles.get(role_nom):
        raise RoutageError(f"rôle inconnu « {role_nom} » (jarvis role liste)")
    taille = (taille or "M").upper()
    if taille not in TAILLES:
        raise RoutageError(f"taille inconnue « {taille} » (S, M ou L)")
    if agent not in FOURNISSEURS + ("auto",):
        raise RoutageError(f"agent inconnu « {agent} » (claude, codex ou auto)")
    cat = catalogue()
    verif = etat_verif()
    if usage_resume is None:
        try:
            from . import usage
            usage_resume = usage.summary()
        except Exception:  # noqa: BLE001 — sans données de jetons, on route quand même
            usage_resume = {}

    if modele:
        m = cat.get(modele.lower())
        if not m:
            raise RoutageError(f"modèle inconnu « {modele} » (jarvis modele liste)")
        if agent != "auto" and m["fournisseur"] != agent:
            raise RoutageError(f"le modèle {m['nom']} appartient à {m['fournisseur']}, pas à {agent}")
        if not utilisable(m, verif):
            raise RoutageError(f"le modèle {m['nom']} n'est pas disponible avec ton abonnement "
                               f"(jarvis modele verifier {m['nom']})")
        out = _fiche(m, taille)
        out.update(role=role["nom"], taille=taille, raison=f"modèle imposé ({m['nom']})", secours=None)
        return out

    cible = max(1, min(4, role["niveau"] + TAILLES[taille]))
    fournisseurs = [agent] if agent != "auto" else [f for f in FOURNISSEURS if f != auteur]
    classement: dict[str, tuple] = {}
    for f in FOURNISSEURS:
        u = usage_resume.get(f) or {}
        if u.get("niveau") == "epuise" and (agent == "auto" or f != agent):
            continue  # épuisé : écarté, sauf si ce fournisseur est imposé (il sera peut-être rétabli au lancement)
        best = None
        for m in cat.values():
            if m["fournisseur"] != f or not utilisable(m, verif):
                continue
            pts, why = _score(m, role, cible, taille, u)
            key = (pts, -m["cout"], m["nom"])
            if best is None or key > best[0]:
                best = (key, m, why)
        if best:
            classement[f] = best
    candidats = [classement[f] for f in fournisseurs if f in classement]
    if not candidats:
        if auteur and agent == "auto":
            raise RoutageError(f"aucun modèle disponible chez l'autre fournisseur pour relire le travail de {auteur}")
        raise RoutageError("aucun modèle disponible : abonnements épuisés ou catalogue vide (jarvis modele liste)")
    _key, m, why = max(candidats, key=lambda c: c[0])
    out = _fiche(m, taille)
    autre = next((f for f in FOURNISSEURS if f != m["fournisseur"]), "")
    secours = None
    if autre in classement and autre != auteur and role["nom"] != "revue":
        secours = _fiche(classement[autre][1], taille)
    raison = f"rôle {role['nom']}, taille {taille} (niveau visé {cible})"
    if why:
        raison += " ; " + ", ".join(why)
    out.update(role=role["nom"], taille=taille, raison=raison, secours=secours)
    return out


def libelle(agent: str, modele: str = "", effort: str = "") -> str:
    """« Codex · sol · high » : affichage court d'une affectation."""
    parts = [agent.capitalize()]
    if modele and not modele.endswith("-defaut"):
        parts.append(modele)
    if effort:
        parts.append(effort)
    return " · ".join(parts)


def texte(usage_resume: dict | None = None) -> str:
    cat = catalogue()
    verif = etat_verif()
    lines = []
    if catalogue_illisible():
        lines += [f"⚠ {catalogue_illisible()}", ""]
    for f in FOURNISSEURS:
        lines.append(f.upper())
        for m in sorted((x for x in cat.values() if x["fournisseur"] == f), key=lambda x: (-x["niveau"], x["nom"])):
            if not m["actif"]:
                etat = "⏸ retiré"
            elif not m["id"]:
                etat = "🟢 par défaut"
            elif not exige_verification():
                etat = "⚪ non vérifié"
            else:
                v = verif.get(m["nom"]) or {}
                if v.get("id") != m["id"]:
                    e = (verif.get("_essais") or {}).get(m["nom"]) or {}
                    etat = "⚪ pas encore essayé" + (f" (dernier essai sans réponse : {e.get('detail', '')[:50]})" if e else "")
                elif v.get("ok"):
                    etat = f"🟢 vérifié le {time.strftime('%d/%m', time.localtime(v.get('ts', 0)))}"
                else:
                    etat = f"🔴 indisponible ({v.get('detail', '')[:60]})"
            ident = m["id"] or "(défaut du CLI)"
            lines.append(f"  {m['nom']:<14} niveau {m['niveau']} · coût {m['cout']} · {ident:<16} {etat}")
            if m["atouts"]:
                lines.append(f"  {'':<14} atouts : {', '.join(m['atouts'])}")
    return "\n".join(lines)


# --- Propositions du chef (veille des modèles), validées par l'humain ------------------------

def _vide() -> dict:
    return {"seq": 0, "items": []}


def proposer(nom: str, champs: dict, pourquoi: str, source: str) -> dict:
    nom = nom.strip().lower()
    if not _NOM_RE.match(nom):
        raise RoutageError("nom de modèle invalide (lettres minuscules, chiffres, tirets)")
    actuel = catalogue().get(nom)
    fournisseur = champs.get("fournisseur") or (actuel or {}).get("fournisseur")
    if fournisseur not in FOURNISSEURS:
        raise RoutageError("précise --fournisseur claude ou codex")
    if champs.get("id") and not _ID_RE.match(str(champs["id"])):
        raise RoutageError("identifiant de modèle invalide")
    if champs.get("effort") and champs["effort"] not in EFFORTS:
        raise RoutageError(f"effort inconnu (valeurs : {', '.join(EFFORTS)})")
    inconnus = [r for r in str(champs.get("atouts") or "").split(",") if r.strip() and not roles.get(r)]
    if inconnus:
        raise RoutageError(f"atouts : rôle(s) inconnu(s) {', '.join(x.strip() for x in inconnus)}")
    if not source.strip().lower().startswith(("http://", "https://")):
        raise RoutageError("une proposition exige sa source (--source https://…)")
    propre = {k: (" ".join(str(v).split()) if isinstance(v, str) else v)
              for k, v in champs.items() if k in CHAMPS and v not in (None, "")}
    propre["fournisseur"] = fournisseur

    def _add(data):
        data["seq"] += 1
        item = {"id": f"M-{data['seq']:04d}", "nom": nom, "champs": propre, "pourquoi": pourquoi.strip(),
                "source": source.strip(), "statut": "en_attente", "cree": time.time(), "decide": None, "par": None,
                "nouveau": actuel is None}
        data["items"].append(item)
        data["items"] = data["items"][-100:]
        return item

    item = store.update_json(PROPOSITIONS_FILE, _vide(), _add)
    store.feed_add("plan_new", f"{item['id']} proposé : modèle {nom} ({fournisseur})", proposition=item["id"])
    return item


def propositions(statut: str | None = "en_attente") -> list[dict]:
    items = store.read_json(PROPOSITIONS_FILE, _vide())["items"]
    return [i for i in items if statut is None or i["statut"] == statut]


def decider(prop_id: str, ok: bool, par: str) -> dict:
    """Applique (ou refuse) une proposition. Le modèle accepté sera essayé avant d'être utilisé."""
    prop_id = prop_id.upper()

    def _decide(data):
        for i in data["items"]:
            if i["id"] == prop_id:
                if i["statut"] != "en_attente":
                    raise RoutageError(f"{prop_id} est déjà {'acceptée' if i['statut'] == 'acceptee' else 'refusée'}")
                i["statut"] = "acceptee" if ok else "refusee"
                i["decide"], i["par"] = time.time(), par
                return dict(i)
        raise RoutageError(f"proposition {prop_id} introuvable")

    item = store.update_json(PROPOSITIONS_FILE, _vide(), _decide)
    if ok:
        enregistrer_perso(item["nom"], item["champs"])
        # Forcer l'essai de ce modèle au prochain passage du démon.
        store.update_json(VERIF_FILE, {}, lambda d: (d.pop(item["nom"], None), (d.get("_essais") or {}).pop(item["nom"], None)))
        store.feed_add("plan_ok", f"{prop_id} accepté ({par}) : modèle {item['nom']} ajouté au catalogue")
        msg = (f"[JARVIS] Proposition {prop_id} ACCEPTÉE par ton humain : le modèle {item['nom']} entre au "
               f"catalogue. Il sera utilisé dès que son essai avec l'abonnement aura réussi.")
    else:
        store.feed_add("plan_no", f"{prop_id} refusé ({par}) : modèle {item['nom']}")
        msg = f"[JARVIS] Proposition {prop_id} REFUSÉE par ton humain (modèle {item['nom']})."
    from . import agents
    agents.chef_inject(msg)
    return item


def format_proposition(i: dict) -> str:
    c = i["champs"]
    statut = {"en_attente": "⏳ en attente", "acceptee": "✅ acceptée", "refusee": "✋ refusée"}
    genre = "nouveau modèle" if i.get("nouveau") else "modification"
    lines = [f"{i['id']} — {genre} « {i['nom']} » ({c.get('fournisseur')})  [{statut.get(i['statut'], i['statut'])}]"]
    detail = [f"{k} = {c[k]}" for k in ("id", "niveau", "cout", "effort", "atouts", "repli", "actif") if k in c]
    if detail:
        lines.append("  " + " · ".join(detail))
    if i.get("pourquoi"):
        lines.append(f"  Pourquoi : {i['pourquoi']}")
    lines.append(f"  Source : {i['source']}")
    return "\n".join(lines)
