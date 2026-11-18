"""Le lanceur fournit les outils Linux au démon et au cockpit, même sans profil interactif."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))


@unittest.skipUnless(Path("/bin/bash").is_file(), "Bash Linux est requis.")
class LancementEnvironnementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-lancement-env-")
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)
        self.maison = self.racine / "maison"
        self.local = self.maison / ".local/bin"
        self.npm = self.maison / ".npm-global/bin"
        self.windows = self.racine / "mnt/c/outils"
        self.ancien = self.racine / "ancienne-version/bin"
        for dossier in (self.local, self.npm, self.windows, self.ancien):
            dossier.mkdir(parents=True, exist_ok=True)
        self._binaire(self.local / "workmux")
        self._binaire(self.npm / "codex")
        self._binaire(self.ancien / "outil-supplementaire")
        for nom in ("jarvis", "workmux", "codex"):
            self._binaire(self.windows / nom)
            self._binaire(self.ancien / nom)
        # Sonde du sous-processus Python : le vrai CLI et l'état Jarvis ne sont jamais ouverts.
        self._binaire(self.local / "python3", f"""#!{sys.executable}
import json, os, shutil, sys
print(json.dumps({{
    "commandes": {{nom: shutil.which(nom) for nom in ("jarvis", "workmux", "codex", "outil-supplementaire")}},
    "arguments": sys.argv[1:],
}}))
""")

    @staticmethod
    def _binaire(chemin, contenu="#!/bin/sh\nexit 0\n"):
        chemin.write_text(contenu)
        chemin.chmod(0o700)
        return chemin

    def _lire_environnement(self, dossiers):
        env = dict(os.environ, HOME=str(self.maison), PATH=os.pathsep.join(map(str, dossiers)))
        resultat = subprocess.run(
            ["/bin/bash", str(ROOT / "bin/jarvis"), "etat"],
            cwd=self.racine, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        return json.loads(resultat.stdout)

    def _verifier_outils_linux(self, sonde):
        self.assertEqual(sonde["arguments"], ["-m", "jarvis", "etat"])
        self.assertEqual(sonde["commandes"]["jarvis"], str(ROOT / "bin/jarvis"))
        self.assertEqual(sonde["commandes"]["workmux"], str(self.local / "workmux"))
        self.assertEqual(sonde["commandes"]["codex"], str(self.npm / "codex"))

    def test_service_sans_profil_retrouve_workmux_et_codex_linux(self):
        sonde = self._lire_environnement(["/usr/bin", "/bin"])
        self._verifier_outils_linux(sonde)

    def test_outils_linux_et_version_courante_precedent_le_path_herite(self):
        sonde = self._lire_environnement([self.windows, self.ancien, "/usr/bin", "/bin"])
        self._verifier_outils_linux(sonde)
        self.assertEqual(sonde["commandes"]["outil-supplementaire"], str(self.ancien / "outil-supplementaire"))

    def test_adaptateur_ignore_windows_et_utilise_le_repli_linux(self):
        from jarvis import adaptateurs
        with (
            mock.patch.dict(os.environ, {"PATH": str(self.windows)}),
            mock.patch.object(adaptateurs.Path, "home", return_value=self.maison),
        ):
            self.assertEqual(adaptateurs.binaire_linux("codex", exclus=(str(self.windows),)), str(self.npm / "codex"))
            (self.npm / "codex").unlink()
            self.assertIsNone(adaptateurs.binaire_linux("codex", exclus=(str(self.windows),)))


if __name__ == "__main__":
    unittest.main()
