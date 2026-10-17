"""Vague 2 : harnais d'évaluation, backend d'exécution, événements et replay, proxy LiteLLM (produits),
observabilité, rollback assisté. Tests déterministes : aucun vrai agent, aucun service externe."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
from test_jarvis import ROOT, TMP, FakeTelegram

from jarvis import (admission, agents, budgets, cli, config, evaluation, evenements, execution, observabilite,  # noqa: E402
                    plans, proxy, rollback, roles, store, taches)

ETAT = ("plans.json", "taches.json", "reservations.json", "pauses.json", "journal.jsonl", "escalades.json",
        "evenements.jsonl", "evaluations.jsonl", "rollbacks.json", "budgets.json", "exceptions.json")


def _fixer(tache_id: str, **champs) -> None:
    def _set(data):
        for t in data["taches"]:
            if t["id"] == tache_id:
                t.update(champs)
    store.update_json(taches.FILE, taches._vide(), _set)


def _git(chemin, *args):
    return subprocess.run(["git", "-C", str(chemin), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class Vague2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ["JARVIS_TELEGRAM_API"] = f"http://127.0.0.1:{cls.server.server_port}"
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        (TMP / "p" / "repriceo").mkdir(parents=True, exist_ok=True)
        config.save_projects({"repriceo": {"chemin": str(TMP / "p/repriceo"), "linear": "Repriceo", "priorite": 1, "actif": True}})
        data = config.settings()
        data["telegram"].update({"token": "123:ABC", "chat_id": "42"})
        data["notifications"]["windows"] = False
        data["sante"]["capacite_auto"] = False
        config.save_settings(data)
        cls.reglages = config.SETTINGS_FILE.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        config.SETTINGS_FILE.write_text(cls.reglages, encoding="utf-8")
        for n in ETAT:
            store.state_path(n).unlink(missing_ok=True)

    def setUp(self):
        FakeTelegram.calls.clear()
        config.SETTINGS_FILE.write_text(self.reglages, encoding="utf-8")
        for n in ETAT:
            store.state_path(n).unlink(missing_ok=True)
        self.libre = mock.patch.object(agents, "status_all", return_value=([], ""))
        self.libre.start()
        self.addCleanup(self.libre.stop)

    # --- P2.1 harnais d'évaluation ---------------------------------------------------------------

    def test_goldens_are_sound_and_protect_role_briefs(self):
        tous = evaluation.cas_tous()
        par_role = {}
        for c in tous:
            par_role.setdefault(c["role"], []).append(c)
        for role in ("backend", "frontend", "qa", "securite", "redaction"):
            self.assertGreaterEqual(len(par_role.get(role, [])), 3, role)
        res = evaluation.controle()
        echecs = [r for r in res if not r["ok"]]
        self.assertEqual(echecs, [], "chaque vérification refuse le départ, accepte la référence, et le brief garde ses règles")
        # Un brief dont on retire une règle exigée casse le contrôle.
        c = evaluation.cas("securite/injection-sql")
        vrai = roles.get("securite")
        appauvri = {**vrai, "corps": vrai["corps"].replace("validation des entrées", "entrées")}
        with mock.patch.object(roles, "get", side_effect=lambda n: appauvri if n == "securite" else vrai):
            self.assertTrue(evaluation.exigences_manquantes(c))
        cfg = json.loads((ROOT / "outils" / "promptfoo" / "promptfooconfig.yaml").read_text())
        self.assertEqual(len(cfg["tests"]), len(tous), "configuration promptfoo à régénérer (jarvis eval promptfoo)")
        self.assertNotIn(str(ROOT), json.dumps(cfg), "aucun chemin personnel dans la configuration versionnée")

    def test_real_run_goes_through_admission_and_records_result(self):
        c = evaluation.cas("backend/pagination")
        copie_ref = [sys.executable, "-c", f"import shutil; shutil.copytree({str(c['dossier'] / 'reference')!r}, '.', dirs_exist_ok=True)"]
        r = evaluation.lancer("backend/pagination", "claude", commande=copie_ref)
        self.assertTrue(r["ok"], r["detail"])
        rien = evaluation.lancer("backend/pagination", "claude", commande=[sys.executable, "-c", "pass"])
        self.assertFalse(rien["ok"])
        self.assertEqual([x["ok"] for x in evaluation.resultats()], [True, False])
        self.assertEqual(admission.en_attente(), [], "la réservation est rendue après l'évaluation")
        from jarvis import pauses
        pauses.poser("humain", par="test")
        with self.assertRaises(admission.Refus):
            evaluation.lancer("backend/pagination", "claude", commande=copie_ref)
        pauses.lever("humain", par="test")
        with mock.patch.dict(os.environ, {"JARVIS_ROLE": "chef"}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["eval", "lancer", "backend/pagination", "--confirmer"]), 4)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["eval", "lancer", "backend/pagination"]), 1, "--confirmer exigé")

    # --- P2.2 backend d'exécution ----------------------------------------------------------------

    def test_execution_backends(self):
        self.assertIsInstance(execution.pour_projet("repriceo"), execution.WorkmuxBackend)
        e2b = execution.E2BBackend(sdk=None)
        with self.assertRaises(execution.NonDisponible) as cm:
            e2b.lancer(projet="repriceo", chemin=".", branche="b", profil="cc", prompt="/dev/null")
        self.assertIn("budget", str(cm.exception))
        appels = []

        class FauxSandbox:
            sandbox_id = "sbx-1"

            class files:
                @staticmethod
                def write(chemin, contenu):
                    appels.append(("ecrire", chemin))

            class commands:
                @staticmethod
                def run(cmd, background=False):
                    appels.append(("lancer", cmd, background))

            @classmethod
            def create(cls, metadata=None):
                appels.append(("creer", metadata))
                return cls()

        sdk = type("SDK", (), {"Sandbox": FauxSandbox})
        budgets.definir("infrastructure", 50, projet="repriceo")
        prompt = TMP / "prompt-e2b.md"
        prompt.write_text("consigne")
        with mock.patch.dict(os.environ, {"E2B_API_KEY": "x"}):
            r = execution.E2BBackend(sdk=sdk).lancer(projet="repriceo", chemin=".", branche="bis-1", profil="cc", prompt=str(prompt))
        self.assertEqual(r, {"backend": "e2b", "cible": "sbx-1"})
        self.assertEqual([a[0] for a in appels], ["creer", "ecrire", "lancer"])
        self.assertTrue(appels[2][2], "agent lancé en arrière-plan")
        # Sans réservation d'admission active, aucun lancement direct.
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main(["execution", "lancer", "--projet", "repriceo", "--branche", "x", "--agent", "cc", "--prompt", str(prompt)])
        self.assertEqual(rc, 4)

    # --- P2.3 événements et replay ---------------------------------------------------------------

    def test_replay_rebuilds_a_complete_chronology(self):
        p = plans.create("Vague", [plans.parse_item("repriceo:BIS-200:claude@backend")])
        plans.decide(p["id"], True, par="Telegram")
        adm = admission.demander(origine="plan", projet="repriceo", issue="BIS-200", agent="claude", plan=p["id"],
                                 worktree="bis-200")
        t = taches.enregistrer(projet="repriceo", issue="BIS-200", agent="claude", worktree="bis-200", role="backend",
                               plan=p["id"], reservation=adm["reservation"])
        admission.confirmer(adm["reservation"], t["id"], "bis-200")
        vu = {"project": "repriceo", "worktree": "bis-200", "workdir": "", "kind": "claude", "window": "wm-bis-200"}
        for st in ("working", "waiting", "working", "done"):
            taches.synchroniser([{**vu, "status": st}])
        taches.noter_verdict("repriceo", "BIS-200", "pret", "ok")
        types = [e["type"] for e in evenements.chronologie(t["id"])]
        for attendu in ("plan_propose", "plan_approuve", "admis", "lance", "tour_agent", "reprise", "termine", "verdict"):
            self.assertIn(attendu, types)
        self.assertEqual(types[:4], ["plan_propose", "plan_approuve", "admis", "lance"])
        self.assertLess(types.index("reprise"), types.index("termine"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["rejouer", t["id"], "--depuis", "3"])
        self.assertIn("admis", out.getvalue())
        self.assertNotIn("plan proposé", out.getvalue())

    # --- P2.4 proxy LiteLLM ----------------------------------------------------------------------

    def test_proxy_is_off_by_default_and_never_writes_keys(self):
        self.assertFalse(proxy.reglages()["actif"])
        conf = proxy.configuration()
        noms = {m["model_name"] for m in conf["model_list"]}
        self.assertTrue({"fable", "opus", "sonnet", "sol"} <= noms)
        for m in conf["model_list"]:
            self.assertTrue(m["litellm_params"]["api_key"].startswith("os.environ/"))
            self.assertTrue(m["litellm_params"]["model"].startswith(("anthropic/claude-", "openai/gpt-")))
        for r in conf["router_settings"]["fallbacks"]:
            for nom, suite in r.items():
                self.assertTrue({nom, *suite} <= noms)
        chemin = proxy.ecrire()
        json.loads(Path(chemin).read_text())
        for lanceur in ("jarvis-claude", "jarvis-codex"):
            self.assertNotIn("litellm", (ROOT / "bin" / lanceur).read_text().lower(), "les agents ne passent jamais par le proxy")

    # --- P2.5 observabilité ----------------------------------------------------------------------

    def test_traces_and_dashboard(self):
        t = taches.enregistrer(projet="repriceo", issue="BIS-210", agent="claude", worktree="bis-210", role="qa", modele="fable")
        _fixer(t["id"], statut="terminee", fin=time.time(), debut=time.time() - 60,
               jetons={"entree": 100_000, "sortie": 10_000, "cache_lecture": 0, "cache_ecriture": 0, "total": 110_000})
        evenements.ecrire(t["id"], "tour_agent", etat="a fini son tour")
        evenements.ecrire(t["id"], "verdict", verdict="pret")
        doc = observabilite.traces(1)
        spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
        noms = [s["name"] for s in spans]
        self.assertIn("tache repriceo BIS-210", noms)
        self.assertIn("agent.tour.1", noms)
        self.assertIn("verdict", noms)
        racine = spans[0]
        attrs = {a["key"]: list(a["value"].values())[0] for a in racine["attributes"]}
        self.assertEqual(attrs["jarvis.jetons"], "110000")
        self.assertAlmostEqual(attrs["jarvis.equivalent_api_usd"], 1.5)
        self.assertEqual(len(racine["traceId"]), 32)
        self.assertTrue(all(s.get("parentSpanId") == racine["spanId"] for s in spans[1:]))
        self.assertTrue(Path(observabilite.exporter_fichier(1)).is_file())
        self.assertFalse(observabilite.envoyer()[0], "rien n'est envoyé sans point d'entrée")
        recus = []

        class Collecteur(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                recus.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Collecteur)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        s = config.settings()
        s["observabilite"]["otlp_endpoint"] = f"http://127.0.0.1:{srv.server_address[1]}"
        config.save_settings(s)
        self.assertTrue(observabilite.envoyer(1)[0])
        srv.server_close()
        self.assertEqual(recus[0][0], "/v1/traces")
        self.assertIn("resourceSpans", recus[0][1])
        from jarvis import web
        e = web.etat()
        self.assertEqual(e["executions"][0]["id"], t["id"])
        self.assertIn("executions(e)", (ROOT / "lib" / "jarvis" / "usine.html").read_text())

    # --- P2.6 rollback assisté -------------------------------------------------------------------

    def _depot_avec_tache(self, nom):
        repo = TMP / f"rb-{nom}"
        shutil.rmtree(repo, ignore_errors=True)
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        (repo / "a.txt").write_text("v1\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "départ")
        wt = TMP / f"rb-{nom}-wt"
        shutil.rmtree(wt, ignore_errors=True)
        _git(repo, "worktree", "add", "-q", str(wt), "-b", f"bis-{nom}")
        (wt / "a.txt").write_text("v2\n")
        _git(wt, "commit", "-qam", "change a")
        (wt / "b.txt").write_text("nouveau\n")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", "ajoute b")
        t = taches.enregistrer(projet="repriceo", issue=f"BIS-{nom}", agent="codex", worktree=f"bis-{nom}", chemin=str(wt), role="backend")
        return t, wt

    def test_rollback_needs_approval_then_reverts(self):
        t, wt = self._depot_avec_tache("300")
        p = rollback.proposer(t["id"])
        self.assertEqual([titre for _, titre in p["commits"]], ["ajoute b", "change a"])
        self.assertIn("revert --no-edit", p["commande"])
        with self.assertRaises(rollback.RollbackError):
            rollback.executer(t["id"], par="chef")                       # sans approbation : refusé
        with mock.patch("jarvis.notify.telegram", return_value=True) as tg:
            rollback.demander(t["id"], par="chef")
        self.assertIn(("↩ Revert", f"rbok:{t['id']}"), tg.call_args[0][1][0])
        self.assertEqual((wt / "a.txt").read_text(), "v2\n", "rien ne bouge avant le clic")
        bot = test_jarvis.Bot("123:ABC")
        from jarvis import daemon
        daemon.handle_update(bot, "42", {"callback_query": {"id": "c1", "data": f"rbok:{t['id']}",
                                                            "from": {"id": 42}, "message": {"chat": {"id": 42}}}})
        self.assertEqual((wt / "a.txt").read_text(), "v1\n")
        self.assertFalse((wt / "b.txt").exists())
        self.assertEqual(store.read_json(rollback.FILE, {})[t["id"]]["statut"], "execute")
        with self.assertRaises(rollback.RollbackError):
            rollback.decider(t["id"], True, par="Telegram")              # une seule fois

    def test_rollback_refused_when_unsafe(self):
        t, wt = self._depot_avec_tache("301")
        with mock.patch("jarvis.notify.telegram", return_value=True):
            rollback.demander(t["id"], par="chef")
        (wt / "a.txt").write_text("modif non commitée\n")
        with self.assertRaises(rollback.RollbackError) as cm:
            rollback.decider(t["id"], True, par="Telegram")
        self.assertIn("non commitées", str(cm.exception))
        _git(wt, "checkout", "--", "a.txt")
        occupe = [{"project": "repriceo", "worktree": "bis-301", "workdir": str(wt), "status": "working"}]
        with mock.patch.object(agents, "status_all", return_value=(occupe, "")):
            with self.assertRaises(rollback.RollbackError) as cm:
                rollback.executer(t["id"], par="humain", autorise_terminal=True)
        self.assertIn("agent travaille", str(cm.exception))
        with mock.patch.dict(os.environ, {"JARVIS_ROLE": "chef"}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["rollback", "executer", t["id"]]), 4)


if __name__ == "__main__":
    unittest.main()
