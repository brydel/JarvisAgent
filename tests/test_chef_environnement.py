"""Résolution des outils du Chef : dépôt actif puis outils Linux de l’utilisateur."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "lanceurs Bash réservés à Linux/WSL")
class ChefEnvironnementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-chef-environnement-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.application = self.base / "application"
        self.bin = self.application / "bin"
        self.local = self.base / "home" / ".local" / "bin"
        self.npm = self.base / "home" / ".npm-global" / "bin"
        self.herite = self.base / "ancien" / "bin"
        self.chef = self.base / "chef"
        for dossier in (self.bin, self.local, self.npm, self.herite, self.chef / ".codex" / "rules"):
            dossier.mkdir(parents=True)
        for nom in ("jarvis-chef", "jarvis-chef-codex"):
            shutil.copy2(RACINE / "bin" / nom, self.bin / nom)
        (self.chef / "AGENTS.md").write_text("Rôle de test.", encoding="utf-8")
        (self.chef / ".codex" / "rules" / "chef.rules").write_text("# règle de test", encoding="utf-8")
        self.garde = self.base / "garde.json"
        self.env = {
            "HOME": str(self.base / "home"), "PATH": f"{self.herite}:/usr/bin:/bin",
            "LANG": "C.UTF-8", "SONDE_GARDE": str(self.garde),
        }
        self.ecrire(self.bin / "python3", """
import json, os, sys
from pathlib import Path
if "chef-garde" in sys.argv:
    Path(os.environ["SONDE_GARDE"]).write_text(json.dumps({
        "arguments": sys.argv[1:], "path": os.environ["PATH"],
        "pythonpath": os.environ.get("PYTHONPATH"),
    }))
    sys.exit(int(os.environ.get("REFUSER_GARDE", "0")))
print("")
""")

    def ecrire(self, chemin, contenu):
        chemin.write_text(f"#!{sys.executable}\n" + contenu, encoding="utf-8")
        chemin.chmod(0o700)

    def outil(self, dossier, nom, origine):
        self.ecrire(dossier / nom, f"""
import json, os, sys
print(json.dumps({{
    "origine": {origine!r}, "arguments": sys.argv[1:], "path": os.environ["PATH"],
    "jarvis_home": os.environ.get("JARVIS_HOME"),
    "role": os.environ.get("JARVIS_ROLE"), "via_chef": os.environ.get("JARVIS_VIA_CHEF"),
}}))
""")

    def lancer(self, nom, *arguments):
        return subprocess.run([str(self.bin / nom), *arguments], cwd=self.chef, env=self.env,
                              capture_output=True, text=True, timeout=10)

    def verifier_priorite(self, path):
        self.assertEqual(path.split(":")[:3], [str(self.bin), str(self.local), str(self.npm)])

    def test_codex_local_precede_le_path_herite_et_garde_son_sandbox(self):
        self.outil(self.local, "codex", "local")
        self.outil(self.herite, "codex", "ancien")
        r = self.lancer("jarvis-chef-codex", "resume", "session-de-test")
        self.assertEqual(r.returncode, 0, r.stderr)
        sonde = json.loads(r.stdout)
        self.assertEqual(sonde["origine"], "local")
        self.verifier_priorite(sonde["path"])
        self.assertEqual(sonde["jarvis_home"], str(self.application))
        self.assertEqual(sonde["role"], "chef")
        args = sonde["arguments"]
        self.assertEqual(args[args.index("--sandbox") + 1], "workspace-write")
        self.assertEqual(args[args.index("--ask-for-approval") + 1], "never")
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("--no-daemon", args)
        self.assertEqual(args[-2:], ["resume", "session-de-test"])

    def test_codex_npm_precede_le_path_herite(self):
        self.outil(self.npm, "codex", "npm-linux")
        self.outil(self.herite, "codex", "ancien")
        r = self.lancer("jarvis-chef-codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["origine"], "npm-linux")

    def test_codex_du_depot_actif_reste_prioritaire(self):
        self.outil(self.bin, "codex", "application")
        self.outil(self.local, "codex", "local")
        r = self.lancer("jarvis-chef-codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["origine"], "application")

    def test_porte_chef_aligne_le_path_avant_la_garde_et_l_execution(self):
        self.outil(self.local, "workmux", "local")
        self.outil(self.herite, "workmux", "ancien")
        r = self.lancer("jarvis-chef", "workmux", "status", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        sonde = json.loads(r.stdout)
        self.assertEqual((sonde["origine"], sonde["arguments"]), ("local", ["status", "--all"]))
        self.assertEqual((sonde["role"], sonde["via_chef"]), ("chef", "1"))
        self.verifier_priorite(sonde["path"])
        garde = json.loads(self.garde.read_text())
        self.verifier_priorite(garde["path"])
        self.assertEqual(garde["pythonpath"], str(self.application / "lib"))
        self.assertEqual(garde["arguments"], ["-m", "jarvis", "chef-garde", "--", "workmux", "status", "--all"])

    def test_refus_de_garde_empeche_toujours_l_execution(self):
        self.outil(self.local, "workmux", "ne-doit-pas-tourner")
        self.env["REFUSER_GARDE"] = "4"
        r = self.lancer("jarvis-chef", "workmux", "status", "--all")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(r.stdout, "")
        self.assertTrue(self.garde.exists())


if __name__ == "__main__":
    unittest.main()
