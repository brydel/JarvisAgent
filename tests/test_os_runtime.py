"""Socle intégré : mêmes contrats, préflight honnête et commandes utilisables sans extension de droits."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import test_missions
from jarvis import adaptateurs, cli, config, contrats, coureur, mandats, os_cli, protocole_executant as proto, specifications, taches


class ContratsRuntimeTest(test_missions.Base):
    def enveloppe(self, **travail):
        m = self.mission_simple(travail={"document": "Document à analyser", **travail}, essais_max=3)
        rid, secret = self.executant()
        return m, rid, secret, test_missions.mi.reclamer(rid, secret)

    def test_contrat_du_moteur_reste_documentaire_et_reflete_limites(self):
        _, _, _, env = self.enveloppe()
        spec = proto.valider_tache(env)["contrats"]
        self.assertEqual(spec["agent"]["profile"], "documentaire")
        self.assertEqual(spec["agent"]["tools"], [])
        self.assertIsNone(spec["agent"]["budget"]["max_cost_cents"])
        self.assertEqual(spec["agent"]["budget"]["max_duration_s"], env["delai_s"])
        self.assertEqual(spec["tache"]["max_attempts"], 3)
        self.assertEqual(spec["run"]["id"], env["tentative_id"])
        self.assertIn('"profile": "documentaire"', adaptateurs._consigne(env))

    def test_contrat_du_document_n_est_pas_une_autorite(self):
        _, _, _, env = self.enveloppe(contrats={"agent": {"profile": "outille", "tools": ["email.send"]}})
        self.assertEqual(env["contrats"]["agent"]["tools"], [])
        self.assertEqual(env["contrats"]["agent"]["role"], "recherche")

    def test_executant_refuse_contrat_elargi_avant_demarrage(self):
        _, rid, secret, env = self.enveloppe()
        env["contrats"]["agent"]["tools"] = ["email.send"]
        transport = coureur.TransportLocal(rid, secret)
        with mock.patch.object(transport, "reclamer", return_value=env), mock.patch.object(transport, "demarrer") as demarrer:
            r = coureur.Coureur(transport, {"factice": adaptateurs.Factice()}).tour()
        self.assertEqual(r["etat"], "invalide")
        demarrer.assert_not_called()

    def test_version_bool_dans_contrat_refusee_et_ancien_protocole_accepte(self):
        _, _, _, env = self.enveloppe()
        env["contrats"]["agent"]["version"] = True
        with self.assertRaises(proto.EnveloppeInvalide):
            proto.valider_tache(env)
        del env["contrats"]
        self.assertIs(proto.valider_tache(env), env)

    def test_mission_complete_sous_factice_avec_extension_de_contrat(self):
        m = self.mission_simple()
        rid, secret = self.executant()
        self.assertEqual(self.coureur(rid, secret).tour()["etat"], "fait")
        self.assertEqual(test_missions.mi.mission(self.org, m["mission_id"])["statut"], "SUCCEEDED")

    def test_fournisseur_personnalise_conserve_sa_reclamation_historique(self):
        mi = test_missions.mi
        nom = "mon-fournisseur-local"
        mi.declarer_connexion(self.org, nom, "abonnement")
        rid, secret = self.executant(fournisseurs=(nom,))
        self.mission_simple(fournisseur=nom)
        env = mi.reclamer(rid, secret)
        self.assertEqual(env["contrats"]["agent"]["provider"], nom)
        self.assertEqual(proto.valider_tache(env)["fournisseur"], nom)

    def test_prompt_code_et_vue_agent_utilisent_le_role_du_registre(self):
        from jarvis import activite
        branche = "jos-1-contrats"
        taches.enregistrer(projet="projet-os", issue="JOS-1", agent="codex", role="backend", worktree=branche)
        session = {"project": "projet-os", "worktree": branche, "kind": "codex", "status": "working",
                   "title": "Contrats", "session": "jarvis", "window": "wm-" + branche, "workdir": "", "elapsed": 0}
        with mock.patch("jarvis.agents.status_all", return_value=([session], "")):
            vue = activite.instantane(self.org, "projet-os")
        spec = vue["sessions"][0]["contrats"]
        self.assertEqual(spec["agent"]["role"], "backend")
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            rc = cli.main(["prompt-construire", "--projet", "projet-os", "--issue", "JOS-1", "--branche", branche,
                           "--regles", "AGENTS.md", "--role", "backend"])
        self.assertEqual(rc, 0)
        self.assertIn('"role": "backend"', sortie.getvalue())
        self.assertIn('"profile": "code"', sortie.getvalue())
        self.assertEqual(spec["agent"]["budget"]["max_duration_s"], None)


class PreflightEtCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-os-")
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(config, "STATE_DIR", Path(self.tmp.name))
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": "json"})
        p.start(); self.addCleanup(p.stop)
        self.agent = {"version": 1, "id": "agent-test", "role": "backend", "profile": "code", "provider": "codex",
                      "tools": ["code.shell"], "required_capabilities": ["python.runtime"]}
        self.tache = {"version": 1, "id": "task-test", "agent_id": "agent-test", "objective": "Vérifier le calcul",
                      "project": "projet-os", "acceptance": ["Résultat attendu vérifié"], "required_tools": ["code.shell"]}
        self.diag = {"capacites": [{"id": "python.runtime", "available": True},
                                    {"id": "provider.codex.cli", "available": True}]}

    def test_mandat_local_sans_destination_et_cli_installe_ne_prouve_pas_inference(self):
        m = mandats.creer({"version": 1, "owner": "humain", "project": "projet-os", "tools": ["code.shell"],
                           "destinations": [], "expires_at": time.time() + 300, "max_actions": 1, "max_cost_cents": 0}, par="humain")
        self.tache["mandate_id"] = m["id"]
        r = specifications.preflight(self.agent, self.tache, self.diag)
        self.assertTrue(r["autorisations"][0]["admis"])
        self.assertFalse(r["admis"])
        self.assertTrue(any("Inférence" in e for e in r["raisons"]))
        self.assertEqual(mandats.get(m["id"])["used_actions"], 0)
        self.diag["capacites"].append({"id": "provider.codex.inference", "available": True})
        self.assertTrue(specifications.preflight(self.agent, self.tache, self.diag)["admis"])
        mandats.revoquer(m["id"], par="humain")
        self.assertFalse(specifications.preflight(self.agent, self.tache, self.diag)["admis"])

    def test_outil_inexistant_et_reference_agent_incoherente_refuses(self):
        self.tache["required_tools"] = ["email.send"]
        r = specifications.preflight(self.agent, self.tache, self.diag)
        self.assertEqual(r["outils_absents"], ["email.send"])
        self.assertFalse(r["admis"])
        self.tache["agent_id"] = "autre-agent"
        with self.assertRaises(contrats.ContratError):
            specifications.preflight(self.agent, self.tache, self.diag)

    def test_creation_et_revocation_cli_exigent_le_proprietaire(self):
        f = Path(self.tmp.name) / "mandat.json"
        f.write_text("{}")
        with mock.patch("jarvis.cli._human_only", return_value=4):
            self.assertEqual(os_cli.main(["mandat", "creer", str(f)]), 4)
            self.assertEqual(os_cli.main(["mandat", "revoquer", "MA-inconnu"]), 4)
        self.assertEqual(mandats.lister(), [])

    def test_cli_valide_json_et_ne_reproduit_pas_champs_secrets(self):
        f = Path(self.tmp.name) / "agent.json"
        f.write_text(json.dumps(self.agent))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["os", "valider", "agent", str(f)]), 0)
        self.assertTrue(json.loads(out.getvalue())["valide"])
        f.write_text(json.dumps({**self.agent, "api_key": "SECRET-A-NE-PAS-AFFICHER"}))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(os_cli.main(["valider", "agent", str(f)]), 1)
        self.assertNotIn("SECRET-A-NE-PAS-AFFICHER", err.getvalue())
