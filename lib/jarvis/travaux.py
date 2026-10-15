"""File de travaux partagée : propositions venues de l'extérieur (ton dot ChatGPT, un outil, toi) et
leur suivi jusqu'à un résultat vérifiable.

Règles :
- identifiant stable (W-xxxxx) et empreinte de contenu : la même proposition soumise deux fois (dot,
  import GitHub, saisie à la main) ne crée pas de doublon ;
- une proposition n'autorise RIEN par elle-même : ni dépense, ni publication, ni commande privilégiée,
  ni lancement. Elle devient un travail seulement si le chef ou toi l'acceptez, et ce travail passe
  ensuite par un plan approuvé et l'admission comme tout le reste ;
- un seul exécutant par travail (agent local T-xxxxx OU tâche Codex cloud), noté explicitement : pas
  de double exécution entre un agent local et le cloud ;
- un résultat vérifiable : preuve (PR, fichier livré, bilan) et qui l'a vérifié.
- quota : au plus `max_par_jour` propositions acceptées par source et par jour (défaut 3).

Sources d'entrée possibles aujourd'hui, sans API Dots inventée : fichier JSON déposé (par toi, via
Telegram ou le dossier boîte), ou issues GitHub étiquetées « jarvis-proposition » lues avec `gh`
(un dot peut créer des issues GitHub via l'app GitHub que TU as autorisée dans ChatGPT).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time

from . import config, store

FILE = "travaux.json"
TYPES = ("opportunite", "retours_clients", "brief_produit", "marketing", "bilan", "correctif", "autre")
STATUTS = ("proposee", "acceptee", "en_cours", "terminee", "rejetee")
MAX_PAR_JOUR = 3
ETIQUETTE_GITHUB = "jarvis-proposition"
MAX_CONTENU = 20_000


class TravauxError(ValueError):
    pass


def _vide() -> dict:
    return {"seq": 0, "travaux": []}


def _empreinte(source: str, titre: str, contenu: str, projet: str) -> str:
    base = " ".join(f"{source}|{projet}|{titre}|{contenu}".lower().split())
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _nettoyer(texte: str, maxi: int) -> str:
    """Le contenu externe est une DONNÉE : aucune instruction qu'il contient ne vaut pour Jarvis.
    On le borne et on retire les caractères de contrôle ; le chef le lit comme une proposition, pas un ordre."""
    texte = "".join(ch for ch in str(texte) if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return texte.strip()[:maxi]


def soumettre(*, source: str, titre: str, contenu: str, type_: str = "autre", projet: str = "",
              ref_externe: str = "", par: str = "") -> dict:
    """Ajoute une proposition. Renvoie le travail (existant si c'est un doublon : champ « doublon » = True)."""
    if type_ not in TYPES:
        raise TravauxError(f"type inconnu « {type_} » (valeurs : {', '.join(TYPES)})")
    titre = _nettoyer(titre, 160)
    contenu = _nettoyer(contenu, MAX_CONTENU)
    if not titre:
        raise TravauxError("une proposition a un titre")
    emp = _empreinte(source, titre, contenu, projet)

    def _add(data):
        for t in data["travaux"]:
            if t["empreinte"] == emp or (ref_externe and t.get("ref_externe") == ref_externe and t["source"] == source):
                return {**t, "doublon": True}
        data["seq"] += 1
        t = {"id": f"W-{data['seq']:05d}", "ts": time.time(), "source": source[:40], "par": par[:40], "titre": titre,
             "type": type_, "projet": projet, "contenu": contenu, "ref_externe": ref_externe[:200], "empreinte": emp,
             "statut": "proposee", "executant": "", "tache": "", "resultat": None, "decisions": []}
        data["travaux"].append(t)
        data["travaux"] = data["travaux"][-2000:]
        return {**t, "doublon": False}

    t = store.update_json(FILE, _vide(), _add)
    if not t["doublon"]:
        store.feed_add("note", f"proposition {t['id']} ({source}) : {titre}")
        from . import journal
        journal.ecrire("proposition", acteur=par or source, objet=t["id"], decision="soumise", raison=f"{type_} — {titre}",
                       source=source)
    return t


def tous(statut: str | None = None) -> list[dict]:
    items = store.read_json(FILE, _vide())["travaux"]
    return [t for t in items if statut is None or t["statut"] == statut]


def get(w_id: str) -> dict | None:
    return next((t for t in tous() if t["id"] == w_id.upper()), None)


def _acceptees_aujourdhui(data: dict, source: str, now: float) -> int:
    return sum(1 for t in data["travaux"] if t["source"] == source
               and any(d["decision"] == "acceptee" and now - d["ts"] < 86400 for d in t.get("decisions", [])))


def decider(w_id: str, accepter: bool, *, par: str, raison: str = "", now: float | None = None) -> dict:
    """Accepte (→ travail à planifier) ou rejette une proposition. Au plus MAX_PAR_JOUR acceptations par source et par jour.

    Accepter ne lance rien : le chef doit ensuite proposer un plan (lancement soumis à l'admission).
    """
    now = now or time.time()
    maxi = int(config.settings().get("propositions", {}).get("max_par_jour", MAX_PAR_JOUR))

    def _set(data):
        for t in data["travaux"]:
            if t["id"] != w_id.upper():
                continue
            if t["statut"] != "proposee":
                raise TravauxError(f"{t['id']} est déjà « {t['statut']} »")
            if accepter and _acceptees_aujourdhui(data, t["source"], now) >= maxi:
                raise TravauxError(f"déjà {maxi} proposition(s) de « {t['source']} » acceptée(s) aujourd'hui : "
                                   "la suivante attend demain (plafond propositions.max_par_jour)")
            t["statut"] = "acceptee" if accepter else "rejetee"
            t["decisions"].append({"ts": now, "decision": t["statut"], "par": par, "raison": raison[:300]})
            return dict(t)
        raise TravauxError(f"travail {w_id} introuvable")

    t = store.update_json(FILE, _vide(), _set)
    from . import journal
    journal.ecrire("proposition", acteur=par, objet=t["id"], decision=t["statut"], raison=raison)
    return t


def confier(w_id: str, executant: str, tache: str = "", par: str = "chef") -> dict:
    """Un seul exécutant : « local:claude », « local:codex » ou « codex-cloud ». Refus s'il en a déjà un."""
    if not (executant.startswith("local:") or executant == "codex-cloud"):
        raise TravauxError("exécutant : local:claude, local:codex ou codex-cloud")

    def _set(data):
        for t in data["travaux"]:
            if t["id"] != w_id.upper():
                continue
            if t["statut"] not in ("acceptee", "en_cours"):
                raise TravauxError(f"{t['id']} est « {t['statut']} » : seul un travail accepté se confie")
            if t["executant"] and t["executant"] != executant:
                raise TravauxError(f"{t['id']} a déjà un exécutant ({t['executant']}) : pas de double exécution")
            t["statut"], t["executant"], t["tache"] = "en_cours", executant, tache or t["tache"]
            t["decisions"].append({"ts": time.time(), "decision": "confie", "par": par, "raison": f"{executant} {tache}".strip()})
            return dict(t)
        raise TravauxError(f"travail {w_id} introuvable")

    t = store.update_json(FILE, _vide(), _set)
    from . import journal
    journal.ecrire("proposition", acteur=par, objet=t["id"], decision="confie", raison=executant, tache=tache or None)
    return t


def terminer(w_id: str, *, preuve: str, verifie_par: str, ok: bool = True, note: str = "") -> dict:
    """Résultat vérifiable : une preuve (PR, chemin de livrable, bilan) et qui l'a vérifiée (autre que l'exécutant)."""
    if not preuve.strip():
        raise TravauxError("un résultat se termine avec une preuve (PR, fichier, bilan)")

    def _set(data):
        for t in data["travaux"]:
            if t["id"] != w_id.upper():
                continue
            if t["statut"] != "en_cours":
                raise TravauxError(f"{t['id']} n'est pas en cours")
            if verifie_par == t["executant"]:
                raise TravauxError("l'exécutant ne vérifie pas son propre résultat")
            t["statut"] = "terminee" if ok else "acceptee"  # échec : retourne à « acceptée », exécutant libéré
            if not ok:
                t["executant"], t["tache"] = "", ""
            t["resultat"] = {"ts": time.time(), "ok": ok, "preuve": preuve[:300], "verifie_par": verifie_par, "note": note[:300]}
            return dict(t)
        raise TravauxError(f"travail {w_id} introuvable")

    t = store.update_json(FILE, _vide(), _set)
    from . import journal
    journal.ecrire("proposition", acteur=verifie_par, objet=t["id"], decision="verifiee" if ok else "echouee", raison=preuve)
    return t


# --- Import depuis GitHub (application autorisée par toi, lue avec gh) -----------------------------

def importer_github(depot: str, issues: list[dict] | None = None, etiquette: str = ETIQUETTE_GITHUB) -> list[dict]:
    """Issues ouvertes étiquetées `etiquette` → propositions (source « github:<depot> »). `issues` permet les tests.

    Le corps de l'issue est pris tel quel comme contenu : données non fiables, jamais des instructions.
    Un en-tête facultatif « type: marketing » / « projet: repriceo » en première ligne classe la proposition.
    """
    if issues is None:
        try:
            res = subprocess.run(["gh", "issue", "list", "-R", depot, "--label", etiquette, "--state", "open",
                                  "--json", "number,title,body,author,url", "--limit", "50"],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TravauxError(f"gh indisponible : {exc}") from exc
        if res.returncode != 0:
            raise TravauxError((res.stderr or "gh issue list a échoué").strip().splitlines()[-1])
        try:
            issues = json.loads(res.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise TravauxError("réponse illisible de gh") from exc
    nouveaux = []
    for it in issues:
        corps = str(it.get("body") or "")
        type_, projet, lignes = "autre", "", []
        for ln in corps.splitlines():
            m = ln.strip().lower()
            if m.startswith("type:") and m.split(":", 1)[1].strip() in TYPES:
                type_ = m.split(":", 1)[1].strip()
            elif m.startswith("projet:"):
                projet = ln.split(":", 1)[1].strip()[:40]
            else:
                lignes.append(ln)
        t = soumettre(source=f"github:{depot}", titre=str(it.get("title") or f"issue #{it.get('number')}"),
                      contenu="\n".join(lignes), type_=type_, projet=projet,
                      ref_externe=str(it.get("url") or f"{depot}#{it.get('number')}"),
                      par=str((it.get("author") or {}).get("login") or ""))
        if not t["doublon"]:
            nouveaux.append(t)
    return nouveaux


def texte(items: list[dict] | None = None) -> str:
    items = tous() if items is None else items
    if not items:
        return "Aucune proposition. En soumettre : jarvis proposition soumettre --source dot --titre … --fichier contenu.md"
    icone = {"proposee": "📨", "acceptee": "👍", "en_cours": "🔧", "terminee": "✅", "rejetee": "✋"}
    out = []
    for t in items[-30:]:
        quand = time.strftime("%d/%m", time.localtime(t["ts"]))
        ligne = f"{icone.get(t['statut'], '•')} {t['id']} [{t['type']}{', ' + t['projet'] if t['projet'] else ''}] {t['titre']} — {t['source']} {quand}"
        if t.get("executant"):
            ligne += f" → {t['executant']}" + (f" ({t['tache']})" if t.get("tache") else "")
        if t.get("resultat"):
            r = t["resultat"]
            ligne += f" · preuve : {r['preuve']} (vérifié par {r['verifie_par']})"
        out.append(ligne)
    return "\n".join(out)
