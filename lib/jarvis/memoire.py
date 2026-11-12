"""Mémoire long terme du chef : décisions, échecs et leçons, retrouvables avant chaque plan.

Une entrée par fin de vague (ou par « jarvis note »), en JSONL ajout seul (memoire.jsonl). La recherche est
plein texte, sans dépendance : chaque mot de la requête rapporte 3 points dans le titre, 2 dans les leçons,
1 ailleurs (corps, décisions, échecs, étiquettes) ; à score égal, la plus récente d'abord ; 90 jours par défaut.

Une recherche sémantique (Mem0 ou autre) pourra se brancher derrière `recherche_semantique` : désactivée
tant que le réglage memoire.semantique n'est pas renseigné ET que la bibliothèque n'est pas installée.

Le prompt d'un agent n'utilise pas cette recherche large mais `pertinentes` : plus sévère (termes distincts,
leçons et échecs mieux notés, mots trop communs écartés, score minimal), elle préfère ne rien renvoyer plutôt
qu'une entrée hors sujet.

Ce que le chef écrit ici est expurgé de ce qui ressemble à un secret (jetons d'API, clés). La mémoire reste
une aide : elle distingue faits, décisions et leçons, mais ne remplace ni Linear ni le journal d'audit.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata

from . import config, store

FILE = "memoire.jsonl"
MAX_ENTREES = 5000
FENETRE_JOURS = 90
POIDS = {"titre": 3, "lecons": 2}
_SECRETS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(sk|pk|rk|whsec)_(live|test)_[A-Za-z0-9]{8,}"),     # Stripe
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                # AWS
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),   # JWT
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),            # jeton de bot Telegram
    # Longue chaîne opaque mêlant majuscules, minuscules et chiffres (clé encodée) ; pas les chemins, ni les
    # empreintes git (hexadécimal minuscule), ni les noms de branche.
    re.compile(r"(?<![A-Za-z0-9+/=])(?=[A-Za-z0-9+/=]*[A-Z])(?=[A-Za-z0-9+/=]*[a-z])(?=[A-Za-z0-9+/=]*\d)[A-Za-z0-9+/=]{32,}"),
]
_MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a", "à", "en", "pour", "par", "sur",
               "dans", "au", "aux", "ce", "ces", "est", "pas", "plus", "que", "qui", "il", "on", "avec", "the", "of"}


_URL_IDENTIFIANTS = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@", re.I)


def _expurger(texte: str) -> str:
    t = str(texte or "")
    for motif in _SECRETS:
        t = motif.sub("[expurgé]", t)
    t = _URL_IDENTIFIANTS.sub(r"\1[expurgé]@", t)          # mot de passe dans une URL
    try:  # valeurs connues des secrets par rôle : retirées telles quelles
        from . import secrets
        for v in secrets.valeurs_connues():
            t = t.replace(v, "[expurgé]")
    except Exception:  # noqa: BLE001
        pass
    return t.strip()


def expurger(texte: str) -> str:
    """Texte sans ce qui ressemble à un secret : à appliquer aussi à la lecture, avant de citer dans un prompt."""
    return _expurger(texte)


def _normal(texte: str) -> str:
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _mots(texte: str) -> list[str]:
    return [m for m in re.findall(r"[a-z0-9][a-z0-9_-]*", _normal(texte)) if m not in _MOTS_VIDES and len(m) > 1]


def _liste(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = [x for x in re.split(r"\s*[;\n]\s*", v) if x]
    return [_expurger(x)[:500] for x in v if str(x).strip()][:30]


def noter(*, titre: str, corps: str = "", decisions=None, echecs=None, lecons=None, projet: str = "",
          etiquettes=None, source: str = "chef", now: float | None = None) -> dict:
    """Ajoute une entrée. `decisions`, `echecs`, `lecons` : listes, ou texte séparé par « ; »."""
    titre = _expurger(titre)[:160]
    if not titre:
        raise ValueError("une entrée de mémoire doit avoir un titre")
    now = now or time.time()
    path = store.state_path(FILE)
    with store.locked(FILE):
        lignes = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        dernier = 0
        for ln in reversed(lignes):
            try:
                dernier = int(json.loads(ln)["id"].split("-")[1])
                break
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                continue
        n = len(lignes)
        e = {"id": f"MEM-{dernier + 1:05d}", "ts": now, "titre": titre, "corps": _expurger(corps)[:4000],
             "decisions": _liste(decisions), "echecs": _liste(echecs), "lecons": _liste(lecons),
             "projet": projet[:40], "etiquettes": [_normal(x)[:30] for x in _liste(etiquettes)], "source": source[:20]}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        if n + 1 > MAX_ENTREES:
            garde = path.read_text(encoding="utf-8").splitlines()[-MAX_ENTREES:]
            tmp = path.with_suffix(".tmp")
            tmp.write_text("\n".join(garde) + "\n", encoding="utf-8")
            tmp.replace(path)  # écriture atomique
    return e


def toutes() -> list[dict]:
    path = store.state_path(FILE)
    try:
        lignes = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lignes:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _score(e: dict, mots: list[str]) -> int:
    champs = {
        "titre": _mots(e.get("titre", "")),
        "lecons": _mots(" ".join(e.get("lecons") or [])),
        "autre": _mots(" ".join([e.get("corps", ""), " ".join(e.get("decisions") or []), " ".join(e.get("echecs") or []),
                                 " ".join(e.get("etiquettes") or []), e.get("projet", "")])),
    }
    total = 0
    for m in mots:
        for champ, liste in champs.items():
            # Un mot de la requête compte aussi s'il est le début d'un mot de l'entrée (« migr » → « migration »).
            occurrences = sum(1 for x in liste if x == m or (len(m) >= 4 and x.startswith(m)))
            total += occurrences * POIDS.get(champ, 1)
    return total


def chercher(requete: str, *, jours: int = FENETRE_JOURS, projet: str = "", limite: int = 8,
             now: float | None = None) -> list[dict]:
    """Entrées les plus pertinentes : [{"entree", "score"}], score décroissant puis plus récentes d'abord."""
    now = now or time.time()
    mots = _mots(requete)
    if not mots:
        return []
    semantique = recherche_semantique(requete, limite=limite)
    if semantique is not None:
        return semantique
    resultats = []
    for e in toutes():
        if now - e.get("ts", 0) > jours * 86400:
            continue
        if projet and e.get("projet") and e["projet"] != projet:
            continue
        sc = _score(e, mots)
        if sc > 0:
            resultats.append({"entree": e, "score": sc})
    resultats.sort(key=lambda r: (-r["score"], -r["entree"].get("ts", 0)))
    return resultats[:limite]


