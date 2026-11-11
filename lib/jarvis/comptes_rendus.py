"""Comptes rendus des agents : un seul format, lisible par une machine, pour finir une tâche et pour relire.

- Fin de tâche : bloc `✅ TERMINÉ` (critère → preuve, commande → résultat, hypothèses, risques, fichiers, branche/PR).
- Relecture : première ligne `VERDICT : PRÊT` ou `VERDICT : CORRECTIONS`, puis la liste numérotée des corrections
  exigées, chacune avec sa sévérité et son `fichier:ligne`.

Les gabarits ci-dessous sont ceux que le prompt de chaque agent reçoit (lib/jarvis/prompt_agent.py) ; l'analyseur
relit ce format. Il est tolérant (gras, accents absents, « : » collé) mais signale tout écart dans « anomalies » :
un texte est « conforme » quand il n'en a aucune. L'analyseur lit un texte, il ne juge pas le travail.

En ligne de commande : `python3 -m jarvis.comptes_rendus <fichier>` (ou l'entrée standard) affiche l'analyse en JSON.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

SEVERITES = ("bloquant", "majeur", "mineur")
_SEVERITES_ALIAS = {"bloquante": "bloquant", "critique": "bloquant", "majeure": "majeur", "mineure": "mineur"}

GABARIT_TERMINE = """\
✅ TERMINÉ
Rôle : <ton rôle> · Tâche : <ISSUE>
Résumé : <2 ou 3 phrases : ce qui change et pourquoi>
Critères :
1. <critère d'acceptation de l'issue> → <preuve : fichier:ligne, test, capture ou commande>
Vérifications :
- `<commande lancée>` → <résultat observé : OK, ou ÉCHEC + la raison>
Hypothèses :
- <choix fait sans confirmation, et pourquoi> (ou « aucune »)
Risques :
- <ce qui peut casser, ce qui reste à faire, ce que tu n'as pas pu vérifier> (ou « aucun »)
Fichiers :
- <chemin modifié ou livrable déposé>
Branche : <branche> · PR : <#numéro, ou « aucune » + la raison>"""

GABARIT_VERDICT = """\
VERDICT : CORRECTIONS
Corrections exigées :
1. [bloquant] chemin/fichier.py:42 — ce qui est faux, et ce qui est attendu
2. [majeur] chemin/autre.ts:10 — …
Suggestions :
- <amélioration non bloquante> (ou « aucune »)
Vérifications :
- `<commande lancée>` → <résultat observé>"""

REGLES_VERDICT = (
    "La première ligne est exactement `VERDICT : PRÊT` ou `VERDICT : CORRECTIONS`, sans rien avant ni autour. "
    "`PRÊT` : aucune correction exigée (écris « Corrections exigées : aucune »). `CORRECTIONS` : au moins une, "
    "numérotée, avec sa sévérité entre crochets (`bloquant` : faux, dangereux ou critère non satisfait ; `majeur` : "
    "non testé ou fragile ; `mineur` : à corriger mais sans risque) et son `fichier:ligne`. Ce qui n'empêche pas de "
    "livrer va dans « Suggestions ».")

