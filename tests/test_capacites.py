"""Diagnostic de capacités : preuves limitées, configurations expurgées et aucune inférence implicite."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import capacites as ca  # noqa: E402


class CapacitesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-capacites-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.codex = self.base / "codex"
        self.claude = self.base / "claude"
        self.repo = self.base / "repo"
        for d in (self.codex, self.claude, self.repo):
            d.mkdir()
        self.env = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.codex), "CLAUDE_CONFIG_DIR": str(self.claude)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.home = mock.patch.object(ca.config, "HOME", self.base)
        self.home.start()
        self.addCleanup(self.home.stop)
        self.root = mock.patch.object(ca.config, "JARVIS_HOME", self.repo)
        self.root.start()
        self.addCleanup(self.root.stop)
        self.which = mock.patch.object(ca.shutil, "which", side_effect=lambda n: f"/bin/{n}")
        self.which.start()
        self.addCleanup(self.which.stop)
        self.calls = []
        self.commande = mock.patch.object(ca, "_commande", side_effect=self.commande_verifiee)
        self.commande.start()
        self.addCleanup(self.commande.stop)

    def commande_verifiee(self, args, **_kw):
        self.calls.append(args)
        nom = Path(args[0]).name
        versions = {"git": "git version 2.47.3", "node": "v22.21.1", "tmux": "tmux 3.5a",
                    "claude": "2.1.10 (Claude Code)", "codex": "codex-cli 0.116.0", "workmux": "workmux 0.1.276"}
        if "rev-parse" in args:
            texte = "true\n"
        elif "status" in args:
            texte = json.dumps({"agents": [{"title": "SECRET-SORTIE-BRUTE"}], "target_errors": []})
        else:
            texte = versions[nom] + "\nSECRET-SORTIE-BRUTE"
        return subprocess.CompletedProcess(args, 0, stdout=texte, stderr="SECRET-ERREUR")

    @staticmethod
    def index(rapport):
        return {c["id"]: c for c in rapport["capacites"]}

    def test_cli_verifie_ne_prouve_ni_modele_ni_authentification(self):
        rapport = ca.collecter()
        caps = self.index(rapport)
        self.assertTrue(caps["python.runtime"]["available"])
        self.assertTrue(caps["provider.codex.cli"]["available"])
        self.assertEqual(caps["provider.codex.cli"]["version"], "0.116.0")
        self.assertEqual(caps["provider.claude.auth"]["etat"], "inconnu")
        self.assertFalse(caps["provider.codex.modeles"]["available"])
        self.assertEqual(caps["provider.codex.modeles"]["etat"], "inconnu")
        self.assertEqual(caps["provider.codex.inference"]["etat"], "inconnu")
        self.assertFalse(caps["provider.codex.inference"]["available"])
        self.assertTrue(caps["git.read"]["available"])
        self.assertTrue(caps["workmux.status"]["available"])
        self.assertIn("local", caps["git.read"]["scope"])
        self.assertTrue(all(a[1] not in ("exec", "-p") for a in self.calls))
        self.assertNotIn("SECRET", json.dumps(rapport))

    def test_limites_des_voies_sont_distinctes_des_permissions_declarees(self):
        voies = ca.collecter()["voies"]
        board = voies["board_documentaire"]
        self.assertFalse(board["outils"])
        self.assertFalse(board["mcp"])
        self.assertFalse(board["web_general"])
        self.assertFalse(board["session_persistante"])
        self.assertIn("web.search", voies["chef_cli"]["outils_declares"])
        self.assertEqual(voies["chef_cli"]["outils_verifies"], [])
        self.assertFalse(voies["chef_cli"]["available"])
        self.assertTrue(voies["code"]["reseau_declare"])
        self.assertFalse(voies["code"]["available"])

    def test_mcp_ne_divulgue_que_transport_hote_et_metadonnees(self):
        (self.codex / "config.toml").write_text('''[mcp_servers.linear]
url = "https://user:SECRET-URL@mcp.linear.app/mcp?token=SECRET-QUERY"
bearer_token_env_var = "SECRET-REFERENCE"
http_headers = {Authorization = "Bearer SECRET-HEADER"}
[mcp_servers.local]
command = "/home/prive/SECRET-COMMANDE"
args = ["--password", "SECRET-ARGUMENT"]
env = {TOKEN = "SECRET-ENV"}
enabled = false
''')
        (self.claude / ".claude.json").write_text(json.dumps({"mcpServers": {"test": {
            "url": "https://example.com/private/SECRET-PATH#SECRET-FRAGMENT", "headers": {"Authorization": "SECRET"}}}}))
        rapport = ca.collecter()
        self.assertNotIn("SECRET", json.dumps(rapport))
        self.assertNotIn("/home/prive", json.dumps(rapport))
        self.assertNotIn(str(self.base), json.dumps(rapport))
        serveurs = {s["nom"]: s for s in rapport["mcp"]["serveurs"]}
        self.assertEqual(serveurs["linear"]["hote"], "mcp.linear.app")
        self.assertEqual(serveurs["local"]["transport"], "stdio")
        self.assertFalse(serveurs["local"]["active"])
        self.assertTrue(serveurs["linear"]["auth_declaree"])
        self.assertTrue(all(s["etat"] == "configure" and not s["available"] for s in serveurs.values()))

    def test_configuration_corrompue_ne_divulgue_pas_exception(self):
        (self.codex / "config.toml").write_text('[mcp_servers.SECRET-MALFORME\n token="SECRET"')
        (self.claude / ".claude.json").write_text('SECRET-JSON-INCOMPLET')
        rapport = ca.collecter()
        self.assertEqual(rapport["mcp"]["serveurs"], [])
        self.assertEqual([d["etat"] for d in rapport["mcp"]["diagnostics"]], ["degrade", "degrade", "absent"])
        self.assertNotIn("SECRET", json.dumps(rapport))

    def test_variables_connues_presence_seulement(self):
        os.environ.update({"OPENAI_API_KEY": "SECRET-OPENAI", "LINEAR_API_KEY": "SECRET-LINEAR",
                           "VARIABLE_AVEC_SECRET_DANS_LE_NOM": "SECRET-INUTILE"})
        rapport = ca.collecter()
        variables = {v["nom"]: v["presente"] for v in rapport["variables"]}
        self.assertTrue(variables["OPENAI_API_KEY"])
        self.assertTrue(variables["LINEAR_API_KEY"])
        self.assertNotIn("VARIABLE_AVEC_SECRET_DANS_LE_NOM", variables)
        self.assertFalse(self.index(rapport)["provider.codex.auth"]["available"])
        self.assertNotIn("SECRET", json.dumps(rapport))

    def test_absence_et_delai_d_executable_restent_observables(self):
        self.commande.stop()
        with mock.patch.object(ca.subprocess, "run", side_effect=subprocess.TimeoutExpired("SECRET-COMMANDE", 1.5)), \
                mock.patch.object(ca.shutil, "which", side_effect=lambda n: None if n == "claude" else f"/bin/{n}"):
            rapport = ca.collecter()
        caps = self.index(rapport)
        self.assertEqual(caps["provider.claude.cli"]["etat"], "absent")
        self.assertEqual(caps["provider.codex.cli"]["etat"], "degrade")
        self.assertFalse(caps["provider.codex.cli"]["available"])
        self.assertNotIn("SECRET", json.dumps(rapport))

    def test_statut_workmux_invalide_ou_partiel_ne_devient_pas_verifie(self):
        for texte in ("pas du JSON SECRET", "[]", '{"agents": ["SECRET-NON-OBJET"]}', '{"agents": [] , "target_errors": ["SECRET-CIBLE"]}',
                      '{"agents": [], "state_files_invalid": 1}'):
            with self.subTest(texte=texte), mock.patch.object(ca, "_commande", return_value=subprocess.CompletedProcess([], 0, stdout=texte)):
                c = ca._workmux_status()
            self.assertEqual(c["etat"], "degrade")
            self.assertFalse(c["available"])
            self.assertNotIn("SECRET", json.dumps(c))

    def test_aucune_sonde_reseau_par_defaut(self):
        with mock.patch.object(ca.urllib.request, "build_opener", side_effect=AssertionError("réseau inattendu")):
            rapport = ca.collecter()
        self.assertEqual(self.index(rapport)["web.https"]["etat"], "inconnu")

    def test_sonde_reseau_fixe_verifie_tls_et_ne_prouve_pas_internet_general(self):
        reponse = mock.MagicMock()
        reponse.__enter__.return_value.status = 200
        opener = mock.Mock()
        opener.open.return_value = reponse
        with mock.patch.object(ca.urllib.request, "build_opener", return_value=opener) as construire:
            rapport = ca.collecter(sonder_reseau=True)
        c = self.index(rapport)["web.https"]
        self.assertTrue(c["available"])
        self.assertEqual(c["hote"], "pypi.org")
        self.assertIn("uniquement", c["scope"])
        args, kw = opener.open.call_args
        self.assertEqual(args[0].full_url, "https://pypi.org/")
        self.assertEqual(args[0].method, "HEAD")
        self.assertEqual(kw["timeout"], ca.DELAI_RESEAU)
        contexte = construire.call_args.args[0]._context
        self.assertTrue(contexte.check_hostname)
        self.assertEqual(contexte.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsInstance(construire.call_args.args[1], ca._SansRedirection)

    def test_echec_ou_redirection_reseau_ne_divulgue_pas_url_ni_secret(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://SECRET.invalid", 302, "SECRET", {}, None)
        with mock.patch.object(ca.urllib.request, "build_opener", return_value=opener):
            rapport = ca.collecter(sonder_reseau=True)
        self.assertFalse(self.index(rapport)["web.https"]["available"])
        self.assertEqual(self.index(rapport)["web.https"]["etat"], "degrade")
        self.assertNotIn("SECRET", json.dumps(rapport))
        self.assertIsNone(ca._SansRedirection().redirect_request(None, None, 302, "", {}, "https://SECRET.invalid"))

    def test_options_de_sonde_et_entrees_mcp_malformees(self):
        with self.assertRaises(ValueError):
            ca.collecter(sonder_reseau="https://serveur-arbitraire.invalid")
        self.assertEqual(ca._serveurs_mcp("codex", {"nom avec espace SECRET": {"url": "https://example.com"},
                                                   "bon": "SECRET-DONNEE"}), [])
        self.assertIsNone(ca._hote("https://[SECRET"))
        self.assertIsNone(ca._hote({"url": "SECRET"}))


if __name__ == "__main__":
    unittest.main()
