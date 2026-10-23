"""Travail en direct : visibilité, cloisonnement, capture ciblée et défaillances observables."""
import json
import subprocess
import time
import unittest
from unittest import mock

import test_missions
from jarvis import activite, agents, missions as mi, protocole_executant as proto


class ActiviteTest(test_missions.Base):
    def setUp(self):
        super().setUp()
        self.sessions = [dict(project=p, worktree="ticket-1", status="working", kind="codex", elapsed=3,
                              title="Travail réel", session=p, window="wm-ticket-1", workdir=f"/projets/{p}",
                              credential="NE-PAS-EXPOSER") for p in ("alpha", "beta")]
        patch = mock.patch.object(agents, "status_all", return_value=(self.sessions, ""))
        patch.start()
        self.addCleanup(patch.stop)

    def test_taches_visibles_sans_carte_mission_et_sans_doublons(self):
        m = self.mission_simple()
        for _ in range(2):
            mi.board_ajouter(self.org, "alpha", "note", "Note contextualisée", auteur="test",
                             mission_id=m["mission_id"], analyser=False)
        e = activite.instantane(self.org, "alpha")
        self.assertEqual(len(e["taches"]), 1)
        self.assertEqual(e["taches"][0]["statut"], mi.QUEUED)
        self.assertEqual([s["project"] for s in e["sessions"]], ["alpha"])
        self.assertNotIn("NE-PAS-EXPOSER", json.dumps(e))
        self.assertEqual(activite.instantane(self.org, "beta")["taches"], [])
        self.assertEqual(len(activite.instantane(self.org, "accueil")["sessions"]), 2)

    def test_tentative_en_cours_bail_expire_et_disparition_apres_resultat(self):
        m = self.mission_simple()
        rid, secret = self.executant()
        env = mi.reclamer(rid, secret)
        mi.demarrer(rid, secret, env["tache_id"], env["tentative_id"], env["bail_jeton"])
        e = activite.instantane(self.org, "accueil", now=env["bail_expire"] + 1)
        t = next(t for t in e["taches"] if t["mission_id"] == m["mission_id"])
        self.assertEqual(t["statut"], mi.RUNNING)
        self.assertTrue(t["bail_perime"])
        self.assertEqual(t["executant"], "poste")
        self.assertNotIn(secret, json.dumps(e))
        self.assertNotIn("bail_jeton", json.dumps(e))
        mi.rendre_resultat(rid, secret, proto.resultat(env, "reussi", contenu="## Résumé\nDocument analysé.\n## Points clés\nRésultat vérifié.", fournisseur="factice", factice=True))
        self.assertEqual(activite.instantane(self.org, "accueil")["taches"], [])

    def test_echec_observation_ne_devient_pas_zero_agents(self):
        with mock.patch.object(agents, "status_all", return_value=(None, "workmux indisponible")):
            e = activite.instantane(self.org, "accueil")
        self.assertIsNone(e["sessions"])
        self.assertEqual(e["sessions_erreur"], "workmux indisponible")

    def test_autre_tenant_ne_voit_ni_sessions_ni_missions_locales(self):
        self.mission_simple()
        autre = mi.creer_organisation("autre")
        with mock.patch.object(agents, "status_all") as observation:
            e = activite.instantane(autre, "accueil")
            observation.assert_not_called()
        self.assertIsNone(e["sessions"])
        self.assertEqual(e["taches"], [])
        with self.assertRaises(mi.MissionError):
            activite.apercu(autre, activite._id(self.sessions[0]), "accueil")

    def test_capture_id_fenetre_et_refus_autre_projet(self):
        sid = activite._id(self.sessions[1])
        with mock.patch.object(agents, "tmux_agent_windows", return_value=[
            {"session": "alpha", "window": "wm-ticket-1", "id": "@1"},
            {"session": "beta", "window": "wm-ticket-1", "id": "@2"},
        ]), mock.patch.object(agents, "_run", return_value=subprocess.CompletedProcess([], 0, stdout="Sortie beta")) as run:
            self.assertEqual(activite.apercu(self.org, sid, "beta"), "Sortie beta")
            self.assertIn("@2", run.call_args.args[0])
            with self.assertRaises(mi.MissionError):
                activite.apercu(self.org, sid, "alpha")
            with self.assertRaises(mi.MissionError):
                activite.apercu(self.org, "0" * 24, "accueil")
            run.side_effect = subprocess.TimeoutExpired("tmux", 5)
            with self.assertRaises(mi.MissionError) as erreur:
                activite.apercu(self.org, sid, "beta")
            self.assertEqual(erreur.exception.code, "indisponible")

    def test_echec_tmux_conserve_message_chef_en_file(self):
        with mock.patch.object(agents, "chef_running", return_value=True), \
                mock.patch.object(agents, "chef_has_dialog", return_value=False), \
                mock.patch.object(agents, "_run", return_value=subprocess.CompletedProcess([], 1)) as run:
            self.assertTrue(agents.chef_inject("Relire la mission"))
            self.assertEqual(run.call_count, 1)  # pas d'Entrée après une saisie refusée
        from jarvis import store
        self.assertIn("Relire la mission", store.read_json(agents.CHEF_QUEUE, []))


