"""Mémoire long terme du chef : décisions, échecs et leçons, retrouvables avant chaque plan.

Une entrée par fin de vague (ou par « jarvis note »), en JSONL ajout seul (memoire.jsonl). La recherche est
plein texte, sans dépendance : chaque mot de la requête rapporte 3 points dans le titre, 2 dans les leçons,
1 ailleurs (corps, décisions, échecs, étiquettes) ; à score égal, la plus récente d'abord ; 90 jours par défaut.

Une recherche sémantique (Mem0 ou autre) pourra se brancher derrière `recherche_semantique` : désactivée
tant que le réglage memoire.semantique n'est pas renseigné ET que la bibliothèque n'est pas installée.

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
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),            # jeton de bot Telegram
    # Longue chaîne opaque mêlant majuscules, minuscules et chiffres (clé encodée) ; pas les chemins, ni les
    # empreintes git (hexadécimal minuscule), ni les noms de branche.
    re.compile(r"(?<![A-Za-z0-9+/=])(?=[A-Za-z0-9+/=]*[A-Z])(?=[A-Za-z0-9+/=]*[a-z])(?=[A-Za-z0-9+/=]*\d)[A-Za-z0-9+/=]{32,}"),
]
_MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a", "à", "en", "pour", "par", "sur",
               "dans", "au", "aux", "ce", "ces", "est", "pas", "plus", "que", "qui", "il", "on", "avec", "the", "of"}


def _expurger(texte: str) -> str:
    t = str(texte or "")
    for motif in _SECRETS:
        t = motif.sub("[expurgé]", t)
    return t.strip()


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
        raise ValueError("une entrée de mémoire a un titre")
    now = now or time.time()
    path = store.state_path(FILE)
    with store.locked(FILE):
        n = 0
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                n = sum(1 for _ in fh)
        e = {"id": f"MEM-{n + 1:05d}", "ts": now, "titre": titre, "corps": _expurger(corps)[:4000],
             "decisions": _liste(decisions), "echecs": _liste(echecs), "lecons": _liste(lecons),
             "projet": projet[:40], "etiquettes": [_normal(x)[:30] for x in _liste(etiquettes)], "source": source[:20]}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        if n + 1 > MAX_ENTREES:
            lignes = path.read_text(encoding="utf-8").splitlines()[-MAX_ENTREES:]
            path.write_text("\n".join(lignes) + "\n", encoding="utf-8")
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


def texte(resultats: list[dict]) -> str:
    if not resultats:
        return "Rien de pertinent dans la mémoire (90 derniers jours)."
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
