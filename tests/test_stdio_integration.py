"""Connexion stdio réelle jusqu'au mandat et à l'arrêt du serveur HTTP du Studio."""

from __future__ import annotations

import http.client
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from test_mcp_stdio import SERVEUR
from jarvis import config, connexions, mandats, outils, store, studio_api


class CasStdioIntegration:
    backend = "json"

    def setUp(self):
        dossier = tempfile.TemporaryDirectory(prefix="jarvis-stdio-integration-")
        self.addCleanup(dossier.cleanup)
        self.tmp = Path(dossier.name)
        patch = mock.patch.multiple(config, STATE_DIR=self.tmp / "etat", CONFIG_DIR=self.tmp / "config",
                                    SETTINGS_FILE=self.tmp / "config" / "settings.toml", DATA_DIR=self.tmp / "donnees")
        patch.start()
        self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": self.backend,
                                          "JARVIS_MCP_SECRET": "credential-factice-non-public"})
        env.start()
        self.addCleanup(env.stop)
        ancien = store._local
        store._local = threading.local()

        def fermer_base():
            c = getattr(store._local, "conn", None)
            if c is not None:
                c.close()
            store._local = ancien
        self.addCleanup(fermer_base)
        self.travail = self.tmp / "travail"
        self.travail.mkdir()
        self.journal = self.tmp / "serveur.jsonl"
        # Le serveur de protocole existant ajoute seulement son PID aux observations locales du test.
        serveur = SERVEUR.replace('if mode == "stderr":',
                                  'noter({"serveur": os.getpid()})\n\nif mode == "stderr":', 1)
        self.lanceur = self.tmp / "serveur-local"
        self.lanceur.write_text("#!" + sys.executable + "\n" + serveur)
        self.lanceur.chmod(0o700)

    def spec(self, mode="normal"):
        return {"id": "local", "nom": "Serveur local de test", "type": "mcp_stdio",
                "command": str(self.lanceur), "args": [mode, str(self.journal)],
                "cwd": str(self.travail), "env_allowlist": ["JARVIS_MCP_SECRET"], "outils_autorises": []}

    def preparer(self, mode="normal"):
        config = connexions.enregistrer(self.spec(mode), par="proprietaire-test")
        self.assertTrue(config["stdio"]["disponible"])
        self.assertFalse(self.journal.exists(), "L'enregistrement seul ne lance pas le processus.")
        decouverte = connexions.decouvrir("local")
        self.assertEqual([o["name"] for o in decouverte["outils"]], ["echo"])
        self.assertEqual(decouverte["etat"], "decouverte_verifiee")
        self.assertTrue(all(not o["autorise"] for o in decouverte["outils"]))
        return connexions.configurer_outils("local", ["echo"], par="proprietaire-test")

    def observations(self):
        if not self.journal.exists():
            return []
        # Le fichier est écrit en ajout par le serveur ; une ligne en cours reste à la lecture suivante.
        resultat = []
        for ligne in self.journal.read_text().splitlines():
            try:
                resultat.append(json.loads(ligne))
            except json.JSONDecodeError:
                pass
        return resultat

    def compter(self, methode):
        return sum(o.get("method") == methode for o in self.observations())

    def mandat(self, *, destination="mcp:local", actions=1, cout=2):
        return mandats.creer({"version": 1, "owner": "proprietaire-test", "project": "integration-stdio",
                             "tools": ["mcp.local.echo"], "destinations": [destination],
                             "expires_at": time.time() + 120, "max_actions": actions, "max_cost_cents": cout},
                            par="proprietaire-test")

    def demande(self, mandat, *, operation="stdio-1"):
        return {"operation_id": operation, "mandat_id": mandat["id"], "project": "integration-stdio",
                "tool": "mcp.local.echo", "arguments": {"texte": "Observation partagée"}, "cost_cents": 2}

    def test_connexion_decouverte_appel_reel_et_rejeu_sans_nouvelle_reservation(self):
        public = self.preparer()
        self.assertEqual(public["hote"], "mcp:local")
        self.assertNotIn(str(self.tmp), json.dumps(public))
        self.assertNotIn("credential-factice-non-public", json.dumps(public))
        self.assertNotIn("command", public)
        self.assertNotIn("args", public)
        self.assertIn("mcp.local.echo", [o["id"] for o in outils.catalogue()["outils"]])
        mandat = self.mandat()
        demande = self.demande(mandat)
        premier = outils.executer(demande, par="agent-test")
        self.assertEqual(premier["status"], "succeeded")
        self.assertEqual(premier["resultat"]["content"][0]["text"], "Observation partagée")
        self.assertFalse(premier["doublon"])
        second = outils.executer(demande, par="agent-test")
        self.assertTrue(second["doublon"])
        self.assertEqual(second["status"], "succeeded")
        self.assertEqual(self.compter("tools/call"), 1)
        self.assertEqual(self.compter("initialize"), 2, "Une découverte et un appel, pas de processus pour le rejeu.")
        utilise = mandats.get(mandat["id"])
        self.assertEqual((utilise["used_actions"], utilise["used_cost_cents"]), (1, 2))
        with self.assertRaises(outils.OutilError):
            outils.executer(self.demande(mandat, operation="quota-epuise"), par="agent-test")
        self.assertEqual(self.compter("tools/call"), 1)

    def test_destination_exacte_refusee_avant_lancement_du_processus(self):
        self.preparer()
        mandat = self.mandat(destination="pypi.org")
        with self.assertRaises(outils.OutilError):
            outils.executer(self.demande(mandat), par="agent-test")
        self.assertEqual(self.compter("initialize"), 1)
        self.assertEqual(self.compter("tools/call"), 0)
        self.assertEqual(mandats.get(mandat["id"])["used_actions"], 0)

    def test_appels_concurrents_partagent_operation_et_quota(self):
        self.preparer()
        mandat = self.mandat()
        demande = self.demande(mandat)
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultats = list(pool.map(lambda _: outils.executer(demande, par="agent-test"), range(8)))
        self.assertTrue(all(r["status"] == "succeeded" for r in resultats))
        self.assertEqual(sum(not r["doublon"] for r in resultats), 1)
        self.assertEqual(self.compter("tools/call"), 1)
        self.assertEqual(mandats.get(mandat["id"])["used_actions"], 1)

    def test_reponse_perdue_conserve_unknown_et_ne_relance_pas_le_serveur(self):
        self.preparer("perdue")
        mandat = self.mandat()
        demande = self.demande(mandat)
        premier = outils.executer(demande, par="agent-test")
        self.assertEqual(premier["status"], "unknown")
        second = outils.executer(demande, par="agent-test")
        self.assertEqual((second["status"], second["doublon"]), ("unknown", True))
        self.assertEqual(self.compter("tools/call"), 1)
        self.assertEqual(self.compter("initialize"), 2)
        self.assertEqual(mandats.get(mandat["id"])["used_actions"], 1)

    def test_registre_revoquable_et_catalogue_web_accessible_apres_desinstallation(self):
        self.preparer()
        self.lanceur.unlink()
        self.travail.rmdir()
        public = connexions.get("local")
        self.assertFalse(public["stdio"]["disponible"])
        self.assertEqual(connexions.lister()[0]["id"], "local")
        self.assertIn("web.fetch", [o["id"] for o in outils.catalogue()["outils"]])
        self.assertFalse(connexions.revoquer("local", par="proprietaire-test")["active"])
        self.assertIn("web.fetch", [o["id"] for o in outils.catalogue()["outils"]])
        self.assertEqual(self.compter("tools/call"), 0)

    def test_retrait_selection_bloque_appel_sans_nouvelle_action(self):
        self.preparer()
        mandat = self.mandat()
        connexions.configurer_outils("local", [], par="proprietaire-test")
        with self.assertRaises(outils.OutilError):
            outils.executer(self.demande(mandat), par="agent-test")
        self.assertEqual(self.compter("initialize"), 1)
        self.assertEqual(mandats.get(mandat["id"])["used_actions"], 0)


