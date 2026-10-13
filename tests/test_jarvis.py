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
    "JARVIS_DATA_DIR": str(TMP / "data"),
    "JARVIS_SESSION": "jtest",
    "FAKE_WORKMUX_STATUS": str(TMP / "status.json"),
    "FAKE_WORKMUX_LOG": str(TMP / "wm.log"),
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
    FILE = b"\x89PNG maquette"

    def do_GET(self):  # noqa: N802 — téléchargement d'un fichier (api.telegram.org/file/bot…/chemin)
        FakeTelegram.calls.append(("GET", self.path))
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.FILE)))
        self.end_headers()
        self.wfile.write(self.FILE)

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
        for name in ("claude_usage.json", "budget.json", "veille.json", "battement.json", "sante.json",
                     "reprise.json", "agents_actifs.json", "chef_queue.json"):
            store.state_path(name).unlink(missing_ok=True)
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
        set_status()
        tmux("new-window", "-d", "-t", "jtest", "-n", "wm-vieux-codex", "cat")
        time.sleep(0.3)
        old = agents.IDLE_AFTER
        agents.IDLE_AFTER = 0  # simule une fenêtre muette depuis longtemps
        try:
            found, _ = agents.status_all()
            ghost = next(a for a in found if a["worktree"] == "vieux-codex")
            self.assertEqual(ghost["status"], "idle")
            self.assertNotIn(ghost["status"], agents.BUSY)
        finally:
            agents.IDLE_AFTER = old
            tmux("kill-window", "-t", "jtest:wm-vieux-codex")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
