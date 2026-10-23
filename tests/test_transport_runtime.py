"""Formulaires OAuth et arrêt réel du transport isolé, sans compte ni réseau distant."""
from __future__ import annotations

import json
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import outils_http as http  # noqa: E402
from jarvis.annulation import ControleExecution, ExecutionAnnulee  # noqa: E402

SECRET = "credential-de-test-avec+&=é"


class ServeurControle(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_POST(self):
        self.close_connection = True
        contenu = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requetes.append({"path": self.path, "type": self.headers.get("Content-Type"),
            "contenu": contenu, "authorization": self.headers.get("Authorization")})
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.close_connection = True
        self.send_response(200)
        if self.path == "/lent":
            self.send_header("Content-Length", "10000")
            self.end_headers()
            self.server.lecture_commencee.set()
            try:
                while not self.server.arret.wait(0.025):
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        else:
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")


def vivant(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0] not in ("Z", "X")
    except FileNotFoundError:
        return False


class TransportRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-transport-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.pids = Path(self.temp.name) / "pids.json"
        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), ServeurControle)
        self.serveur.daemon_threads = True
        self.serveur.requetes = []
        self.serveur.arret = threading.Event()
        self.serveur.lecture_commencee = threading.Event()
        self.thread = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.fermer)
        env = mock.patch.dict(os.environ, {"JARVIS_HTTPS_PROXY": "", "JARVIS_PROXY_HOTES_AUTORISES": ""})
        env.start()
        self.addCleanup(env.stop)

    def fermer(self):
        self.serveur.arret.set()
        self.serveur.shutdown()
        self.serveur.server_close()
        self.thread.join(timeout=2)
        if self.pids.exists():
            for pid in json.loads(self.pids.read_text()):
                if vivant(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def worker(self, *, enfant=False, dns=False):
        code = "import sys;sys.path.insert(0,sys.argv[1]);from jarvis import outils_http as h\n"
        if enfant:
            # L'enfant garde volontairement son groupe et ignore TERM : la borne KILL est exercée.
            code += ("import json,os,signal,subprocess,time\nfrom pathlib import Path\n"
                     "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                     "enfant=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'],"
                     "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                     f"Path({str(self.pids)!r}).write_text(json.dumps([os.getpid(),enfant.pid]))\n")
        if dns:
            code += "import time\nh._adresse=lambda *_:time.sleep(60)\nh._proxy=lambda *_:None\n"
        else:
            # Frontière TLS adaptée uniquement dans ce worker de test ; le protocole/stdin sont réels.
            code += ("from http.client import HTTPConnection\n"
                     f"h._proxy=lambda host,port,timeout:HTTPConnection('127.0.0.1',{self.serveur.server_address[1]},timeout=timeout)\n")
        return code + "h._worker()\n"

    def annuler_au_demarrage(self, jeton, *, lecture=False):
        def attendre():
            fin = time.monotonic() + 4
            while time.monotonic() < fin:
                pret = self.serveur.lecture_commencee.is_set() if lecture else self.pids.exists()
                if pret:
                    break
                time.sleep(0.01)
            jeton.annuler("arrêt du test de transport")
        thread = threading.Thread(target=attendre, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)

    def verifier_groupes_arretes(self):
        pids = json.loads(self.pids.read_text())
        fin = time.monotonic() + 0.8
        while any(vivant(pid) for pid in pids) and time.monotonic() < fin:
            time.sleep(0.01)
        self.assertFalse(any(vivant(pid) for pid in pids), "Un processus possédé continue après le retour du transport.")

    def test_formulaire_urlencode_via_vrai_worker_stdin_sans_credential_argv(self):
        processus = []
        vrai_popen = subprocess.Popen
        def lancer(args, **kw):
            self.assertNotIn(SECRET, repr(args))
            self.assertIsNone(kw.get("env"), "Le credential est transmis par stdin, sans environnement ajouté.")
            p = vrai_popen(args, **kw)
            processus.append(p)
            return p
        formulaire = {"grant_type": "authorization_code", "client_secret": SECRET, "code": "un code + accents é", "vide": ""}
        with mock.patch.object(http, "_WORKER_CODE", self.worker()), mock.patch.object(subprocess, "Popen", side_effect=lancer):
            reponse = http.requete("https://api.example.invalid/token", methode="POST", formulaire=formulaire,
                entetes={"Authorization": "Bearer " + SECRET}, timeout=3)
        self.assertEqual((reponse["status"], reponse["contenu"]), (200, b"ok"))
        self.assertEqual(len(processus), 1)
        self.assertIsNotNone(processus[0].returncode)
        requete = self.serveur.requetes[0]
        self.assertEqual(requete["type"], "application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(requete["contenu"].decode(), keep_blank_values=True), {k: [v] for k, v in formulaire.items()})
        self.assertEqual(requete["authorization"], "Bearer " + SECRET)

    def test_json_reste_distinct_du_formulaire(self):
        with mock.patch.object(http, "_WORKER_CODE", self.worker()):
            http.requete("https://api.example.invalid/responses", methode="POST", donnees={"texte": "écriture"}, timeout=3)
        r = self.serveur.requetes[0]
        self.assertEqual(r["type"], "application/json")
        self.assertEqual(json.loads(r["contenu"]), {"texte": "écriture"})

    def test_formulaire_invalide_refuse_avant_spawn(self):
        demandes = [dict(methode="GET", formulaire={"code": "x"}),
                    dict(methode="POST", formulaire={"code": "x"}, donnees={"autre": "y"}),
                    dict(methode="POST", formulaire={"code": 12}), dict(methode="POST", formulaire={12: "code"}),
                    dict(methode="POST", formulaire=["code"])]
        with mock.patch.object(subprocess, "Popen") as lancer:
            for demande in demandes:
                with self.subTest(demande=list(demande)), self.assertRaises(http.TransportError):
                    http.requete("https://api.example.invalid/token", **demande)
            lancer.assert_not_called()

    def test_annulation_avant_depart_ne_cree_pas_de_processus(self):
        jeton = ControleExecution()
        jeton.annuler("run arrêté")
        with mock.patch.object(subprocess, "Popen") as lancer, self.assertRaises(ExecutionAnnulee):
            http.requete("https://api.example.invalid/", timeout=3, annulation=jeton)
        lancer.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "groupes POSIX nécessaires")
    def test_annulation_pendant_dns_interrompt_groupe_et_propage_exception(self):
        jeton = ControleExecution()
        self.annuler_au_demarrage(jeton)
        debut = time.monotonic()
        with mock.patch.object(http, "_WORKER_CODE", self.worker(enfant=True, dns=True)), self.assertRaises(ExecutionAnnulee):
            http.requete("https://api.example.invalid/", timeout=30, annulation=jeton)
        self.assertLess(time.monotonic() - debut, 3)
        self.verifier_groupes_arretes()

    @unittest.skipUnless(os.name == "posix", "groupes POSIX nécessaires")
    def test_annulation_pendant_lecture_lente_n_attend_pas_timeout(self):
        jeton = ControleExecution()
        self.annuler_au_demarrage(jeton, lecture=True)
        debut = time.monotonic()
        with mock.patch.object(http, "_WORKER_CODE", self.worker(enfant=True)), self.assertRaises(ExecutionAnnulee):
            http.requete("https://api.example.invalid/lent", timeout=30, annulation=jeton)
        self.assertTrue(self.serveur.lecture_commencee.is_set())
        self.assertLess(time.monotonic() - debut, 3)
        self.verifier_groupes_arretes()

    @unittest.skipUnless(os.name == "posix", "groupes POSIX nécessaires")
    def test_exception_du_controleur_est_propagee_apres_nettoyage(self):
        def verifier_autorite():
            if self.pids.exists():
                raise RuntimeError("contrôleur indisponible pendant la requête")
            return ""
        jeton = ControleExecution(interruption=verifier_autorite)
        debut = time.monotonic()
        with mock.patch.object(http, "_WORKER_CODE", self.worker(enfant=True, dns=True)), self.assertRaises(RuntimeError) as ctx:
            http.requete("https://api.example.invalid/", timeout=30, annulation=jeton)
        self.assertNotIsInstance(ctx.exception, http.TransportError)
        self.assertLess(time.monotonic() - debut, 3)
        self.verifier_groupes_arretes()

    @unittest.skipUnless(os.name == "posix", "groupes POSIX nécessaires")
    def test_deadline_totale_ne_repart_pas_a_chaque_octet(self):
        debut = time.monotonic()
        with mock.patch.object(http, "_WORKER_CODE", self.worker(enfant=True)), self.assertRaises(http.TransportError):
            http.requete("https://api.example.invalid/lent", timeout=0.35)
        self.assertTrue(self.serveur.lecture_commencee.is_set())
        self.assertLess(time.monotonic() - debut, 3)
        self.verifier_groupes_arretes()

    @unittest.skipUnless(os.name == "posix", "groupes POSIX nécessaires")
    def test_worker_termine_ne_garde_pas_d_enfant_en_arriere_plan(self):
        with mock.patch.object(http, "_WORKER_CODE", self.worker(enfant=True)):
            reponse = http.requete("https://api.example.invalid/", timeout=3)
        self.assertEqual(reponse["contenu"], b"ok")
        self.verifier_groupes_arretes()

    def test_cap_120_secondes_accepte_et_parametres_hors_bornes_refuses(self):
        with mock.patch.object(http, "_WORKER_CODE", self.worker()):
            self.assertEqual(http.requete("https://api.example.invalid/", timeout=120)["status"], 200)
        with mock.patch.object(subprocess, "Popen") as lancer:
            for timeout in (True, 0, 121, float("nan"), float("inf")):
                with self.subTest(timeout=repr(timeout)), self.assertRaises(http.TransportError):
                    http.requete("https://api.example.invalid/", timeout=timeout)
            lancer.assert_not_called()

    def test_tls_verifie_et_scope_public_restent_obligatoires(self):
        connexion = http._Connexion("api.example.invalid", 443, "1.1.1.1", 1)
        self.addCleanup(connexion.close)
        self.assertTrue(connexion._context.check_hostname)
        self.assertEqual(connexion._context.verify_mode, ssl.CERT_REQUIRED)
        prive = [(None, None, None, None, ("127.0.0.1", 443))]
        with mock.patch.object(http.socket, "getaddrinfo", return_value=prive), mock.patch.object(http, "_Connexion") as ouvrir:
            with self.assertRaises(http.TransportError):
                http._requete_directe("https://api.example.invalid/token", methode="POST", formulaire={"code": "x"})
            ouvrir.assert_not_called()
        with mock.patch.object(subprocess, "Popen") as lancer:
            for url in ("http://api.example.invalid/", "https://user:secret@api.example.invalid/", "https://api.example.invalid:444/"):
                with self.subTest(url=url), self.assertRaises(http.TransportError):
                    http.requete(url, formulaire={"code": "x"}, methode="POST")
            lancer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
