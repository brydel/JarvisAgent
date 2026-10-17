"""Bilan quotidien : ce qui a été livré, prouvé, échoué, consommé, les risques et les décisions qui t'attendent.

Calculé à partir des registres réels (tâches, travaux, budgets, pauses, politique, plans) : aucune donnée
de démonstration. Envoyé chaque matin sur Telegram par le démon (réglage bilan.heure), ou affiché avec
« jarvis bilan quotidien ». Les trois chiffres qui comptent viennent en premier.
"""

from __future__ import annotations

import time

JOUR = 86400


def donnees(now: float | None = None) -> dict:
    from . import budgets, couts, pauses, plans, politique, store, taches, travaux, usage
    now = now or time.time()
    fiches = taches.toutes()

    def _fini(t, duree):
        return t.get("fin") and now - t["fin"] < duree

    livrees = [t for t in fiches if t["statut"] == "terminee" and _fini(t, JOUR) and not taches.echoue(t)
               and (t.get("echec") or {}).get("classe") != "quota"]
    echouees = [t for t in fiches if _fini(t, JOUR) and (taches.echoue(t) or (t.get("echec") or {}).get("classe") == "quota")]
    prouvees = [t for t in fiches if t.get("verdict") == "pret" and now - (t.get("verdict_ts") or 0) < JOUR]
    travaux_prouves = [w for w in travaux.tous("terminee") if now - ((w.get("resultat") or {}).get("ts") or 0) < JOUR]
    semaine = {"livrees": sum(1 for t in fiches if t["statut"] == "terminee" and _fini(t, 7 * JOUR) and not taches.echoue(t)
                              and (t.get("echec") or {}).get("classe") != "quota"),
               "echouees": sum(1 for t in fiches if _fini(t, 7 * JOUR)
                               and (taches.echoue(t) or (t.get("echec") or {}).get("classe") == "quota"))}

    jour = [t for t in fiches if (t.get("fin") and now - t["fin"] < JOUR) or t["statut"] in taches.OUVERTS]
    lignes = couts.tableau(jour, mesurer_ouvertes=False)
    usd = sum(x["usd"] or 0 for x in lignes)
    jetons = sum(x["jetons"] for x in lignes)
    par_fournisseur: dict[str, int] = {}
    for x in lignes:
        par_fournisseur[x["agent"]] = par_fournisseur.get(x["agent"], 0) + x["jetons"]
    depenses = [m for m in store.read_json(budgets.FILE, budgets._vide())["mouvements"]
                if m["type"] == "depense" and not m.get("estime") and now - m["ts"] < JOUR]

    try:
        resume = usage.summary(now)
    except Exception:  # noqa: BLE001
        resume = {}
    quotas = {p: {"niveau": u.get("niveau"), "perime": u.get("perime")} for p, u in resume.items()}

    escalades = []
    vus = set()
    for t in fiches:
        cle = (t["projet"], t["issue"], t.get("role", ""))
        if cle in vus or now - t["cree"] > 7 * JOUR:
            continue
        vus.add(cle)
        unite = taches.unite(*cle, liste=fiches)
        dernier = unite[-1]
        if dernier["statut"] in taches.OUVERTS or not taches.echoue(dernier):
            continue
        bloque = taches.verifier_reprise(*cle, liste=fiches)
        if bloque and bloque[0] == "escalade":
            escalades.append({"projet": cle[0], "issue": cle[1], "role": cle[2], "tache": dernier["id"]})

    return {
        "ts": now,
        "livrees": livrees, "echouees": echouees, "prouvees": prouvees, "travaux_prouves": travaux_prouves,
        "semaine": semaine, "usd": usd, "estimation": any(x["estimation"] for x in lignes), "jetons": jetons,
        "par_fournisseur": par_fournisseur, "depenses": depenses, "quotas": quotas,
        "pauses": pauses.actives(), "exceptions": politique.exceptions(),
        "plans": plans.pending(), "propositions_travaux": travaux.tous("proposee"), "escalades": escalades,
    }


def quotidien(now: float | None = None, d: dict | None = None) -> str:
    from . import couts, pauses, taches
    d = d or donnees(now)
    quand = time.strftime("%d/%m", time.localtime(d["ts"]))
    out = [f"📊 Bilan du {quand} — livré {len(d['livrees'])} · échoué {len(d['echouees'])} · "
           f"équivalent API {couts.monnaie(d['usd'])}{' (estim.)' if d['estimation'] else ''}",
           f"7 jours : {d['semaine']['livrees']} livrée(s), {d['semaine']['echouees']} en échec.", ""]

    out.append("✅ LIVRÉ (24 h)")
    out += [f"  {t['projet']} {t['issue']} [{t.get('role')}] {t['id']}" for t in d["livrees"][:10]] or ["  rien"]
    prouve = [f"  {t['projet']} {t['issue']} : relecture « prêt »" for t in d["prouvees"]]
    prouve += [f"  {w['id']} {w['titre']} : {w['resultat']['preuve']}" for w in d["travaux_prouves"]]
    out += ["", "🔎 PROUVÉ (24 h)"] + (prouve[:10] or ["  rien de vérifié par un tiers"])
    out += ["", "⚠ ÉCHOUÉ (24 h)"]
    out += [f"  {t['projet']} {t['issue']} {t['id']} : "
            + ((t.get('echec') or {}).get('classe') or taches.STATUTS.get(t['statut'], t['statut']))
            for t in d["echouees"][:10]] or ["  aucun"]

    out += ["", "💶 CONSOMMÉ (24 h)"]
    fourn = ", ".join(f"{p} {taches.fmt_jetons(n)}" for p, n in sorted(d["par_fournisseur"].items())) or "aucune mesure"
    out.append(f"  jetons : {taches.fmt_jetons(d['jetons'])} ({fourn}) — équivalent API, pas une dépense")
    reel = sum(m["montant"] for m in d["depenses"])
    out.append(f"  dépenses réelles enregistrées : {reel:g}" if d["depenses"] else "  dépenses réelles : aucune")
    for p, q in d["quotas"].items():
        if q.get("niveau") in ("alerte", "epuise") or q.get("perime"):
            out.append(f"  quota {p} : {q['niveau']}" + (" (mesure périmée)" if q.get("perime") else ""))

    risques = []
    if d["pauses"]:
        risques.append("  " + pauses.texte(d["pauses"]))
    if d["exceptions"]:
        risques.append(f"  {len(d['exceptions'])} demande(s) hors politique en attente")
    out += ["", "🧯 RISQUES"] + (risques or ["  rien à signaler"])

    decisions = [f"  plan {p['id']} : {p['titre']}" for p in d["plans"]]
    decisions += [f"  exception {e['id']} : {e['action']} ({e['raison'][:80]})" for e in d["exceptions"][:5]]
    decisions += [f"  escalade : {x['projet']} {x['issue']} [{x['role']}] — jarvis tache relancer {x['tache']} --autoriser"
                  for x in d["escalades"]]
    if d["propositions_travaux"]:
        decisions.append(f"  {len(d['propositions_travaux'])} proposition(s) dans la file (jarvis proposition)")
    out += ["", "🗳 DÉCISIONS DEMANDÉES"] + (decisions or ["  aucune"])
    note = couts.note_monnaie()
    if note:
        out += ["", note]
    return "\n".join(out)