class SessionsTest(unittest.TestCase):
    def fenetres(self):
        return [dict(session=p, window="wm-ticket-1", path=f"/projets/{p}", command=c,
                     activity=int(time.time()), id=f"@{i}", pid=0)
                for i, (p, c) in enumerate((("alpha", "codex"), ("beta", "claude")), 1)]

    def test_deux_sessions_de_meme_nom_ne_se_masquent_pas(self):
        data = {"agents": [{"window_name": "wm-ticket-1", "session": "alpha", "worktree": "ticket-1",
                            "workdir": "/projets/alpha", "status": "working"}]}
        with mock.patch.object(agents, "_run", return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(data))), \
                mock.patch.object(agents, "tmux_agent_windows", side_effect=self.fenetres), \
                mock.patch.object(agents, "_pane_commands", return_value={("alpha", "wm-ticket-1"): "codex", ("beta", "wm-ticket-1"): "claude"}), \
                mock.patch.object(agents.shutil, "which", return_value="/bin/outils"), \
                mock.patch.object(agents.config, "project_for_path", side_effect=lambda p: p.rsplit("/", 1)[-1]):
            found, err = agents.status_all()
        self.assertEqual(err, "")
        self.assertEqual({(a["project"], a["kind"]) for a in found}, {("alpha", "codex"), ("beta", "claude")})

    def test_voir_ne_capture_pas_le_projet_homonyme(self):
        with mock.patch.object(agents, "tmux_agent_windows", side_effect=self.fenetres), \
                mock.patch.object(agents.shutil, "which", return_value=None), \
                mock.patch.object(agents.config, "project_for_path", side_effect=lambda p: p.rsplit("/", 1)[-1]), \
                mock.patch.object(agents, "_run", return_value=subprocess.CompletedProcess([], 0, stdout="Sortie beta")) as run:
            self.assertEqual(agents.capture("beta:ticket-1"), "Sortie beta")
            self.assertIn("@2", run.call_args.args[0])
            run.reset_mock()
            self.assertIn("ambiguë", agents.capture("ticket-1"))
            run.assert_not_called()

    def test_commandes_des_volets_separees_par_session(self):
        with mock.patch.object(agents.shutil, "which", return_value="/bin/tmux"), \
                mock.patch.object(agents, "_run", return_value=subprocess.CompletedProcess([], 0, stdout=
                                  "alpha\twm-ticket-1\tcodex\nbeta\twm-ticket-1\tclaude\n")):
            self.assertEqual(agents._pane_commands(), {("alpha", "wm-ticket-1"): "codex", ("beta", "wm-ticket-1"): "claude"})
