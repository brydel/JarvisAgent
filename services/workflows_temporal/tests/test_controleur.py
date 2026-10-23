"""Vrai HTTP local : aucune requête vers un modèle ou outil externe."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis_temporal.controleur import Controleur, ErreurControleur


class ControleurTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.jeton = Path(self.temp.name) / "jeton"
        self.jeton.write_text("fixture-locale-aucun-vrai-secret-00000")
        self.appels = []
        self.code = 200
        self.operation_id = "op-1"
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                parent.appels.append((self.path, data, dict(self.headers)))
                if self.path == "/api/session":
                    corps = {"authentifie": True}
                    code = 200
                else:
                    corps = {"status": "succeeded", "operation_id": parent.operation_id, "resultat": {"preuve": "locale"}}
                    code = parent.code
                contenu = json.dumps(corps).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(contenu)))
                if self.path == "/api/session":
                    self.send_header("Set-Cookie", "jarvis_studio=fixture-session; HttpOnly; SameSite=Strict")
                self.end_headers()
                self.wfile.write(contenu)

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.fil = threading.Thread(target=self.serveur.serve_forever)
        self.fil.start()
        self.client = Controleur(f"http://127.0.0.1:{self.serveur.server_port}", str(self.jeton))

    def tearDown(self):
        self.serveur.shutdown(); self.serveur.server_close(); self.fil.join()
        self.temp.cleanup()

    def test_authentifie_et_propage_identite_sans_secret_resultat(self):
        demande = {"operation_id": "op-1", "project": "demo", "tool": "web.fetch", "arguments": {}, "mandat_id": "m-1"}
        resultat = self.client.executer(demande)
        self.assertEqual(resultat["status"], "succeeded")
        self.assertEqual([a[0] for a in self.appels], ["/api/session", "/api/v2/outils/executer"])
        self.assertEqual(self.appels[1][1], demande)
        self.assertEqual(self.appels[1][2]["Cookie"], "jarvis_studio=fixture-session")
        self.assertEqual(self.appels[1][2]["X-Jarvis-Studio"], "1")
        self.assertNotIn(self.jeton.read_text(), json.dumps(resultat))

    def test_aucun_depart_apres_annulation(self):
        def verifier():
            if self.appels:
                raise InterruptedError("annulation locale")
        with self.assertRaises(InterruptedError):
            self.client.executer({"operation_id": "op-1"}, verifier_annulation=verifier)
        self.assertEqual(len(self.appels), 1)

    def test_refus_auth_non_reessaye(self):
        self.code = 403
        with self.assertRaises(ErreurControleur) as exc:
            self.client.executer({"operation_id": "op-1"})
        self.assertTrue(exc.exception.definitive)
        self.assertNotIn(self.jeton.read_text(), str(exc.exception))

    def test_503_est_reessayable_avec_meme_operation(self):
        self.code = 503
        with self.assertRaises(ErreurControleur) as exc:
            self.client.executer({"operation_id": "op-1"})
        self.assertFalse(exc.exception.definitive)

    def test_identite_incoherente_refusee(self):
        self.operation_id = "autre-operation"
        with self.assertRaises(ErreurControleur) as exc:
            self.client.executer({"operation_id": "op-1"})
        self.assertTrue(exc.exception.definitive)

    def test_url_distante_et_injection_refusees(self):
        for url in ("http://example.org", "http://secret@localhost", "http://localhost/route", "http://localhost?cle=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Controleur(url, str(self.jeton))


if __name__ == "__main__":
    unittest.main()
