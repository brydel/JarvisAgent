"""Routes réelles et raccordement des échanges : aucun auteur inventé ni acquittement anticipé."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_studio
from jarvis import communaute, communaute_runtime, config, os_cli, store


class ReseauApiTest(unittest.TestCase):
    req = test_studio.StudioTest.req
    connecter = test_studio.StudioTest.connecter

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jarvis-reseau-api-")
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(config, "STATE_DIR", Path(tmp.name))
        patch.start()
        self.addCleanup(patch.stop)
        test_studio.StudioTest.setUp(self)

    def tearDown(self):
        test_studio.StudioTest.tearDown(self)
        self.fil.join(timeout=2)

    def test_session_et_origine_requises_sur_les_nouvelles_routes(self):
        for route in ("communaute", "connexions", "outils", "outils/operations", "os/outbox"):
            self.assertEqual(self.req("GET", "/api/v2/" + route)[0], 401)
        self.assertEqual(self.req("POST", "/api/v2/communaute/fils", {"contenu": "Bonjour"})[0], 401)
        self.connecter()
        self.assertEqual(self.req("POST", "/api/v2/communaute/fils", {"contenu": "Bonjour"},
                                  entetes={"Origin": "https://ailleurs.example"})[0], 403)

    def test_discussion_globale_libre_reponse_et_idempotence_reelles(self):
        self.connecter()
        corps = {"contenu": "Ces modèles et toute notre usine méritent une discussion libre.",
                 "salon": "retours libres", "operation_id": "racine-1"}
        code, message, _ = self.req("POST", "/api/v2/communaute/fils", corps)
        self.assertEqual(code, 201, message)
        self.assertEqual((message["auteur"], message["projet"], message["type"], message["preuves"]),
                         ("proprietaire", "", "discussion", []))
        self.assertEqual(self.req("POST", "/api/v2/communaute/fils", corps)[1]["id"], message["id"])
        code, reponse, _ = self.req("POST", f"/api/v2/communaute/fils/{message['id']}/messages",
                                    {"contenu": "Parlons aussi du choix des modèles.", "operation_id": "reponse-1"})
        self.assertEqual(code, 201, reponse)
        self.assertEqual(reponse["fil_id"], message["id"])
        self.assertEqual(reponse["salon"], "retours libres")
        code, detail, _ = self.req("GET", f"/api/v2/communaute/fils/{message['id']}")
        self.assertEqual(code, 200)
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(self.req("GET", "/api/v2/communaute")[1]["fils"][0]["messages_nombre"], 2)

    def test_auteur_du_corps_refuse_et_projet_facultatif_isole(self):
        self.connecter()
        self.assertEqual(self.req("POST", "/api/v2/communaute/fils", {"auteur": "agent:inventé", "contenu": "Bonjour"})[0], 400)
        code, message, _ = self.req("POST", "/api/v2/communaute/fils", {"contenu": "Projet seulement", "projet": "A"})
        self.assertEqual(code, 201)
        self.assertEqual(self.req("GET", "/api/v2/communaute")[1]["fils"], [])
        self.assertEqual(self.req("GET", "/api/v2/communaute?projet=B")[1]["fils"], [])
        self.assertEqual(self.req("GET", "/api/v2/communaute?projet=A")[1]["fils"][0]["id"], message["id"])
        self.assertNotEqual(self.req("GET", f"/api/v2/communaute/fils/{message['id']}")[0], 200)

    def test_lecture_catalogue_et_connexion_revoquee_sans_secret(self):
        self.connecter()
        code, catalogue, _ = self.req("GET", "/api/v2/outils")
        self.assertEqual(code, 200)
        self.assertEqual(catalogue["outils"][0]["id"], "web.fetch")
        with mock.patch.dict(os.environ, {"JARVIS_TEST_MCP_SECRET": "secret-non-restitue"}):
            code, connexion, _ = self.req("POST", "/api/v2/connexions", {
                "id": "test-mcp", "nom": "MCP de test", "type": "mcp_http", "url": "https://pypi.org/mcp",
                "token_env": "JARVIS_TEST_MCP_SECRET", "outils_autorises": []})
            self.assertEqual(code, 201, connexion)
            self.assertNotIn("secret-non-restitue", json.dumps(connexion))
            self.assertNotIn("url", connexion)
            self.assertEqual(self.req("POST", "/api/v2/connexions/test-mcp/revoquer", {})[0], 200)
        self.assertFalse(self.req("GET", "/api/v2/connexions")[1]["connexions"][0]["active"])

    def test_cli_chef_peut_parler_et_contexte_ne_confond_pas_opinion_et_lecon(self):
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"JARVIS_ROLE": "chef"}), contextlib.redirect_stdout(sortie):
            code = os_cli.main(["communaute", "publier", "Je préfère comparer les modèles sur des tâches réelles.",
                                "--salon", "modeles"])
        self.assertEqual(code, 0)
        message = json.loads(sortie.getvalue())
        self.assertEqual(message["auteur"], "chef")
        self.assertEqual(communaute.lecons(tenant_id=self.org), [])
        contexte = communaute_runtime.contexte()
        self.assertIn("modèles sur des tâches réelles", contexte)
        self.assertIn("sans autorité", contexte)

    def test_le_bavardage_entre_agents_ne_reveille_pas_le_chef(self):
        communaute.publier(contenu="Bravo pour la PR #135 !", auteur="agent:design", type="felicitation", tenant_id=self.org)
        with mock.patch("jarvis.agents.chef_running", return_value=True), mock.patch("jarvis.agents.chef_inject") as inject:
            self.assertEqual(communaute_runtime.notifier(), 0)
            inject.assert_not_called()
        self.assertTrue(store.existe(communaute_runtime.ETAT), "le curseur avance : le message n'est pas relu en boucle")

    def test_notification_non_acquittee_avant_remise_et_pas_de_boucle_chef(self):
        # une idée (comme une question ou une demande d'aide) d'un agent réveille le chef ; le bavardage, non
        communaute.publier(contenu="Une idée", auteur="agent:chercheur", type="idee", tenant_id=self.org)
        with mock.patch("jarvis.agents.chef_running", return_value=True), \
             mock.patch("jarvis.agents.chef_inject", side_effect=[False, True]) as inject:
            self.assertEqual(communaute_runtime.notifier(), 0)
            self.assertFalse(store.existe(communaute_runtime.ETAT))
            self.assertEqual(communaute_runtime.notifier(), 1)
            self.assertEqual(inject.call_args_list[0].kwargs["message_id"], inject.call_args_list[1].kwargs["message_id"])
        communaute.publier(contenu="Réponse du chef", auteur="chef", tenant_id=self.org)
        with mock.patch("jarvis.agents.chef_running", return_value=True), mock.patch("jarvis.agents.chef_inject") as inject:
            self.assertEqual(communaute_runtime.notifier(), 0)
            inject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
