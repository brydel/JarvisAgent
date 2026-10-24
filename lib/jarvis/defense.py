"""Triage déterministe sur données fournies ; aucune collecte ni remédiation."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import re
import stat
import sys

MAX_BYTES = 64_000
MAX_EVENTS = 200
MAX_LINE = 2048
TOOL = "security.auth_triage"
SCHEMA = {"type": "object", "properties": {"journal": {"type": "string", "maxLength": MAX_BYTES}},
          "required": ["journal"], "additionalProperties": False}
AUTH = re.compile(r"(?P<time>\S+) (?P<host>[\w.-]+) sshd(?:\[\d+\])?: "
                  r"(?P<outcome>Failed|Accepted) (?P<method>password|publickey) for "
                  r"(?:invalid user )?(?P<account>\S+) from (?P<source>\S+) port \d+(?: ssh2)?")
KINDS = {"auth_failure", "auth_success"}


class DefenseError(ValueError):
    """Erreur statique : ne jamais reproduire une entrée non fiable."""


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError
    return dt.astimezone(timezone.utc)


def normaliser(journal: str) -> tuple[list[dict], dict]:
    """JSONL structuré ou lignes SSH strictes à date ISO avec fuseau ; pas de texte libre exporté."""
    if not isinstance(journal, str):
        raise DefenseError("Un journal texte est requis.")
    try:
        if len(journal) > MAX_BYTES or len(journal.encode("utf-8")) > MAX_BYTES:
            raise DefenseError("Journal trop volumineux (64 000 octets maximum).")
    except UnicodeError:
        raise DefenseError("Encodage du journal invalide.") from None
    lines = journal.splitlines()
    if len(lines) > MAX_EVENTS:
        raise DefenseError("Trop de lignes (200 maximum).")
    events, seen = [], set()
    counts = {"lignes": len(lines), "valides": 0, "invalides": 0, "doublons": 0, "vides": 0}
    for index, line in enumerate(lines, 1):
        if not line.strip():
            counts["vides"] += 1
            continue
        try:
            if len(line.encode()) > MAX_LINE:
                raise ValueError
            if line.lstrip().startswith("{"):
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError
                        result[key] = value
                    return result
                raw = json.loads(line, object_pairs_hook=pairs)
                if (not isinstance(raw, dict)
                        or not {"timestamp", "kind", "source", "account", "host"} <= set(raw)
                        or set(raw) - {"timestamp", "kind", "source", "account", "host", "message"}):
                    raise ValueError
                if "message" in raw and not isinstance(raw["message"], str):
                    raise ValueError
            else:
                match = AUTH.fullmatch(line)
                if not match:
                    raise ValueError
                raw = {"timestamp": match["time"], "host": match["host"], "source": match["source"],
                       "account": match["account"],
                       "kind": "auth_failure" if match["outcome"] == "Failed" else "auth_success"}
            if raw["kind"] not in KINDS:
                raise ValueError
            for key in ("source", "account", "host"):
                v = raw[key]
                if not isinstance(v, str) or not v or len(v) > 128 or any(c.isspace() or ord(c) < 32 for c in v):
                    raise ValueError
            timestamp = _timestamp(raw["timestamp"])
            identity = (timestamp, raw["kind"], raw["source"], raw["account"], raw["host"])
            if identity in seen:
                counts["doublons"] += 1
                continue
            seen.add(identity)
            events.append({"time": timestamp, "kind": raw["kind"], "source": raw["source"],
                           "account": raw["account"], "host": raw["host"], "line": index})
            counts["valides"] += 1
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            counts["invalides"] += 1
    return sorted(events, key=lambda e: (e["time"], e["line"])), counts


def analyser(journal: str) -> dict:
    events, counts = normaliser(journal)
    # Identifiants opaques limités à ce rapport : aucune empreinte devinable ni valeur brute.
    aliases = {key: {} for key in ("source", "account", "host")}
    public = []
    for event in events:
        safe = {"id": f"E-{event['line']}", "ligne": event["line"], "type": event["kind"]}
        for key, mapping in aliases.items():
            safe[key] = mapping.setdefault(event[key], f"{key}-{len(mapping) + 1}")
        public.append(safe)
    groups = defaultdict(list)
    for event in events:
        groups[(event["source"], event["account"], event["host"])].append(event)
    alerts = []
    for group in groups.values():
        failures = []
        selected = []
        success = None
        for event in group:
            failures = [e for e in failures if (event["time"] - e["time"]).total_seconds() <= 300]
            if event["kind"] == "auth_failure":
                failures.append(event)
                if len(failures) >= 5 and not selected:
                    selected = list(failures)
            else:
                earlier = [e for e in failures if e["time"] < event["time"]]
                if len(earlier) >= 5:
                    selected, success = earlier, event
                    break
        if selected:
            refs = [f"E-{e['line']}" for e in selected + ([success] if success else [])]
            alerts.append({"id": f"A-{len(alerts) + 1}",
                "regle": "AUTH-002" if success else "AUTH-001",
                "gravite": "elevee" if success else "moyenne", "qualification": "signal_a_verifier",
                "intrusion_confirmee": False, "preuves": refs,
                "justification": "Au moins cinq échecs uniques en cinq minutes, suivis d'un succès dans cette fenêtre."
                    if success else "Au moins cinq échecs uniques en cinq minutes pour le même triplet source/compte/hôte.",
                "incertitude": "Événements déclarés non authentifiés ; erreur humaine, automatisation légitime ou collecte répétée possibles.",
                "recommandations": ["Faire valider le contexte et la provenance par un humain.",
                    "Vérifier avec le titulaire si cette activité était attendue.",
                    "Si l'activité est confirmée indésirable, proposer un plan de restriction ou de renouvellement des accès à approuver ; ne rien exécuter."]})
    return {"version": 1, "agent": "jarvis-defense", "mode": "observation", "source_non_fiable": True,
            "statut": "donnees_insuffisantes" if not events else "revue_requise" if alerts else "aucun_signal_detecte",
            "couverture": counts, "evenements": public, "alertes": alerts,
            "intrusion_confirmee": False, "actions_executees": [], "validation_humaine_requise": True,
            "limites": ["Analyse du seul lot fourni ; absence de signal ne prouve pas l'absence d'intrusion.",
                        "Dédoublonnage sémantique dans le lot uniquement ; événements simultanés identiques fusionnés.",
                        "Messages, dates et identifiants bruts supprimés du rapport ; conserver les originaux hors dépôt public."]}


def catalogue():
    return [{"id": TOOL, "nom": "Trier un journal fourni", "effet": "lecture", "disponible": True,
             "inputSchema": SCHEMA}]


def preparer(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {"journal"}:
        raise DefenseError("Seul le champ journal est accepté.")
    # Validation avant réservation ; aucune lecture de fichier dans la passerelle.
    result = analyser(arguments["journal"])
    def appel(verifier):
        verifier()
        return result
    return None, False, appel


def lire_fichier(path):
    # Ne pas bloquer sur FIFO, périphérique ou lien ; lecture bornée sur le descripteur validé.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise DefenseError("Un fichier ordinaire est requis.")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DefenseError("Journal trop volumineux (64 000 octets maximum).")
    return data.decode("utf-8")


def command(args):
    try:
        result = analyser(lire_fichier(args.fichier))
    except (ValueError, OSError):
        print("Défense : entrée refusée ou illisible ; vérifier le format et les limites.", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def add_parser(sub):
    parser = sub.add_parser("defense", help="triage défensif en observation, sans collecte")
    actions = parser.add_subparsers(dest="defense_action", required=True)
    triage = actions.add_parser("triage", help="analyser un fichier explicitement fourni")
    triage.add_argument("fichier")
    triage.set_defaults(fn=command)
