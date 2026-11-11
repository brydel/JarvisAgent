"""Briques de recherche de la Bibliothèque de références : découpage, mots, BM25, vecteurs, fusion RRF, extraits.

Fonctions pures (aucune base, aucun réseau sauf l'embarqueur Ollama, optionnel et désactivé par défaut) :
- `normaliser` : minuscules sans accents (« Élégance » → « elegance », « cœur » → « coeur ») ;
- `decouper` : sections (titres h1-h3) → fragments bornés, coupés aux phrases, avec recouvrement ;
- `requete_fts` : question en langage naturel → requête FTS5 (mots vides retirés, racines en préfixe) ;
- `bm25_python` : repli sans FTS5 (ou sur PostgreSQL), mêmes règles de correspondance ;
- `Embarqueur` : interface enfichable ; `EmbarqueurOllama` parle HTTP à un Ollama local par urllib ;
- vecteurs en BLOB (float32), similarité cosinus en Python pur ;
- `fusion_rrf` : fusion des classements par rangs réciproques ;
- `extrait` : passage autour des mots trouvés, avec les plages à surligner (jamais de HTML).
"""

from __future__ import annotations

import array
import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.request
from typing import Protocol

FRAGMENT_MAX = 900       # caractères par fragment
RECOUVREMENT = 120       # caractères repris du fragment précédent (contexte)
FRAGMENTS_MAX = 400      # par référence
RRF_K = 60
VERSION_INDEX = 1        # à incrémenter si le découpage ou la préparation du texte change

MOTS_VIDES = frozenset("""a afin ai au aux avec ce ces cet cette comme comment d dans de des du elle elles en est et etre
il ils j je l la le les leur leurs lui ma mais me mes mon n ne nos notre nous on ou où par pas pour qu que quel quelle
quelles quels qui quoi s sa se ses si son sont sur ta te tes ton tu un une vos votre vous y the of and to in is for on
with that this are what which how""".split())

_LIGATURES = {"œ": "oe", "æ": "ae", "ß": "ss", "Œ": "oe", "Æ": "ae"}


def _norm_car(ch: str) -> str:
    if ch in _LIGATURES:
        return _LIGATURES[ch]
    return "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)).lower()


def normaliser(texte: str) -> str:
    """Minuscules, sans accents ni ligatures. Sert à l'index (désaccentuation) et aux requêtes."""
    return "".join(_norm_car(ch) for ch in texte)


def _norm_carte(texte: str) -> tuple[str, list[int]]:
    """Texte normalisé + pour chaque caractère normalisé, sa position dans le texte d'origine."""
    sortie, carte = [], []
    for i, ch in enumerate(texte):
        for c in _norm_car(ch):
            sortie.append(c)
            carte.append(i)
    return "".join(sortie), carte


def racine(mot: str) -> str:
    """Racine légère (pluriels et e muet) : « couleurs » et « couleur » se rejoignent par préfixe."""
    if len(mot) >= 5:
        for suffixe in ("es", "s", "x", "e"):
            if mot.endswith(suffixe) and len(mot) - len(suffixe) >= 4:
                return mot[: -len(suffixe)]
    return mot


def termes(question: str) -> list[str]:
    """Racines utiles d'une question (ordre conservé, sans doublon). Si tout est mot vide, on garde tout."""
    mots = re.findall(r"[0-9a-z]+", normaliser(question))[:32]
    utiles = [m for m in mots if m not in MOTS_VIDES and len(m) >= 2] or [m for m in mots if len(m) >= 2]
    vus, sortie = set(), []
    for m in utiles:
        r = racine(m)
        if r not in vus:
            vus.add(r)
            sortie.append(r)
    return sortie


def requete_fts(question: str) -> str:
    """Requête FTS5 : chaque racine en préfixe, reliées par OR (BM25 classe d'abord ce qui en contient le plus)."""
    return " OR ".join(f'"{t}"*' for t in termes(question))


# --- Découpage ------------------------------------------------------------------------------------------