_VERDICT = re.compile(r"^\W*VERDICT\s*:\s*(PR[EÊ]TE?|CORRECTIONS?)(?![A-Za-zÀ-ÿ])", re.I)
_NUMERO = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+(.*\S)\s*$")
_PUCE = re.compile(r"^\s*[-*•]\s+(.*\S)\s*$")
_CROCHET = re.compile(r"^\[\s*([A-Za-zÀ-ÿ]+)\s*\]\s*")
# Chemin de fichier (avec extension ou au moins un « / »), suivi ou non de « :ligne » ou « :ligne-ligne ».
_LIEU = re.compile(r"^`?((?:[\w.@+-]+/)*[\w.@+-]+\.[A-Za-z0-9]{1,8}|(?:[\w.@+-]+/)+[\w.@+-]+)(?::(\d+)(?:-\d+)?)?`?")
_SEPARATEUR = re.compile(r"^\s*(?:—|–|-|:)\s*")
_FLECHE = re.compile(r"\s*(?:→|->|=>)\s*")
_VIDE = re.compile(r"^(aucune?s?|néant|rien|n/a|ras)\b", re.I)
_RUBRIQUES = {
    "corrections": re.compile(r"^corrections?(\s+(exig[ée]e?s?|demand[ée]e?s?|bloquantes?))?$", re.I),
    "suggestions": re.compile(r"^(suggestions?|remarques?(\s+non\s+bloquantes?)?)$", re.I),
    "verifications": re.compile(r"^v[ée]rifications?(\s+lanc[ée]e?s?)?$", re.I),
    "resume": re.compile(r"^r[ée]sum[ée]$", re.I),
    "criteres": re.compile(r"^crit[èe]res?(\s+d'acceptation)?$", re.I),
    "hypotheses": re.compile(r"^hypoth[èe]ses?(\s+prises?)?$", re.I),
    "risques": re.compile(r"^risques?$", re.I),
    "fichiers": re.compile(r"^(fichiers?|livrables?)(\s+(modifi[ée]s?|d[ée]pos[ée]s?))?$", re.I),
}


def _propre(ligne: str) -> str:
    """Ligne sans décoration Markdown de début (titre, citation, gras), espaces insécables ramenés à des espaces."""
    t = unicodedata.normalize("NFC", ligne).replace(" ", " ").replace(" ", " ")
    t = re.sub(r"^\s*(?:>+\s*)*(?:#{1,6}\s+)?", "", t)
    return t.replace("**", "").replace("__", "").strip()


def _rubrique(ligne: str) -> tuple[str, str] | None:
    """(rubrique, reste de la ligne) si la ligne ouvre une rubrique connue : « Risques : » ou « Risques : aucun »."""
    tete, deux_points, reste = _propre(ligne).partition(":")
    tete = tete.strip()
    for nom, motif in _RUBRIQUES.items():
        if motif.match(tete) and (deux_points or not reste):
            return nom, reste.strip()
    return None


def _element(ligne: str) -> str | None:
    """Texte d'un élément de liste (numéroté ou à puce), sinon None."""
    m = _NUMERO.match(ligne) or _PUCE.match(ligne)
    return m.group(m.lastindex).strip() if m else None


def _correction(numero: int, texte: str) -> dict:
    t = texte.strip()
    severite = ""
    m = _CROCHET.match(t)
    if m:
        mot = unicodedata.normalize("NFC", m.group(1)).lower()
        mot = _SEVERITES_ALIAS.get(mot, mot)
        if mot in SEVERITES:
            severite, t = mot, t[m.end():]
    fichier, ligne = "", None
    m = _LIEU.match(t)
    if m:
        fichier, ligne = m.group(1), int(m.group(2)) if m.group(2) else None
        t = t[m.end():]
    t = _SEPARATEUR.sub("", t, count=1).strip()
    return {"n": numero, "severite": severite, "fichier": fichier, "ligne": ligne, "texte": t}


def _paire(texte: str, gauche: str, droite: str) -> dict:
    a, *b = _FLECHE.split(texte, maxsplit=1)
    return {gauche: a.strip().strip("`").strip(), droite: (b[0].strip() if b else "")}


def _sections(lignes: list[str]) -> dict[str, list[str]]:
    """Découpe en rubriques : {rubrique: [éléments]}. Une ligne indentée sans puce prolonge l'élément précédent."""
    out: dict[str, list[str]] = {}
    courante: str | None = None
    for brute in lignes:
        r = _rubrique(brute)
        if r:
            courante = r[0]
            out.setdefault(courante, [])
            if r[1]:
                out[courante].append(r[1])
            continue
        if courante is None or not brute.strip():
            continue
        if re.match(r"^\s*(?:>+\s*)*#{1,6}\s", brute):  # un titre inconnu ferme la rubrique
            courante = None
            continue
        elt = _element(_propre(brute) if brute.lstrip().startswith(">") else brute)
        if elt is not None:
            out[courante].append(elt)
        elif out[courante] and brute[:1] in (" ", "\t"):
            out[courante][-1] += " " + brute.strip()
        elif courante in ("resume",):
            out[courante].append(brute.strip())
    return out


