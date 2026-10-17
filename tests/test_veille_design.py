"""Veille approfondie, direction artistique et rôle IA produit : compétences, rôles, routage, captures."""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _Silencieux(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
from pathlib import Path

import test_jarvis  # noqa: F401 — environnement isolé (variables, chemins)
from test_jarvis import ROOT

from jarvis import modeles, plans, roles  # noqa: E402


class VeilleDesignTest(unittest.TestCase):
    def test_skills_exist_with_frontmatter_and_are_installed(self):
        install = (ROOT / "install.sh").read_text(encoding="utf-8")
        for nom in ("jarvis-studio", "jarvis-veille", "jarvis-design"):
            skill = (ROOT / "skills" / nom / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(skill.startswith(f"---\nname: {nom}\ndescription: "), nom)
            self.assertIn(nom, install)
        self.assertIn("for skill in jarvis-studio jarvis-veille jarvis-design", install)
        veille = (ROOT / "skills" / "jarvis-veille" / "SKILL.md").read_text(encoding="utf-8")
        for exigence in ("robots.txt", "On ne copie jamais", "matrice", "signature", "capturer.cjs"):
            self.assertIn(exigence, veille)
        for modele in ("matrice.csv", "cibles.json", "ux.md", "rapport.md"):
            self.assertTrue((ROOT / "skills" / "jarvis-veille" / "modeles" / modele).is_file(), modele)
        json.loads((ROOT / "skills" / "jarvis-veille" / "modeles" / "cibles.json").read_text())

    def test_roles_point_to_the_new_skills(self):
        ia = roles.get("ia-produit")
        self.assertIsNotNone(ia)
        self.assertEqual(ia["equipe"], "Fabrication")
        self.assertIn("fournisseur simulé", ia["corps"])
        self.assertIn("désactivé par défaut", ia["corps"])
        self.assertEqual(roles.get("design")["niveau"], 4)
        self.assertIn("jarvis-design", roles.get("design")["corps"])
        self.assertIn("jarvis-design", roles.get("frontend")["corps"])
        self.assertIn("jarvis-design", roles.get("revue")["corps"])
        self.assertIn("jarvis-veille", roles.get("recherche")["corps"])
        chef = (ROOT / "chef" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("@recherche+L:veille", chef)
        self.assertIn("ia-produit", chef)

    def test_plan_items_accept_the_new_role(self):
        it = plans.parse_item("repriceo:BIS-120:auto@ia-produit+M:resume-ia")
        self.assertEqual(it["role"], "ia-produit")
        choix = modeles.choisir("ia-produit", "M", "auto", usage_resume={})
        self.assertEqual(choix["role"], "ia-produit")
        self.assertEqual(modeles.choisir("design", "L", "auto", usage_resume={})["role"], "design")

    def test_capture_respects_robots_and_builds_the_sheet(self):
        racine = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        if not (shutil.which("node") and racine and (Path(racine) / "playwright").is_dir()):
            self.skipTest("node et Playwright requis")
        d = Path(tempfile.mkdtemp(prefix="jarvis-veille-"))
        site = d / "site"
        (site / "prive").mkdir(parents=True)
        (site / "index.html").write_text("<!doctype html><title>A</title><h1>Concurrent</h1>")
        (site / "prive" / "index.html").write_text("<title>Privé</title>secret")
        (site / "robots.txt").write_text("User-agent: *\nDisallow: /prive\n")
        # 127.0.0.2 n'est pas traité comme « local » : son robots.txt s'applique.
        try:
            srv = ThreadingHTTPServer(("127.0.0.2", 0), functools.partial(_Silencieux, directory=str(site)))
        except OSError:
            self.skipTest("127.0.0.2 indisponible")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        cibles = {"formats": ["bureau"], "cibles": [
            {"nom": "Concurrent A", "ecran": "Accueil", "url": f"http://127.0.0.2:{port}/"},
            {"nom": "Concurrent A", "ecran": "privé", "url": f"http://127.0.0.2:{port}/prive/"},
            {"nom": "nous", "ecran": "Accueil", "url": f"http://127.0.0.2:{port}/"}]}
        (d / "cibles.json").write_text(json.dumps(cibles))
        try:
            env = dict(os.environ, NODE_PATH=racine, NO_PROXY="127.0.0.2,localhost,127.0.0.1", no_proxy="127.0.0.2,localhost,127.0.0.1")
            res = subprocess.run(["node", str(ROOT / "skills" / "jarvis-veille" / "scripts" / "capturer.cjs"),
                                  str(d / "cibles.json"), str(d / "out")], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
            index = {(i["nom"], i["ecran"]): i for i in json.loads((d / "out" / "index.json").read_text())}
            self.assertEqual(index[("concurrent-a", "accueil")]["statut"], 200)
            self.assertEqual(index[("concurrent-a", "prive")]["statut"], "interdit-robots")
            self.assertNotIn("fichier", index[("concurrent-a", "prive")])
            self.assertTrue((d / "out" / "concurrent-a" / "accueil-bureau.png").is_file())
            self.assertTrue((d / "out" / "planche-bureau.png").stat().st_size > 1000)
            # Adresse non http(s) refusée avant tout travail.
            (d / "ko.json").write_text(json.dumps({"cibles": [{"nom": "x", "url": "file:///etc/passwd"}]}))
            ko = subprocess.run(["node", str(ROOT / "skills" / "jarvis-veille" / "scripts" / "capturer.cjs"),
                                 str(d / "ko.json"), str(d / "ko")], capture_output=True, text=True, env=env, timeout=60)
            self.assertNotEqual(ko.returncode, 0)
            self.assertIn("http(s)", ko.stderr)
        finally:
            srv.shutdown()
            srv.server_close()
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