def _propre(texte: str) -> str:
    texte = "".join(ch for ch in (texte or "") if ch >= " " or ch in "\n\t")  # ni NUL ni caractère de contrôle
    texte = re.sub(r"[ \t\u00a0]+", " ", texte)
    return re.sub(r"\s*\n\s*", "\n", texte).strip()


def _morceaux(texte: str, maximum: int, recouvrement: int) -> list[str]:
    if len(texte) <= maximum:
        return [texte] if texte else []
    sorties, debut = [], 0
    while debut < len(texte):
        fin = min(len(texte), debut + maximum)
        if fin < len(texte):
            fenetre = texte[debut:fin]
            coupes = [m.end() for m in re.finditer(r"\n|[.!?…](?=\s)", fenetre)]
            coupes = [c for c in coupes if c >= maximum // 2]
            if coupes:
                fin = debut + coupes[-1]
            else:
                espace = fenetre.rfind(" ")
                if espace >= maximum // 2:
                    fin = debut + espace
        morceau = texte[debut:fin].strip()
        if morceau:
            sorties.append(morceau)
        if fin >= len(texte):
            break
        suivant = fin - recouvrement
        if recouvrement:  # ne pas repartir au milieu d'un mot
            espace = texte.find(" ", suivant, fin)
            suivant = espace + 1 if espace != -1 else fin
        debut = max(suivant, debut + 1)
    return sorties


def decouper(sections: list[dict], *, maximum: int = FRAGMENT_MAX, recouvrement: int = RECOUVREMENT) -> list[dict]:
    """Sections `{titre, niveau, texte, zone?}` → fragments `{position, section, niveau, texte, zone}`.
    Un titre sans texte reste trouvable (le fragment porte alors le titre seul)."""
    fragments: list[dict] = []
    for s in sections:
        titre = _propre(str(s.get("titre") or ""))[:200]
        texte = _propre(str(s.get("texte") or ""))
        for morceau in _morceaux(texte, maximum, recouvrement) or ([titre] if titre else []):
            if len(fragments) >= FRAGMENTS_MAX:
                return fragments
            fragments.append({"position": len(fragments), "section": titre, "niveau": int(s.get("niveau") or 0),
                              "texte": morceau, "zone": s.get("zone") or None})
    return fragments


def sections_de_texte(texte: str) -> list[dict]:
    """Texte libre ou Markdown → sections : les lignes « # », « ## », « ### » ouvrent une section."""
    sections, courant = [], {"titre": "", "niveau": 0, "lignes": []}
    for ligne in (texte or "").splitlines():
        m = re.match(r"^(#{1,3})\s+(.+?)\s*#*\s*$", ligne)
        if m:
            if courant["titre"] or any(l.strip() for l in courant["lignes"]):
                sections.append(courant)
            courant = {"titre": m.group(2), "niveau": len(m.group(1)), "lignes": []}
        else:
            courant["lignes"].append(ligne)
    if courant["titre"] or any(l.strip() for l in courant["lignes"]):
        sections.append(courant)
    return [{"titre": s["titre"], "niveau": s["niveau"], "texte": "\n".join(s["lignes"])} for s in sections]


# --- BM25 de repli (sans FTS5) --------------------------------------------------------------------------

def bm25_python(documents: list[tuple[str, str]], question: str, *, limite: int = 50,
                k1: float = 1.2, b: float = 0.75) -> list[tuple[str, float]]:
    """`documents` : (identifiant, texte déjà normalisé). Renvoie (identifiant, score) du meilleur au moins bon.
    Même règle que l'index FTS5 : un mot du document correspond s'il commence par la racine demandée."""
    racines = termes(question)
    if not racines or not documents:
        return []
    jetons = [(i, re.findall(r"[0-9a-z]+", t)) for i, t in documents]
    moyenne = sum(len(j) for _, j in jetons) / len(jetons) or 1.0
    frequences = []
    presence = dict.fromkeys(racines, 0)
    for _, mots in jetons:
        f = {r: sum(1 for m in mots if m.startswith(r)) for r in racines}
        frequences.append(f)
        for r, n in f.items():
            if n:
                presence[r] += 1
    n_docs = len(jetons)
    scores = []
    for (ident, mots), f in zip(jetons, frequences):
        score = 0.0
        for r in racines:
            if f[r]:
                idf = math.log(1 + (n_docs - presence[r] + 0.5) / (presence[r] + 0.5))
                score += idf * f[r] * (k1 + 1) / (f[r] + k1 * (1 - b + b * len(mots) / moyenne))
        if score > 0:
            scores.append((ident, score))
    scores.sort(key=lambda s: (-s[1], s[0]))
    return scores[:limite]


# --- Vecteurs -------------------------------------------------------------------------------------------

class EmbarqueurIndisponible(RuntimeError):
    """Le service de vecteurs ne répond pas : la recherche continue en BM25 seul."""


class Embarqueur(Protocol):
    """Interface enfichable. `modele` identifie l'espace vectoriel : changer de modèle impose de ré-indexer."""

    modele: str

    def embarquer(self, textes: list[str]) -> list[list[float]]:
        """Un vecteur par texte, dans l'ordre. Lève EmbarqueurIndisponible en cas de panne."""


class EmbarqueurOllama:
    """Vecteurs par un Ollama local (POST /api/embed), bibliothèque standard seulement. Rien n'est téléchargé ici :
    le modèle doit déjà être présent (`ollama pull bge-m3`, fait par le propriétaire)."""

    LOT = 16
    TEXTE_MAX = 6000

    def __init__(self, url: str = "http://127.0.0.1:11434", modele: str = "bge-m3", delai_s: float = 30.0):
        if not re.match(r"^https?://[^\s/]+", url or ""):
            raise ValueError("adresse Ollama invalide (http://hôte:port attendu)")
        self.url, self.modele, self.delai_s = url.rstrip("/"), modele, delai_s

    def embarquer(self, textes: list[str], *, delai_s: float | None = None) -> list[list[float]]:
        vecteurs: list[list[float]] = []
        for i in range(0, len(textes), self.LOT):
            lot = [t[: self.TEXTE_MAX] for t in textes[i:i + self.LOT]]
            corps = json.dumps({"model": self.modele, "input": lot}).encode()
            requete = urllib.request.Request(self.url + "/api/embed", data=corps, method="POST",
                                             headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(requete, timeout=delai_s or self.delai_s) as r:  # noqa: S310 — schéma vérifié
                    donnees = json.loads(r.read(64 * 1024 * 1024))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise EmbarqueurIndisponible(f"Ollama injoignable ({type(exc).__name__})") from exc
            recus = donnees.get("embeddings") if isinstance(donnees, dict) else None
            if not isinstance(recus, list) or len(recus) != len(lot):
                raise EmbarqueurIndisponible("réponse Ollama inattendue (modèle absent ?)")
            for v in recus:
                if not isinstance(v, list) or not v or len(v) > 8192 or not all(isinstance(x, (int, float)) for x in v):
                    raise EmbarqueurIndisponible("vecteur Ollama invalide")
                vecteurs.append([float(x) for x in v])
        return vecteurs


def embarqueur_configure() -> Embarqueur | None:
    """L'embarqueur choisi par le propriétaire, ou None (défaut : désactivé).
    Réglages : table `[references]` de settings.toml (`embarqueur = "ollama"`, `ollama_url`, `modele`), ou les
    variables JARVIS_REFERENCES_EMBARQUEUR, JARVIS_REFERENCES_OLLAMA_URL, JARVIS_REFERENCES_MODELE."""
    reglages: dict = {}
    try:
        from . import config
        reglages = config.settings().get("references") or {}
    except Exception:  # noqa: BLE001 — une configuration illisible ne doit pas casser la recherche par mots
        reglages = {}
    sorte = (os.environ.get("JARVIS_REFERENCES_EMBARQUEUR") or str(reglages.get("embarqueur") or "")).strip().lower()
    if sorte != "ollama":
        return None
    try:
        return EmbarqueurOllama(
            os.environ.get("JARVIS_REFERENCES_OLLAMA_URL") or str(reglages.get("ollama_url") or "http://127.0.0.1:11434"),
            os.environ.get("JARVIS_REFERENCES_MODELE") or str(reglages.get("modele") or "bge-m3"))
    except ValueError:
        return None


def emballer(vecteur: list[float]) -> bytes:
    return array.array("f", vecteur).tobytes()


def deballer(blob: bytes) -> array.array:
    a = array.array("f")
    a.frombytes(bytes(blob))
    return a


def cosinus(a, b) -> float:
    if len(a) != len(b) or not len(a):
        return 0.0
    produit = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return produit / (na * nb) if na and nb else 0.0


def plus_proches(requete, candidats: list[tuple[str, bytes]], *, limite: int = 50, seuil: float = 0.0
                 ) -> list[tuple[str, float]]:
    """Voisins par cosinus, en Python pur. `candidats` est borné par l'appelant (pas d'index approché ici)."""
    scores = []
    for ident, blob in candidats:
        s = cosinus(requete, deballer(blob))
        if s > seuil:
            scores.append((ident, s))
    scores.sort(key=lambda s: (-s[1], s[0]))
    return scores[:limite]


def fusion_rrf(classements: list[list[str]], *, k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion : score = Σ 1 / (k + rang). Insensible aux échelles des scores d'origine."""
    scores: dict[str, float] = {}
    for classement in classements:
        for rang, ident in enumerate(classement, start=1):
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + rang)
    return sorted(scores.items(), key=lambda s: (-s[1], s[0]))


# --- Extraits surlignés ---------------------------------------------------------------------------------

def plages(texte: str, question: str) -> list[tuple[int, int]]:
    """Plages (début, fin) du texte d'origine qui correspondent aux racines de la question."""
    racines = termes(question)
    if not racines or not texte:
        return []
    norme, carte = _norm_carte(texte)
    motif = re.compile(r"(?<![0-9a-z])(?:" + "|".join(re.escape(r) for r in sorted(racines, key=len, reverse=True))
                       + r")[0-9a-z]*")
    trouvees = []
    for m in motif.finditer(norme):
        debut, fin = carte[m.start()], carte[m.end() - 1] + 1
        if trouvees and debut <= trouvees[-1][1]:
            trouvees[-1] = (trouvees[-1][0], max(fin, trouvees[-1][1]))
        else:
            trouvees.append((debut, fin))
    return trouvees


def extrait(texte: str, question: str, *, largeur: int = 260) -> dict:
    """Le passage le plus dense en mots trouvés : `{texte, surlignages: [[début, fin]…]}` (positions dans l'extrait)."""
    texte = texte or ""
    trouvees = plages(texte, question)
    if not trouvees or len(texte) <= largeur:
        debut = 0
    else:
        meilleur, debut = -1, 0
        for d, _ in trouvees:
            n = sum(1 for a, b in trouvees if a >= d and b <= d + largeur)
            if n > meilleur:
                meilleur, debut = n, d
        debut = max(0, min(debut - largeur // 5, len(texte) - largeur))
        if debut:
            espace = texte.rfind(" ", 0, debut + 1)
            debut = espace + 1 if espace != -1 and debut - espace < 30 else debut
    fin = min(len(texte), debut + largeur)
    if fin < len(texte):
        espace = texte.rfind(" ", debut, fin)
        fin = espace if espace > debut + largeur // 2 else fin
    prefixe, suffixe = ("… " if debut else ""), (" …" if fin < len(texte) else "")
    marques = [[a - debut + len(prefixe), b - debut + len(prefixe)] for a, b in trouvees if a >= debut and b <= fin]
    return {"texte": prefixe + texte[debut:fin] + suffixe, "surlignages": marques}


def marquer(e: dict, ouvre: str = "«", ferme: str = "»") -> str:
    """Extrait en texte brut avec les mots trouvés entre marques (sortie de la ligne de commande)."""
    texte, sortie, curseur = e["texte"], [], 0
    for a, b in e["surlignages"]:
        sortie.append(texte[curseur:a] + ouvre + texte[a:b] + ferme)
        curseur = b
    sortie.append(texte[curseur:])
    return "".join(sortie)
