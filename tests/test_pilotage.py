"""Contrôleur réel et workers locaux ; fournisseur explicitement factice, sans réseau externe."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import agent_runtime, config, mandats, modeles_runtime, outils_http, pilotage, store  # noqa: E402
from jarvis.annulation import ExecutionAnnulee  # noqa: E402


class OpenAIResponsesFactice:
    """Double injecté à la seule frontière fournisseur ; aucune inférence OpenAI réelle."""

    provider = modeles_runtime.PROVIDER
    destination = modeles_runtime.DESTINATION
    factice = True

    def __init__(self, configuration, *, bloquer=False, retenir_sortie=False):
        self.configuration = copy.deepcopy(configuration)
        self.model = configuration["model"]
        self.bloquer = bloquer
        self.operations = []
        self.entree = threading.Event()
        self.annule = threading.Event()
        self.termine = threading.Event()
        self.autoriser_sortie = threading.Event()
        if not retenir_sortie:
            self.autoriser_sortie.set()

    def __call__(self, contexte, *, operation_id, annulation=None):
        if getattr(store._local, "profondeur", 0):
            raise AssertionError("Le fournisseur factice ne doit pas être appelé sous transaction SQL.")
        self.operations.append(operation_id)
        self.entree.set()
        try:
            if self.bloquer:
                limite = time.monotonic() + 5
                while time.monotonic() < limite:
                    annulation.verifier()
                    self.annule.wait(0.01)
                raise AssertionError("Le contrôleur n'a pas annulé le fournisseur factice.")
            return {"type": "final", "contenu": "Livrable factice à relire.", "appels": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "provider": self.provider, "model": self.model, "factice": True}
        except ExecutionAnnulee:
            self.annule.set()
            raise
        finally:
            self.autoriser_sortie.wait(3)
            self.termine.set()


class PilotageTest(unittest.TestCase):
    def setUp(self):
        temporaire = tempfile.TemporaryDirectory(prefix="jarvis-pilotage-")
        self.addCleanup(temporaire.cleanup)
        patch = mock.patch.object(config, "STATE_DIR", Path(temporaire.name))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": "json",
            "JARVIS_TEST_PILOTAGE_KEY": "credential-strictement-factice-du-test"})
        patch.start()
        self.addCleanup(patch.stop)
        precedent = store._local
        store._local = threading.local()

        def fermer_base():
            self.fermer_base_thread()
            store._local = precedent

        self.addCleanup(fermer_base)
        patch = mock.patch.object(outils_http, "requete", side_effect=AssertionError("Réseau interdit dans ces tests."))
        self.reseau = patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.reseau.assert_not_called)
        self.modeles = []
        self.bloquer_modele = False
        self.retenir_sortie = False
        self.fils_auxiliaires = []
        patch = mock.patch.object(pilotage, "_fabrique_modele", side_effect=self.fabriquer_modele)
        self.usine = patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.fermer_workers)
        self.assertEqual(pilotage._workers, {}, "Un test précédent a conservé un worker actif.")
        self.configuration = {"provider": modeles_runtime.PROVIDER, "model": "modele-factice-pilotage",
            "api_key_env": "JARVIS_TEST_PILOTAGE_KEY", "max_output_tokens": 256, "timeout_s": 5, "max_turns": 3}
        pilotage.configurer_modele(self.configuration, par="proprietaire-test")
        self.mandat = mandats.creer({"version": 1, "owner": "proprietaire-test", "project": "projet-test",
            "tools": ["model.openai_responses.inference"], "destinations": [modeles_runtime.DESTINATION],
            "expires_at": time.time() + 300, "max_cost_cents": 100, "max_actions": 100}, par="proprietaire-test")
        self.agent = {"version": 1, "id": "chercheur-test", "role": "Recherche factice vérifiable",
            "profile": "outille", "provider": modeles_runtime.PROVIDER, "model": self.configuration["model"],
            "tools": [], "budget": {"max_tokens": 100_000, "max_cost_cents": 50, "max_duration_s": 60}}
        self.tache = {"version": 1, "id": "tache-test", "agent_id": self.agent["id"],
            "objective": "Proposer un livrable de test.", "project": "projet-test",
            "acceptance": ["Le livrable attend une revue indépendante."], "required_tools": [],
            "mandate_id": self.mandat["id"]}

    @staticmethod
    def fermer_base_thread():
        c = getattr(store._local, "conn", None)
        if c is not None:
            c.close()
            store._local.conn = None

    def fermer_workers(self):
        for modele in self.modeles:
            modele.autoriser_sortie.set()
        pilotage.arreter()
        for fil in self.fils_auxiliaires:
            fil.join(timeout=5)

    def fabriquer_modele(self, configuration):
        modele = OpenAIResponsesFactice(configuration, bloquer=self.bloquer_modele,
                                       retenir_sortie=self.retenir_sortie)
        self.modeles.append(modele)
        return modele

    def corps(self, numero="test", **modifications):
        return {"agent": copy.deepcopy(self.agent), "tache": self.tache | {"id": "tache-" + numero},
                "operation_id": "creation-" + numero, **modifications}

    def creer(self, numero="test", **modifications):
        return pilotage.creer_run(self.corps(numero, **modifications), par="proprietaire-test")

    def attendre_entree(self, ident):
        with pilotage._verrou:
            fil, controle = pilotage._workers[ident]
        self.assertTrue(fil.is_alive())
        limite = time.monotonic() + 3
        while time.monotonic() < limite:
            if any(modele.entree.is_set() for modele in self.modeles if "ar:" + ident + ":model:1" in modele.operations):
                return fil, controle
            threading.Event().wait(0.01)
        self.fail("Le fournisseur factice n'a pas reçu le run attendu.")

    def test_liaison_immuable_execute_le_modele_initial_apres_changement_global(self):
        run = self.creer()
        pilotage.configurer_modele(self.configuration | {"model": "autre-modele-factice"}, par="proprietaire-test")
        pilotage.lancer(run["id"], par="proprietaire-test")
        pilotage.attendre(run["id"])
        self.assertEqual(self.modeles[0].configuration, modeles_runtime.valider_configuration(self.configuration))
        self.assertEqual(pilotage.modele()["configuration"]["model"], "autre-modele-factice")
        resultat = agent_runtime.voir(run["id"])
        self.assertEqual(resultat["status"], "awaiting_review")
        self.assertTrue(resultat["factice"])
        self.assertEqual(len(self.modeles[0].operations), 1)

    def test_creation_idempotente_et_conflit_ne_creent_pas_un_second_run(self):
        premier = self.creer()
        second = self.creer()
        self.assertEqual(premier["id"], second["id"])
        with self.assertRaises(ValueError):
            self.creer(max_tours=1)
        self.assertEqual([r["id"] for r in agent_runtime.lister()], [premier["id"]])
        self.assertEqual(pilotage._modele_du_run(premier["id"]), modeles_runtime.valider_configuration(self.configuration))
        self.usine.assert_not_called()

    def test_creation_concurrente_conserve_un_seul_run_et_sa_liaison(self):
        barriere = threading.Barrier(3)
        resultats, erreurs = [], []

        def creer():
            try:
                barriere.wait(timeout=3)
                resultats.append(self.creer())
            except Exception as exc:  # noqa: BLE001 — une erreur de thread doit faire échouer le test
                erreurs.append(exc)
            finally:
                self.fermer_base_thread()

        fils = [threading.Thread(target=creer) for _ in range(2)]
        self.fils_auxiliaires.extend(fils)
        for fil in fils:
            fil.start()
        barriere.wait(timeout=3)
        for fil in fils:
            fil.join(timeout=5)
            self.assertFalse(fil.is_alive())
        self.assertEqual(erreurs, [])
        self.assertEqual(len(resultats), 2)
        self.assertEqual(len({r["id"] for r in resultats}), 1)
        self.assertEqual(len(agent_runtime.lister()), 1)
        self.assertEqual(pilotage._modele_du_run(resultats[0]["id"]), modeles_runtime.valider_configuration(self.configuration))

    def test_limites_et_identite_configurees_sont_imposees_avant_creation(self):
        demandes = [{"max_tours": 4}, {"max_model_output_tokens": 257}, {"max_tours": True},
            {"max_model_output_tokens": True}, {"max_tours": 0}, {"max_model_output_tokens": 0},
            {"configuration_modele": self.configuration | {"max_turns": 4}},
            {"agent": self.agent | {"provider": "autre-provider"}},
            {"agent": self.agent | {"model": "autre-modele"}}]
        for demande in demandes:
            with self.subTest(champs=list(demande)), self.assertRaises(ValueError):
                self.creer(**demande)
        self.assertEqual(agent_runtime.lister(), [])
        self.usine.assert_not_called()
        run = self.creer()
        self.assertEqual(run["max_tours"], self.configuration["max_turns"])
        self.assertEqual(run["max_model_output_tokens"], self.configuration["max_output_tokens"])

    def test_auth_absente_refuse_sans_worker_appel_ni_consommation_du_mandat(self):
        run = self.creer()
        with mock.patch.dict(os.environ):
            os.environ.pop("JARVIS_TEST_PILOTAGE_KEY", None)
            with self.assertRaises(ValueError):
                pilotage.lancer(run["id"], par="proprietaire-test")
        self.usine.assert_not_called()
        self.assertEqual(pilotage._workers, {})
        self.assertEqual(agent_runtime.voir(run["id"])["status"], "planned")
        self.assertEqual(mandats.get(self.mandat["id"])["used_actions"], 0)

    def test_deux_workers_maximum_et_lancement_double_sans_second_appel(self):
        self.bloquer_modele = True
        runs = [self.creer(str(i)) for i in range(3)]
        for run in runs[:2]:
            pilotage.lancer(run["id"], par="proprietaire-test")
            self.attendre_entree(run["id"])
        pilotage.lancer(runs[0]["id"], par="proprietaire-test")
        with self.assertRaises(ValueError):
            pilotage.lancer(runs[2]["id"], par="proprietaire-test")
        self.assertEqual(self.usine.call_count, 2)
        self.assertEqual([len(modele.operations) for modele in self.modeles], [1, 1])
        self.assertEqual(agent_runtime.voir(runs[2]["id"])["status"], "planned")
        with pilotage._verrou:
            self.assertEqual(sum(fil.is_alive() for fil, _ in pilotage._workers.values()), 2)

    def test_arreter_annule_et_attend_la_fin_effective_du_worker(self):
        self.bloquer_modele, self.retenir_sortie = True, True
        run = self.creer()
        pilotage.lancer(run["id"], par="proprietaire-test")
        worker, _ = self.attendre_entree(run["id"])
        modele = self.modeles[0]
        arret = threading.Thread(target=pilotage.arreter)
        self.fils_auxiliaires.append(arret)
        arret.start()
        self.assertTrue(modele.annule.wait(2))
        self.assertTrue(arret.is_alive(), "arreter doit joindre le worker jusqu'à sa sortie réelle.")
        self.assertTrue(worker.is_alive())
        modele.autoriser_sortie.set()
        arret.join(timeout=3)
        self.assertFalse(arret.is_alive())
        self.assertFalse(worker.is_alive())
        self.assertTrue(modele.termine.is_set())
        self.assertEqual(pilotage._workers, {})
        resultat = agent_runtime.voir(run["id"])
        self.assertEqual((resultat["status"], resultat["blocage"]), ("blocked", "model_unknown"))
        self.assertEqual(resultat["resultat"], "")
        self.assertEqual(len(modele.operations), 1)

    def test_service_deja_arrete_refuse_avant_creation_du_fournisseur(self):
        run = self.creer()
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ValueError):
            pilotage.lancer(run["id"], par="proprietaire-test", stop=stop)
        self.usine.assert_not_called()
        self.assertEqual(pilotage._workers, {})
        self.assertEqual(agent_runtime.voir(run["id"])["status"], "planned")
        self.assertEqual(mandats.get(self.mandat["id"])["used_actions"], 0)


if __name__ == "__main__":
    unittest.main()