# --- Sélection sévère pour le prompt d'un agent --------------------------------------------------------------------

# Ce qu'un agent doit retenir d'abord : ce qui a été appris (leçon) et ce qui a raté (échec).
POIDS_PERTINENCE = {"lecons": 3, "echecs": 3, "titre": 2, "decisions": 2, "autre": 1}
SCORE_MIN = 4            # en dessous, l'entrée n'est pas injectée
TERMES_MIN = 2           # termes distincts de la requête que l'entrée doit contenir
COMMUN_A_PARTIR_DE = 6   # dès ce nombre d'entrées candidates, un terme présent dans plus de la moitié ne compte plus
# Mots qui ne disent rien du sujet d'une tâche : vocabulaire de l'usine et rubriques du gabarit de consignes.
_MOTS_GENERIQUES = {
    "objectif", "critere", "criteres", "verifiable", "verifiables", "verifie", "verifier", "verification",
    "verifications", "fichier", "fichiers", "concerne", "concernes", "hors", "perimetre", "entree", "entrees",
    "amont", "piege", "pieges", "connu", "connus", "aucun", "aucune", "issue", "tache", "taches", "agent", "agents",
    "projet", "projets", "vague", "chef", "commande", "commandes", "test", "tests", "resultat", "attendu", "attendus",
    "doit", "doivent", "faire", "fait", "etre", "sans", "tout", "tous", "toute", "toutes", "cette", "leur", "leurs",
    "sont", "ont", "ses", "son", "sa", "se", "ne", "ni", "si", "comme", "apres", "avant", "puis", "dont", "elle",
    "ils", "entre", "aussi", "chaque", "avoir", "peut", "fin", "exister", "code", "depot", "branche", "main",
    "and", "for", "with", "this", "that", "from", "into",
}


def termes(texte: str, exclure=()) -> list[str]:
    """Termes distinctifs d'un texte (sans doublon, dans l'ordre) : ni mot vide, ni vocabulaire générique de
    l'usine, ni nombre, ni identifiant d'issue, ni ce que `exclure` nomme (projet, issue : le projet filtre déjà)."""
    interdits = set()
    for x in exclure:
        interdits.update(_mots(x))
        interdits.update(re.findall(r"[a-z0-9]+", _normal(x)))
    vus: list[str] = []
    for m in _mots(texte):
        m = m.strip("-_")
        if (len(m) < 3 or m in interdits or m in _MOTS_GENERIQUES or m in _MOTS_VIDES or m in vus
                or m.isdigit() or re.fullmatch(r"[a-z]{1,10}-\d+", m)):
            continue
        vus.append(m)
    return vus


def _proches(a: str, b: str) -> bool:
    """Même mot, l'un début de l'autre (« migr » → « migration »), ou même radical : au moins cinq lettres
    communes en tête et pas plus de deux lettres de fin qui diffèrent sur le plus court (« paginer » et
    « pagination », « offre » et « offres »). Volontairement grossier : sans dépendance, il rapproche parfois
    deux mots voisins (« contrat », « contrainte ») ; l'exigence de deux termes distincts limite l'effet."""
    if a == b:
        return True
    court, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(court) >= 4 and long_.startswith(court):
        return True
    commun = 0
    for x, y in zip(court, long_):
        if x != y:
            break
        commun += 1
    return len(court) >= 6 and commun >= 5 and commun >= len(court) - 2


def _contient(mots_champ: list[str], terme: str) -> bool:
    return any(_proches(x, terme) for x in mots_champ)


