"""Préservation du service installé, restrictions SSH et sauvegardes de l'extension."""
from __future__ import annotations

import os
import importlib
import io
import json
import sys
import tempfile
import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/noeud_jetson"))
import installer_redteam
import jarvis_redteam
import redteam_models


class ExtensionTests(unittest.TestCase):
    def test_install_and_activate_twice_without_replacing_service(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            directory = home / ".local/share/jarvis-noeud"
            directory.mkdir(parents=True)
            base = directory / "jarvis_noeud.py"
            original = ("import json\nOUTILS=[{'name':'texte_generer'}]\n"
                        "def appeler_outil(*args): return {'conserve':True}\n"
                        "def principal(argv): print(json.dumps(OUTILS)); return 0\n")
            base.write_text(original)
            audio_conf = home / ".config/jarvis-noeud/env"
            audio_conf.parent.mkdir(parents=True)
            audio_conf.write_bytes(b"configuration audio originale\n")
            keys = home / ".ssh/authorized_keys"
            keys.parent.mkdir()
            keys.write_text(f'command="/usr/bin/python3 {base} ssh",restrict ssh-ed25519 AAAA jarvis\n')
            public = home / "cle.pub"
            public.write_text("ssh-ed25519 AAAA jarvis")
            fake_bin = home / "bin"
            fake_bin.mkdir()
            docker = fake_bin / "docker"
            docker.write_text(f"#!{sys.executable}\nprint('sha256:'+'a'*64)\n")
            docker.chmod(0o700)
            root = home / "source"
            root.mkdir()
            command = [sys.executable, str(Path(installer_redteam.__file__)), "--racine", str(root),
                       "--etat", str(home / "state"), "--image", "test:local", "--cle-jarvis", str(public)]
            env = {**os.environ, "HOME": str(home), "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}
            for _ in range(2):
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(base.read_text(), original)
            self.assertEqual(audio_conf.read_bytes(), b"configuration audio originale\n")
            self.assertIn("jarvis_redteam.py ssh", keys.read_text())
            self.assertEqual(len(list(keys.parent.glob("authorized_keys.avant-redteam-*"))), 1)
            result = subprocess.run([sys.executable, str(directory / "jarvis_redteam.py"), "mcp"],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([tool["name"] for tool in json.loads(result.stdout)], ["texte_generer", "redteam_auditer"])

    def test_truncated_model_output_is_explicit_failure(self):
        data = {"done": True, "done_reason": "length", "message": {"content": '{"hypotheses": ["incomplet'}}
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            with self.assertRaisesRegex(ValueError, "budget de sortie"):
                redteam_models.Ollama(max_tokens=64).analyze({})

    def test_valid_model_output_stays_hypothesis_with_timings(self):
        data = {"done": True, "done_reason": "stop", "eval_count": 34, "eval_duration": 123,
                "message": {"content": '{"hypotheses": ["À examiner"]}'}}
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
            result = redteam_models.Ollama().analyze({})
        self.assertEqual(result["status"], "hypothesis")
        self.assertEqual(result["metrics"]["eval_duration"], 123)

    def test_preserve_multimodal_tools_and_dispatch(self):
        original = Mock(return_value={"travail": "existant"})
        tools = [{"name": name} for name in ("audio_transcrire", "texte_generer", "image_decrire", "noeud_sante")]
        node = types.SimpleNamespace(OUTILS=tools, appeler_outil=original, ErreurNoeud=ValueError)
        jarvis_redteam.activer(node)
        jarvis_redteam.activer(node)
        self.assertEqual(node.OUTILS[:-1], tools)
        self.assertEqual(sum(t["name"] == "redteam_auditer" for t in node.OUTILS), 1)
        for tool in tools:
            self.assertEqual(node.appeler_outil(tool["name"], {"test": True}, {"jeton": "privé"}), {"travail": "existant"})
            original.assert_called_with(tool["name"], {"test": True}, {"jeton": "privé"})

    def test_refuse_existing_redteam_tool(self):
        original = Mock()
        autre = {**jarvis_redteam.OUTIL, "inputSchema": {"type": "object", "properties": {"cible": {"type": "string"}}}}
        node = types.SimpleNamespace(OUTILS=[autre], appeler_outil=original)
        with self.assertRaises(ValueError):
            jarvis_redteam.activer(node)
        self.assertIs(node.appeler_outil, original)

    def test_reprend_l_outil_natif_de_meme_schema(self):
        """Le jarvis_noeud.py du dépôt déclare déjà redteam_auditer : l'extension ne casse plus le point d'entrée."""
        original = Mock(return_value={"travail": "existant"})
        natif = {**jarvis_redteam.OUTIL, "description": "version native"}
        node = types.SimpleNamespace(OUTILS=[natif, {"name": "noeud_sante"}], appeler_outil=original, ErreurNoeud=ValueError)
        jarvis_redteam.activer(node)
        self.assertEqual([t["name"] for t in node.OUTILS], ["noeud_sante", "redteam_auditer"])
        self.assertEqual(node.OUTILS[-1], jarvis_redteam.OUTIL)
        self.assertEqual(node.appeler_outil("noeud_sante", {}, {}), {"travail": "existant"})

    def test_point_d_entree_du_depot_accepte(self):
        noeud = importlib.import_module("jarvis_noeud")
        copie = types.SimpleNamespace(OUTILS=list(noeud.OUTILS), appeler_outil=Mock(), ErreurNoeud=ValueError)
        jarvis_redteam.activer(copie)
        self.assertEqual(sum(t["name"] == "redteam_auditer" for t in copie.OUTILS), 1)

    def test_scan_error_remains_mcp_error(self):
        class ErreurNoeud(Exception):
            pass
        node = types.SimpleNamespace(OUTILS=[], appeler_outil=Mock(), ErreurNoeud=ErreurNoeud)
        jarvis_redteam.activer(node)
        with patch.object(jarvis_redteam, "politique"), patch("redteam_engine.Engine") as engine:
            engine.return_value.run.side_effect = RuntimeError("chemin privé")
            with self.assertRaisesRegex(ErreurNoeud, "RuntimeError") as error:
                node.appeler_outil("redteam_auditer", {}, {})
            self.assertNotIn("privé", str(error.exception))

    def test_policy_requires_docker_even_when_host_configured(self):
        with tempfile.TemporaryDirectory() as td:
            conf = Path(td) / "redteam.env"
            conf.write_text("JARVIS_REDTEAM_ROOT=/tmp\nJARVIS_REDTEAM_STATE=/other\nJARVIS_REDTEAM_SEMGREP=semgrep\n")
            with patch.dict(os.environ, {"JARVIS_REDTEAM_CONF": str(conf)}), self.assertRaises(ValueError):
                jarvis_redteam.politique()

    def test_forced_key_only_changes_jarvis_entrypoint(self):
        directory = Path("/installation/noeud")
        line = 'command="/usr/bin/python3 /installation/noeud/jarvis_noeud.py ssh",restrict ssh-ed25519 AAAA jarvis\n'
        other = 'ssh-ed25519 BBBB autre\n'
        result = installer_redteam.raccorder(other + line, "ssh-ed25519 AAAA jarvis", directory)
        self.assertEqual(result, other + line.replace("jarvis_noeud.py", "jarvis_redteam.py"))
        self.assertEqual(result, installer_redteam.raccorder(result, "ssh-ed25519 AAAA", directory))

    def test_refuse_unknown_or_ambiguous_key_and_custom_permissions(self):
        line = 'command="/usr/bin/python3 /installation/noeud/jarvis_noeud.py ssh",restrict ssh-ed25519 AAAA\n'
        for content in (line.replace("AAAA", "AAAB"), line + line,
                        line.replace(",restrict", ""), line.replace(" ssh\"", " shell\"")):
            with self.subTest(content=content), self.assertRaises(ValueError):
                installer_redteam.raccorder(content, "ssh-ed25519 AAAA", Path("/installation/noeud"))

    def test_backup_keeps_original_and_repeat_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "authorized_keys"
            path.write_bytes(b"original")
            installer_redteam.publier(path, b"nouveau", 0o600)
            backup = list(Path(td).glob("authorized_keys.avant-redteam-*/authorized_keys"))
            self.assertEqual(len(backup), 1)
            self.assertEqual(backup[0].read_bytes(), b"original")
            stamp = path.stat().st_mtime_ns
            installer_redteam.publier(path, b"nouveau", 0o600)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_refuse_symlink_without_changing_target(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "cible"
            target.write_bytes(b"original")
            path = Path(td) / "lien"
            path.symlink_to(target)
            with self.assertRaises(ValueError):
                installer_redteam.publier(path, b"nouveau", 0o600)
            self.assertEqual(target.read_bytes(), b"original")
