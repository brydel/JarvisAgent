"""Tests de bout en bout de Jarvis : plans, routeur, registre, démon, studio, pont Telegram, interfaces.

Lancement :  python3 -m unittest discover -s tests -v
Prérequis : tmux (une session tmux isolée est créée puis détruite).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="jarvis-test-"))
TMUX_SOCKET = f"jarvis-test-{os.getpid()}"

# L'environnement doit être prêt AVANT d'importer jarvis (chemins lus à l'import).
os.environ.update({
    "JARVIS_CONFIG_DIR": str(TMP / "cfg"),
    "JARVIS_STATE_DIR": str(TMP / "state"),
    "JARVIS_DATA_DIR": str(TMP / "data"),
    "JARVIS_SESSION": "jtest",
    "FAKE_WORKMUX_STATUS": str(TMP / "status.json"),
    "FAKE_WORKMUX_LOG": str(TMP / "wm.log"),
    "FAKE_CLI_LOG": str(TMP / "cli.log"),
    "CODEX_HOME": str(TMP / "codexhome"),
    "CLAUDE_CONFIG_DIR": str(TMP / "claudecfg"),
    "PATH": f"{TMP / 'bin'}:{ROOT / 'tests' / 'fake-bin'}:{os.environ['PATH']}",
})
sys.path.insert(0, str(ROOT / "lib"))

# Toutes les commandes tmux du code passent par ce petit wrapper → serveur tmux isolé.
(TMP / "bin").mkdir()
real_tmux = shutil.which("tmux")
wrapper = TMP / "bin" / "tmux"
wrapper.write_text(f"#!/bin/sh\nexec {real_tmux} -L {TMUX_SOCKET} \"$@\"\n")
wrapper.chmod(0o755)

from jarvis import admission, agents, config, daemon, plans, store, taches  # noqa: E402
from jarvis.telegram import Bot  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "status.json").read_text())


def set_status(**overrides):
    data = json.loads(json.dumps(FIXTURE))
    for a in data["agents"]:
        if a["worktree"] in overrides:
            a["status"] = overrides[a["worktree"]]
    Path(os.environ["FAKE_WORKMUX_STATUS"]).write_text(json.dumps(data))


class FakeTelegram(BaseHTTPRequestHandler):
    calls: list = []
    updates: list = []
    FILE = b"\x89PNG maquette"

    def do_GET(self):  # noqa: N802 — téléchargement d'un fichier (api.telegram.org/file/bot…/chemin)
        FakeTelegram.calls.append(("GET", self.path))
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.FILE)))
        self.end_headers()
        self.wfile.write(self.FILE)

    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        method = self.path.rsplit("/", 1)[-1]
        if self.headers.get("Content-Type", "").startswith("multipart/form-data"):
            # Envoi d'un fichier (sendVideo, sendPhoto, sendDocument) : on garde de quoi vérifier.
            body = {"multipart": True, "octets": len(raw), "brut": raw[:4000].decode("utf-8", errors="replace")}
        else:
            body = json.loads(raw or b"{}")
        FakeTelegram.calls.append((method, body))
        result = True
        if method == "getUpdates":
            result, FakeTelegram.updates = FakeTelegram.updates, []
        elif method == "getMe":
            result = {"username": "jarvis_test_bot"}
        elif method == "sendMessage":
            result = {"message_id": len(FakeTelegram.calls)}
        elif method == "getFile":
            result = {"file_id": body.get("file_id"), "file_path": "photos/file_1.jpg", "file_size": len(self.FILE)}
        payload = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def tmux(*args) -> str:
    return subprocess.run([str(wrapper), *args], capture_output=True, text=True).stdout


class JarvisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ["JARVIS_TELEGRAM_API"] = f"http://127.0.0.1:{cls.server.server_port}"
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

        for name in ("repriceo", "jobpilot-ia"):
            d = TMP / "p" / name
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", str(d)], check=True)
        config.save_projects({
            "repriceo": {"chemin": str(TMP / "p/repriceo"), "linear": "Repriceo", "priorite": 1, "actif": True},
            "jobpilot-ia": {"chemin": str(TMP / "p/jobpilot-ia"), "linear": "JobPilot", "priorite": 2, "actif": True},
        })
        data = config.settings()
        data["telegram"].update({"token": "123:ABC", "chat_id": "42"})
        data["notifications"]["windows"] = False
        data["sante"]["capacite_auto"] = False  # la mémoire de la machine de test ne doit rien décider
        config.save_settings(data)

        # Le « chef » : une fenêtre tmux qui affiche tout ce qu'on lui tape.
        tmux("new-session", "-d", "-s", "jtest", "-n", "cockpit", "-x", "200", "-y", "50", "sh")
        tmux("new-window", "-d", "-t", "jtest", "-n", "chef", "cat")
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        tmux("kill-server")
        cls.server.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        FakeTelegram.calls.clear()
        store.write_json(plans.PLANS_FILE, {"seq": 0, "plans": []})  # chaque test part de zéro
        store.set_paused(False)
        for name in ("claude_usage.json", "budget.json", "veille.json", "battement.json", "sante.json",
                     "reprise.json", "agents_actifs.json", "chef_queue.json", "taches.json", "modeles_verif.json",
                     "modeles_propositions.json", "livrables.json", "usage_hist.json", "prevision.json",
                     "blocage.json", "chef_garde.json", "demon.json", "sante_windows.json", "watch.json",
                     "pauses.json", "reservations.json", "lourdes/operations.json", "relances.json", "journal.jsonl",
                     "ressources.json", "delegations.json", "exceptions.json", "budgets.json", "travaux.json"):
            store.state_path(name).unlink(missing_ok=True)
        (TMP / "cfg" / "modeles.toml").unlink(missing_ok=True)
        Path(os.environ["FAKE_CLI_LOG"]).write_text("")
        shutil.rmtree(TMP / "codexhome" / "sessions", ignore_errors=True)

    # --- jetons -----------------------------------------------------------------
    def set_claude(self, five, week=10.0):
        now = int(time.time())
        payload = {"rate_limits": {"five_hour": {"used_percentage": five, "resets_at": now + 3600},
                                   "seven_day": {"used_percentage": week, "resets_at": now + 5 * 86400}}}
        res = subprocess.run([str(ROOT / "bin" / "jarvis-statusline")], input=json.dumps(payload),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def set_codex(self, five, week=10.0, reached=None):
        now = int(time.time())
        d = TMP / "codexhome" / "sessions" / time.strftime("%Y/%m/%d")
        d.mkdir(parents=True, exist_ok=True)
        line = {"timestamp": "2026-10-12T23:00:00.000Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": None, "rate_limits": {
                "primary": {"used_percent": five, "window_minutes": 300, "resets_at": now + 7200},
                "secondary": {"used_percent": week, "window_minutes": 10080, "resets_at": now + 3 * 86400},
                "rate_limit_reached_type": reached}}}
        with (d / "rollout-test.jsonl").open("a") as fh:
            fh.write(json.dumps({"type": "session_meta", "payload": {}}) + "\n")
            fh.write(json.dumps(line) + "\n")

    def test_statusline_and_codex_rollouts_are_read(self):
        from jarvis import usage
        out = self.set_claude(42.4, 61)
        self.assertIn("5h 42%", out)
        self.set_codex(88, 30)
        s = usage.summary()
        self.assertEqual(s["claude"]["5h"]["used"], 42.4)
        self.assertEqual(s["claude"]["niveau"], "ok")
        self.assertEqual(s["codex"]["5h"]["used"], 88)
        self.assertEqual(s["codex"]["semaine"]["used"], 30)
        self.assertEqual(s["codex"]["niveau"], "alerte")
        self.assertAlmostEqual(s["codex"]["marge"], 12)

    def test_expired_window_counts_as_reset(self):
        from jarvis import usage
        store.write_json(usage.CLAUDE_FILE, {"ts": time.time(), "five_hour": {
            "used_percentage": 99, "resets_at": int(time.time()) - 10}})
        self.assertEqual(usage.claude_usage()["5h"]["used"], 0.0)

    def test_budget_alert_stop_pause_and_recover(self):
        set_status()  # jp-12-onboarding : agent Claude au travail
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        self.set_claude(50)
        self.set_codex(20)
        daemon.budget_check()
        self.set_claude(85)
        self.assertIn("Claude alerte", daemon.budget_check())
        self.assertIn("[JARVIS jetons] Claude a dépassé le seuil d'alerte", self.chef_screen())
        self.set_claude(97)
        self.assertIn("Claude épuisé", daemon.budget_check())
        sent = Path(os.environ["FAKE_WORKMUX_LOG"]).read_text()
        self.assertIn("send jobpilot-ia:jp-12-onboarding [JARVIS] La limite de jetons", sent)
        # Lancement refusé côté Claude, accepté côté Codex.
        p = plans.create("Budget", [plans.parse_item("repriceo:BIS-60:claude"), plans.parse_item("repriceo:BIS-61:codex")])
        plans.decide(p["id"], True, par="test")
        res = subprocess.run([sys.executable, "-m", "jarvis", "plan", "verifier", p["id"], "repriceo", "BIS-60", "claude"],
                             capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "lib")))
        self.assertEqual(res.returncode, 5, res.stderr)
        self.assertIn("épuisés", res.stderr)
        # Les deux épuisés → pause automatique, puis reprise quand Claude se libère.
        self.set_codex(99)
        self.assertIn("pause auto", daemon.budget_check())
        self.assertTrue(store.paused())
        self.set_claude(10)
        events = daemon.budget_check()
        self.assertIn("Claude rétabli", events)
        self.assertIn("reprise auto", events)
        self.assertFalse(store.paused())

    def test_human_pause_is_not_lifted_by_budget(self):
        self.set_claude(10)
        self.set_codex(10)
        store.set_paused(True)  # pause décidée par l'humain
        daemon.budget_check()
        self.assertTrue(store.paused())

    def test_veille_reminder_is_due_then_throttled(self):
        self.assertEqual(daemon.veille_check(), "repriceo")  # priorité 1, jamais faite
        self.assertIn("[JARVIS veille] Veille concurrentielle due pour « repriceo »", self.chef_screen())
        self.assertIsNone(daemon.veille_check())  # au plus un rappel toutes les 6 h
        from jarvis import cli
        cli.main(["veille", "fait", "repriceo"])
        st = store.read_json(daemon.VEILLE_STATE, {})
        st["dernier_rappel"] = 0
        store.write_json(daemon.VEILLE_STATE, st)
        self.assertEqual(daemon.veille_check(), "jobpilot-ia")  # repriceo est à jour

    def test_auto_validation_setting(self):
        from jarvis import cli
        data = config.settings()
        data["plans"]["validation"] = "auto"
        config.save_settings(data)
        try:
            self.assertEqual(cli.main(["plan", "nouveau", "--titre", "Auto", "--item", "repriceo:BIS-70:codex"]), 0)
            self.assertEqual(plans.all_plans()[-1]["statut"], "approuve")
        finally:
            data["plans"]["validation"] = "humain"
            config.save_settings(data)

    def test_installer_statusline_never_overwrites(self):
        cfg = TMP / "claudecfg"
        cfg.mkdir(exist_ok=True)
        (cfg / "settings.json").unlink(missing_ok=True)
        run = lambda: subprocess.run([sys.executable, "-m", "jarvis", "installer-statusline"], capture_output=True,
                                     text=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "lib")))
        self.assertEqual(run().returncode, 0)
        self.assertIn("jarvis-statusline", json.loads((cfg / "settings.json").read_text())["statusLine"]["command"])
        self.assertIn("déjà", run().stdout)
        (cfg / "settings.json").write_text(json.dumps({"statusLine": {"type": "command", "command": "ma-barre"}}))
        self.assertEqual(run().returncode, 3)
        self.assertEqual(json.loads((cfg / "settings.json").read_text())["statusLine"]["command"], "ma-barre")

    def chef_screen(self) -> str:
        time.sleep(0.4)
        return tmux("capture-pane", "-p", "-J", "-t", "jtest:chef")

    # --- plans -----------------------------------------------------------------
    def test_plan_cycle_and_chef_is_told(self):
        p = plans.create("Vague test", [plans.parse_item("repriceo:BIS-80:claude:auth")])
        with self.assertRaises(plans.PlanError):
            plans.authorize_launch(p["id"], "repriceo", "BIS-80", "claude")
        plans.decide(p["id"], True, par="test")
        self.assertIn(f"Plan {p['id']} APPROUVÉ", self.chef_screen())
        plans.authorize_launch(p["id"], "repriceo", "bis-80", "cc")
        self.assertEqual(plans.get(p["id"])["statut"], "termine")
        with self.assertRaises(plans.PlanError):
            plans.authorize_launch(p["id"], "repriceo", "BIS-80", "claude")

    def test_parse_item_rejects_garbage(self):
        for bad in ("repriceo:BIS80:claude", "repriceo:BIS-1:gemini", "pas un item"):
            with self.assertRaises(plans.PlanError):
                plans.parse_item(bad)

    # --- démon -------------------------------------------------------------------
    def test_watch_detects_transitions_and_wakes_chef(self):
        set_status(**{"bis-71-guardrails-couts": "working", "bis-69-adr-architecture": "working"})
        daemon.watch_once(first=True)
        set_status(**{"bis-71-guardrails-couts": "waiting", "bis-69-adr-architecture": "done"})
        events = daemon.watch_once()
        texts = " | ".join(e["texte"] for e in events)
        self.assertIn("bis-69-adr-architecture (Claude) a terminé", texts)
        self.assertIn("bis-71-guardrails-couts (Codex) attend une réponse", texts)
        screen = self.chef_screen()
        self.assertIn("[JARVIS événement]", screen)
        self.assertIn("repriceo:bis-71-guardrails-couts", screen)
        # Aucun changement → aucun événement
        self.assertEqual(daemon.watch_once(), [])

    def test_chef_is_never_treated_as_an_agent(self):
        set_status(chef="working")
        daemon.watch_once(first=True)
        set_status(chef="done")
        events = daemon.watch_once()
        self.assertFalse(any("chef" in e["texte"] for e in events))  # pas d'auto-réveil en boucle
        found, _ = agents.status_all()
        self.assertNotIn("chef", [a["worktree"] for a in found])

    def test_watch_fails_closed_when_workmux_breaks(self):
        Path(os.environ["FAKE_WORKMUX_STATUS"]).write_text("pas du json")
        self.assertEqual(daemon.watch_once(), [])

    # --- Telegram ----------------------------------------------------------------
    def test_telegram_buttons_approve_plan(self):
        p = plans.create("Vague Telegram", [plans.parse_item("jobpilot-ia:JP-3:codex")])
        bot = Bot("123:ABC")
        daemon.handle_update(bot, "42", {"callback_query": {
            "id": "cb1", "data": f"ok:{p['id']}",
            "message": {"message_id": 7, "chat": {"id": 42}, "text": "plan"}}})
        self.assertEqual(plans.get(p["id"])["statut"], "approuve")
        methods = [m for m, _ in FakeTelegram.calls]
        self.assertIn("answerCallbackQuery", methods)
        self.assertIn("editMessageText", methods)

    def test_telegram_rejects_strangers(self):
        p = plans.create("Vague intrus", [plans.parse_item("repriceo:BIS-81:codex")])
        bot = Bot("123:ABC")
        daemon.handle_update(bot, "42", {"callback_query": {
            "id": "cb2", "data": f"ok:{p['id']}", "message": {"message_id": 8, "chat": {"id": 666}}}})
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 666}, "text": "/pause"}})
        self.assertEqual(plans.get(p["id"])["statut"], "en_attente")
        self.assertFalse(store.paused())

    def test_telegram_text_goes_to_chef_and_commands_work(self):
        set_status()
        bot = Bot("123:ABC")
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 42}, "text": "Priorise JobPilot cette nuit"}})
        self.assertIn("[Message de ton humain via Telegram] Priorise JobPilot cette nuit", self.chef_screen())
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 42}, "text": "/etat"}})
        sent = [b["text"] for m, b in FakeTelegram.calls if m == "sendMessage"]
        self.assertTrue(any("AGENTS" in t for t in sent))
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 42}, "text": "/pause"}})
        self.assertTrue(store.paused())
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 42}, "text": "/reprendre"}})
        self.assertFalse(store.paused())

    def test_new_plan_cli_sends_buttons(self):
        from jarvis import cli
        rc = cli.main(["plan", "nouveau", "--titre", "Vague CLI", "--item", "repriceo:BIS-90:claude:x"])
        self.assertEqual(rc, 0)
        msg = [b for m, b in FakeTelegram.calls if m == "sendMessage"][-1]
        buttons = msg["reply_markup"]["inline_keyboard"][0]
        self.assertTrue(buttons[0]["callback_data"].startswith("ok:P-"))

    # --- garde-fous ---------------------------------------------------------------
    def run_jarvis(self, *args, cwd=None, env_extra=None):
        env = dict(os.environ, TMUX="faux", **(env_extra or {}))
        return subprocess.run([str(ROOT / "bin" / "jarvis"), *args], cwd=cwd or str(TMP),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)

    def test_agent_cannot_approve_or_change_settings(self):
        p = plans.create("Auto-approbation", [plans.parse_item("repriceo:BIS-91:claude")])
        for args in (["plan", "ok", p["id"]], ["regler", "general.max_agents", "99"]):
            res = self.run_jarvis(*args)
            self.assertEqual(res.returncode, 4, res.stderr)
            self.assertIn("réservé à l'humain", res.stderr)
        self.assertEqual(plans.get(p["id"])["statut"], "en_attente")
        self.assertEqual(config.settings()["general"]["max_agents"], 3)

    def test_task_without_terminal_needs_plan_and_project(self):
        res = self.run_jarvis("task", "BIS-92", "claude", cwd=str(TMP / "p/repriceo"))
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("sans plan approuvé", res.stderr)
        res = self.run_jarvis("task", "--plan", "P-9999", "BIS-92", "claude")
        self.assertIn("--projet", res.stderr)

    def test_task_with_approved_plan_relative_brief_and_review(self):
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        p = plans.create("Vague bash", [plans.parse_item("repriceo:BIS-93:claude:x"),
                                        plans.parse_item("repriceo:BIS-93:codex:revue")])
        plans.decide(p["id"], True, par="test")
        chef_dir = TMP / "chefdir"
        (chef_dir / "consignes").mkdir(parents=True, exist_ok=True)
        (chef_dir / "consignes" / "BIS-93.md").write_text("Brief : ajouter la 2FA")
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-93", "claude", "2FA",
                              "--consignes", "./consignes/BIS-93.md", cwd=str(chef_dir))
        self.assertEqual(res.returncode, 0, res.stderr)
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-93", "codex",
                              "--revue", "12", cwd=str(chef_dir))
        self.assertEqual(res.returncode, 0, res.stderr)
        adds = [ln.split() for ln in Path(os.environ["FAKE_WORKMUX_LOG"]).read_text().splitlines()
                if ln.startswith("add ")]
        brief = Path(adds[-2][-1]).read_text()
        review = Path(adds[-1][-1]).read_text()
        self.assertIn("Brief : ajouter la 2FA", brief)
        self.assertIn("RELECTURE uniquement", review)
        self.assertEqual(adds[-1][1], "bis-93-revue-pr-12")
        # Plan épuisé : plus rien ne passe.
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-93", "claude", cwd=str(chef_dir))
        self.assertNotEqual(res.returncode, 0)

    def test_capacity_counts_launches_not_yet_visible(self):
        p = plans.create("Capacité", [plans.parse_item("repriceo:BIS-94:claude"),
                                      plans.parse_item("repriceo:BIS-95:codex")])
        plans.decide(p["id"], True, par="test")
        plans.authorize_launch(p["id"], "repriceo", "BIS-94", "claude", busy=0, visible=set(), max_agents=1)
        with self.assertRaises(plans.PlanError):  # BIS-94 démarre encore : la place est prise
            plans.authorize_launch(p["id"], "repriceo", "BIS-95", "codex", busy=0, visible=set(), max_agents=1)
        # Dès que workmux voit BIS-94 (et qu'il a terminé), la place se libère.
        plans.authorize_launch(p["id"], "repriceo", "BIS-95", "codex", busy=0,
                               visible={"bis-94-x"}, max_agents=1)

    def test_failed_launch_can_be_released(self):
        p = plans.create("Relâche", [plans.parse_item("repriceo:BIS-96:claude")])
        plans.decide(p["id"], True, par="test")
        plans.authorize_launch(p["id"], "repriceo", "BIS-96", "claude")
        self.assertEqual(plans.get(p["id"])["statut"], "termine")
        plans.release(p["id"], "repriceo", "BIS-96", "claude")
        self.assertEqual(plans.get(p["id"])["statut"], "approuve")
        plans.authorize_launch(p["id"], "repriceo", "BIS-96", "claude")

    def test_telegram_requires_owner_as_sender(self):
        p = plans.create("Groupe", [plans.parse_item("repriceo:BIS-97:claude")])
        bot = Bot("123:ABC")
        daemon.handle_update(bot, "42", {"callback_query": {
            "id": "cb3", "data": f"ok:{p['id']}", "from": {"id": 99},
            "message": {"message_id": 9, "chat": {"id": 42}}}})
        self.assertEqual(plans.get(p["id"])["statut"], "en_attente")

    def test_chef_permissions_deny_self_approval(self):
        res = subprocess.run([sys.executable, "-m", "jarvis", "chef-preparer"], capture_output=True, text=True,
                             env=dict(os.environ, PYTHONPATH=str(ROOT / "lib"), JARVIS_DATA_DIR=str(TMP / "data")))
        self.assertEqual(res.returncode, 0, res.stderr)
        settings = json.loads((Path(res.stdout.strip()) / ".claude" / "settings.json").read_text())
        deny = settings["permissions"]["deny"]
        for rule in ("Bash(jarvis plan ok *)", "Bash(jarvis regler *)", "Bash(workmux add *)", "Bash(python3 *)"):
            self.assertIn(rule, deny)
        self.assertNotIn("Bash(jarvis *)", settings["permissions"]["allow"])
        self.assertTrue(any(str(TMP / "p" / "repriceo") in r for r in deny))

    # --- autonomie et visibilité ---------------------------------------------------
    def test_worktree_trust_for_claude_and_codex(self):
        from jarvis import trust
        cfg = TMP / "claudecfg"
        cfg.mkdir(exist_ok=True)
        (cfg / ".claude.json").write_text(json.dumps({"numStartups": 3, "projects": {"/autre": {"x": 1}}}))
        wt = str(TMP / "p" / "repriceo__worktrees" / "bis-1-x")
        self.assertTrue(trust.trust_claude(wt))
        self.assertFalse(trust.trust_claude(wt))  # idempotent
        data = json.loads((cfg / ".claude.json").read_text())
        self.assertTrue(data["projects"][wt]["hasTrustDialogAccepted"])
        self.assertEqual(data["numStartups"], 3)          # le reste du fichier est préservé
        self.assertEqual(data["projects"]["/autre"], {"x": 1})

        codex_cfg = TMP / "codexhome" / "config.toml"
        codex_cfg.parent.mkdir(exist_ok=True)
        codex_cfg.write_text('model = "gpt"\n')
        self.assertTrue(trust.trust_codex(wt))
        self.assertFalse(trust.trust_codex(wt))
        import tomllib
        parsed = tomllib.loads(codex_cfg.read_text())       # reste du TOML valide
        self.assertEqual(parsed["projects"][wt]["trust_level"], "trusted")
        self.assertEqual(parsed["model"], "gpt")

    def test_untracked_agent_windows_are_visible_and_capturable(self):
        set_status()
        wt_dir = TMP / "p" / "repriceo__worktrees" / "bis-77-revue"
        wt_dir.mkdir(parents=True, exist_ok=True)
        tmux("new-window", "-d", "-t", "jtest", "-n", "wm-bis-77-revue", "-c", str(wt_dir),
             "sh -c 'echo Codex relit la PR 3; exec cat'")
        time.sleep(0.4)
        found, _ = agents.status_all()
        ghost = [a for a in found if a["worktree"] == "bis-77-revue"]
        self.assertEqual(len(ghost), 1)
        self.assertEqual(ghost[0]["status"], "untracked")
        self.assertEqual(ghost[0]["project"], "repriceo")
        self.assertIn("Codex relit la PR 3", agents.capture("repriceo:bis-77-revue"))
        # Compté comme occupé : on ne lance rien par-dessus.
        from jarvis import report
        self.assertEqual(report.snapshot()["busy"], 3)  # 1 attend + 1 travaille + 1 non suivi
        tmux("kill-window", "-t", "jtest:wm-bis-77-revue")

    def test_long_idle_untracked_window_frees_its_slot(self):
        """Silence prolongé : « silencieux » (occupé) tant qu'un programme tourne, « inactif » (libéré) sinon."""
        set_status()
        tmux("new-window", "-d", "-t", "jtest", "-n", "wm-vieux-codex", "cat")      # programme vivant, muet
        tmux("new-window", "-d", "-t", "jtest", "-n", "wm-fini-codex", "bash")      # plus qu'un shell
        time.sleep(0.5)
        old = agents.IDLE_AFTER
        agents.IDLE_AFTER = 0  # simule des fenêtres muettes depuis longtemps
        try:
            found, _ = agents.status_all()
            ghost = next(a for a in found if a["worktree"] == "vieux-codex")
            self.assertEqual(ghost["status"], "silent")       # jamais « terminé » faute de sortie
            self.assertIn(ghost["status"], agents.BUSY)
            fini = next(a for a in found if a["worktree"] == "fini-codex")
            self.assertEqual(fini["status"], "idle")
            self.assertNotIn(fini["status"], agents.BUSY)
            self.assertIn(fini["status"], agents.CLOSABLE)
            # La fiche d'un agent silencieux reste ouverte ; celle d'un agent sans programme se termine.
            taches.enregistrer(projet="?", issue="BIS-1", agent="codex", worktree="vieux-codex")
            taches.enregistrer(projet="?", issue="BIS-2", agent="codex", worktree="fini-codex")
            taches.synchroniser(found)
            etats = {t["worktree"]: t["statut"] for t in taches.toutes()}
            self.assertEqual(etats["vieux-codex"], "silencieuse")
            self.assertEqual(etats["fini-codex"], "terminee")
        finally:
            agents.IDLE_AFTER = old
            tmux("kill-window", "-t", "jtest:wm-vieux-codex")
            tmux("kill-window", "-t", "jtest:wm-fini-codex")

    def test_task_pre_trusts_the_new_worktree(self):
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        p = plans.create("Confiance", [plans.parse_item("repriceo:BIS-98:codex")])
        plans.decide(p["id"], True, par="test")
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-98", "codex", "auth")
        self.assertEqual(res.returncode, 0, res.stderr)
        expected = str((TMP / "p" / "repriceo__worktrees" / "bis-98-auth").resolve())
        self.assertIn(f'[projects."{expected}"]', (TMP / "codexhome" / "config.toml").read_text())

    def test_reglage_lire_never_prints_the_token(self):
        res = subprocess.run([sys.executable, "-m", "jarvis", "reglage-lire", "telegram.token"],
                             capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "lib")))
        self.assertNotIn("123:ABC", res.stdout)

    def test_chef_injection_is_single_line(self):
        agents.chef_inject("ligne un\nligne deux")
        self.assertIn("ligne un ligne deux", self.chef_screen())

    def test_injection_waits_while_chef_shows_a_dialog(self):
        # Simule une demande de permission à l'écran : rien ne doit être tapé dedans.
        tmux("new-window", "-d", "-t", "jtest", "-n", "dialog-tmp", "sh")
        tmux("kill-window", "-t", "jtest:chef")
        tmux("new-window", "-d", "-t", "jtest", "-n", "chef",
             "printf 'Do you want to proceed?\\n❯ 1. Yes\\n  2. No\\n'; exec cat")
        time.sleep(0.4)
        self.assertTrue(agents.chef_inject("message important"))
        self.assertNotIn("message important", self.chef_screen())
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), ["message important"])
        self.assertEqual(agents.chef_flush_queue(), 0)  # boîte toujours là : on attend
        # La boîte disparaît (nouveau chef) → la file est vidée.
        tmux("kill-window", "-t", "jtest:chef")
        tmux("new-window", "-d", "-t", "jtest", "-n", "chef", "cat")
        time.sleep(0.4)
        self.assertEqual(agents.chef_flush_queue(), 1)
        self.assertIn("message important", self.chef_screen())
        tmux("kill-window", "-t", "jtest:dialog-tmp")


    # --- fenêtres, redémarrage, santé, Telegram fichiers, Codex ------------------------
    def wm_log(self) -> str:
        return Path(os.environ["FAKE_WORKMUX_LOG"]).read_text()

    def test_fermer_only_closes_finished_agents(self):
        from jarvis import cli
        set_status(**{"bis-69-adr-architecture": "done", "jp-12-onboarding": "working"})
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        self.assertEqual(cli.main(["fermer", "jobpilot-ia:jp-12-onboarding"]), 1)  # travaille : refusé
        self.assertNotIn("close", self.wm_log())
        self.assertEqual(cli.main(["fermer", "--termines"]), 0)
        self.assertIn("close bis-69-adr-architecture", self.wm_log())
        self.assertNotIn("close jp-12-onboarding", self.wm_log())

    def test_menage_closes_long_finished_windows(self):
        set_status(**{"bis-69-adr-architecture": "done", "jp-12-onboarding": "working"})
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        closed = daemon.menage_check()  # bis-69 : terminé depuis 412 s < 60 min
        self.assertEqual(closed, [])
        data = config.settings()
        data["general"]["fermeture_auto_min"] = 5
        config.save_settings(data)
        try:
            self.assertEqual(daemon.menage_check(), ["repriceo:bis-69-adr-architecture"])
        finally:
            data["general"]["fermeture_auto_min"] = 60
            config.save_settings(data)

    def test_reboot_resumes_only_working_agents_and_tells_chef(self):
        from jarvis import cli, poste
        wt = TMP / "p" / "repriceo__worktrees" / "bis-71-guardrails-couts"
        wt.mkdir(parents=True, exist_ok=True)
        set_status(**{"bis-71-guardrails-couts": "working", "bis-69-adr-architecture": "done",
                      "jp-12-onboarding": "done"})
        daemon.watch_once(first=True)  # le démon mémorise les agents au travail
        snap = store.read_json(poste.SNAPSHOT, {})
        self.assertEqual([a["worktree"] for a in snap["agents"]], ["bis-71-guardrails-couts"])
        # tmux arrêté volontairement (même démarrage de Linux) : on ne relance rien.
        self.assertIsNone(poste.preparer_reprise())
        # Vrai redémarrage : l'identifiant de démarrage a changé.
        snap["boot"] = "demarrage-precedent"
        store.write_json(poste.SNAPSHOT, snap)
        self.assertIsNotNone(poste.preparer_reprise())
        self.assertFalse(store.state_path(poste.SNAPSHOT).exists())
        # Le chemin du fixture n'existe pas ici : on pointe vers le vrai dossier de test.
        rep = store.read_json(poste.REPRISE, {})
        rep["agents"][0]["workdir"] = str(wt)
        store.write_json(poste.REPRISE, rep)
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        lignes = poste.reprendre()
        self.assertTrue(any(ln.startswith("repris : repriceo/bis-71") for ln in lignes), lignes)
        self.assertIn("open bis-71-guardrails-couts --continue -p [JARVIS] Le PC a redémarré", self.wm_log())
        self.assertNotIn("bis-69", self.wm_log())
        self.assertIsNone(poste.reprise_en_attente())
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["chef-message"])
        self.assertIn("IMPORTANT : Le PC a redémarré", out.getvalue())
        self.assertIn("repriceo/bis-71-guardrails-couts", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["chef-message"])
        self.assertNotIn("IMPORTANT", out.getvalue())  # dit une seule fois

    def test_old_snapshot_is_not_resumed(self):
        from jarvis import poste
        store.write_json(poste.SNAPSHOT, {"ts": time.time() - 3 * 86400, "chef": True,
                                          "agents": [{"project": "repriceo", "worktree": "x"}]})
        self.assertIsNone(poste.preparer_reprise())

    def test_heartbeat_wakes_idle_chef_then_backs_off(self):
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        self.set_claude(20)
        self.set_codex(20)
        old = agents.chef_idle_secs
        agents.chef_idle_secs = lambda: 3600
        try:
            self.assertTrue(daemon.battement_check())
            self.assertIn("[JARVIS battement]", self.chef_screen())
            self.assertFalse(daemon.battement_check())  # trop tôt
            st = store.read_json(daemon.BATTEMENT_STATE, {})
            self.assertEqual(st["intervalle"], 2 * 30 * 60)  # aucun plan proposé : on espace
            # Un plan en attente de l'humain : rien à faire pour le chef.
            st["dernier"] = 0
            store.write_json(daemon.BATTEMENT_STATE, st)
            plans.create("Attente", [plans.parse_item("repriceo:BIS-1:claude")])
            self.assertFalse(daemon.battement_check())
            store.write_json(plans.PLANS_FILE, {"seq": 0, "plans": []})
            # Capacité pleine : pas de réveil.
            set_status()
            data = config.settings()
            data["general"]["max_agents"] = 2
            config.save_settings(data)
            self.assertFalse(daemon.battement_check())
        finally:
            agents.chef_idle_secs = old
            data = config.settings()
            data["general"]["max_agents"] = 3
            config.save_settings(data)

    def test_health_checks_and_alerts(self):
        from jarvis import poste
        items = {i["cle"]: i for i in poste.checks(windows=False)}
        self.assertIn("memoire", items)
        self.assertEqual(items["disque"]["niveau"], "ok")
        data = config.settings()
        data["sante"]["disque_min_go"] = 10 ** 9  # seuil impossible : alerte garantie
        config.save_settings(data)
        try:
            self.assertIn("disque", daemon.sante_check())
            sent = [b["text"] for m, b in FakeTelegram.calls if m == "sendMessage"]
            self.assertTrue(any("Disque Linux" in t for t in sent))
            self.assertEqual(daemon.sante_check(), [])  # pas de répétition dans les 5 min
        finally:
            data["sante"]["disque_min_go"] = 10
            config.save_settings(data)

    def test_telegram_photo_reaches_chef(self):
        bot = Bot("123:ABC")
        daemon.handle_update(bot, "42", {"message": {
            "chat": {"id": 42}, "from": {"id": 42}, "caption": "Direction artistique du tableau de bord",
            "photo": [{"file_id": "petit", "file_size": 10, "width": 90, "height": 90},
                      {"file_id": "grand", "file_size": 999, "width": 1280, "height": 720}]}})
        self.assertIn(("getFile", {"file_id": "grand"}), FakeTelegram.calls)
        saved = list((TMP / "data" / "chef" / "boite").glob("*image.jpg"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), FakeTelegram.FILE)
        screen = self.chef_screen()
        self.assertIn("Fichier joint", screen)
        self.assertIn("Direction artistique du tableau de bord", screen)
        # Un inconnu ne peut rien déposer.
        FakeTelegram.calls.clear()
        daemon.handle_update(bot, "42", {"message": {"chat": {"id": 666}, "photo": [{"file_id": "x"}]}})
        self.assertNotIn("getFile", [m for m, _ in FakeTelegram.calls])

    def test_reparer_git_rebuilds_broken_remote_refs(self):
        from jarvis import poste
        base = TMP / "git-crash"
        origin = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        work = base / "travail"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=work,
                                      check=True, capture_output=True, text=True)
        g("commit", "-q", "--allow-empty", "-m", "init")
        g("push", "-q", "origin", "HEAD:refs/heads/bis-90-ops-jobs")
        g("fetch", "-q")
        ref = work / ".git" / "refs" / "remotes" / "origin" / "bis-90-ops-jobs"
        ref.write_text("0" * 40 + "\n")  # référence abîmée comme après le crash
        (work / ".git" / "objects" / "ab").mkdir(exist_ok=True)
        (work / ".git" / "objects" / "ab" / ("c" * 38)).write_bytes(b"")  # objet vide
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        ok, lignes = poste.reparer_git(work)
        self.assertTrue(ok, "\n".join(lignes))
        self.assertFalse((work / ".git" / "objects" / "ab" / ("c" * 38)).exists())
        self.assertIn("refs/remotes/origin/bis-90-ops-jobs", "\n".join(lignes))
        self.assertNotEqual(ref.read_text().strip(), "0" * 40)  # recréée par le fetch
        self.assertTrue(any((config.STATE_DIR / "sauvegardes").iterdir()))

    def test_codex_wrapper_approves_mcp_and_opens_git_dir(self):
        fake = TMP / "bin" / "codex"
        fake.write_text('#!/bin/sh\nfor a in "$@"; do echo "$a"; done\n')
        fake.chmod(0o755)
        try:
            (TMP / "codexhome").mkdir(exist_ok=True)
            (TMP / "codexhome" / "config.toml").write_text(
                '[mcp_servers.linear]\nurl = "https://mcp.linear.app/mcp"\n[mcp_servers.linear.env]\nX = "y"\n'
                '[mcp_servers.shell]\ncommand = "shell-mcp"\n')
            repo = TMP / "p" / "repriceo"
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                            "-m", "i"], cwd=repo, check=True)
            wt = TMP / "p" / "repriceo__worktrees" / "codex-essai"
            subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "codex-essai"], cwd=repo, check=True)
            out = subprocess.run([str(ROOT / "bin" / "jarvis-codex"), "prompt"], cwd=wt, capture_output=True,
                                 text=True, check=True).stdout.splitlines()
            self.assertIn('mcp_servers.linear.default_tools_approval_mode="approve"', out)
            # Seulement les serveurs choisis (linear), et pas la sous-table .env.
            self.assertEqual(sum("default_tools_approval_mode" in x for x in out), 1)
            roots = next(x for x in out if x.startswith("sandbox_workspace_write.writable_roots="))
            git = str((repo / ".git").resolve())
            self.assertIn(f'"{git}/objects"', roots)
            self.assertIn(f'"{git}/worktrees/codex-essai"', roots)
            self.assertNotIn(f'"{git}"', roots)  # jamais .git entier (hooks, config)
            self.assertEqual(out[-1], "prompt")
        finally:
            fake.unlink()
            (TMP / "codexhome" / "config.toml").unlink(missing_ok=True)

    def test_kind_is_guessed_from_window_when_workmux_omits_it(self):
        data = json.loads(json.dumps(FIXTURE))
        data["agents"][1]["agent_kind"] = ""
        data["agents"][1]["window_name"] = "wm-revue-sans-type"
        Path(os.environ["FAKE_WORKMUX_STATUS"]).write_text(json.dumps(data))
        tmux("new-window", "-d", "-t", "jtest", "-n", "wm-revue-sans-type", "sh -c 'exec -a codex cat'")
        time.sleep(0.3)
        try:
            found, _ = agents.status_all()
            a = next(x for x in found if x["window"] == "wm-revue-sans-type")
            # Selon la plateforme, tmux voit « codex » ou « cat » : on vérifie au moins l'absence d'erreur.
            self.assertIn(a["kind"], ("codex", ""))
        finally:
            tmux("kill-window", "-t", "jtest:wm-revue-sans-type")

    # === Usine : rôles, routeur, registre, studio, interfaces ==========================================

    def verifier_modeles(self, sauf=()):
        """Marque les modèles du catalogue comme essayés avec succès (sauf ceux listés)."""
        from jarvis import modeles
        data = {n: {"ok": n not in sauf, "id": m["id"], "ts": time.time(), "detail": "essai"}
                for n, m in modeles.catalogue().items() if m["id"]}
        data["_derniere"] = {"ts": time.time()}
        store.write_json(modeles.VERIF_FILE, data)

    def fiche(self, **k):
        from jarvis import taches
        base = dict(projet="repriceo", issue="BIS-1", agent="claude", worktree="bis-1", role="backend", modele="opus",
                    modele_id="opus", effort="high")
        base.update(k)
        return taches.enregistrer(**base)

    # --- rôles et éléments de plan ---------------------------------------------------------
    def test_roles_are_loaded_and_grouped_by_team(self):
        from jarvis import roles
        tous = roles.tous()
        for nom in ("architecte", "backend", "frontend", "devops", "securite", "qa", "revue", "marketing", "video"):
            self.assertIn(nom, tous)
            self.assertTrue(tous[nom]["corps"], nom)
            self.assertEqual(len(tous[nom]["sigle"]), len(tous[nom]["sigle"].strip()))
        equipes = [eq for eq, _ in roles.par_equipe()]
        self.assertEqual(equipes[:3], ["Conception", "Fabrication", "Exploitation"])
        self.assertEqual(roles.ou_defaut("inconnu")["nom"], "generaliste")
        # Un rôle personnel remplace celui du dépôt sans toucher au code.
        perso = TMP / "cfg" / "roles"
        perso.mkdir(parents=True, exist_ok=True)
        (perso / "devops.md").write_text("---\ntitre: SRE maison\nequipe: Exploitation\nniveau: 4\n---\nBrief maison")
        try:
            self.assertEqual(roles.get("devops")["titre"], "SRE maison")
            self.assertEqual(roles.get("devops")["niveau"], 4)
        finally:
            (perso / "devops.md").unlink()
        self.assertEqual(roles.get("devops")["titre"], "Ingénieur DevOps")

    def test_plan_item_accepts_role_model_and_size(self):
        it = plans.parse_item("repriceo:bis-82:auto/fable@architecte+l:ADR sessions : v2")
        self.assertEqual((it["issue"], it["agent"], it["modele"], it["role"], it["taille"], it["desc"]),
                         ("BIS-82", "auto", "fable", "architecte", "L", "ADR sessions : v2"))
        ancien = plans.parse_item("repriceo:BIS-1:codex:garde-fous")
        self.assertEqual((ancien["agent"], ancien["role"], ancien["taille"]), ("codex", "", "M"))
        for bad in ("repriceo:BIS-1:auto+XL", "repriceo:BIS-1:auto@Front End", "repriceo:BIS-1:auto/"):
            with self.assertRaises(plans.PlanError, msg=bad):
                plans.parse_item(bad)

    # --- routeur ---------------------------------------------------------------------------
    def test_router_only_uses_models_proven_with_the_subscription(self):
        from jarvis import modeles
        choix = modeles.choisir("architecte", "L", usage_resume={})
        self.assertEqual(choix["modele_id"], "")  # rien d'essayé : modèle par défaut du CLI, toujours valide
        self.verifier_modeles()
        choix = modeles.choisir("architecte", "L", usage_resume={})
        self.assertEqual((choix["agent"], choix["modele"], choix["effort"]), ("claude", "fable", "xhigh"))
        self.assertIn("architecte", choix["raison"])
        self.assertEqual(choix["secours"]["agent"], "codex")
        # Le modèle le plus fort devient indisponible : le routeur l'ignore.
        self.verifier_modeles(sauf=("fable",))
        self.assertNotEqual(modeles.choisir("architecte", "L", usage_resume={})["modele"], "fable")
        with self.assertRaises(modeles.RoutageError):
            modeles.choisir("architecte", modele="fable", usage_resume={})

    def test_router_follows_role_size_and_token_budget(self):
        from jarvis import modeles
        self.verifier_modeles()
        aise = {"niveau": "ok", "marge": 80.0, "semaine": {"used": 20.0}}
        tendu = {"niveau": "alerte", "marge": 12.0, "semaine": {"used": 40.0}}
        # Front-end de taille M : le modèle courant dont c'est l'atout, pas le plus puissant.
        c = modeles.choisir("frontend", "M", usage_resume={"claude": aise, "codex": aise})
        self.assertEqual((c["agent"], c["modele"], c["effort"]), ("claude", "sonnet", "medium"))
        # Petite retouche : effort réduit. Grosse tâche : modèle plus fort et effort relevé.
        self.assertEqual(modeles.choisir("frontend", "S", usage_resume={"claude": aise, "codex": aise})["effort"], "low")
        c = modeles.choisir("frontend", "L", usage_resume={"claude": aise, "codex": aise})
        self.assertEqual((c["modele"], c["effort"]), ("sol", "xhigh"))
        # Back-end : deux modèles forts à égalité, le moins coûteux l'emporte.
        self.assertEqual(modeles.choisir("backend", "M", usage_resume={"claude": aise, "codex": aise})["modele"], "sol")
        # Sécurité : Claude préféré… sauf quand Claude est en alerte et Codex à l'aise.
        self.assertEqual(modeles.choisir("securite", "M", usage_resume={"claude": aise, "codex": aise})["agent"], "claude")
        self.assertEqual(modeles.choisir("securite", "M", usage_resume={"claude": tendu, "codex": aise})["agent"], "codex")
        # Fournisseur épuisé : écarté, et pas proposé en secours.
        vide = {"niveau": "epuise", "marge": 0.0}
        c = modeles.choisir("securite", "M", usage_resume={"claude": vide, "codex": aise})
        self.assertEqual(c["agent"], "codex")
        self.assertIsNone(c["secours"])
        with self.assertRaises(modeles.RoutageError):
            modeles.choisir("backend", usage_resume={"claude": vide, "codex": vide})
        # Semaine très entamée : le modèle le plus coûteux est gardé pour les tâches L.
        semaine = {"niveau": "ok", "marge": 25.0, "semaine": {"used": 75.0}}
        self.assertNotEqual(modeles.choisir("architecte", "M", agent="claude", usage_resume={"claude": semaine})["modele"], "fable")
        self.assertEqual(modeles.choisir("architecte", "L", agent="claude", usage_resume={"claude": semaine})["modele"], "fable")
        # Contre-relecture : toujours l'autre fournisseur que l'auteur.
        self.assertEqual(modeles.choisir("revue", auteur="codex", usage_resume={})["agent"], "claude")
        self.assertEqual(modeles.choisir("revue", auteur="claude", usage_resume={})["agent"], "codex")
        for args in ({"role_nom": "plombier"}, {"taille": "XL"}, {"agent": "gemini"}, {"modele": "inconnu"},
                     {"agent": "codex", "modele": "opus"}):
            with self.assertRaises(modeles.RoutageError, msg=str(args)):
                modeles.choisir(**{"usage_resume": {}, **args})

    def test_plan_routing_review_goes_to_the_other_provider(self):
        self.verifier_modeles()
        self.set_claude(20)
        self.set_codex(20)
        items = [plans.parse_item("repriceo:BIS-40:auto@revue:revue-pr-7"),   # la relecture est listée d'abord
                 plans.parse_item("repriceo:BIS-40:auto@backend+M:api")]
        plans.resoudre(items)
        revue, prod = items
        self.assertNotEqual(revue["agent"], prod["agent"])
        self.assertEqual(revue["role"], "revue")
        self.assertIsNone(revue["secours"])  # le secours d'une relecture serait l'auteur lui-même
        texte = plans.format_plan(plans.create("Routage", items))
        self.assertIn("Développeur back-end", texte)
        self.assertIn("secours si", texte)
        with self.assertRaises(plans.PlanError):  # deux fois la même issue pour le même agent
            plans.resoudre([plans.parse_item("repriceo:BIS-41:codex@backend"), plans.parse_item("repriceo:BIS-41:codex@qa")])
        with self.assertRaises(plans.PlanError):
            plans.resoudre([plans.parse_item("repriceo:BIS-42:auto@plombier")])

    def test_plan_cli_shows_the_exact_assignment_to_the_human(self):
        from jarvis import cli
        self.verifier_modeles()
        self.set_claude(10)
        self.set_codex(10)
        self.assertEqual(cli.main(["plan", "nouveau", "--titre", "Usine", "--item", "repriceo:BIS-50:auto@devops+M:ci",
                                   "--item", "repriceo:BIS-51:auto@architecte+L:adr"]), 0)
        p = plans.all_plans()[-1]
        self.assertEqual([i["role"] for i in p["items"]], ["devops", "architecte"])
        self.assertTrue(all(i["modele"] and i["raison"] for i in p["items"]))
        envoye = next(b for m, b in reversed(FakeTelegram.calls) if m == "sendMessage")["text"]
        self.assertIn("Ingénieur DevOps", envoye)
        self.assertIn("Architecte logiciel", envoye)

    # --- lancement : rôle, modèle, registre, lanceurs ---------------------------------------
    def test_task_launches_the_approved_specialist_with_its_model(self):
        from jarvis import taches
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        self.verifier_modeles()
        self.set_claude(10)
        self.set_codex(10)
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        items = [plans.parse_item("repriceo:BIS-60:auto@devops+M:pipeline")]
        plans.resoudre(items)
        p = plans.create("Usine", items)
        plans.decide(p["id"], True, par="test")
        prevu = plans.get(p["id"])["items"][0]
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-60", "auto", "pipeline",
                              "--role", "video")  # ignoré : le plan fait foi
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("le plan approuvé fait foi", res.stdout + res.stderr)
        add = next(ln.split() for ln in Path(os.environ["FAKE_WORKMUX_LOG"]).read_text().splitlines() if ln.startswith("add "))
        self.assertEqual(add[1], "bis-60-pipeline")
        self.assertEqual(add[add.index("-a") + 1], {"claude": "cc", "codex": "cx"}[prevu["agent"]])
        prompt = Path(add[-1]).read_text()
        self.assertIn("Ingénieur DevOps", prompt)
        self.assertIn("Scripts idempotents", prompt)          # le brief du rôle
        self.assertIn("livrables/repriceo/BIS-60", prompt)    # son dossier de livrables
        t = taches.toutes()[-1]
        self.assertEqual((t["issue"], t["role"], t["agent"], t["modele"], t["plan"], t["statut"]),
                         ("BIS-60", "devops", prevu["agent"], prevu["modele"], p["id"], "lancee"))
        self.assertTrue(t["chemin"].endswith("repriceo__worktrees/bis-60-pipeline"))
        # Le lanceur retrouve le modèle depuis le dossier du worktree (et ses sous-dossiers).
        wt = Path(t["chemin"]) / "src"
        wt.mkdir(parents=True)
        out = subprocess.run([sys.executable, "-m", "jarvis", "lancement-args", prevu["agent"]], cwd=wt,
                             capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "lib"))).stdout
        self.assertIn(f"arg\t{prevu['modele_id']}", out)
        self.assertIn("env\tJARVIS_METIER=devops", out)
        # Une tâche déjà lancée ne repart pas.
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-60", "auto")
        self.assertNotEqual(res.returncode, 0)

    def test_failed_launch_frees_the_plan_item_and_the_ledger(self):
        from jarvis import taches
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        p = plans.create("Échec", plans.resoudre([plans.parse_item("repriceo:BIS-61:claude@backend")]))
        plans.decide(p["id"], True, par="test")
        casse = TMP / "casse"
        casse.mkdir(exist_ok=True)
        (casse / "workmux").write_text('#!/bin/sh\n[ "$1" = add ] && exit 1\nexec "%s" "$@"\n' % (ROOT / "tests/fake-bin/workmux"))
        (casse / "workmux").chmod(0o755)
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-61", "claude",
                              env_extra={"PATH": f"{casse}:{os.environ['PATH']}"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("workmux add a échoué", res.stderr)
        self.assertFalse(plans.get(p["id"])["items"][0]["lance"])   # relançable
        self.assertEqual(taches.toutes(), [])                        # aucune fiche fantôme

    def test_exhausted_provider_falls_back_to_the_approved_backup(self):
        from jarvis import taches
        set_status(**{a["worktree"]: "done" for a in FIXTURE["agents"]})
        self.verifier_modeles()
        self.set_claude(10)
        self.set_codex(10)
        items = plans.resoudre([plans.parse_item("repriceo:BIS-62:claude@backend+M:api")])
        self.assertEqual(items[0]["secours"]["agent"], "codex")
        p = plans.create("Secours", items)
        plans.decide(p["id"], True, par="test")
        # Tant que Claude a des jetons, le secours est refusé : il ne sert pas à changer d'avis.
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-62", "codex")
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("ne sert que si claude est épuisé", res.stderr)
        self.set_claude(99)
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-62", "claude")
        self.assertEqual(res.returncode, 5, res.stderr)
        self.assertIn("secours", res.stderr)
        res = self.run_jarvis("task", "--plan", p["id"], "--projet", "repriceo", "BIS-62", "auto", "api")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("secours", res.stdout + res.stderr)
        t = taches.toutes()[-1]
        self.assertEqual((t["agent"], t["secours"]), ("codex", True))
        self.assertEqual(plans.get(p["id"])["items"][0]["lance_par"], "codex")
        # Les deux épuisés : rien ne part.
        p2 = plans.create("Secours 2", plans.resoudre([plans.parse_item("repriceo:BIS-63:claude@backend")]))
        plans.decide(p2["id"], True, par="test")
        self.set_codex(99)
        res = self.run_jarvis("task", "--plan", p2["id"], "--projet", "repriceo", "BIS-63", "auto")
        self.assertEqual(res.returncode, 5, res.stderr)

    def test_claude_launcher_applies_model_fallbacks_effort_and_env(self):
        wt = TMP / "p" / "repriceo__worktrees" / "bis-70-adr"
        wt.mkdir(parents=True, exist_ok=True)
        self.verifier_modeles()
        self.fiche(issue="BIS-70", worktree="bis-70-adr", chemin=str(wt), role="architecte", modele="fable",
                   modele_id="fable", effort="xhigh", repli="opus,sonnet")
        out = subprocess.run([str(ROOT / "bin" / "jarvis-claude"), "--", "le prompt"], cwd=wt, capture_output=True,
                             text=True, check=True).stdout.splitlines()
        self.assertEqual(out[:8], ["--permission-mode", "auto", "--model", "fable", "--fallback-model", "opus,sonnet",
                                   "--effort", "xhigh"])
        self.assertEqual(out[8:10], ["--", "le prompt"])
        self.assertIn("JARVIS_METIER=architecte", out)
        self.assertIn(f"JARVIS_LIVRABLES={TMP / 'data' / 'livrables' / 'repriceo' / 'BIS-70'}", out)
        # Modèle devenu indisponible depuis la validation : l'agent démarre avec le modèle par défaut.
        self.verifier_modeles(sauf=("fable",))
        out = subprocess.run([str(ROOT / "bin" / "jarvis-claude"), "x"], cwd=wt, capture_output=True, text=True,
                             check=True).stdout.splitlines()
        self.assertNotIn("--model", out)
        self.assertIn("--effort", out)
        # Hors registre (dossier lancé à la main) : aucun réglage imposé.
        ailleurs = TMP / "ailleurs"
        ailleurs.mkdir(exist_ok=True)
        out = subprocess.run([str(ROOT / "bin" / "jarvis-claude"), "x"], cwd=ailleurs, capture_output=True, text=True,
                             check=True).stdout.splitlines()
        self.assertEqual(out[:3], ["--permission-mode", "auto", "x"])

    def test_codex_launcher_applies_model_effort_and_opens_deliverables(self):
        repo = TMP / "p" / "jobpilot-ia"
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
                       cwd=repo, check=True)
        wt = TMP / "p" / "jobpilot-ia__worktrees" / "jp-30-front"
        if not wt.exists():
            subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "jp-30-front"], cwd=repo, check=True)
        self.verifier_modeles()
        self.fiche(projet="jobpilot-ia", issue="JP-30", agent="codex", worktree="jp-30-front", chemin=str(wt),
                   role="frontend", modele="sol", modele_id="gpt-6.1-sol", effort="high")
        out = subprocess.run([str(ROOT / "bin" / "jarvis-codex"), "prompt"], cwd=wt, capture_output=True, text=True,
                             check=True).stdout.splitlines()
        self.assertEqual(out[out.index("--model") + 1], "gpt-6.1-sol")
        self.assertIn('model_reasoning_effort="high"', out)
        roots = next(x for x in out if x.startswith("sandbox_workspace_write.writable_roots="))
        self.assertIn(f'"{TMP / "data" / "livrables" / "jobpilot-ia" / "JP-30"}"', roots)
        self.assertEqual(out[-1], "prompt")

    # --- catalogue : essai des modèles et propositions du chef ----------------------------------
    def test_model_verification_separates_missing_from_unknown(self):
        from jarvis import modeles
        env = {"FAKE_MODELES_KO": "fable,gpt-6-astra", "FAKE_MODELES_FLOU": "sonnet"}
        with mock.patch.dict(os.environ, env):
            res = modeles.verifier()
        self.assertIs(res["opus"]["ok"], True)
        self.assertIs(res["fable"]["ok"], False)
        self.assertIs(res["astra"]["ok"], False)
        self.assertIsNone(res["sonnet"]["ok"])          # limite atteinte : on ne conclut rien sur le modèle
        etat = modeles.etat_verif()
        self.assertNotIn("sonnet", etat)
        self.assertFalse(modeles.utilisable(modeles.catalogue()["fable"]))
        self.assertTrue(modeles.utilisable(modeles.catalogue()["sol"]))
        self.assertTrue(modeles.utilisable(modeles.catalogue()["claude-defaut"]))
        self.assertEqual(modeles.a_verifier(), [])       # vient d'être fait ; sonnet attend son heure
        self.assertIn("indisponible", modeles.texte())
        # Le modèle resté sans réponse est réessayé seul, de moins en moins souvent : jamais tout le catalogue.
        self.assertEqual(modeles.a_verifier(time.time() + 3700), ["sonnet"])
        Path(os.environ["FAKE_CLI_LOG"]).write_text("")
        with mock.patch.dict(os.environ, {"FAKE_MODELES_FLOU": "sonnet"}):
            modeles.verifier(["sonnet"])
        self.assertEqual(Path(os.environ["FAKE_CLI_LOG"]).read_text().split(), ["sonnet"])
        self.assertEqual(modeles.a_verifier(time.time() + 3700), [])            # deuxième échec : deux heures
        self.assertEqual(modeles.a_verifier(time.time() + 7300), ["sonnet"])
        modeles.verifier(["sonnet"])                                              # enfin une réponse
        self.assertTrue(modeles.utilisable(modeles.catalogue()["sonnet"]))
        self.assertNotIn("sonnet", modeles.etat_verif().get("_essais", {}))
        tous = sorted(m["nom"] for m in modeles.catalogue().values() if m["id"])
        self.assertEqual(sorted(modeles.a_verifier(time.time() + 8 * 86400)), tous)   # essai complet hebdomadaire
        # Abonnement épuisé : l'essai est reporté, l'état précédent est conservé.
        Path(os.environ["FAKE_CLI_LOG"]).write_text("")
        res = modeles.verifier(["opus"], {"claude": {"niveau": "epuise"}})
        self.assertIsNone(res["opus"]["ok"])
        self.assertEqual(Path(os.environ["FAKE_CLI_LOG"]).read_text(), "")
        self.assertTrue(modeles.utilisable(modeles.catalogue()["opus"]))

    def test_chef_proposes_catalogue_changes_and_only_the_human_applies_them(self):
        from jarvis import cli, modeles
        self.assertNotEqual(cli.main(["modele", "proposer", "nova", "--fournisseur", "codex", "--id", "gpt-7-nova",
                                      "--source", "pas-une-url", "--pourquoi", "x"]), 0)   # source exigée
        self.assertNotEqual(cli.main(["modele", "proposer", "nova", "--fournisseur", "codex", "--atouts", "plombier",
                                      "--source", "https://exemple.org", "--pourquoi", "x"]), 0)
        self.assertEqual(cli.main(["modele", "proposer", "nova", "--fournisseur", "codex", "--id", "gpt-7-nova",
                                   "--niveau", "4", "--cout", "4", "--effort", "high", "--atouts", "backend,frontend",
                                   "--source", "https://exemple.org/modeles", "--pourquoi", "Nouveau modèle fort"]), 0)
        prop = modeles.propositions()[-1]
        boutons = next(b for m, b in reversed(FakeTelegram.calls) if m == "sendMessage")["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(boutons[0]["callback_data"], f"mok:{prop['id']}")
        res = self.run_jarvis("modele", "ok", prop["id"])                # un agent ne peut pas l'appliquer
        self.assertEqual(res.returncode, 4, res.stderr)
        self.assertNotIn("nova", modeles.catalogue())
        daemon.handle_update(Bot("123:ABC"), "42", {"callback_query": {
            "id": "cbm", "data": f"mok:{prop['id']}", "from": {"id": 42}, "message": {"message_id": 5, "chat": {"id": 42}, "text": "x"}}})
        nova = modeles.catalogue()["nova"]
        self.assertEqual((nova["id"], nova["niveau"], nova["atouts"]), ("gpt-7-nova", 4, ["backend", "frontend"]))
        self.assertFalse(modeles.utilisable(nova))        # accepté, mais pas encore essayé
        self.assertTrue(modeles.verification_due())
        self.assertIn(f"Proposition {prop['id']} ACCEPTÉE", self.chef_screen())
        with self.assertRaises(modeles.RoutageError):
            modeles.decider(prop["id"], True, par="test")  # déjà décidée
        # Retrait d'un modèle : il sort du routage.
        retrait = modeles.proposer("luna", {"actif": False}, "retiré par l'éditeur", "https://exemple.org/retraits")
        modeles.decider(retrait["id"], True, par="test")
        self.assertFalse(modeles.catalogue()["luna"]["actif"])

    # --- registre, jetons par tâche, porte qualité ----------------------------------------------
    def test_ledger_follows_agents_and_tells_chef_what_the_role_requires(self):
        from jarvis import taches
        self.fiche(projet="repriceo", issue="BIS-69", agent="claude", worktree="bis-69-adr-architecture", role="architecte",
                   modele="fable", modele_id="fable")
        self.fiche(projet="jobpilot-ia", issue="JP-12", agent="claude", worktree="jp-12-onboarding", role="video")
        set_status(**{"bis-69-adr-architecture": "working", "jp-12-onboarding": "working"})
        daemon.watch_once(first=True)
        self.assertEqual({t["statut"] for t in taches.toutes()}, {"en_cours"})
        set_status(**{"bis-69-adr-architecture": "done", "jp-12-onboarding": "done"})
        events = " | ".join(e["texte"] for e in daemon.watch_once())
        self.assertIn("Architecte logiciel", events)
        self.assertIn("Claude · fable", events)
        par_issue = {t["issue"]: t for t in taches.toutes()}
        self.assertEqual(par_issue["BIS-69"]["statut"], "terminee")
        self.assertIsNotNone(par_issue["BIS-69"]["fin"])
        screen = " ".join(self.chef_screen().split())
        self.assertIn("contre-relecture par codex", screen)             # produit par Claude → relu par Codex
        self.assertIn("jarvis livrer", screen)                           # rôle à livrables : contrôle puis envoi
        # Le verdict de la relecture est enregistré sur la tâche de production.
        self.assertEqual(self.run_jarvis("verdict", "repriceo", "BIS-69", "corrections", "tests", "manquants").returncode, 0)
        self.assertEqual(taches.pour_agent("repriceo", "bis-69-adr-architecture")["verdict"], "corrections")
        self.assertNotEqual(self.run_jarvis("verdict", "repriceo", "BIS-404", "pret").returncode, 0)
        b = taches.bilan()
        self.assertEqual(b["fournisseurs"]["claude"]["terminees"], 2)
        self.assertEqual([t["issue"] for t in b["a_relire"]], ["JP-12"])   # terminée, pas encore relue
        self.assertIn("SANS CONTRE-RELECTURE", taches.texte_bilan(b))

    def test_ledger_tolerates_a_brief_absence_but_flags_a_lost_agent(self):
        from jarvis import taches
        f = self.fiche(worktree="bis-5-x")
        en_cours = [{"project": "repriceo", "worktree": "bis-5-x", "status": "working"}]
        taches.synchroniser(en_cours, now=1000)
        self.assertEqual(taches.synchroniser([], now=1030), [])          # workmux a répondu à moitié
        self.assertEqual(taches.toutes()[-1]["statut"], "en_cours")
        taches.synchroniser(en_cours, now=1060)
        self.assertNotIn("absent", taches.toutes()[-1])
        taches.synchroniser([], now=2000)
        perdues = taches.synchroniser([], now=2000 + taches.ABSENCE_MAX)
        self.assertEqual([t["id"] for t in perdues], [f["id"]])
        self.assertEqual(taches.toutes()[-1]["statut"], "perdue")
        taches.reouvrir("repriceo", "bis-5-x")                           # reprise après redémarrage
        self.assertEqual(taches.toutes()[-1]["statut"], "en_cours")

    def test_tokens_are_measured_per_task_for_both_providers(self):
        from jarvis import usage
        wt = "/home/x/projets/repriceo__worktrees/bis-9.api"
        d = TMP / "claudecfg" / "projects" / "-home-x-projets-repriceo--worktrees-bis-9-api"
        d.mkdir(parents=True, exist_ok=True)
        ligne = lambda mid, rid, i, o, cr, cw: json.dumps({"type": "assistant", "requestId": rid, "message": {
            "id": mid, "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
                                 "cache_creation_input_tokens": cw}}})
        (d / "s1.jsonl").write_text("\n".join([
            json.dumps({"type": "user", "message": {"content": "bonjour"}}),
            ligne("m1", "r1", 100, 50, 1000, 200), ligne("m1", "r1", 100, 50, 1000, 200),   # même message, écrit deux fois
            ligne("m2", "r2", 10, 5, 0, 0), "ligne abîmée {"]) + "\n")
        j = usage.claude_task_tokens(wt)
        self.assertEqual((j["entree"], j["sortie"], j["cache_lecture"], j["cache_ecriture"], j["total"]),
                         (110, 55, 1000, 200, 365))
        self.assertIsNone(usage.claude_task_tokens("/nulle/part"))
        jour = TMP / "codexhome" / "sessions" / time.strftime("%Y/%m/%d")
        jour.mkdir(parents=True, exist_ok=True)
        compte = lambda tot: json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": tot, "cached_input_tokens": tot // 2, "output_tokens": 40}}}})
        (jour / "rollout-a.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"cwd": wt}}) + "\n"
                                              + compte(100) + "\n" + compte(300) + "\n")
        (jour / "rollout-b.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"cwd": "/autre"}}) + "\n"
                                              + compte(9999) + "\n")
        j = usage.codex_task_tokens(wt)
        self.assertEqual((j["entree"], j["cache_lecture"], j["sortie"], j["total"]), (150, 150, 40, 190))
        self.assertEqual(usage.task_tokens({"agent": "codex", "chemin": wt, "cree": 0})["total"], 190)

    # --- jetons : prévision ------------------------------------------------------------------
    def test_burn_rate_forecast_warns_before_exhaustion(self):
        from jarvis import usage
        now = time.time()
        reset = int(now) + 2 * 3600
        store.write_json(usage.CLAUDE_FILE, {"ts": now, "five_hour": {"used_percentage": 80, "resets_at": reset}})
        # +30 points en 30 minutes : 60 %/h, seuil d'arrêt (95 %) dans 15 minutes, bien avant la remise à zéro.
        store.write_json(usage.HIST_FILE, {"claude": [[now - 1800, 50, reset], [now - 900, 65, reset]]})
        prev = usage.summary(now)["claude"]["prevision"]
        self.assertAlmostEqual(prev["rythme"], 60, delta=1)
        self.assertAlmostEqual(prev["minutes"], 15, delta=1)
        self.assertTrue(prev["avant_reset"])
        self.assertIn("avant la remise à zéro", usage.text())
        self.assertIn("Claude prévision", daemon.prevision_check(now))
        self.assertIn("[JARVIS jetons] Au rythme actuel", self.chef_screen())
        self.assertEqual(daemon.prevision_check(now + 60), [])        # une seule alerte par fenêtre
        # Fenêtre remise à zéro entre-temps : l'ancien rythme ne vaut plus rien.
        store.write_json(usage.CLAUDE_FILE, {"ts": now, "five_hour": {"used_percentage": 5, "resets_at": reset + 18000}})
        self.assertIsNone(usage.summary(now)["claude"]["prevision"])
        # Rythme lent : pas d'alerte.
        store.write_json(usage.CLAUDE_FILE, {"ts": now, "five_hour": {"used_percentage": 52, "resets_at": reset}})
        store.write_json(usage.HIST_FILE, {"claude": [[now - 1800, 50, reset]]})
        self.assertFalse(usage.summary(now)["claude"]["prevision"]["avant_reset"])

    # --- appareil : capacité, batterie, chiens de garde ---------------------------------------
    def test_capacity_follows_memory_and_battery(self):
        from jarvis import poste
        data = config.settings()
        data["sante"]["capacite_auto"] = True
        config.save_settings(data)
        try:
            go = 1048576
            with mock.patch.object(poste, "_meminfo", return_value={"MemTotal": 16 * go, "MemAvailable": 12 * go}), \
                    mock.patch.object(os, "getloadavg", return_value=(0.1, 0.1, 0.1)):
                self.assertEqual(poste.capacite(0)["max"], 3)                      # large : le plafond reste max_agents
                store.write_json(poste.WIN_CACHE, {"ts": time.time(), "info": {"batterie": 18, "secteur": False}})
                cap = poste.capacite(1)
                self.assertEqual(cap["max"], 1)                                    # batterie faible : personne de plus
                self.assertIn("batterie", cap["raisons"][0])
                store.write_json(poste.WIN_CACHE, {"ts": time.time(), "info": {"batterie": 18, "secteur": True}})
                self.assertEqual(poste.capacite(1)["max"], 3)
            with mock.patch.object(poste, "_meminfo", return_value={"MemTotal": 8 * go, "MemAvailable": int(2.8 * go)}), \
                    mock.patch.object(os, "getloadavg", return_value=(0.1, 0.1, 0.1)):
                cap = poste.capacite(1)
                self.assertEqual(cap["max"], 2)                                    # 2,8 Go libres : une place, pas deux
                self.assertIn("mémoire", cap["raisons"][0])
                self.assertEqual(poste.capacite(3)["max"], 3)                      # on n'arrête jamais un agent en cours
        finally:
            data["sante"]["capacite_auto"] = False
            config.save_settings(data)
            store.state_path(poste.WIN_CACHE).unlink(missing_ok=True)

    def test_critical_battery_saves_work_then_resumes_when_plugged(self):
        from jarvis import poste
        set_status()  # jp-12-onboarding travaille
        Path(os.environ["FAKE_WORKMUX_LOG"]).write_text("")
        store.state_path(daemon.BATTERIE_STATE).unlink(missing_ok=True)
        store.write_json(poste.WIN_CACHE, {"ts": time.time(), "info": {"batterie": 9, "secteur": False}})
        self.assertEqual(daemon.batterie_check(), ["batterie"])
        self.assertTrue(store.paused())
        self.assertIn("send jobpilot-ia:jp-12-onboarding [JARVIS] La batterie", Path(os.environ["FAKE_WORKMUX_LOG"]).read_text())
        self.assertEqual(daemon.batterie_check(), [])                              # une seule fois
        store.write_json(poste.WIN_CACHE, {"ts": time.time(), "info": {"batterie": 14, "secteur": True}})
        self.assertEqual(daemon.batterie_check(), ["batterie rétablie"])
        self.assertFalse(store.paused())
        # Sur batterie, une mesure de plus de deux minutes est relue (PowerShell) : jamais un vieux chiffre.
        store.write_json(poste.WIN_CACHE, {"ts": time.time() - 200, "info": {"batterie": 40, "secteur": False}})
        with mock.patch("shutil.which", return_value="/faux/powershell.exe"), mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(stdout='{"batterie": 8, "secteur": false, "redemarrage": false}', returncode=0)
            self.assertEqual(poste.batterie_critique(rafraichir=True), 8)
        self.assertEqual(poste.batterie()["pct"], 8)
        # Une mesure trop vieille ne restreint plus rien.
        store.write_json(poste.WIN_CACHE, {"ts": time.time() - 3600, "info": {"batterie": 5, "secteur": False}})
        self.assertIsNone(poste.batterie())
        store.state_path(poste.WIN_CACHE).unlink(missing_ok=True)

    def test_watchdog_reports_silent_and_endless_agents_once(self):
        set_status()  # jp-12-onboarding : « working » depuis 1830 s
        with mock.patch.object(agents, "window_idle", return_value={"wm-jp-12-onboarding": 50 * 60}):
            self.assertEqual(daemon.blocage_check(), ["jobpilot-ia:jp-12-onboarding"])
            self.assertIn("[JARVIS blocage]", self.chef_screen())
            self.assertEqual(daemon.blocage_check(), [])                           # déjà signalé
        with mock.patch.object(agents, "window_idle", return_value={"wm-jp-12-onboarding": 5}):
            self.assertEqual(daemon.blocage_check(), [])                           # il a repris : on oublie
        with mock.patch.object(agents, "window_idle", return_value={"wm-jp-12-onboarding": 50 * 60}):
            self.assertEqual(daemon.blocage_check(), ["jobpilot-ia:jp-12-onboarding"])  # nouveau silence, nouveau signal

    def test_chef_watchdog_restarts_only_when_work_remains(self):
        set_status()
        daemon._chef_vu = False
        occupe = mock.patch.object(agents, "status_all", return_value=([{"status": "working"}], ""))
        with mock.patch.object(agents, "chef_running", return_value=False), mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            # Ce démon n'a jamais vu le chef tourner (redémarrage du PC, « jarvis start » sans « jarvis chef ») :
            # même avec du travail en attente, il ne le lance pas à ta place.
            with occupe:
                self.assertIsNone(daemon.chef_check())
            run.assert_not_called()
        self.assertIsNone(daemon.chef_check())                                     # le chef tourne : c'est noté
        self.assertTrue(daemon._chef_vu)
        with mock.patch.object(agents, "chef_running", return_value=False), mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            with occupe:
                self.assertEqual(daemon.chef_check(), "relance")
            self.assertTrue(any("chef-lancer" in " ".join(map(str, c.args[0])) for c in run.call_args_list))
            # Trop de relances en une heure (compteur borné de l'admission) : on prévient l'humain au lieu d'insister.
            store.write_json(admission.RELANCES, {"chef": [time.time()] * 3})
            with occupe:
                self.assertEqual(daemon.chef_check(), "alerte")
            # Rien en cours : un chef arrêté est un arrêt normal, on ne relance pas et on l'oublie.
            run.reset_mock()
            with mock.patch.object(agents, "status_all", return_value=([], "")):
                self.assertIsNone(daemon.chef_check())
            run.assert_not_called()
            self.assertFalse(daemon._chef_vu)
        self.assertTrue(any(m == "sendMessage" and "chef est arrêté" in b.get("text", "") for m, b in FakeTelegram.calls))

    def test_a_chef_window_left_on_a_shell_is_not_a_chef(self):
        self.assertTrue(agents.chef_running())                 # fenêtre « chef » : un programme y tourne (cat)
        with mock.patch.object(config, "CHEF_WINDOW", "cockpit"):   # fenêtre où il ne reste qu'un shell
            self.assertFalse(agents.chef_running())
            self.assertFalse(agents.chef_inject("texte ; echo DANGER"))   # rien n'est tapé dans un shell
        with mock.patch.object(config, "CHEF_WINDOW", "absente"):
            self.assertFalse(agents.chef_running())
        self.assertNotIn("DANGER", tmux("capture-pane", "-p", "-t", "jtest:cockpit"))

    def test_daemon_heartbeat_is_visible_in_the_state(self):
        from jarvis import report
        self.assertFalse(report.demon_vivant())
        daemon.battement_demon()
        self.assertTrue(report.demon_vivant())
        self.assertFalse(report.demon_vivant(now=time.time() + 600))
        snap = report.snapshot()
        self.assertTrue(snap["demon"])
        self.assertNotIn("démon arrêté", report.text(snap))

    # --- studio et livrables ------------------------------------------------------------------
    def video(self, dest: Path, *, taille="1280x720", ips=30, duree=6, source="testsrc2", pix="yuv420p"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"{source}{':' if '=' in source else '='}size={taille}:rate={ips}:duration={duree}", "-f", "lavfi", "-i",
                        "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", pix,
                        "-c:a", "aac", "-movflags", "+faststart", str(dest)], check=True)
        return dest

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg requis")
    def test_studio_check_accepts_a_sound_video_and_explains_a_bad_one(self):
        from jarvis import studio
        bonne = self.video(TMP / "studio" / "bonne.mp4")
        r = studio.verifier(bonne)
        self.assertEqual(r["verdict"], "PRÊT", studio.texte(r))
        self.assertTrue(Path(r["planche"]).is_file())                    # la planche-contact à regarder
        self.assertEqual((r["infos"]["largeur"], r["infos"]["codec"]), (1280, "h264"))
        mauvaise = self.video(TMP / "studio" / "mauvaise.mp4", taille="640x360", ips=12, source="color=c=black", pix="yuv444p")
        r = studio.verifier(mauvaise)
        self.assertEqual(r["verdict"], "À CORRIGER")
        rates = {p["nom"] for p in r["points"] if not p["ok"] and p["bloquant"]}
        self.assertLessEqual({"définition", "fluidité", "compatibilité", "écran noir", "image figée"}, rates)
        self.assertEqual(studio.verifier(bonne, duree_min=20)["verdict"], "À CORRIGER")   # trop courte pour la commande
        self.assertEqual(studio.verifier(TMP / "studio" / "absente.mp4")["verdict"], "À CORRIGER")
        res = self.run_jarvis("studio", "verifier", str(mauvaise))
        self.assertEqual(res.returncode, 1)
        self.assertIn("À CORRIGER", res.stdout)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg requis")
    def test_delivery_checks_then_sends_to_the_owner_only(self):
        from jarvis import livrables
        d = livrables.dossier("repriceo", "BIS-80")
        bonne = self.video(d / "demo.mp4")
        chef = {"JARVIS_ROLE": "chef"}
        res = self.run_jarvis("livrer", str(bonne), "--titre", "Démo Repriceo", "--legende", "Première version", env_extra=chef)
        self.assertEqual(res.returncode, 0, res.stderr)
        methode, corps = next((m, b) for m, b in reversed(FakeTelegram.calls) if isinstance(b, dict) and b.get("multipart"))
        self.assertEqual(methode, "sendVideo")
        self.assertIn('name="chat_id"\r\n\r\n42', corps["brut"])          # ta conversation, et elle seule
        self.assertIn("Démo Repriceo", corps["brut"])
        self.assertIn('filename="demo.mp4"', corps["brut"])
        self.assertGreater(corps["octets"], bonne.stat().st_size)
        item = livrables.tous()[-1]
        self.assertEqual((item["id"], item["projet"], item["issue"], item["genre"], item["envoye"]),
                         ("L-0001", "repriceo", "BIS-80", "video", True))
        # Une vidéo ratée ne part pas ; « --forcer » est réservé à l'humain.
        mauvaise = self.video(d / "ratee.mp4", taille="640x360", ips=12, source="color=c=black")
        avant = len(FakeTelegram.calls)
        res = self.run_jarvis("livrer", str(mauvaise), env_extra=chef)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("rien n'a été envoyé", res.stderr)
        self.assertEqual(self.run_jarvis("livrer", str(mauvaise), "--forcer", env_extra=chef).returncode, 4)
        self.assertEqual(len(FakeTelegram.calls), avant)
        # Une vidéo tronquée (l'en-tête annonce 6 s, le fichier s'arrête avant) ne part pas non plus.
        tronquee = d / "tronquee.mp4"
        tronquee.write_bytes(bonne.read_bytes()[: bonne.stat().st_size // 2])
        res = self.run_jarvis("livrer", str(tronquee), env_extra=chef)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("intégrité", res.stderr)
        # Seuls les fichiers du dossier des livrables partent : ni un fichier du projet, ni un lien qui en sort.
        (TMP / "p" / "repriceo" / "secret.md").write_text("interne")
        self.assertIn("seuls les fichiers déposés", self.run_jarvis("livrer", str(TMP / "p/repriceo/secret.md"), env_extra=chef).stderr)
        (d / "lien.md").symlink_to(TMP / "p" / "repriceo" / "secret.md")
        self.assertNotEqual(self.run_jarvis("livrer", str(d / "lien.md"), env_extra=chef).returncode, 0)
        (d / ".env").write_text("X=1")
        self.assertIn("non livrable", self.run_jarvis("livrer", str(d / ".env"), env_extra=chef).stderr)
        # Un agent de l'usine ne livre pas lui-même : c'est le chef qui contrôle puis envoie.
        for env in ({"JARVIS_METIER": "video", "JARVIS_ROLE": "chef"}, {}):   # agent de l'usine ; agent lancé à la main
            res = self.run_jarvis("livrer", str(bonne), env_extra=env)
            self.assertEqual(res.returncode, 4)
            self.assertIn("revient au chef", res.stderr)
        self.assertEqual(len(FakeTelegram.calls), avant)
        # Un document : envoyé comme document.
        (d / "brief.md").write_text("# Brief\n")
        self.assertEqual(self.run_jarvis("livrer", str(d / "brief.md"), env_extra=chef).returncode, 0)
        self.assertEqual(next(m for m, b in reversed(FakeTelegram.calls) if isinstance(b, dict) and b.get("multipart")), "sendDocument")
        self.assertIn("L-0002", livrables.texte())
        self.assertEqual(self.run_jarvis("livrables", "repriceo", "BIS-80").stdout.strip(), str(d))
        res = self.run_jarvis("livrables", "repriceo", "../../../../ailleurs")       # jamais de dossier hors des livrables
        self.assertNotEqual(res.returncode, 0)
        self.assertFalse((TMP / "ailleurs" / "x").exists())
        # Telegram en panne : la fiche dit « non envoyé » ; le nouvel essai la met à jour, sans doublon.
        (d / "note.md").write_text("# Note\n")
        with mock.patch.dict(os.environ, {"JARVIS_TELEGRAM_API": "http://127.0.0.1:9"}):
            self.assertEqual(self.run_jarvis("livrer", str(d / "note.md"), env_extra=chef).returncode, 6)
        nb = len(livrables.tous())
        self.assertFalse(livrables.tous()[-1]["envoye"])
        self.assertEqual(self.run_jarvis("livrer", str(d / "note.md"), env_extra=chef).returncode, 0)
        self.assertEqual(len(livrables.tous()), nb)
        self.assertTrue(livrables.tous()[-1]["envoye"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg requis")
    def test_montage_assembles_trims_and_reformats(self):
        from jarvis import studio
        d = TMP / "montage"
        self.video(d / "a.mp4", duree=4)
        self.video(d / "b.mp4", taille="1000x1000", duree=5, source="smptebars")
        (d / "b.mp4.json").write_text(json.dumps({"debut_utile": 1.0}))     # film d'enregistrer.cjs : rogné tout seul
        (d / "m.json").write_text(json.dumps({"format": "9:16", "transition": 0.5, "segments": [
            {"fichier": "a.mp4", "fin": 3}, {"fichier": "b.mp4", "vitesse": 2}]}))
        script = ROOT / "skills" / "jarvis-studio" / "scripts" / "monter.py"
        res = subprocess.run([sys.executable, str(script), str(d / "m.json"), str(d / "sortie.mp4")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        infos = studio.sonder(d / "sortie.mp4")
        self.assertEqual((infos["largeur"], infos["hauteur"], infos["codec"], infos["audio"]), (1080, 1920, "h264", "aac"))
        self.assertAlmostEqual(infos["duree"], 3 + (5 - 1) / 2 - 0.5, delta=0.3)   # rognage, vitesse et fondu
        self.assertTrue(studio.faststart(d / "sortie.mp4"))
        (d / "vide.json").write_text(json.dumps({"segments": [{"fichier": "absent.mp4"}]}))
        res = subprocess.run([sys.executable, str(script), str(d / "vide.json"), str(d / "x.mp4")], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("introuvable", res.stderr)

    def test_studio_scenes_render_to_image_and_video(self):
        racine = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        if not (shutil.which("node") and shutil.which("ffmpeg") and racine and (Path(racine) / "playwright").is_dir()):
            self.skipTest("node, ffmpeg et Playwright requis")
        from jarvis import studio
        d = TMP / "scenes"
        d.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1600x1000:duration=1",
                        "-frames:v", "1", str(d / "capture.png")], check=True)
        (d / "sb.json").write_text(json.dumps({"marque": {"nom": "Démo <b>", "accent": "#22c55e"}, "scenes": [
            {"type": "titre", "duree": 1.5, "titre": "Un titre <script>alert(1)</script>", "sous_titre": "Sous-titre"},
            {"type": "capture", "duree": 2, "image": "capture.png", "titre": "Le produit", "reperes": [{"x": 20, "y": 80, "texte": "Ici"}]},
            {"type": "chiffre", "duree": 1.5, "valeur": 12.5, "suffixe": " %", "libelle": "mesuré"},
            {"type": "points", "duree": 1.5, "titre": "Pourquoi", "points": ["Un", "Deux"]},
            {"type": "fin", "duree": 1.5, "titre": "Fin", "bouton": "Essayer", "url": "exemple.app"}]}))
        script = ROOT / "skills" / "jarvis-studio" / "scripts" / "rendre.cjs"
        env = dict(os.environ, NODE_PATH=racine)
        res = subprocess.run(["node", str(script), str(d / "sb.json"), str(d / "carre.png"), "--image", "2.6", "--format", "1:1"],
                             capture_output=True, text=True, env=env)
        if "Chromium ne démarre pas" in res.stderr:
            self.skipTest("Chromium indisponible sur cette machine")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((studio.sonder(d / "carre.png")["largeur"], studio.sonder(d / "carre.png")["hauteur"]), (1080, 1080))
        res = subprocess.run(["node", str(script), str(d / "sb.json"), str(d / "video.mp4"), "--ips", "12", "--format", "9:16"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        r = studio.verifier(d / "video.mp4", fps_min=12)
        self.assertEqual(r["verdict"], "PRÊT", studio.texte(r))
        self.assertEqual((r["infos"]["largeur"], r["infos"]["hauteur"]), (1080, 1920))
        self.assertAlmostEqual(r["infos"]["duree"], 8, delta=0.4)
        # Un fichier manquant est dit clairement, avant tout rendu.
        (d / "ko.json").write_text(json.dumps({"scenes": [{"type": "capture", "image": "absente.png"}]}))
        res = subprocess.run(["node", str(script), str(d / "ko.json"), str(d / "ko.mp4")], capture_output=True, text=True, env=env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("absente.png", res.stderr)

    # --- interfaces : Telegram, web, cockpit ----------------------------------------------------
    def test_telegram_shows_the_factory_models_and_deliverables(self):
        self.fiche(projet="jobpilot-ia", issue="JP-12", agent="claude", worktree="jp-12-onboarding", role="frontend",
                   modele="sonnet", modele_id="sonnet", effort="medium")
        set_status()
        bot = Bot("123:ABC")
        for cmd in ("/usine", "/modeles", "/livrables", "/bilan", "/aide"):
            daemon.handle_update(bot, "42", {"message": {"text": cmd, "chat": {"id": 42}, "from": {"id": 42}}})
        textes = [b["text"] for m, b in FakeTelegram.calls if m == "sendMessage"]
        usine = next(t for t in textes if t.startswith("USINE"))
        self.assertIn("Développeur front-end", usine)
        self.assertIn("Claude · sonnet · medium", usine)
        self.assertIn("libres : ", usine)
        self.assertTrue(any("gpt-6.1-sol" in t for t in textes))
        self.assertTrue(any("Aucun livrable" in t for t in textes))
        self.assertTrue(any("/usine" in t for t in textes))

    def test_web_dashboard_is_read_only_and_answers_this_pc_only(self):
        from jarvis import livrables, web
        self.fiche(projet="jobpilot-ia", issue="JP-12", agent="claude", worktree="jp-12-onboarding", role="frontend",
                   modele="sonnet", modele_id="sonnet", effort="medium")
        set_status()
        d = livrables.dossier("repriceo", "BIS-81")
        (d / "note.md").write_text("0123456789")
        store.write_json(livrables.FILE, {"seq": 1, "items": [{"id": "L-0001", "projet": "repriceo", "issue": "BIS-81",
            "fichier": str(d / "note.md"), "titre": "Note", "genre": "document", "octets": 10, "ts": time.time(),
            "envoye": True, "erreur": "", "verdict": "PRÊT", "infos": {}, "planche": ""}]})
        httpd = web._serveur(0)
        port = httpd.server_port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(chemin, **entetes):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{chemin}", headers=entetes)
            try:
                with opener.open(req, timeout=10) as rep:
                    return rep.status, rep.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read()
        try:
            web._cache["ts"] = 0
            code, corps = get("/api/etat")
            self.assertEqual(code, 200)
            etat = json.loads(corps)
            agent = next(a for a in etat["agents"] if a["worktree"] == "jp-12-onboarding")
            self.assertEqual((agent["role"], agent["modele"], agent["fournisseur"]), ("frontend", "sonnet", "claude"))
            self.assertIn("Fabrication", [e["nom"] for e in etat["equipes"]])
            self.assertNotIn("123:ABC", corps.decode())                      # aucun secret dans la page
            self.assertEqual(get("/")[0], 200)
            self.assertEqual(get("/api/etat", Host="attaquant.exemple")[0], 403)   # pas de détournement par nom de domaine
            self.assertEqual(get("/livrable/L-0001", Range="bytes=2-5"), (206, b"2345"))
            self.assertEqual(get("/livrable/L-9999")[0], 404)
            self.assertEqual(get("/livrable/..%2f..%2fetc%2fpasswd")[0], 404)
            self.assertEqual(get("/n-importe-quoi")[0], 404)
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/etat", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:           # lecture seule : aucune action possible
                opener.open(req, timeout=10)
            self.assertEqual(ctx.exception.code, 501)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_cockpit_shows_each_specialist_at_its_station(self):
        from jarvis import cockpit
        self.verifier_modeles()
        self.fiche(projet="jobpilot-ia", issue="JP-12", agent="claude", worktree="jp-12-onboarding", role="frontend",
                   modele="sonnet", modele_id="sonnet", effort="medium")
        self.fiche(projet="repriceo", issue="BIS-71", agent="codex", worktree="bis-71-guardrails-couts", role="devops",
                   modele="sol", modele_id="gpt-6.1-sol", effort="high")
        set_status()
        plans.create("Vague cockpit", plans.resoudre([plans.parse_item("repriceo:BIS-99:auto@securite+L:audit")]))
        # Mise en ateliers : chaque équipe a sa ligne, les agents sont sous leur équipe, le reste hors registre.
        from jarvis import report
        rows = cockpit.ateliers(report.snapshot()["agents"])
        equipes = [r[1] for r in rows if r[0] == "equipe"]
        self.assertEqual(equipes[:2] + equipes[-1:], ["Conception", "Fabrication", "Hors registre"])
        fab = rows.index(("equipe", "Fabrication", next(r[2] for r in rows if r[:2] == ("equipe", "Fabrication"))))
        self.assertEqual(rows[fab + 1][1]["worktree"], "jp-12-onboarding")
        self.assertNotIn("FRT", rows[fab][2])                              # poste occupé : plus dans les « libres »
        self.assertEqual(cockpit.affectation(rows[fab + 1][1]), "Claude · sonnet · medium")
        # Rendu réel dans un terminal.
        tmux("new-window", "-d", "-t", "jtest", "-n", "essai-cockpit",
             f"env LC_ALL=C.UTF-8 LANG=C.UTF-8 {ROOT / 'bin' / 'jarvis'} cockpit")
        try:
            ecran = ""
            for _ in range(40):
                time.sleep(0.25)
                ecran = tmux("capture-pane", "-p", "-t", "jtest:essai-cockpit")
                if "ATELIERS" in ecran and "jp-12-onboarding" in ecran:
                    break
            self.assertIn("ATELIERS", ecran)
            ligne = next(ln for ln in ecran.splitlines() if "jp-12-onboarding" in ln)
            self.assertIn("FRT", ligne)
            self.assertIn("Front-end", ligne)
            self.assertIn("Claude · sonnet · medium", ligne)
            self.assertTrue(any("OPS" in ln and "bis-71-guardrails-couts" in ln for ln in ecran.splitlines()))
            self.assertIn("BIS-99", ecran)                                  # le plan à valider, avec son affectation
            self.assertIn("SEC", ecran)
            tmux("send-keys", "-t", "jtest:essai-cockpit", "d")
            time.sleep(0.8)
            fiche = tmux("capture-pane", "-p", "-t", "jtest:essai-cockpit")
            self.assertIn("FICHE DE LA TÂCHE", fiche)
            tmux("send-keys", "-t", "jtest:essai-cockpit", "v")
            time.sleep(0.8)
            self.assertIn("AGENTS", tmux("capture-pane", "-p", "-t", "jtest:essai-cockpit"))
        finally:
            tmux("kill-window", "-t", "jtest:essai-cockpit")

    def test_chef_may_propose_and_deliver_but_not_decide_or_force(self):
        from jarvis import cli
        cli.main(["chef-preparer"])
        perms = json.loads((TMP / "data" / "chef" / ".claude" / "settings.json").read_text())["permissions"]
        for regle in ("Bash(jarvis modele proposer *)", "Bash(jarvis livrer *)", "Bash(jarvis verdict *)", "Bash(jarvis usine)"):
            self.assertIn(regle, perms["allow"])
        for regle in ("Bash(jarvis modele ok *)", "Bash(jarvis modele non *)", "Bash(jarvis livrer * --forcer*)",
                      "Bash(jarvis tache-enregistrer *)", "Bash(jarvis chef-lancer)"):
            self.assertIn(regle, perms["deny"])

    # === Régressions trouvées en relecture ===========================================================

    def test_release_frees_the_launch_that_just_failed_not_its_sibling(self):
        # Même issue : production par Claude (en cours) et relecture par Codex, partie avec son secours Claude.
        prod = plans.parse_item("repriceo:BIS-20:claude@backend")
        revue = plans.parse_item("repriceo:BIS-20:codex@revue")
        revue["secours"] = {"agent": "claude", "modele": "claude-defaut", "modele_id": "", "effort": "", "repli": ""}
        p = plans.create("Deux éléments", [prod, revue])
        plans.decide(p["id"], True, par="test")
        plans.authorize_launch(p["id"], "repriceo", "BIS-20", "claude")
        time.sleep(0.01)
        lance = plans.authorize_launch(p["id"], "repriceo", "BIS-20", "claude", epuises={"codex"}, relecture=True)
        self.assertTrue(lance["par_secours"])
        plans.release(p["id"], "repriceo", "BIS-20", "claude")           # le lancement de la relecture a échoué
        items = plans.get(p["id"])["items"]
        self.assertTrue(items[0]["lance"])                               # la production, elle, tourne toujours
        self.assertFalse(items[1]["lance"])
        self.assertNotIn("lance_par", items[1])

    def test_backup_provider_is_never_confused_with_the_review_item(self):
        self.verifier_modeles()
        items = plans.resoudre([plans.parse_item("repriceo:BIS-21:claude@backend"),
                                plans.parse_item("repriceo:BIS-21:auto@revue")], usage_resume={})
        self.assertEqual((items[0]["secours"]["agent"], items[1]["agent"]), ("codex", "codex"))
        p = plans.create("Secours et relecture", items)
        plans.decide(p["id"], True, par="test")
        # Claude épuisé. « codex » sans --revue désigne la production (par son secours), pas la relecture.
        lance = plans.authorize_launch(p["id"], "repriceo", "BIS-21", "codex", epuises={"claude"})
        self.assertEqual((lance["role"], lance.get("par_secours")), ("backend", True))
        # Il ne reste que la relecture : « auto » la prend, et elle ne peut pas partir deux fois.
        self.assertEqual(plans.authorize_launch(p["id"], "repriceo", "BIS-21", "auto")["role"], "revue")
        with self.assertRaises(plans.PlanError):
            plans.authorize_launch(p["id"], "repriceo", "BIS-21", "auto")
        # Avec --revue, seule une relecture peut partir.
        p2 = plans.create("Relecture d'abord", plans.resoudre([plans.parse_item("repriceo:BIS-22:claude@backend"),
                                                              plans.parse_item("repriceo:BIS-22:codex@revue")], usage_resume={}))
        plans.decide(p2["id"], True, par="test")
        self.assertEqual(plans.authorize_launch(p2["id"], "repriceo", "BIS-22", "auto", relecture=True)["role"], "revue")
        with self.assertRaises(plans.PlanError):
            plans.authorize_launch(p2["id"], "repriceo", "BIS-22", "auto", relecture=True)
        self.assertEqual(plans.authorize_launch(p2["id"], "repriceo", "BIS-22", "auto")["role"], "backend")

    def test_only_the_legacy_review_spelling_becomes_a_review(self):
        self.verifier_modeles()
        roles = lambda *specs: [i["role"] for i in plans.resoudre([plans.parse_item(x) for x in specs], usage_resume={})]
        self.assertEqual(roles("repriceo:BIS-30:codex:revue-pr-12"), ["revue"])
        self.assertEqual(roles("repriceo:BIS-31:codex:revue"), ["revue"])
        self.assertEqual(roles("repriceo:BIS-32:codex:date-prevue-livraison", "repriceo:BIS-33:codex:revue-de-presse",
                               "repriceo:BIS-34:codex:page-entrevue"), ["generaliste"] * 3)

    def test_ledger_reopens_a_task_that_resumes_and_frees_one_that_never_started(self):
        from jarvis import taches
        f = self.fiche(worktree="bis-6-x")
        a = lambda st: [{"project": "repriceo", "worktree": "bis-6-x", "status": st}]
        taches.synchroniser(a("working"), now=1000)
        self.assertEqual(len(taches.synchroniser(a("done"), now=2000)), 1)
        self.assertEqual(taches.synchroniser(a("done"), now=2100), [])           # déjà close : rien de neuf
        taches.synchroniser(a("working"), now=3000)                               # consigne corrective : il reprend
        t = taches.toutes()[-1]
        self.assertEqual((t["statut"], t["fin"], t["debut"]), ("en_cours", None, 1000))
        closes = taches.synchroniser(a("done"), now=9000, jetons_fn=lambda t: {"total": 42})
        self.assertEqual((closes[0]["id"], closes[0]["jetons"]), (f["id"], {"total": 42}))
        self.assertEqual(taches.toutes()[-1]["fin"], 9000)                        # la durée couvre tout le travail
        # workmux nomme le projet autrement que le registre : l'agent est reconnu par son dossier, ou son worktree.
        g = self.fiche(worktree="bis-7-y", chemin=str(TMP / "p" / "repriceo__worktrees" / "bis-7-y"))
        vu = [{"project": "Repriceo-App", "worktree": "bis-7-y", "status": "working", "workdir": g["chemin"]}]
        taches.synchroniser(vu)
        self.assertEqual(taches.pour_agent("Repriceo-App", "bis-7-y", chemin=g["chemin"])["statut"], "en_cours")
        self.fiche(worktree="bis-8-z")
        taches.synchroniser([{"project": "Repriceo-App", "worktree": "bis-8-z", "status": "working"}])
        self.assertEqual(taches.pour_agent("repriceo", "bis-8-z")["statut"], "en_cours")
        # Un lancement coupé avant l'apparition de l'agent rend son élément au plan et prévient le chef.
        p = plans.create("Avorté", plans.resoudre([plans.parse_item("repriceo:BIS-9:claude@backend")], usage_resume={}))
        plans.decide(p["id"], True, par="test")
        plans.authorize_launch(p["id"], "repriceo", "BIS-9", "claude")
        self.fiche(issue="BIS-9", worktree="bis-9-api", plan=p["id"])
        closes = taches.synchroniser([], now=time.time() + taches.DEMARRAGE_MAX + 5)
        avortes = [t for t in closes if t.get("jamais_demarre")]
        self.assertEqual([t["issue"] for t in avortes], ["BIS-9"])
        daemon._lancements_avortes(avortes, [])
        self.assertFalse(plans.get(p["id"])["items"][0]["lance"])
        self.assertIn("BIS-9 (claude) n'a jamais démarré", self.chef_screen())
        # Si une fenêtre porte ce nom, on ne libère rien : mieux vaut un élément bloqué que deux agents.
        plans.authorize_launch(p["id"], "repriceo", "BIS-9", "claude")
        daemon._lancements_avortes(avortes, [{"worktree": "bis-9-api"}])
        self.assertTrue(plans.get(p["id"])["items"][0]["lance"])

    def test_task_list_command_accepts_a_count(self):
        self.fiche(worktree="a")
        self.fiche(worktree="b", issue="BIS-2")
        self.assertEqual(len(self.run_jarvis("tache").stdout.strip().splitlines()), 2)
        self.assertEqual(len(self.run_jarvis("tache", "1").stdout.strip().splitlines()), 1)
        self.assertEqual(len(self.run_jarvis("tache", "liste", "1").stdout.strip().splitlines()), 1)
        self.assertNotEqual(self.run_jarvis("tache", "beaucoup").returncode, 0)

    def test_personal_catalogue_survives_odd_text_and_is_never_overwritten_blind(self):
        from jarvis import modeles
        prop = modeles.proposer("nova", {"fournisseur": "codex", "id": "gpt-7-nova", "note": 'ligne 1\nligne "2"'},
                                "raison\nsur deux lignes", "https://exemple.org")
        modeles.decider(prop["id"], True, par="test")
        self.assertEqual(modeles.catalogue()["nova"]["note"], 'ligne 1 ligne "2"')
        self.assertEqual(modeles.catalogue_illisible(), "")
        # Catalogue personnel abîmé à la main : signalé, mis de côté, jamais écrasé en silence.
        perso = TMP / "cfg" / "modeles.toml"
        perso.write_text('[modeles.luna]\nactif = false\n[modeles.casse\n')
        self.assertIn("illisible", modeles.catalogue_illisible())
        self.assertIn("illisible", modeles.texte())
        modeles.enregistrer_perso("zeta", {"fournisseur": "claude", "id": "zeta"})
        self.assertEqual(len(list((TMP / "cfg").glob("modeles.toml.illisible.*"))), 1)
        self.assertIn("zeta", modeles.catalogue())
        for f in (TMP / "cfg").glob("modeles.toml.illisible.*"):
            f.unlink()

    def test_launcher_never_passes_a_model_id_that_is_no_longer_verified(self):
        from jarvis import modeles
        wt = TMP / "p" / "repriceo__worktrees" / "bis-75-x"
        wt.mkdir(parents=True, exist_ok=True)
        self.verifier_modeles()
        self.fiche(issue="BIS-75", worktree="bis-75-x", chemin=str(wt), modele="opus", modele_id="opus", repli="sonnet,vieux-modele")
        args = lambda: subprocess.run([sys.executable, "-m", "jarvis", "lancement-args", "claude"], cwd=wt, capture_output=True,
                                      text=True, env=dict(os.environ, PYTHONPATH=str(ROOT / "lib"))).stdout
        self.assertIn("arg\topus", args())
        self.assertIn("arg\tsonnet\n", args())                        # repli vérifié gardé, repli inconnu retiré
        self.assertNotIn("vieux-modele", args())
        modeles.enregistrer_perso("opus", {"id": "opus-9"})            # l'identifiant a changé depuis le plan
        self.assertNotIn("--model", args())
        (TMP / "cfg" / "modeles.toml").unlink()
        modeles.enregistrer_perso("opus", {"actif": False})            # modèle retiré depuis le plan
        self.assertNotIn("--model", args())

    def test_model_watch_reminder_is_not_starved_by_project_watches(self):
        self.set_claude(10)
        now = time.time()
        self.assertEqual(daemon.veille_check(now), "repriceo")           # une veille de projet vient d'être rappelée
        self.assertTrue(daemon.veille_modeles_check(now + 60))            # la veille des modèles part quand même
        self.assertFalse(daemon.veille_modeles_check(now + 120))          # une fois par période
        self.assertIsNone(daemon.veille_check(now + 180))                 # et le rythme des projets est inchangé

    def test_web_never_serves_what_a_deliverable_was_replaced_with(self):
        from jarvis import livrables, web
        d = livrables.dossier("repriceo", "BIS-82")
        (d / "note.md").write_text("contenu")
        (d / "page.html").write_text("<script>fetch('/api/etat')</script>")
        entree = lambda i, f: {"id": i, "projet": "repriceo", "issue": "BIS-82", "fichier": str(d / f), "titre": f,
                               "genre": "document", "octets": 7, "ts": time.time(), "envoye": True, "erreur": "",
                               "verdict": "PRÊT", "infos": {}, "planche": ""}
        store.write_json(livrables.FILE, {"seq": 2, "items": [entree("L-0001", "note.md"), entree("L-0002", "page.html")]})
        httpd = web._serveur(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(chemin):
            try:
                with opener.open(f"http://127.0.0.1:{httpd.server_port}{chemin}", timeout=10) as rep:
                    return rep.status, rep.read(), rep.headers
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read(), exc.headers
        try:
            code, corps, entetes = get("/livrable/L-0002")
            self.assertEqual((code, entetes["Content-Type"]), (200, "application/octet-stream"))   # jamais une page
            self.assertIn("attachment", entetes["Content-Disposition"])
            self.assertIn("sandbox", entetes["Content-Security-Policy"])
            self.assertEqual(get("/livrable/L-0001")[:2], (200, b"contenu"))
            # Le fichier inscrit est remplacé par un lien vers les réglages (jeton Telegram) : refusé.
            (d / "note.md").unlink()
            (d / "note.md").symlink_to(config.SETTINGS_FILE)
            code, corps, _ = get("/livrable/L-0001")
            self.assertEqual(code, 404)
            self.assertNotIn(b"123:ABC", corps)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_cockpit_selection_follows_the_item_not_its_position(self):
        from jarvis import cockpit
        c = cockpit.Cockpit.__new__(cockpit.Cockpit)                      # sans terminal : seule la logique de sélection
        c.vue, c.focus = "liste", "agents"
        c.sel, c.cle = {"agents": 0, "plans": 0}, {"agents": None, "plans": None}
        ag_ = lambda w: {"project": "repriceo", "worktree": w, "status": "working", "role": ""}
        snap = {"agents": [ag_("a"), ag_("b"), ag_("c")], "pending": [{"id": "P-0001"}, {"id": "P-0002"}], "propositions": []}
        c._deplacer(snap, +1)
        self.assertEqual(c.selected_agent(snap)["worktree"], "b")
        snap["agents"] = [ag_("b"), ag_("c"), ag_("a")]                   # la liste se réordonne toute seule
        self.assertEqual(c.selected_agent(snap)["worktree"], "b")          # la sélection suit « b »
        snap["agents"] = [ag_("c"), ag_("a")]                             # « b » a disparu : on reste à sa place
        self.assertEqual(c.selected_agent(snap)["worktree"], "c")
        c.focus = "plans"
        c._deplacer(snap, +1)
        self.assertEqual(c.selected_decision(snap)[1]["id"], "P-0002")
        snap["pending"] = [{"id": "P-0000"}, {"id": "P-0001"}, {"id": "P-0002"}]
        self.assertEqual(c.selected_decision(snap)[1]["id"], "P-0002")    # jamais le voisin
        snap["agents"], snap["pending"] = [], []
        self.assertIsNone(c.selected_agent(snap))
        self.assertIsNone(c.selected_decision(snap))

    def test_studio_scripts_reject_bad_input_before_working(self):
        racine = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        if not (shutil.which("node") and shutil.which("ffmpeg") and racine and (Path(racine) / "playwright").is_dir()):
            self.skipTest("node, ffmpeg et Playwright requis")
        d = TMP / "refus"
        d.mkdir(exist_ok=True)
        scripts = ROOT / "skills" / "jarvis-studio" / "scripts"
        env = dict(os.environ, NODE_PATH=racine, JARVIS_LIVRABLES=str(d))
        travail = lambda: set(Path(tempfile.gettempdir()).glob("jarvis-studio-*"))
        avant = travail()

        def rendre(storyboard, sortie="x.mp4"):
            (d / "sb.json").write_text(json.dumps(storyboard))
            return subprocess.run(["node", str(scripts / "rendre.cjs"), str(d / "sb.json"), str(d / sortie)],
                                  capture_output=True, text=True, env=env, timeout=120)
        for sb, attendu in (({"scenes": [{"type": "chifre", "valeur": 3}]}, "type « chifre » inconnu"),
                            ({"scenes": [{"type": "points", "titre": "T", "points": "pas une liste"}]}, "liste de phrases"),
                            ({"scenes": [{"type": "capture"}]}, "« image » ou « video »"),
                            ({"scenes": [None]}, "une scène est un objet"),
                            ({"scenes": []}, "non vide"),
                            ({"scenes": [{"type": "titre", "titre": "T", "duree": 600}]}, "trop long"),
                            ({"scenes": [{"type": "capture", "image": "$JARVIS_LIVRABLES/absente.png"}]}, "absente.png")):
            res = rendre(sb)
            self.assertNotEqual(res.returncode, 0, sb)
            self.assertIn(attendu, res.stderr)
            self.assertNotIn("    at ", res.stderr)                        # un message, pas une trace de pile
        self.assertIn(".mp4", rendre({"scenes": [{"type": "titre", "titre": "T"}]}, "x.xyz").stderr)
        self.assertEqual(travail() - avant, set())                         # aucun dossier de travail oublié
        # Enregistrement : une étape = une action connue, sortie en .webm, et pas d'ancien film laissé en place.
        vieux = d / "film.webm"
        vieux.write_bytes(b"ancien film")

        def filmer(scenario, sortie="film.webm"):
            (d / "sc.json").write_text(json.dumps(scenario))
            return subprocess.run(["node", str(scripts / "enregistrer.cjs"), str(d / "sc.json"), str(d / sortie)],
                                  capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("exactement une action", filmer({"etapes": [{"attendre": 10, "cliquer": "#x"}]}).stderr)
        self.assertIn("action inconnue", filmer({"etapes": [{"danser": 1}]}).stderr)
        self.assertIn(".webm", filmer({"etapes": [{"attendre": 10}]}, "film.mp4").stderr)
        page = d / "page.html"
        page.write_text("<html><body><p class='secret'>alice@exemple.com</p><a id='suite' href='page2.html'>suite</a></body></html>")
        (d / "page2.html").write_text("<html><body><p class='secret'>bob@exemple.com</p></body></html>")
        res = filmer({"largeur": 640, "hauteur": 400, "etapes": [{"aller": page.as_uri()}, {"masquer": "text=alice"}]})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("sélecteur CSS", res.stderr)
        self.assertFalse(vieux.exists())                                   # l'ancien film ne passe pas pour le nouveau
        # Montage : erreurs lisibles, jamais une trace Python.
        for montage, attendu in (({"segments": [{}]}, "fichier"), ({"segments": [{"fichier": "a.mp4"}], "ips": "vite"}, "nombre"),
                                 ({"segments": "x"}, ""), ([1], "objet JSON")):
            (d / "m.json").write_text(json.dumps(montage))
            res = subprocess.run([sys.executable, str(scripts / "monter.py"), str(d / "m.json"), str(d / "m.mp4")],
                                 capture_output=True, text=True, env=env)
            self.assertNotEqual(res.returncode, 0, montage)
            self.assertNotIn("Traceback", res.stderr, montage)
            self.assertIn(attendu, res.stderr)

    def test_recording_keeps_sensitive_zones_blurred_across_pages(self):
        racine = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        if not (shutil.which("node") and shutil.which("ffmpeg") and racine and (Path(racine) / "playwright").is_dir()):
            self.skipTest("node, ffmpeg et Playwright requis")
        from jarvis import studio
        d = TMP / "flou"
        d.mkdir(exist_ok=True)
        style = "<style>body{margin:0;background:#fff}.secret{position:fixed;inset:0;background:repeating-linear-gradient(90deg,#000 0 4px,#fff 4px 8px)}</style>"
        (d / "p1.html").write_text(f"<html>{style}<body><a id='suite' href='p2.html' style='position:fixed;z-index:9;top:0'>suite</a></body></html>")
        (d / "p2.html").write_text(f"<html>{style}<body><div class='secret'></div></body></html>")
        scenario = lambda masquer: {"largeur": 400, "hauteur": 300, "curseur": False, "etapes":
                                    [{"aller": (d / "p1.html").as_uri()}] + ([{"masquer": ".secret"}] if masquer else [])
                                    + [{"cliquer": "#suite"}, {"attendre": 300}, {"capture": "net.png" if not masquer else "flou.png"}]}
        script = ROOT / "skills" / "jarvis-studio" / "scripts" / "enregistrer.cjs"
        for masquer in (False, True):
            (d / "sc.json").write_text(json.dumps(scenario(masquer)))
            res = subprocess.run(["node", str(script), str(d / "sc.json"), str(d / "film.webm")], capture_output=True, text=True,
                                 env=dict(os.environ, NODE_PATH=racine), timeout=120)
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((d / "film.webm").is_file() and (d / "film.webm.json").is_file())
        self.assertGreater(studio.sonder(d / "film.webm")["duree"], 0.3)

        def contraste(png):   # écart-type de la luminosité : des rayures nettes en ont beaucoup, un flou presque pas
            out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(png), "-vf", "crop=200:100:100:150,signalstats,metadata=print",
                                  "-f", "null", "-"], capture_output=True, text=True).stderr
            bas = float(out.split("lavfi.signalstats.YLOW=")[1].split()[0])
            haut = float(out.split("lavfi.signalstats.YHIGH=")[1].split()[0])
            return haut - bas
        self.assertGreater(contraste(d / "net.png"), 150)                  # rayures noires et blanches, nettes
        self.assertLess(contraste(d / "flou.png"), 60)                     # la zone est restée floutée après la navigation


    def test_running_chef_is_seen_even_behind_its_launch_shell(self):
        # Le chef est lancé comme « env … claude …; exec bash » : tmux ne rapporte que le shell parent.
        # Il doit quand même être vu actif, et « jarvis chef » ne doit jamais refermer un chef vivant.
        env = dict(os.environ, JARVIS_SESSION="jtest2", PYTHONPATH=str(ROOT / "lib"))
        tmux("new-session", "-d", "-s", "jtest2", "-n", "cockpit", "sleep 300")
        tmux("new-window", "-d", "-t", "jtest2:", "-n", "chef", "env JARVIS_ROLE=chef sleep 300; exec bash")
        time.sleep(0.5)
        etat = lambda: subprocess.run([sys.executable, "-m", "jarvis", "chef-etat"], capture_output=True, text=True, env=env)
        try:
            self.assertIn("bash", tmux("list-panes", "-t", "jtest2:chef", "-F", "#{pane_current_command}"))
            self.assertEqual((etat().returncode, etat().stdout.strip()), (0, "actif"))
            avant = tmux("list-windows", "-t", "jtest2", "-F", "#{window_id} #{window_name}")
            res = subprocess.run([str(ROOT / "bin" / "jarvis"), "chef-lancer"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(tmux("list-windows", "-t", "jtest2", "-F", "#{window_id} #{window_name}"), avant)
            # Claude Code s'arrête : la fenêtre reste sur un shell, et ce n'est plus un chef.
            pid = int(tmux("list-panes", "-t", "jtest2:chef", "-F", "#{pane_pid}").strip())
            enfants = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
            for e in enfants:
                os.kill(int(e), 15)
            time.sleep(0.6)
            self.assertEqual((etat().returncode, etat().stdout.strip()), (2, "eteint"))
            tmux("kill-window", "-t", "jtest2:chef")
            self.assertEqual(etat().returncode, 1)
        finally:
            tmux("kill-session", "-t", "jtest2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
