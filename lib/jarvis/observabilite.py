"""Observabilité : chaque tâche devient une trace (format OpenTelemetry), avec jetons, durée et équivalent API.

Construit à partir des registres réels (tâches, événements, coûts) : rien n'est instrumenté dans les agents.
- `traces(jours)` : spans au format OTLP/JSON (« resourceSpans »), lisibles par Jaeger, Tempo, Langfuse
  (point d'entrée OTLP) ou tout collecteur OpenTelemetry.
- `exporter_fichier()` : écrit ce JSON (bibliothèque standard, aucune dépendance).
- `envoyer()` : POST HTTP vers `observabilite.otlp_endpoint` (ex. http://localhost:4318) si ce réglage est
  renseigné ; sinon rien ne quitte le poste. Le SDK OpenTelemetry n'est pas nécessaire (protocole OTLP/HTTP JSON).
- `dernieres_executions(20)` : résumé pour le tableau de bord web.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request

from . import config

SERVICE = "jarvis-usine"


def _id(texte: str, n: int) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:n]


def _ns(ts: float) -> str:
    return str(int(ts * 1e9))


def _attr(cle: str, valeur) -> dict:
    if isinstance(valeur, bool):
        v = {"boolValue": valeur}
    elif isinstance(valeur, int):
        v = {"intValue": str(valeur)}
    elif isinstance(valeur, float):
        v = {"doubleValue": valeur}
    else:
        v = {"stringValue": str(valeur)}
    return {"key": cle, "value": v}


def spans_tache(fiche: dict, now: float | None = None) -> list[dict]:
    """Spans d'une tâche : racine « tache », puis « admission », un span par tour d'agent, et « verdict »."""
    from . import couts, evenements, taches
    now = now or time.time()
    trace = _id(fiche["id"], 32)
    racine = _id(fiche["id"] + ":racine", 16)
    fin = fiche.get("fin") or now
    c = couts.cout_fiche(fiche, mesurer=False)
    attrs = [_attr("jarvis.tache", fiche["id"]), _attr("jarvis.projet", fiche["projet"]), _attr("jarvis.issue", fiche["issue"]),
             _attr("jarvis.role", fiche.get("role", "")), _attr("jarvis.agent", fiche["agent"]),
             _attr("jarvis.modele", fiche.get("modele") or f"{fiche['agent']}-defaut"), _attr("jarvis.statut", fiche["statut"]),
             _attr("jarvis.essai", int(fiche.get("essai") or 1)), _attr("jarvis.jetons", int(c["jetons"])),
             _attr("jarvis.equivalent_api_usd", round(c["usd"] or 0.0, 4)), _attr("jarvis.cout_estime", bool(c["estimation"]))]
    if fiche.get("echec"):
        attrs.append(_attr("jarvis.echec", fiche["echec"]["classe"]))
    statut = {"code": "STATUS_CODE_ERROR"} if taches.echoue(fiche) else {"code": "STATUS_CODE_OK"} \
        if fiche["statut"] == "terminee" else {"code": "STATUS_CODE_UNSET"}
    spans = [{"traceId": trace, "spanId": racine, "name": f"tache {fiche['projet']} {fiche['issue']}",
              "kind": "SPAN_KIND_INTERNAL", "startTimeUnixNano": _ns(fiche["cree"]), "endTimeUnixNano": _ns(fin),
              "attributes": attrs, "status": statut}]
    evs = evenements.lire(fiche["id"])
    debut_tour = fiche.get("debut") or fiche["cree"]
    n_tour = 0
    for e in evs:
        if e["type"] == "admis":
            spans.append({"traceId": trace, "spanId": _id(f"{fiche['id']}:admis", 16), "parentSpanId": racine,
                          "name": "admission", "kind": "SPAN_KIND_INTERNAL", "startTimeUnixNano": _ns(e["ts"]),
                          "endTimeUnixNano": _ns(fiche["cree"]), "attributes": [_attr("jarvis.reservation", e.get("reservation", ""))]})
        elif e["type"] == "tour_agent":
            n_tour += 1
            spans.append({"traceId": trace, "spanId": _id(f"{fiche['id']}:tour{n_tour}", 16), "parentSpanId": racine,
                          "name": f"agent.tour.{n_tour}", "kind": "SPAN_KIND_INTERNAL", "startTimeUnixNano": _ns(debut_tour),
                          "endTimeUnixNano": _ns(e["ts"]), "attributes": [_attr("jarvis.etat", e.get("etat", ""))]})
        elif e["type"] == "reprise":
            debut_tour = e["ts"]
        elif e["type"] == "verdict":
            spans.append({"traceId": trace, "spanId": _id(f"{fiche['id']}:verdict", 16), "parentSpanId": racine,
                          "name": "verdict", "kind": "SPAN_KIND_INTERNAL", "startTimeUnixNano": _ns(e["ts"]),
                          "endTimeUnixNano": _ns(e["ts"]), "attributes": [_attr("jarvis.verdict", e.get("verdict", ""))]})
    return spans


def traces(jours: float = 7, now: float | None = None) -> dict:
    from . import taches
    now = now or time.time()
    spans = []
    for t in taches.toutes():
        if now - t["cree"] <= jours * 86400:
            spans += spans_tache(t, now)
    return {"resourceSpans": [{"resource": {"attributes": [_attr("service.name", SERVICE)]},
                               "scopeSpans": [{"scope": {"name": "jarvis.observabilite", "version": "1"}, "spans": spans}]}]}


def exporter_fichier(jours: float = 7) -> str:
    chemin = config.DATA_DIR / "traces" / f"traces-{time.strftime('%Y%m%d-%H%M%S')}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(traces(jours), ensure_ascii=False), encoding="utf-8")
    return str(chemin)


def envoyer(jours: float = 1) -> tuple[bool, str]:
    """POST OTLP/HTTP JSON vers observabilite.otlp_endpoint. Rien n'est envoyé sans ce réglage."""
    point = str(config.settings().get("observabilite", {}).get("otlp_endpoint") or "").rstrip("/")
    if not point:
        return False, "aucun point d'entrée OTLP réglé (observabilite.otlp_endpoint) : rien n'est envoyé"
    if not point.startswith(("http://", "https://")):
        return False, "observabilite.otlp_endpoint doit commencer par http:// ou https://"
    corps = json.dumps(traces(jours)).encode("utf-8")
    req = urllib.request.Request(point + "/v1/traces", data=corps, headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300, f"réponse {r.status}"
    except OSError as exc:
        return False, f"envoi impossible : {exc}"


def dernieres_executions(n: int = 20) -> list[dict]:
    from . import couts, taches
    out = []
    for t in list(reversed(taches.toutes()))[:n]:
        c = couts.cout_fiche(t, mesurer=False)
        fin = t.get("fin") or time.time()
        out.append({"id": t["id"], "projet": t["projet"], "issue": t["issue"], "role": t.get("role", ""),
                    "agent": t["agent"], "modele": t.get("modele") or f"{t['agent']}-defaut", "statut": t["statut"],
                    "echec": (t.get("echec") or {}).get("classe", ""), "duree_min": round((fin - t["cree"]) / 60, 1),
                    "jetons": c["jetons"], "usd": c["usd"], "estimation": c["estimation"], "cree": t["cree"]})
    return out