def _liste(elements: list[str]) -> list[str]:
    return [e for e in elements if not _VIDE.match(e.strip("« »\"'*_ "))]


def analyser_verdict(texte: str) -> dict:
    """Verdict d'une relecture et corrections exigées.

    Renvoie {"verdict": "pret" | "corrections" | "", "premiere_ligne": bool, "corrections": [{"n", "severite",
    "fichier", "ligne", "texte"}], "suggestions": [...], "verifications": [{"commande", "resultat"}],
    "anomalies": [...], "conforme": bool}. Le verdict retenu est le premier rencontré.
    """
    lignes = str(texte or "").splitlines()
    verdict, premiere, debut = "", False, 0
    utiles = [i for i, ln in enumerate(lignes) if ln.strip()]
    for i in utiles:
        m = _VERDICT.match(_propre(lignes[i]))
        if m:
            mot = unicodedata.normalize("NFD", m.group(1)).encode("ascii", "ignore").decode().upper()
            verdict = "pret" if mot.startswith("PRET") else "corrections"
            premiere, debut = i == utiles[0], i + 1
            break
    suite = lignes[debut:]
    sections = _sections(suite)
    brutes = sections.get("corrections")
    if brutes is None and verdict == "corrections":
        # Liste numérotée posée directement sous le verdict, sans l'intitulé « Corrections exigées : ».
        brutes = []
        for ln in suite:
            if _rubrique(ln):
                break
            m = _NUMERO.match(ln)
            if m:
                brutes.append(m.group(2))
            elif brutes and ln[:1] in (" ", "\t") and ln.strip():
                brutes[-1] += " " + ln.strip()
    corrections = [_correction(n, t) for n, t in enumerate(_liste(brutes or []), 1)]
    anomalies = []
    if not verdict:
        anomalies.append("verdict absent : la première ligne doit être « VERDICT : PRÊT » ou « VERDICT : CORRECTIONS »")
    elif not premiere:
        anomalies.append("le verdict n'est pas sur la première ligne")
    if verdict == "corrections" and not corrections:
        anomalies.append("verdict CORRECTIONS sans liste numérotée de corrections exigées")
    if verdict == "pret" and corrections:
        anomalies.append("verdict PRÊT avec des corrections exigées : contradiction")
    for c in corrections:
        if not c["severite"]:
            anomalies.append(f"correction {c['n']} sans sévérité ({', '.join(SEVERITES)})")
        if not c["fichier"]:
            anomalies.append(f"correction {c['n']} sans fichier:ligne")
        elif c["ligne"] is None:
            anomalies.append(f"correction {c['n']} sans numéro de ligne")
    return {"verdict": verdict, "premiere_ligne": premiere, "corrections": corrections,
            "suggestions": _liste(sections.get("suggestions", [])),
            "verifications": [_paire(v, "commande", "resultat") for v in _liste(sections.get("verifications", []))],
            "anomalies": anomalies, "conforme": not anomalies}


_TERMINE = re.compile(r"^\W*TERMIN[ÉE]\b", re.I)
_BRANCHE = re.compile(r"branche\s*:\s*`?([^\s·`|,;]+)", re.I)
_PR = re.compile(r"\bPR\s*:\s*`?(?:#\s*(\d+)|\S*/pull/(\d+))", re.I)