def _champs_pertinence(e: dict) -> dict[str, list[str]]:
    return {"lecons": _mots(" ".join(e.get("lecons") or [])), "echecs": _mots(" ".join(e.get("echecs") or [])),
            "titre": _mots(e.get("titre", "")), "decisions": _mots(" ".join(e.get("decisions") or [])),
            "autre": _mots(" ".join([e.get("corps", ""), " ".join(e.get("etiquettes") or [])]))}


def pertinentes(sujet: str, *, projet: str = "", contexte: str = "", exclure=(), limite: int = 3,
                score_min: int = SCORE_MIN, jours: int = FENETRE_JOURS, now: float | None = None) -> list[dict]:
    """Entrées à injecter dans le prompt d'un agent : [{"entree", "score", "termes"}], les plus justes d'abord.

    `sujet` : ce dont parle la tâche (consignes du chef, critères, description courte). `contexte` : mots du
    rôle, qui départagent mais ne suffisent jamais. `exclure` : nom du projet et identifiant d'issue, retirés de
    la requête (le projet sert déjà de filtre ; un identifiant ne dit rien du sujet).

    Chaque terme ne compte qu'une fois par entrée, au poids du meilleur champ où il apparaît (leçon et échec 3,
    titre et décision 2, reste 1) : une note longue ne gagne pas en répétant un mot. Un terme présent dans plus
    de la moitié des entrées candidates (dès COMMUN_A_PARTIR_DE) ne distingue rien : il est ignoré. Une entrée
    n'est renvoyée que si elle contient au moins TERMES_MIN termes du sujet et atteint `score_min`. La date ne
    sert qu'à départager deux scores égaux : une note récente hors sujet ne remonte pas.
    """
    now = now or time.time()
    exclure = [x for x in (*exclure, projet) if x]
    t_sujet: list[str] = []
    for t in termes(sujet, exclure):  # « offre » et « offres » ne font qu'un terme : pas deux points pour un mot
        if not any(_proches(t, k) for k in t_sujet):
            t_sujet.append(t)
    if not t_sujet:
        return []
    t_contexte = [t for t in termes(contexte, exclure) if not any(_proches(t, k) for k in t_sujet)]
    candidates = []
    for e in toutes():
        if now - e.get("ts", 0) > jours * 86400:
            continue
        if projet and e.get("projet") and e["projet"] != projet:
            continue
        candidates.append((e, _champs_pertinence(e)))
    communs: set[str] = set()
    if len(candidates) >= COMMUN_A_PARTIR_DE:
        for t in (*t_sujet, *t_contexte):
            if sum(1 for _, ch in candidates if any(_contient(m, t) for m in ch.values())) * 2 > len(candidates):
                communs.add(t)

    def poids(champs: dict, terme: str) -> int:
        return max((POIDS_PERTINENCE[c] for c, m in champs.items() if _contient(m, terme)), default=0)

    resultats = []
    for e, champs in candidates:
        trouves = {t: poids(champs, t) for t in t_sujet if t not in communs}
        trouves = {t: p for t, p in trouves.items() if p}
        if len(trouves) < TERMES_MIN:
            continue
        score = sum(trouves.values()) + (1 if any(poids(champs, t) for t in t_contexte if t not in communs) else 0)
        if score >= score_min:
            resultats.append({"entree": e, "score": score, "termes": list(trouves)})
    resultats.sort(key=lambda r: (-r["score"], -r["entree"].get("ts", 0)))
    return resultats[:limite]


def recherche_semantique(requete: str, limite: int = 8) -> list[dict] | None:
    """Point d'extension : recherche sémantique (ex. Mem0) si elle est configurée ET installée.

    Renvoie None tant qu'elle ne l'est pas : la recherche plein texte prend le relais. Aucune donnée ne
    quitte le poste par ce module tant que ce réglage est vide.
    """
    moteur = str(config.settings().get("memoire", {}).get("semantique") or "")
    if moteur != "mem0":
        return None
    try:
        import mem0  # noqa: F401 — dépendance optionnelle, jamais requise
    except ImportError:
        return None
    return None  # branchement à écrire quand Mem0 sera retenu (lot ultérieur)


def texte(resultats: list[dict], jours: int = FENETRE_JOURS) -> str:
    if not resultats:
        return f"Rien de pertinent dans la mémoire ({jours} derniers jours)."
    out = []
    for r in resultats:
        e = r["entree"]
        quand = time.strftime("%d/%m/%Y", time.localtime(e.get("ts", 0)))
        out.append(f"{e['id']} [{quand}{', ' + e['projet'] if e.get('projet') else ''}] {e['titre']}  (pertinence {r['score']})")
        for cle, nom in (("decisions", "décision"), ("echecs", "échec"), ("lecons", "leçon")):
            for x in (e.get(cle) or [])[:4]:
                out.append(f"    {nom} : {x}")
        if e.get("corps") and not any(e.get(k) for k in ("decisions", "echecs", "lecons")):
            out.append(f"    {e['corps'][:300]}")
    return "\n".join(out)
