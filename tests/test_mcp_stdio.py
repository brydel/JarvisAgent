"""Vrais serveurs MCP Python locaux : protocole stdio, contrôle, délais et descendants."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import annulation, mcp_stdio as mcp  # noqa: E402


SERVEUR = r'''
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

mode, journal = sys.argv[1:3]
def noter(message):
    with open(journal, "a") as fh:
        fh.write(json.dumps(message) + "\n")
def envoyer(message):
    print(json.dumps(message, ensure_ascii=False), flush=True)
def enfant():
    p = subprocess.Popen([sys.executable, "-c", "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"])
    noter({"enfant": p.pid})
    time.sleep(0.1)
    return p

if mode == "stderr":
    os.write(2, ((os.environ.get("JARVIS_MCP_SECRET", "journal") + "\n") * 30_000).encode())
if mode == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

for ligne in sys.stdin:
    message = json.loads(ligne)
    noter(message)
    if "method" not in message:
        continue
    methode = message["method"]
    if methode == "notifications/initialized":
        continue
    if methode == "initialize":
        if mode in ("attente", "ignore"):
            if mode == "ignore":
                enfant()
            time.sleep(60)
        if mode == "lent":
            while True:
                os.write(1, b"x")
                time.sleep(0.05)
        resultat = {"protocolVersion": "version-impossible" if mode == "version" else "2025-03-26",
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1"}}
    elif methode == "tools/list":
        params = message.get("params", {})
        outil = {"name": "etat" if params.get("cursor") else "echo", "description": "Outil local contrôlé",
                 "inputSchema": {"type": "object", "properties": {"texte": {"type": "string"}}}}
        resultat = {"tools": [outil]}
        if mode in ("pagination", "cycle") and (not params.get("cursor") or mode == "cycle"):
            resultat["nextCursor"] = "page-suivante"
        if mode == "double":
            resultat["tools"].append(outil)
        if mode == "schema":
            resultat["tools"][0]["inputSchema"] = {"description": "x" * 33_000}
        if mode in ("requete-serveur", "ping-serveur"):
            envoyer({"jsonrpc": "2.0", "id": "demande-serveur",
                     "method": "ping" if mode == "ping-serveur" else "sampling/createMessage", "params": {}})
            retour = json.loads(sys.stdin.readline())
            noter({"retour_serveur": retour})
    elif methode == "tools/call":
        if mode == "perdue":
            os._exit(0)
        if mode == "gros":
            os.write(1, b"x" * 1_100_000)
            time.sleep(60)
        if mode == "env":
            texte = json.dumps({"secret": os.environ.get("JARVIS_MCP_SECRET"),
                                "non_transmis": os.environ.get("JARVIS_MCP_NON_TRANSMIS"),
                                "home": os.environ.get("HOME"), "cwd": str(Path.cwd()),
                                "path": os.environ.get("PATH")})
        else:
            texte = message["params"]["arguments"].get("texte", "ok")
        resultat = {"content": [{"type": "text", "text": texte}], "isError": False}
        if mode == "parent-sort":
            enfant()
    else:
        resultat = {}
    reponse = {"jsonrpc": "2.0", "id": message["id"], "result": resultat}
    if mode == "id":
        reponse["id"] = 999
    if mode == "bool-id":
        reponse["id"] = True
    if mode == "erreur":
        reponse = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": "credential-factice-cache"}}
        os.write(2, b"credential-factice-cache")
    if mode == "json":
        print("pas du JSON credential-factice-cache", flush=True)
    elif mode == "nan":
        print('{"jsonrpc":"2.0","id":1,"result":{"nombre":NaN}}', flush=True)
    elif mode == "utf16":
        sys.stdout.buffer.write(json.dumps(reponse).encode("utf-16") + b"\n")
        sys.stdout.buffer.flush()
    else:
        envoyer(reponse)
    if mode == "parent-sort" and methode == "tools/call":
        os._exit(0)
'''


class StdioTest(unittest.TestCase):
    def setUp(self):
        dossier = tempfile.TemporaryDirectory(prefix="jarvis-mcp-stdio-")
        self.addCleanup(dossier.cleanup)
        self.tmp = Path(dossier.name)
        self.serveur = self.tmp / "serveur.py"
        self.serveur.write_text(SERVEUR)
        self.journal = self.tmp / "messages.jsonl"

    def spec(self, mode="normal", **kw):
        return {"command": sys.executable, "args": ["-u", str(self.serveur), mode, str(self.journal)],
                "cwd": str(self.tmp), "env_allowlist": [], **kw}

    def messages(self):
        return [json.loads(ligne) for ligne in self.journal.read_text().splitlines()] if self.journal.exists() else []

    def methodes(self):
        return [m.get("method") for m in self.messages() if m.get("method")]

    def test_initialisation_pagination_et_fermeture_du_processus(self):
        with mcp.Client(self.spec("pagination")) as client:
            outils = client.decouvrir()
            self.assertEqual([o["name"] for o in outils], ["echo", "etat"])
            self.assertEqual(client.protocole, "2025-03-26")
            self.assertEqual(client.diagnostic()["stderr_conserve"], False)
        self.assertIsNotNone(client.proc.poll())
        self.assertEqual(self.methodes(), ["initialize", "notifications/initialized", "tools/list", "tools/list"])
        self.assertEqual(self.messages()[0]["params"]["capabilities"], {})

    def test_appel_json_reel_sans_interpretation_shell(self):
        injection = f"bonjour ; touch {self.tmp / 'ne-doit-pas-exister'}"
        resultat = mcp.appeler(self.spec(), "echo", {"texte": injection})
        self.assertEqual(resultat["content"][0]["text"], injection)
        self.assertFalse((self.tmp / "ne-doit-pas-exister").exists())
        self.assertEqual(self.methodes(), ["initialize", "notifications/initialized", "tools/call"])

    def test_environnement_minimal_et_expurgation_des_valeurs(self):
        secret = "credential-factice-cache"
        with mock.patch.dict(os.environ, {"JARVIS_MCP_SECRET": secret, "JARVIS_MCP_NON_TRANSMIS": "non transmis"}):
            spec = self.spec("env", env_allowlist=["JARVIS_MCP_SECRET"])
            resultat = mcp.appeler(spec, "echo", {})
            metadata = mcp.metadata(spec)
        texte = resultat["content"][0]["text"]
        self.assertNotIn(secret, texte)
        env = json.loads(texte)
        self.assertEqual(env["secret"], "[SECRET]")
        self.assertIsNone(env["home"])
        self.assertIsNone(env["non_transmis"])
        self.assertEqual(env["cwd"], str(self.tmp))
        self.assertEqual(env["path"], os.defpath)
        self.assertEqual(metadata["env"], [{"nom": "JARVIS_MCP_SECRET", "presente": True}])
        self.assertNotIn("args", metadata)
        self.assertNotIn("command", metadata)
        self.assertNotIn(str(self.tmp), json.dumps(metadata))

    def test_validation_stricte_du_transport(self):
        invalides = [
            {"command": "python3"}, {"command": str(self.tmp)}, {"command": "/inexistant"},
            self.spec(args="commande shell"), self.spec(env_allowlist=["A=B"]), self.spec(env_allowlist=["A", "A"]),
            self.spec(cwd="relatif"), self.spec(cwd=str(self.tmp / "absent")), self.spec(inconnu=True),
            self.spec(args=["\0"]), self.spec(args=["x"] * 65), self.spec(env_allowlist={"SECRET": "valeur"}),
        ]
        for spec in invalides:
            with self.subTest(spec=spec), self.assertRaises(mcp.StdioError):
                mcp.valider_configuration(spec)
        for timeout in (True, float("nan"), 0, 31):
            with self.subTest(timeout=timeout), self.assertRaises(mcp.StdioError):
                mcp.Client(self.spec(), timeout=timeout)

    def test_verification_avant_lancement(self):
        def refuser():
            raise mcp.StdioError("Connexion révoquée.")
        with mock.patch.object(mcp.subprocess, "Popen") as popen, self.assertRaises(mcp.StdioError):
            mcp.decouvrir(self.spec(), verifier=refuser)
        popen.assert_not_called()

    def test_lecture_du_registre_possible_apres_disparition_des_fichiers(self):
        executable = self.tmp / "lanceur-local"
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o700)
        repertoire = self.tmp / "travail"
        repertoire.mkdir()
        spec = {"command": str(executable), "cwd": str(repertoire)}
        self.assertTrue(mcp.metadata(spec)["disponible"])
        normalisee = mcp.valider_configuration(spec)
        executable.unlink()
        repertoire.rmdir()
        self.assertEqual(mcp.valider_configuration(normalisee, verifier_fichiers=False), normalisee)
        self.assertFalse(mcp.metadata(normalisee)["disponible"])
        self.assertNotIn(str(self.tmp), json.dumps(mcp.metadata(normalisee)))
        with self.assertRaises(mcp.StdioError):
            mcp.valider_configuration(normalisee)
        with self.assertRaises(mcp.StdioError):
            mcp.Client(normalisee)

    def test_retrait_du_scope_apres_handshake_bloque_tools_call(self):
        actif = True
        def verifier():
            if not actif:
                raise mcp.StdioError("Outil retiré de la connexion.")
        def retrait():
            nonlocal actif
            actif = False
        with self.assertRaises(mcp.StdioError):
            mcp.appeler(self.spec(), "echo", {}, verifier=verifier, avant_effet=retrait)
        self.assertIn("initialize", self.methodes())
        self.assertNotIn("tools/call", self.methodes())

    def test_controle_mandat_refuse_avant_envoi_outil(self):
        def refuser():
            raise ValueError("Mandat révoqué.")
        with self.assertRaisesRegex(ValueError, "Mandat révoqué"):
            mcp.appeler(self.spec(), "echo", {}, avant_effet=refuser)
        self.assertNotIn("tools/call", self.methodes())

    def test_correlations_version_et_json_refuses_sans_fuite(self):
        for mode in ("id", "bool-id", "version", "json", "erreur", "nan", "utf16"):
            with self.subTest(mode=mode), self.assertRaises(mcp.StdioError) as ctx:
                mcp.decouvrir(self.spec(mode))
            self.assertNotIn("credential-factice-cache", str(ctx.exception))

    def test_catalogue_duplique_schema_et_pagination_cyclique_refuses(self):
        for mode in ("double", "schema", "cycle"):
            with self.subTest(mode=mode), self.assertRaises(mcp.StdioError):
                mcp.decouvrir(self.spec(mode))

    def test_requete_serveur_refusee_sans_capacite_implicite(self):
        outils = mcp.decouvrir(self.spec("requete-serveur"))
        self.assertEqual(outils[0]["name"], "echo")
        retour = [m["retour_serveur"] for m in self.messages() if "retour_serveur" in m][0]
        self.assertEqual(retour["error"]["code"], -32601)
        self.assertEqual(retour["id"], "demande-serveur")
        self.assertNotIn("tools/call", self.methodes())

    def test_ping_du_serveur_recoit_une_reponse_sans_capacite_supplementaire(self):
        self.assertEqual(mcp.decouvrir(self.spec("ping-serveur"))[0]["name"], "echo")
        retour = [m["retour_serveur"] for m in self.messages() if "retour_serveur" in m][0]
        self.assertEqual(retour, {"jsonrpc": "2.0", "id": "demande-serveur", "result": {}})

    def test_reponse_perdue_apres_outil_ne_rejoue_pas_le_processus(self):
        with self.assertRaises(mcp.StdioError):
            mcp.appeler(self.spec("perdue"), "echo", {})
        self.assertEqual(self.methodes().count("tools/call"), 1)
        self.assertEqual(self.methodes().count("initialize"), 1)

    def test_stderr_abondant_draine_et_non_conserve(self):
        secret = "credential-factice-cache"
        with mock.patch.dict(os.environ, {"JARVIS_MCP_SECRET": secret}), \
                mcp.Client(self.spec("stderr", env_allowlist=["JARVIS_MCP_SECRET"]), timeout=5) as client:
            client.decouvrir()
            diagnostic = client.diagnostic()
        self.assertGreater(diagnostic["stderr_octets"], 64_000)
        self.assertTrue(diagnostic["stderr_tronque"])
        self.assertFalse(diagnostic["stderr_conserve"])
        self.assertNotIn(secret, json.dumps(diagnostic))

    def test_sortie_trop_grande_rejetee_avant_attente_illimitee(self):
        debut = time.monotonic()
        with self.assertRaisesRegex(mcp.StdioError, "volumineu"):
            mcp.appeler(self.spec("gros"), "echo", {}, timeout=3)
        self.assertLess(time.monotonic() - debut, 2.5)

    def test_delai_total_couvre_serveur_silencieux_et_flux_lent(self):
        for mode in ("attente", "lent"):
            debut = time.monotonic()
            with self.subTest(mode=mode), self.assertRaisesRegex(mcp.StdioError, "Délai total"):
                mcp.decouvrir(self.spec(mode), timeout=0.3)
            self.assertLess(time.monotonic() - debut, 2)

    def test_annulation_avant_lancement(self):
        controle = annulation.ControleExecution()
        controle.annuler("Test")
        with self.assertRaises(annulation.ExecutionAnnulee):
            mcp.decouvrir(self.spec(), annulation=controle)
        self.assertFalse(self.journal.exists())

    @unittest.skipUnless(os.name == "posix", "groupes de processus POSIX")
    def test_annulation_tue_parent_et_enfant_ignorant_term(self):
        controle = annulation.ControleExecution()
        timer = threading.Timer(0.4, controle.annuler)
        self.addCleanup(timer.cancel)
        debut = time.monotonic()
        timer.start()
        with mcp.Client(self.spec("ignore"), annulation=controle, timeout=5) as client:
            with self.assertRaises(annulation.ExecutionAnnulee):
                client.initialiser()
        self.assertLess(time.monotonic() - debut, 3)
        self.assertIsNotNone(client.proc.poll())
        self.assertEnfantsArretes()

    @unittest.skipUnless(os.name == "posix", "groupes de processus POSIX")
    def test_parent_termine_ne_conserve_pas_un_enfant_en_arriere_plan(self):
        resultat = mcp.appeler(self.spec("parent-sort"), "echo", {})
        self.assertFalse(resultat["isError"])
        self.assertEnfantsArretes()

    def assertEnfantsArretes(self):
        pids = [m["enfant"] for m in self.messages() if "enfant" in m]
        self.assertTrue(pids)
        for pid in pids:
            fin = time.monotonic() + 1
            while time.monotonic() < fin:
                stat = Path(f"/proc/{pid}/stat")
                if not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z"):
                    break
                time.sleep(0.02)
            else:
                self.fail("Un descendant du serveur MCP stdio continue à tourner.")


if __name__ == "__main__":
    unittest.main()
