"""Tests de bout en bout du noyau Jarvis : plans, démon, pont Telegram, injection dans le chef.

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
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="jarvis-test-"))
TMUX_SOCKET = f"jarvis-test-{os.getpid()}"

# L'environnement doit être prêt AVANT d'importer jarvis (chemins lus à l'import).
os.environ.update({
    "JARVIS_CONFIG_DIR": str(TMP / "cfg"),
    "JARVIS_STATE_DIR": str(TMP / "state"),
    "JARVIS_SESSION": "jtest",
    "FAKE_WORKMUX_STATUS": str(TMP / "status.json"),
    "FAKE_WORKMUX_LOG": str(TMP / "wm.log"),
    "PATH": f"{TMP / 'bin'}:{ROOT / 'tests' / 'fake-bin'}:{os.environ['PATH']}",
})
sys.path.insert(0, str(ROOT / "lib"))

# Toutes les commandes tmux du code passent par ce petit wrapper → serveur tmux isolé.
(TMP / "bin").mkdir()
real_tmux = shutil.which("tmux")
wrapper = TMP / "bin" / "tmux"
wrapper.write_text(f"#!/bin/sh\nexec {real_tmux} -L {TMUX_SOCKET} \"$@\"\n")
wrapper.chmod(0o755)

from jarvis import agents, config, daemon, plans, store  # noqa: E402
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

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        method = self.path.rsplit("/", 1)[-1]
        FakeTelegram.calls.append((method, body))
        result = True
        if method == "getUpdates":
            result, FakeTelegram.updates = FakeTelegram.updates, []
        elif method == "getMe":
            result = {"username": "jarvis_test_bot"}
        elif method == "sendMessage":
            result = {"message_id": len(FakeTelegram.calls)}
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
            d.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(d)], check=True)
        config.save_projects({
            "repriceo": {"chemin": str(TMP / "p/repriceo"), "linear": "Repriceo", "priorite": 1, "actif": True},
            "jobpilot-ia": {"chemin": str(TMP / "p/jobpilot-ia"), "linear": "JobPilot", "priorite": 2, "actif": True},
        })
        data = config.settings()
        data["telegram"].update({"token": "123:ABC", "chat_id": "42"})
        data["notifications"]["windows"] = False
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
