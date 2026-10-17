"""Vague 1 : plafonds de jetons, coûts (équivalent API), mémoire du chef, bilan quotidien, échecs et reprise
bornée, secrets minimaux par tâche. Tests déterministes : aucun vrai agent, aucun vrai Telegram."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
from test_jarvis import ROOT, TMP, FakeTelegram

from jarvis import admission, agents, bilan, cli, config, couts, daemon, memoire, plans, store, taches, usage  # noqa: E402
from jarvis import secrets as jsecrets  # noqa: E402

ETAT = ("plans.json", "taches.json", "reservations.json", "pauses.json", "journal.jsonl", "escalades.json",
        "memoire.jsonl", "jetons_garde.json", "bilan_quotidien.json", "budgets.json", "travaux.json",
        "exceptions.json", "blocage.json", "journal.md", "claude_usage.json", "budget.json")


def _fixer(tache_id: str, **champs) -> None:
    def _set(data):
        for t in data["taches"]:
            if t["id"] == tache_id:
                t.update(champs)
    store.update_json(taches.FILE, taches._vide(), _set)


def _essai(issue="BIS-70", role="backend", agent="claude", modele="opus", statut="terminee", jetons=0, echec=None,
           taille="M", empreinte="", fin=None, **extra) -> dict:
    t = taches.enregistrer(projet="repriceo", issue=issue, agent=agent, worktree=f"{issue.lower()}-{time.time_ns()}",
                           role=role, modele=modele, taille=taille, consignes_empreinte=empreinte)
    champs = {"statut": statut, "fin": fin if fin is not None else time.time(), "debut": time.time() - 60}
    if jetons:
        champs["jetons"] = {"entree": jetons // 2, "sortie": jetons // 4, "cache_lecture": 0,
                            "cache_ecriture": jetons - jetons // 2 - jetons // 4, "total": jetons}
    if echec:
        champs["echec"] = {"classe": echec, "source": "declare", "par": "chef", "note": "", "ts": time.time()}
    champs.update(extra)
    _fixer(t["id"], **champs)
    return taches.get(t["id"])


class Vague1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import HTTPServer
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
            store.supprimer(n)
        shutil.rmtree(config.CONFIG_DIR / "secrets", ignore_errors=True)

    def setUp(self):
        FakeTelegram.calls.clear()
        config.SETTINGS_FILE.write_text(self.reglages, encoding="utf-8")
        for n in ETAT:
            store.supprimer(n)
        shutil.rmtree(TMP / "codexhome" / "sessions", ignore_errors=True)
        self.libre = mock.patch.object(agents, "status_all", return_value=([], ""))
        self.libre.start()
        self.addCleanup(self.libre.stop)

    def plan(self, *items):
        its = plans.resoudre([plans.parse_item(i) for i in items], usage_resume={})
        p = plans.create("Plan", its)
        return plans.decide(p["id"], True, par="test")

    # --- P1.1 plafonds de jetons -----------------------------------------------------------------

    def test_plan_items_carry_a_token_cap(self):
        it = plans.parse_item("repriceo:BIS-70:auto@backend+L%2.5M:auth")
        self.assertEqual(it["jetons_max"], 2_500_000)
        with self.assertRaises(plans.PlanError):
            plans.parse_item("repriceo:BIS-70:auto@backend%5")         # sous 10k : refusé
        p = self.plan("repriceo:BIS-71:auto@backend+M", "repriceo:BIS-72:auto@qa+L%900k")
        par_issue = {i["issue"]: i for i in p["items"]}
        self.assertEqual(par_issue["BIS-71"]["jetons_max"], 3 * 800_000)     # 3 × estimation M par défaut
        self.assertEqual(par_issue["BIS-72"]["jetons_max"], 900_000)
        self.assertIn("≤ 2.4 M jetons", plans.format_plan(p))
        # Dès 5 tâches terminées de même rôle et taille, l'estimation devient leur médiane.
        for n in (100_000, 200_000, 300_000, 400_000, 500_000):
            _essai(issue=f"BIS-{n // 1000}", role="frontend", jetons=n, taille="S")
        est, source = couts.estimation("frontend", "S")
        self.assertEqual(est, 300_000)
        self.assertIn("médiane de 5", source)

    def test_relaunch_over_cap_is_refused_and_chef_notified(self):
        p = self.plan("repriceo:BIS-80:claude@backend+M%1M")
        _essai(issue="BIS-80", role="backend", jetons=1_200_000, statut="perdue", jetons_max=1_000_000)
        cpt = usage.compteur_tache(taches.toutes()[-1]["id"])
        self.assertTrue(cpt["depasse"])
        with mock.patch.object(agents, "chef_inject") as chef, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            rc = cli.main(["plan", "verifier", p["id"], "repriceo", "BIS-80", "claude"])
        self.assertEqual(rc, 8)
        self.assertIn("plafond", err.getvalue())
        self.assertTrue(chef.called and "budget_jetons" in chef.call_args[0][0])
        self.assertFalse(plans.get(p["id"])["items"][0]["lance"], "l'élément de plan reste lançable")
        self.assertEqual(admission.en_attente(), [])
        self.assertTrue(any(e.get("code") == "budget_jetons" for e in __import__("jarvis.journal").journal.lire(5)))

    def test_daemon_stops_an_agent_that_crosses_its_cap_once(self):
        t = taches.enregistrer(projet="repriceo", issue="BIS-81", agent="claude", worktree="bis-81", role="backend",
                               jetons_max=500_000, chemin=str(TMP))
        _fixer(t["id"], statut="en_cours")
        vus = [{"project": "repriceo", "worktree": "bis-81", "status": "working", "workdir": str(TMP), "kind": "claude",
                "window": "wm-bis-81", "elapsed": 10}]
        with mock.patch.object(usage, "task_tokens", return_value={"total": 600_000}), \
                mock.patch.object(agents, "send", return_value=(True, "")) as send, \
                mock.patch.object(agents, "chef_inject") as chef:
            self.assertEqual(daemon.jetons_check(now=1e10, agents=vus), [t["id"]])
            self.assertEqual(daemon.jetons_check(now=1e10 + 3600, agents=vus), [])   # une seule fois
        self.assertIn("plafond de jetons", send.call_args[0][1])
        self.assertIn("[JARVIS jetons]", chef.call_args[0][0])

    # --- P1.2 coût -------------------------------------------------------------------------------

    def test_cost_uses_sourced_prices_and_flags_estimates(self):
        c = couts.cout_jetons({"entree": 1_000_000, "sortie": 1_000_000, "cache_lecture": 1_000_000,
                               "cache_ecriture": 1_000_000}, "claude", "fable")
        self.assertAlmostEqual(c["usd"], 10 + 50 + 0.25 + 12.5)
        self.assertFalse(c["estimation"])
        self.assertTrue(couts.cout_jetons({"entree": 1, "sortie": 1}, "claude", "opus")["estimation"],
                        "cache d'Opus non publié : estimé")
        defaut = couts.cout_jetons({"entree": 1_000_000, "sortie": 0}, "codex", "codex-defaut")
        self.assertTrue(defaut["estimation"])
        self.assertAlmostEqual(defaut["usd"], 2.0)                          # tarif de référence (sol)
        a = _essai(issue="BIS-90", agent="claude", modele="fable", jetons=400_000)
        b = _essai(issue="BIS-91", agent="codex", modele="sol", jetons=800_000)
        _essai(issue="BIS-92", agent="claude", modele="claude-defaut", jetons=100_000)
        r = couts.par_projet("repriceo", "7j")
        self.assertAlmostEqual(r["usd"], sum(x["usd"] for x in r["lignes"]))
        self.assertTrue(r["estimation"])
        self.assertEqual(r["jetons"], 1_300_000)
        self.assertGreater(couts.cout_fiche(a)["usd"], couts.cout_fiche(b)["usd"])
        self.assertIn("$ US", couts.monnaie(3.5))
        s = config.settings()
        s["couts"]["taux"] = 0.9
        config.save_settings(s)
        self.assertEqual(couts.monnaie(10), "9,00 €")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["cout", "projet", "repriceo"])
        self.assertIn("Équivalent API", out.getvalue())
        self.assertIn("pas une dépense", out.getvalue())

    # --- P1.3 mémoire ----------------------------------------------------------------------------

    def test_memory_search_is_weighted_recent_and_redacted(self):
        memoire.noter(titre="Corps seulement", corps="la migration de la base a cassé la prod de test")
        memoire.noter(titre="Vague auth", lecons="toujours répéter la migration en staging avant")
        memoire.noter(titre="Migration Drizzle ratée", decisions="revenir au schéma précédent")
        memoire.noter(titre="Ancienne migration", now=time.time() - 120 * 86400)
        r = memoire.chercher("migration")
        self.assertEqual([x["entree"]["titre"] for x in r], ["Migration Drizzle ratée", "Vague auth", "Corps seulement"])
        self.assertEqual([x["score"] for x in r], [3, 2, 1])
        # Sur un an : même score que le titre récent, mais plus vieille, donc juste après lui.
        self.assertEqual([x["entree"]["titre"] for x in memoire.chercher("migration", jours=365)][:2],
                         ["Migration Drizzle ratée", "Ancienne migration"])
        e = memoire.noter(titre="clé", corps="ne pas garder sk-ABCDEFGHIJKLMNOPQRSTUV ni 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw0")
        self.assertNotIn("sk-ABC", json.dumps(e))
        self.assertNotIn("AAHdq", store.state_path(memoire.FILE).read_text())
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["note", "Vague 12 terminée : le screener est livré"])
        self.assertEqual(memoire.chercher("screener")[0]["entree"]["source"], "note")
        chef = (ROOT / "chef" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("## Mémoire", chef)
        self.assertIn("jarvis memoire chercher", chef)
        self.assertIsNone(memoire.recherche_semantique("x"), "aucune recherche sémantique sans réglage")

    # --- P1.4 bilan quotidien --------------------------------------------------------------------

    def test_daily_report_sections_and_once_a_day(self):
        _essai(issue="BIS-60", jetons=200_000, verdict="pret", verdict_ts=time.time())
        _essai(issue="BIS-61", statut="perdue", echec="regression")
        plans.create("En attente", [plans.parse_item("repriceo:BIS-62:claude")])
        from jarvis import pauses
        pauses.poser("batterie", "9 %", par="demon")
        texte = bilan.quotidien()
        premiere = texte.splitlines()[0]
        self.assertIn("livré 1", premiere)
        self.assertIn("échoué 1", premiere)
        self.assertIn("équivalent API", premiere)
        for section in ("LIVRÉ", "PROUVÉ", "ÉCHOUÉ", "CONSOMMÉ", "RISQUES", "DÉCISIONS DEMANDÉES"):
            self.assertIn(section, texte)
        self.assertIn("regression", texte)
        self.assertIn("batterie", texte)
        self.assertIn("plan P-", texte)
        s = config.settings()
        s["bilan"]["heure"] = "08:00"
        config.save_settings(s)
        matin = time.mktime(time.strptime("2026-10-18 07:59", "%Y-%m-%d %H:%M"))
        with mock.patch("jarvis.notify.telegram", return_value=True) as tg:
            self.assertFalse(daemon.bilan_check(matin))                       # trop tôt
            self.assertTrue(daemon.bilan_check(matin + 120))
            self.assertFalse(daemon.bilan_check(matin + 3 * 3600))            # déjà envoyé ce jour
            self.assertTrue(daemon.bilan_check(matin + 86400 + 120))          # lendemain
        self.assertEqual(tg.call_count, 2)
        s["bilan"]["heure"] = "8h"
        self.assertTrue(any("bilan.heure" in e for e in config.valider(s)))

    # --- P1.5 échecs et reprise bornée -----------------------------------------------------------

    def test_failure_classes_and_bounded_retries(self):
        for classe in taches.CLASSES_ECHEC:
            t = _essai(issue=f"BIS-1{len(classe)}", role="data")
            source = "auto" if classe in taches.CLASSES_AUTO else "declare"
            self.assertEqual(taches.classer(t["id"], classe, source=source)["echec"]["classe"], classe)
        t = _essai(issue="BIS-19", role="data")
        taches.classer(t["id"], "regression")
        with self.assertRaises(ValueError):
            taches.classer(t["id"], "fatigue")
        # Une classe déclarée n'est jamais écrasée par une classe constatée.
        self.assertIsNone(taches.classer(t["id"], "quota", source="auto", remplacer=False))
        # Quota et lancements jamais démarrés ne comptent pas comme essais.
        _essai(issue="BIS-40", role="backend", echec="quota")
        _essai(issue="BIS-40", role="backend", jamais_demarre=True, statut="perdue")
        self.assertIsNone(taches.verifier_reprise("repriceo", "BIS-40", "backend"))
        # Après une erreur d'outil, le même essai relancé tel quel est refusé ; un autre modèle passe.
        _essai(issue="BIS-41", role="backend", agent="claude", modele="opus", echec="erreur_outil", empreinte="e1")
        self.assertEqual(taches.verifier_reprise("repriceo", "BIS-41", "backend", agent="claude", modele="opus",
                                                 consignes_empreinte="e1")[0], "meme_approche")
        self.assertIsNone(taches.verifier_reprise("repriceo", "BIS-41", "backend", agent="claude", modele="fable",
                                                  consignes_empreinte="e1"))
        self.assertIsNone(taches.verifier_reprise("repriceo", "BIS-41", "backend", agent="claude", modele="opus",
                                                  consignes_empreinte="e2"))
        # 3e essai : escalade, via l'admission (plan) — l'élément reste lançable.
        _essai(issue="BIS-42", role="backend", statut="perdue")
        _essai(issue="BIS-42", role="backend", statut="terminee", echec="regression")
        p = self.plan("repriceo:BIS-42:claude@backend")
        with self.assertRaises(admission.Refus) as cm:
            admission.demander(origine="plan", projet="repriceo", issue="BIS-42", agent="claude", plan=p["id"])
        self.assertEqual(cm.exception.code, "escalade")
        self.assertFalse(plans.get(p["id"])["items"][0]["lance"])
        # Une reprise après redémarrage continue le même essai : pas d'escalade.
        rep_ = admission.demander(origine="reprise", projet="repriceo", issue="BIS-42", agent="claude", role="backend",
                                  worktree="bis-42-reprise")
        admission.liberer(rep_["reservation"])
        # Un humain débloque un essai : il passe.
        self.assertEqual(taches.autoriser_essai("repriceo", "BIS-42", "backend", par="humain"), 3)
        adm = admission.demander(origine="plan", projet="repriceo", issue="BIS-42", agent="claude", plan=p["id"])
        self.assertTrue(adm["reservation"])
        # Les essais d'un autre rôle (relecture) forment une autre unité.
        self.assertIsNone(taches.verifier_reprise("repriceo", "BIS-42", "revue"))

    def test_failure_classification_rights_and_auto_bloque(self):
        t = _essai(issue="BIS-50", role="backend", statut="en_cours")
        env_agent = dict(os.environ, JARVIS_METIER="backend")
        with mock.patch.dict(os.environ, env_agent), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["tache", "echec", t["id"], "regression"]), 4)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["tache", "echec", t["id"], "hors_perimetre", "a modifié l'auth"]), 0)
        self.assertEqual(taches.get(t["id"])["echec"]["classe"], "hors_perimetre")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["tache", "voir", t["id"]])
        self.assertIn("hors_perimetre", out.getvalue())
        self.assertIn("essais comptés pour cette unité : 1/2", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["tache", "relancer", t["id"], "--autoriser"]), 4, "humain seulement")
        # « bloque » constaté par le démon : un agent qui attend une réponse depuis trop longtemps.
        u = taches.enregistrer(projet="repriceo", issue="BIS-51", agent="codex", worktree="bis-51", role="qa")
        _fixer(u["id"], statut="attente")
        attend = [{"project": "repriceo", "worktree": "bis-51", "status": "waiting", "elapsed": 3 * 3600,
                   "workdir": "", "kind": "codex", "window": "wm-bis-51"}]
        with mock.patch.object(agents, "status_all", return_value=(attend, "")), \
                mock.patch.object(agents, "window_idle", return_value={}):
            daemon.blocage_check()
        self.assertEqual(taches.get(u["id"])["echec"]["classe"], "bloque")
        self.assertEqual(taches.get(u["id"])["echec"]["source"], "auto")

    # --- P1.6 secrets minimaux -------------------------------------------------------------------

    def _secrets(self, mode=0o600):
        d = config.CONFIG_DIR / "secrets"
        d.mkdir(parents=True, exist_ok=True)
        (d / "repriceo.toml").write_text('[role.backend]\nvars = ["STRIPE_KEY", "DATABASE_URL"]\n\n'
                                         '[role."*"]\nvars = ["SENTRY_DSN"]\n', encoding="utf-8")
        env = d / "repriceo.env"
        env.write_text('STRIPE_KEY="sk_test_VALEUR_SECRETE_123"\nDATABASE_URL=postgres://u:mdp@h/db\n'
                       'SENTRY_DSN=https://dsn\nAUTRE=inutile\n', encoding="utf-8")
        os.chmod(env, mode)

    def test_secrets_are_scoped_by_role_and_never_stored(self):
        self._secrets()
        self.assertEqual(jsecrets.pour_tache("repriceo", "backend"),
                         {"DATABASE_URL": "postgres://u:mdp@h/db", "SENTRY_DSN": "https://dsn",
                          "STRIPE_KEY": "sk_test_VALEUR_SECRETE_123"})
        self.assertEqual(jsecrets.pour_tache("repriceo", "qa"), {"SENTRY_DSN": "https://dsn"})
        self.assertEqual(jsecrets.pour_tache("autre", "backend"), {})
        # Lanceur : la fiche du worktree décide du rôle ; seules ses variables sortent.
        wt = TMP / "wt-secrets-qa"
        wt.mkdir(exist_ok=True)
        taches.enregistrer(projet="repriceo", issue="BIS-55", agent="claude", worktree="wt-secrets-qa", chemin=str(wt), role="qa")
        cwd = os.getcwd()
        out = io.StringIO()
        try:
            os.chdir(wt)
            with contextlib.redirect_stdout(out):
                cli.main(["lancement-args", "claude"])
        finally:
            os.chdir(cwd)
        self.assertIn("secret\tSENTRY_DSN=https://dsn", out.getvalue())
        self.assertNotIn("STRIPE_KEY", out.getvalue(), "un agent qa ne reçoit pas la clé réservée au backend")
        # Aucune valeur dans les fichiers d'état (registre, fil, journal…).
        for f in config.STATE_DIR.rglob("*"):
            if f.is_file():
                contenu = f.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("VALEUR_SECRETE", contenu, f)
                self.assertNotIn("https://dsn", contenu, f)
        rapport = "\n".join(jsecrets.verifier("repriceo"))
        self.assertIn("STRIPE_KEY (défini)", rapport)
        self.assertNotIn("VALEUR_SECRETE", rapport)
        self.assertNotIn("mdp", rapport)
        # Codex : les secrets autorisés passent, les autres variables sensibles restent filtrées.
        self.assertEqual(jsecrets.exclusions_codex(["STRIPE_KEY"], {"STRIPE_KEY": "x", "GH_TOKEN": "y", "PATH": "/bin",
                                                                   "AWS_SECRET_ACCESS_KEY": "z"}),
                         ["AWS_SECRET_ACCESS_KEY", "GH_TOKEN"])

    def test_secrets_refused_when_unsafe(self):
        self._secrets(mode=0o644)
        with self.assertRaises(jsecrets.SecretsError):
            jsecrets.pour_tache("repriceo", "backend")
        wt = TMP / "wt-secrets-be"
        wt.mkdir(exist_ok=True)
        taches.enregistrer(projet="repriceo", issue="BIS-56", agent="claude", worktree="wt-secrets-be", chemin=str(wt), role="backend")
        cwd = os.getcwd()
        out = io.StringIO()
        try:
            os.chdir(wt)
            with contextlib.redirect_stdout(out):
                cli.main(["lancement-args", "claude"])
        finally:
            os.chdir(cwd)
        self.assertNotIn("secret\t", out.getvalue(), "fichier trop ouvert : rien n'est injecté")
        (config.CONFIG_DIR / "secrets" / "repriceo.toml").write_text('[role.backend]\nvars = ["PATH"]\n', encoding="utf-8")
        with self.assertRaises(jsecrets.SecretsError):
            jsecrets.autorisations("repriceo")

    def test_codex_launcher_passes_only_allowed_secrets(self):
        self._secrets()
        repo = TMP / "p" / "repriceo"
        if not (repo / ".git").exists():
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
                       cwd=repo, check=True)
        wt = TMP / "p" / "repriceo__worktrees" / "bis-57-sec"
        if not wt.exists():
            subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "bis-57-sec"], cwd=repo, check=True)
        taches.enregistrer(projet="repriceo", issue="BIS-57", agent="codex", worktree="bis-57-sec", chemin=str(wt), role="backend")
        env = dict(os.environ, GH_TOKEN="ne-doit-pas-passer")
        out = subprocess.run([str(ROOT / "bin" / "jarvis-codex"), "prompt"], cwd=wt, capture_output=True, text=True,
                             env=env, check=True).stdout.splitlines()
        self.assertIn("shell_environment_policy.ignore_default_excludes=true", out)
        exclusion = next(x for x in out if x.startswith("shell_environment_policy.exclude="))
        self.assertIn("GH_TOKEN", exclusion)
        self.assertNotIn("STRIPE_KEY", exclusion)
        self.assertNotIn("sk_test", " ".join(out), "aucune valeur sur la ligne de commande")


    # --- Correctifs de la revue indépendante ------------------------------------------------------

    def test_review_fixes_attempts_and_labels(self):
        # « quota » et « bloque » ne se déclarent pas : sinon la borne des essais se contourne.
        t = _essai(issue="BIS-30", role="backend", statut="perdue")
        for classe in ("quota", "bloque"):
            with self.assertRaises(ValueError):
                taches.classer(t["id"], classe)
        # Un essai terminé sans échec ne compte pas ; un essai en cours, si.
        _essai(issue="BIS-31", role="backend", statut="terminee")
        _essai(issue="BIS-31", role="backend", statut="terminee", verdict="pret")
        self.assertIsNone(taches.verifier_reprise("repriceo", "BIS-31", "backend"))
        _essai(issue="BIS-32", role="backend", statut="terminee", verdict="corrections")
        _essai(issue="BIS-32", role="backend", statut="terminee", verdict="corrections")
        self.assertEqual(taches.verifier_reprise("repriceo", "BIS-32", "backend")[0], "escalade")
        # Un seul essai à la fois par unité, même avec un autre fournisseur.
        _essai(issue="BIS-33", role="backend", statut="en_cours")
        with self.assertRaises(admission.Refus) as cm:
            admission.demander(origine="cli", projet="repriceo", issue="BIS-33", agent="codex", role="backend", worktree="x33")
        self.assertEqual(cm.exception.code, "doublon")
        # « bloque » constaté disparaît quand l'agent repart ; la tâche finie compte alors comme livrée.
        u = taches.enregistrer(projet="repriceo", issue="BIS-34", agent="claude", worktree="bis-34", role="qa")
        _fixer(u["id"], statut="attente")
        taches.classer(u["id"], "bloque", source="auto", par="demon")
        vu = {"project": "repriceo", "worktree": "bis-34", "workdir": "", "kind": "claude", "window": "wm-bis-34"}
        taches.synchroniser([{**vu, "status": "working"}])
        self.assertIsNone(taches.get(u["id"])["echec"])
        taches.synchroniser([{**vu, "status": "done"}])
        self.assertIn(u["id"], [x["id"] for x in bilan.donnees()["livrees"]])

    def test_review_fixes_tokens_reprise_and_settings(self):
        # Une relance dans le même worktree ne recompte pas les jetons du 1er essai.
        wt = TMP / "wt-relance"
        wt.mkdir(exist_ok=True)
        import re
        d = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(wt))
        d.mkdir(parents=True, exist_ok=True)
        ancien, recent = time.time() - 7200, time.time()
        def ligne(ts, mid, n):
            iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))
            return json.dumps({"timestamp": iso, "requestId": mid, "message": {"id": mid, "usage": {
                "input_tokens": n, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})
        (d / "a.jsonl").write_text(ligne(ancien, "m1", 1000) + "\n" + ligne(recent, "m2", 10) + "\n")
        self.assertEqual(usage.claude_task_tokens(str(wt))["total"], 1010)
        self.assertEqual(usage.claude_task_tokens(str(wt), depuis=recent - 30)["total"], 10)
        # Reprise après redémarrage : le plafond validé dans le plan (5M) vaut, pas celui par défaut.
        _essai(issue="BIS-35", role="backend", statut="perdue", jetons=3_000_000, jetons_max=5_000_000)
        rep = admission.demander(origine="reprise", projet="repriceo", issue="BIS-35", agent="claude", role="backend",
                                 worktree="bis-35", jetons_max=5_000_000)
        self.assertEqual(rep["jetons_max"], 5_000_000)
        # Réglages : multiplicateur décimal accepté, heure H:MM acceptée, valeur invalide refusée.
        with mock.patch.object(cli, "_human_only", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["regler", "budget_jetons.multiplicateur", "2.5"]), 0)
            self.assertEqual(cli.main(["regler", "bilan.heure", "8:30"]), 0)
            self.assertNotEqual(cli.main(["regler", "bilan.heure", "huit heures"]), 0)
        self.assertEqual(config.settings()["budget_jetons"]["multiplicateur"], 2.5)
        self.assertEqual(config.settings()["bilan"]["heure"], "8:30")

    def test_review_fixes_secrets_and_memory(self):
        self._secrets()
        # lancement-args : réservé aux lanceurs (pas à un agent ni au chef).
        for var in ("JARVIS_METIER", "JARVIS_ROLE"):
            with mock.patch.dict(os.environ, {var: "x"}), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["lancement-args", "claude"]), 4)
        # Variables des fournisseurs d'IA jamais injectables.
        for nom in ("ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN", "IFS"):
            (config.CONFIG_DIR / "secrets" / "repriceo.toml").write_text(f'[role.ia-produit]\nvars = ["{nom}"]\n')
            with self.assertRaises(jsecrets.SecretsError):
                jsecrets.autorisations("repriceo")
        # Le chef n'a pas le droit de lire le dossier des secrets.
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["chef-preparer"])
        regles = json.loads((config.DATA_DIR / "chef" / ".claude" / "settings.json").read_text())
        self.assertTrue(any("/secrets/**" in r for r in regles["permissions"]["deny"]))
        # Codex : les exclusions de l'utilisateur sont gardées.
        self.assertEqual(jsecrets.exclusions_codex(["A_KEY"], {"A_KEY": "1", "B_TOKEN": "2"}, existantes=["AWS_*"]),
                         ["AWS_*", "B_TOKEN"])
        # Mémoire : expurgation élargie et valeurs connues ; identifiants uniques après coupe.
        self._secrets()
        e = memoire.noter(titre="fuites", corps="sk_live_abcdefghijk AKIAABCDEFGHIJKLMNOP github_pat_abcdefghijklmnopqrstuvwx "
                                                 "postgres://u:motdepasse@h/db eyJhbGciOiJ.eyJzdWIiOiIx.SflKxwRJSMeKKF2 "
                                                 "valeur sk_test_VALEUR_SECRETE_123")
        for fuite in ("abcdefghijk", "AKIAABC", "github_pat_a", "motdepasse", "eyJhbGci", "VALEUR_SECRETE"):
            self.assertNotIn(fuite, json.dumps(e), fuite)
        ancien = memoire.MAX_ENTREES
        memoire.MAX_ENTREES = 3
        try:
            ids = [memoire.noter(titre=f"n{i}")["id"] for i in range(5)]
        finally:
            memoire.MAX_ENTREES = ancien
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(len(memoire.toutes()), 3)


if __name__ == "__main__":
    unittest.main()
