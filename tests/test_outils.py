"""Passerelle réelle : protocole MCP sur socket local, mandat et reprise sans double effet."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import config, connexions, mandats, outils, outils_http, store  # noqa: E402


class ServeurMCP(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _repondre(self, status, data, content_type="application/json", headers=None):
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.lectures += 1
        if self.path == "/redirect":
            self._repondre(302, b"", headers={"Location": "http://127.0.0.1/secret"})
        elif self.path == "/gros":
            self._repondre(200, b"x" * 70000, "text/plain")
        else:
            self._repondre(200, b"Une page source.", "text/plain; charset=utf-8")

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        message = json.loads(raw)
        self.server.messages.append(message)
        self.server.auth.append(self.headers.get("Authorization"))
        method = message["method"]
        if method == "notifications/initialized":
            self._repondre(202, b"")
            return
        if method != "initialize" and self.headers.get("Mcp-Session-Id") != "session-test":
            self._repondre(400, b"session absente")
            return
        if method == "initialize":
            if self.server.revoquer_mandat:
                mandats.revoquer(self.server.revoquer_mandat, par="test")
                self.server.revoquer_mandat = None
            if self.server.retirer_outil:
                connexions.configurer_outils("recherche", [], par="test")
                self.server.retirer_outil = False
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "test", "version": "1"}}
        elif method == "tools/list":
            if self.server.changer_selection_liste:
                connexions.configurer_outils("recherche", ["interdit"], par="test")
                self.server.changer_selection_liste = False
            result = {"tools": [{"name": "noter", "description": "Noter un constat",
                                  "inputSchema": {"type": "object", "properties": {"texte": {"type": "string"}},
                                                  "required": ["texte"], "additionalProperties": False}},
                                 {"name": "interdit", "inputSchema": {"type": "object"}}]}
        elif method == "tools/call":
            self.server.appels += 1
            if self.server.perdre_reponse:
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            result = {"content": [{"type": "text", "text": message["params"]["arguments"].get("texte", "ok")}],
                      "isError": False}
        else:
            self._repondre(400, b"methode inconnue")
            return
        encoded = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}).encode()
        if self.server.sse:
            if self.server.stream_ouvert:
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Mcp-Session-Id", "session-test")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                chunk = b": keepalive\n\nevent: message\ndata: " + encoded + b"\n\n"
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
                self.server.fin_stream.wait(3)
                return
            self._repondre(200, b"event: message\ndata: " + encoded + b"\n\n", "text/event-stream", {"Mcp-Session-Id": "session-test"})
        else:
            self._repondre(200, encoded, headers={"Mcp-Session-Id": "session-test"})


class CasPasserelle:
    backend = "json"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jarvis-outils-")
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(config, "STATE_DIR", Path(tmp.name)); patch.start(); self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": self.backend, "JARVIS_TEST_MCP_TOKEN": "credential-factice-ne-pas-afficher",
                                          "JARVIS_HTTPS_PROXY": "", "JARVIS_PROXY_HOTES_AUTORISES": ""})
        env.start(); self.addCleanup(env.stop)
        old = store._local
        store._local = threading.local()

        def fermer_base():
            c = getattr(store._local, "conn", None)
            if c:
                c.close()
            store._local = old
        self.addCleanup(fermer_base)
        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), ServeurMCP)
        self.serveur.daemon_threads = True
        self.serveur.messages = []; self.serveur.auth = []; self.serveur.appels = 0; self.serveur.lectures = 0
        self.serveur.sse = False; self.serveur.perdre_reponse = False; self.serveur.revoquer_mandat = None
        self.serveur.retirer_outil = False; self.serveur.stream_ouvert = False; self.serveur.fin_stream = threading.Event()
        self.serveur.changer_selection_liste = False
        thread = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        thread.start()

        def fermer_serveur():
            self.serveur.fin_stream.set()
            self.serveur.shutdown(); self.serveur.server_close(); thread.join(timeout=2)
        self.addCleanup(fermer_serveur)
        # Adaptateur de test privé uniquement : même client/protocole et vraies requêtes TCP, TLS testé
        # séparément. La configuration de production n'expose aucun drapeau pour autoriser ce détour.
        self.conn = mock.patch.object(outils_http, "_Connexion", side_effect=lambda host, port, adresse, timeout: HTTPConnection("127.0.0.1", self.serveur.server_port, timeout=timeout))
        self.conn.start(); self.addCleanup(self.conn.stop)
        dns = mock.patch.object(outils_http, "_adresse", return_value="203.0.113.1")
        dns.start(); self.addCleanup(dns.stop)
        transport = mock.patch.object(outils_http, "requete", side_effect=outils_http._requete_directe)
        transport.start(); self.addCleanup(transport.stop)

    def connexion(self):
        return connexions.enregistrer({"id": "recherche", "nom": "Serveur de test", "type": "mcp_http",
                    "url": "https://api.example.invalid/mcp", "token_env": "JARVIS_TEST_MCP_TOKEN",
                    "outils_autorises": ["noter"]}, par="proprietaire")

    def mandat(self, tool="web.fetch", max_actions=10):
        return mandats.creer({"version": 1, "owner": "proprietaire", "project": "projet-test", "tools": [tool],
                    "destinations": ["api.example.invalid"], "expires_at": time.time() + 120,
                    "max_cost_cents": 0, "max_actions": max_actions}, par="proprietaire")

    def requete(self, mandat, tool="web.fetch", ident="operation-1", **extra):
        return {"operation_id": ident, "mandat_id": mandat["id"], "project": "projet-test", "tool": tool,
                "arguments": {"url": "https://api.example.invalid/page"} if tool == "web.fetch" else {"texte": "Constat vérifié"}, **extra}

    def test_decouverte_mcp_effective_json_session_et_bearer(self):
        self.connexion()
        observed = connexions.decouvrir("recherche")
        self.assertEqual([m["method"] for m in self.serveur.messages], ["initialize", "notifications/initialized", "tools/list"])
        self.assertEqual(observed["etat"], "decouverte_verifiee")
        self.assertEqual(len(observed["outils"]), 2)
        self.assertEqual(self.serveur.auth, ["Bearer credential-factice-ne-pas-afficher"] * 3)
        public = json.dumps(observed)
        self.assertNotIn("credential-factice", public)
        self.assertNotIn("/mcp", public)
        self.assertNotIn("token_env", public)
        ids = [t["id"] for t in outils.catalogue()["outils"]]
        self.assertIn("mcp.recherche.noter", ids)
        self.assertNotIn("mcp.recherche.interdit", ids)

    def test_sse_mcp_outil_reel_et_doublon_sans_nouvel_effet(self):
        self.serveur.sse = True
        self.connexion(); connexions.decouvrir("recherche")
        m = self.mandat("mcp.recherche.noter", 1)
        req = self.requete(m, "mcp.recherche.noter")
        first = outils.executer(req, par="agent:recherche")
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(first["resultat"]["content"][0]["text"], "Constat vérifié")
        self.assertEqual(outils.executer(req, par="agent:recherche")["status"], "succeeded")
        self.assertEqual(self.serveur.appels, 1)
        self.assertEqual(mandats.get(m["id"])["used_actions"], 1)
        self.assertEqual(outils.operations("autre-projet"), [])

    def test_reponse_perdue_est_unknown_sans_double_ecriture(self):
        self.connexion(); connexions.decouvrir("recherche")
        self.serveur.perdre_reponse = True
        req = self.requete(self.mandat("mcp.recherche.noter"), "mcp.recherche.noter")
        first = outils.executer(req, par="agent:recherche")
        self.assertEqual(first["status"], "unknown")
        replay = outils.executer(req, par="agent:recherche")
        self.assertTrue(replay["doublon"])
        self.assertEqual(self.serveur.appels, 1)

    def test_revoquer_pendant_initialisation_bloque_tools_call(self):
        self.connexion(); connexions.decouvrir("recherche")
        m = self.mandat("mcp.recherche.noter")
        self.serveur.revoquer_mandat = m["id"]
        result = outils.executer(self.requete(m, "mcp.recherche.noter"), par="agent:recherche")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(self.serveur.appels, 0)

    def test_retirer_selection_pendant_initialisation_bloque_tools_call(self):
        self.connexion(); connexions.decouvrir("recherche")
        self.serveur.retirer_outil = True
        req = self.requete(self.mandat("mcp.recherche.noter"), "mcp.recherche.noter")
        self.assertEqual(outils.executer(req, par="agent")["status"], "unknown")
        self.assertEqual(self.serveur.appels, 0)

    def test_sse_persistant_retourne_avant_fermeture_du_stream(self):
        self.serveur.sse = True; self.serveur.stream_ouvert = True
        self.connexion()
        debut = time.monotonic()
        connexions.decouvrir("recherche")
        req = self.requete(self.mandat("mcp.recherche.noter"), "mcp.recherche.noter")
        self.assertEqual(outils.executer(req, par="agent")["status"], "succeeded")
        self.assertLess(time.monotonic() - debut, 2)
        self.assertFalse(self.serveur.fin_stream.is_set())

    def test_decouverte_concurrente_garde_selection_actuelle(self):
        self.connexion(); connexions.decouvrir("recherche")
        self.serveur.changer_selection_liste = True
        resultat = connexions.decouvrir("recherche")
        self.assertEqual(resultat["outils_autorises"], ["interdit"])
        self.assertEqual([t["name"] for t in resultat["outils"] if t["autorise"]], ["interdit"])

    def test_refus_mandat_outil_ou_connexion_sans_appel(self):
        m = self.mandat()
        mandats.revoquer(m["id"], par="proprietaire")
        with self.assertRaises(outils.OutilError):
            outils.executer(self.requete(m), par="agent")
        self.assertEqual(self.serveur.lectures, 0)
        self.connexion(); connexions.decouvrir("recherche")
        req = self.requete(self.mandat("mcp.recherche.interdit"), "mcp.recherche.interdit", "autre")
        with self.assertRaises(outils.OutilError):
            outils.executer(req, par="agent")
        connexions.revoquer("recherche", par="proprietaire")
        with self.assertRaises(connexions.ConnexionError):
            connexions.decouvrir("recherche")
        self.assertEqual(self.serveur.appels, 0)

    def test_web_fetch_borne_et_redirection_refusee(self):
        m = self.mandat()
        result = outils.executer(self.requete(m), par="agent")
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(result["resultat"]["source_non_fiable"])
        for path in ("redirect", "gros"):
            req = self.requete(m, ident=path, arguments={"url": "https://api.example.invalid/" + path})
            self.assertEqual(outils.executer(req, par="agent")["status"], "failed")
        self.assertEqual(self.serveur.lectures, 3)

    def test_concurrence_une_seule_lecture_et_quota(self):
        m = self.mandat(max_actions=1)
        req = self.requete(m)

        def appel(_):
            try:
                return outils.executer(req, par="agent")
            finally:
                conn = getattr(store._local, "conn", None)
                if conn:
                    conn.close(); store._local.conn = None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(appel, range(12)))
        self.assertTrue(all(r["status"] == "succeeded" for r in results))
        self.assertEqual(self.serveur.lectures, 1)
        self.assertEqual(mandats.get(m["id"])["used_actions"], 1)

    def test_identite_lie_les_arguments_et_reprise_in_progress_ne_rejoue_pas(self):
        m = self.mandat()
        req = self.requete(m)
        outils.executer(req, par="agent")
        with self.assertRaises(outils.OutilError):
            outils.executer({**req, "arguments": {"url": "https://api.example.invalid/autre"}}, par="agent")
        store.connexion().execute("UPDATE os_operations_outils SET status='in_progress' WHERE operation_id=?", (req["operation_id"],))
        self.assertEqual(outils.executer(req, par="agent")["status"], "unknown")
        self.assertEqual(self.serveur.lectures, 1)

    def test_validation_faille_fermee_sans_consommer(self):
        m = self.mandat()
        invalid = [{"arguments": {"url": "http://api.example.invalid/"}}, {"cost_cents": True},
                   {"arguments": {"url": "https://api.example.invalid/", "maximum": True}},
                   {"arguments": {"url": "https://api.example.invalid/", "timeout": float("nan")}},
                   {"tool": "admin.all"}, {"arguments": {"url": "https://api.example.invalid/?token=secret"}}]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(outils.OutilError):
                outils.executer({**self.requete(m), **change}, par="agent")
        self.assertEqual(mandats.get(m["id"])["used_actions"], 0)
        self.assertEqual(self.serveur.lectures, 0)

    def test_validation_schema_mcp_avant_reservation(self):
        self.connexion(); connexions.decouvrir("recherche")
        m = self.mandat("mcp.recherche.noter")
        for arguments in ({}, {"texte": True}, {"texte": "ok", "destinataire": "non autorisé"}):
            with self.subTest(arguments=arguments), self.assertRaises(outils.OutilError):
                outils.executer(self.requete(m, "mcp.recherche.noter", arguments=arguments), par="agent")
        self.assertEqual(mandats.get(m["id"])["used_actions"], 0)
        self.assertEqual(self.serveur.appels, 0)

    def test_selection_apres_decouverte_ne_revele_pas_endpoint_ou_secret(self):
        spec = {"id": "nouveau", "nom": "Connexion à sélectionner", "type": "mcp_http",
                "url": "https://api.example.invalid/mcp", "outils_autorises": []}
        connexions.enregistrer(spec, par="proprietaire")
        connexions.decouvrir("nouveau")
        self.assertNotIn("mcp.nouveau.noter", [t["id"] for t in outils.catalogue()["outils"]])
        resultat = connexions.configurer_outils("nouveau", ["noter"], par="proprietaire")
        self.assertTrue(next(t for t in resultat["outils"] if t["name"] == "noter")["autorise"])
        self.assertIn("mcp.nouveau.noter", [t["id"] for t in outils.catalogue()["outils"]])
        with self.assertRaises(connexions.ConnexionError):
            connexions.configurer_outils("nouveau", ["non_decouvert"], par="proprietaire")
        self.assertNotIn("url", resultat)

    def test_secret_reflete_par_mcp_est_expurge_du_resultat_et_journal(self):
        self.connexion(); connexions.decouvrir("recherche")
        m = self.mandat("mcp.recherche.noter")
        req = self.requete(m, "mcp.recherche.noter", arguments={"texte": os.environ["JARVIS_TEST_MCP_TOKEN"]})
        resultat = outils.executer(req, par="agent")
        self.assertNotIn(os.environ["JARVIS_TEST_MCP_TOKEN"], json.dumps(resultat))
        self.assertIn("[SECRET]", json.dumps(resultat))


class TestPasserelleJSON(CasPasserelle, unittest.TestCase):
    pass


class TestPasserelleSQLite(CasPasserelle, unittest.TestCase):
    backend = "sqlite"


class TestTransport(unittest.TestCase):
    def test_deadline_dure_arrete_processus_dns_bloque(self):
        code = ("import sys,time; sys.path.insert(0,sys.argv[1]); from jarvis import outils_http; "
                "outils_http.socket.getaddrinfo=lambda *a,**k:time.sleep(30); outils_http._worker()")
        original, processus = subprocess.Popen, []

        def lancer(*args, **kwargs):
            proc = original(*args, **kwargs); processus.append(proc); return proc
        debut = time.monotonic()
        with mock.patch.dict(os.environ, {"JARVIS_HTTPS_PROXY": ""}), mock.patch.object(outils_http, "_WORKER_CODE", code), mock.patch.object(subprocess, "Popen", side_effect=lancer):
            with self.assertRaises(outils_http.TransportError):
                outils_http.requete("https://api.example.invalid/", timeout=0.2)
        self.assertLess(time.monotonic() - debut, 2)
        self.assertEqual(len(processus), 1)
        self.assertIsNotNone(processus[0].poll())

    def test_proxy_approuve_perimetre_exact_sans_heriter_proxy_ambiant(self):
        with mock.patch.dict(os.environ, {"JARVIS_HTTPS_PROXY": "", "HTTPS_PROXY": "http://proxy.example:8080"}):
            self.assertIsNone(outils_http._proxy("pypi.org", 443, 3))
        with mock.patch.dict(os.environ, {"JARVIS_HTTPS_PROXY": "http://proxy.example:8080", "JARVIS_PROXY_HOTES_AUTORISES": "pypi.org,127.0.0.1,service.internal"}):
            for host in ("autre.org", "sub.pypi.org", "127.0.0.1", "service.internal"):
                with self.subTest(host=host), self.assertRaises(outils_http.TransportError):
                    outils_http._proxy(host, 443, 3)
            with mock.patch.object(outils_http.http.client, "HTTPSConnection") as factory:
                connexion = outils_http._proxy("pypi.org", 443, 3)
                factory.assert_called_once()
                connexion.set_tunnel.assert_called_once_with("pypi.org", 443, headers={})

    def test_refuse_url_locale_et_credentials_ou_port_non_https(self):
        for url in ("http://example.com/", "https://user:pass@example.com/", "https://example.com:80/", "https://example.com/#fragment", "https://example.com/?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(outils_http.TransportError):
                outils_http.cible(url)
        for ip in ("127.0.0.1", "10.2.3.4", "169.254.169.254", "::1", "2001:db8::1"):
            with mock.patch.object(socket, "getaddrinfo", return_value=[(None, None, None, None, (ip, 443))]):
                with self.assertRaises(outils_http.TransportError):
                    outils_http._adresse("serveur.example", 443)

    def test_dns_mixte_refuse_et_adresse_publique_epinglee(self):
        addresses = [(None, None, None, None, ("1.1.1.1", 443)), (None, None, None, None, ("127.0.0.1", 443))]
        with mock.patch.object(socket, "getaddrinfo", return_value=addresses), self.assertRaises(outils_http.TransportError):
            outils_http._adresse("serveur.example", 443)
        with mock.patch.object(socket, "getaddrinfo", return_value=addresses[:1]):
            self.assertEqual(outils_http._adresse("serveur.example", 443), "1.1.1.1")
        with mock.patch.object(outils_http.ssl, "create_default_context") as context, mock.patch.object(socket, "create_connection") as create:
            connexion = outils_http._Connexion("serveur.example", 443, "1.1.1.1", 3)
            connexion.connect()
            create.assert_called_once_with(("1.1.1.1", 443), 3)
            context.return_value.wrap_socket.assert_called_once_with(create.return_value, server_hostname="serveur.example")
            connexion.close()


if __name__ == "__main__":
    unittest.main()