def analyser_termine(texte: str) -> dict:
    """Compte rendu de fin de tâche (bloc ✅ TERMINÉ).

    Renvoie {"termine": bool, "resume", "criteres": [{"critere", "preuve"}], "verifications": [{"commande",
    "resultat"}], "hypotheses", "risques", "fichiers", "branche", "pr": int | None, "anomalies", "conforme"}.
    """
    lignes = str(texte or "").splitlines()
    debut = next((i for i, ln in enumerate(lignes) if "✅" in ln and _TERMINE.match(_propre(ln).replace("✅", ""))), None)
    corps = lignes[debut + 1:] if debut is not None else lignes
    s = _sections(corps)
    plein = "\n".join(_propre(ln) for ln in corps)
    branche = _BRANCHE.search(plein)
    pr = _PR.search(plein)
    criteres = [_paire(c, "critere", "preuve") for c in _liste(s.get("criteres", []))]
    verifs = [_paire(v, "commande", "resultat") for v in _liste(s.get("verifications", []))]
    anomalies = []
    if debut is None:
        anomalies.append("bloc « ✅ TERMINÉ » absent")
    for cle, nom in (("resume", "Résumé"), ("criteres", "Critères"), ("verifications", "Vérifications"),
                     ("hypotheses", "Hypothèses"), ("risques", "Risques"), ("fichiers", "Fichiers")):
        if cle not in s or (cle in ("resume", "criteres", "verifications", "fichiers") and not _liste(s[cle])):
            anomalies.append(f"rubrique « {nom} » absente ou vide")
    anomalies += [f"critère {i} sans preuve" for i, c in enumerate(criteres, 1) if not c["preuve"]]
    anomalies += [f"vérification {i} sans résultat" for i, v in enumerate(verifs, 1) if not v["resultat"]]
    if not branche:
        anomalies.append("branche absente")
    return {"termine": debut is not None, "resume": " ".join(s.get("resume", [])).strip(), "criteres": criteres,
            "verifications": verifs, "hypotheses": _liste(s.get("hypotheses", [])),
            "risques": _liste(s.get("risques", [])), "fichiers": [f.strip("`") for f in _liste(s.get("fichiers", []))],
            "branche": branche.group(1) if branche else "",
            "pr": int(pr.group(1) or pr.group(2)) if pr else None,
            "anomalies": anomalies, "conforme": not anomalies}


def analyser(texte: str) -> dict:
    """Reconnaît le type du compte rendu : {"type": "verdict" | "termine" | "inconnu", …analyse}."""
    v = analyser_verdict(texte)
    if v["verdict"]:
        return {"type": "verdict", **v}
    t = analyser_termine(texte)
    if t["termine"]:
        return {"type": "termine", **t}
    return {"type": "inconnu", "anomalies": ["ni « VERDICT : … » ni « ✅ TERMINÉ »"], "conforme": False}


def ligne_correction(c: dict) -> str:
    """Une correction sur une ligne, au format du gabarit."""
    lieu = c["fichier"] + (f":{c['ligne']}" if c.get("ligne") else "") if c.get("fichier") else ""
    tete = " ".join(x for x in (f"[{c['severite']}]" if c.get("severite") else "", lieu) if x)
    return f"{c['n']}. " + (f"{tete} — {c['texte']}" if tete and c["texte"] else tete or c["texte"])


def resume_verdict(analyse: dict, maxi: int = 500) -> str:
    """Résumé court des corrections, pour `jarvis verdict <projet> <ISSUE> corrections "<résumé>"`."""
    texte = " ; ".join(ligne_correction(c) for c in analyse.get("corrections", []))
    return texte if len(texte) <= maxi else texte[:maxi - 1].rstrip() + "…"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        texte = open(argv[0], encoding="utf-8").read() if argv else sys.stdin.read()
    except OSError as exc:
        print(f"compte rendu illisible : {exc}", file=sys.stderr)
        return 1
    res = analyser(texte)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["conforme"] else 2


if __name__ == "__main__":
    sys.exit(main())