class StdioIntegrationJSONTest(CasStdioIntegration, unittest.TestCase):
    pass


class StdioIntegrationSQLiteTest(CasStdioIntegration, unittest.TestCase):
    backend = "sqlite"


class StudioStdioArretTest(unittest.TestCase):
    # Réutiliser le banc isolé sans réexécuter les douze scénarios fonctionnels déjà couverts.
    backend = "json"
    setUp = CasStdioIntegration.setUp
    spec = CasStdioIntegration.spec
    observations = CasStdioIntegration.observations
    compter = CasStdioIntegration.compter

    @unittest.skipUnless(os.name == "posix", "nettoyage des groupes POSIX")
    def test_arret_studio_joint_handler_et_nettoie_la_decouverte_bloquee(self):
        connexions.enregistrer(self.spec("ignore"), par="proprietaire-test")
        httpd = studio_api.serveur(0)
        serveur = threading.Thread(target=httpd.serve_forever, daemon=True)
        serveur.start()
        port = httpd.server_address[1]
        erreurs = []
        requete_terminee = threading.Event()
        reponse = {}

        def nettoyer():
            httpd.arret.set()
            httpd.shutdown()
            # Le serveur de test appartient à cette classe ; aucun autre groupe n'est signalé.
            for observation in self.observations():
                if "serveur" in observation:
                    try:
                        os.killpg(observation["serveur"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            httpd.server_close()
            serveur.join(timeout=2)
        self.addCleanup(nettoyer)

        c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        c.request("POST", "/api/session", body=json.dumps({"jeton": studio_api.jeton()}),
                  headers={"Host": f"localhost:{port}", "Content-Type": "application/json",
                           "X-Jarvis-Studio": "1", "Connection": "close"})
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        cookie = r.getheader("Set-Cookie").split(";", 1)[0]
        r.read()
        c.close()

        def demander():
            connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
            try:
                connexion.request("POST", "/api/v2/connexions/local/decouvrir", body="{}",
                                   headers={"Host": f"localhost:{port}", "Content-Type": "application/json",
                                            "X-Jarvis-Studio": "1", "Cookie": cookie, "Connection": "close"})
                retour = connexion.getresponse()
                reponse["status"] = retour.status
                retour.read()
            except (OSError, http.client.HTTPException):
                reponse["fermee"] = True
            finally:
                connexion.close()
                requete_terminee.set()

        with mock.patch.object(httpd, "handle_error", side_effect=lambda *_: erreurs.append("requete interrompue")):
            client = threading.Thread(target=demander, daemon=True)
            client.start()
            fin = time.monotonic() + 4
            while time.monotonic() < fin and not any("enfant" in m for m in self.observations()):
                time.sleep(0.01)
            observations = self.observations()
            pids = [m[cle] for m in observations for cle in ("serveur", "enfant") if cle in m]
            self.assertEqual(len(pids), 2, "Le serveur et son enfant sont réellement lancés avant le signal.")
            threads_http = [t for t in httpd._threads if t.is_alive()]
            self.assertTrue(threads_http)
            self.assertFalse(requete_terminee.is_set())

            def fermer():
                httpd.arret.set()
                httpd.shutdown()
                httpd.server_close()

            debut = time.monotonic()
            fermeture = threading.Thread(target=fermer, daemon=True)
            fermeture.start()
            fermeture.join(timeout=5)
            self.assertFalse(fermeture.is_alive(), "server_close doit attendre un nettoyage borné, pas quinze secondes de keepalive.")
            self.assertLess(time.monotonic() - debut, 4)
            client.join(timeout=1)
            self.assertTrue(requete_terminee.is_set())
            self.assertTrue(all(not t.is_alive() for t in threads_http), "Les handlers sont joints avant le retour de fermeture.")
            self.assertTrue(reponse.get("fermee") or reponse.get("status") in (400, 409, 503))
            for pid in pids:
                fin = time.monotonic() + 1
                while True:
                    try:
                        etat = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1]
                    except FileNotFoundError:
                        break
                    if etat.startswith("Z"):
                        break
                    if time.monotonic() >= fin:
                        self.fail("Un processus MCP continue après la fermeture du Studio.")
                    time.sleep(0.02)
        self.assertEqual(self.compter("tools/call"), 0)


if __name__ == "__main__":
    unittest.main()
