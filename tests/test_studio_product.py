"""Atelier des agents : HTTP authentifie, permissions et essais lies a un contenu precis."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import test_jarvis  # noqa: F401
import test_studio
from jarvis import config, missions, roles, store, studio_product, versions_roles


class AtelierTests(unittest.TestCase):
    setUpStudio = test_studio.StudioTest.setUp
    tearDown = test_studio.StudioTest.tearDown
    req = test_studio.StudioTest.req
    connecter = test_studio.StudioTest.connecter

    def setUp(self):
        self.setUpStudio()
        store.write_json(versions_roles.FILE, {"seq": 0, "propositions": []})
        self.role = roles.get("design") or next(iter(roles.tous().values()))
        self.body = {"corps": self.role["corps"] + "\n\nAvant toute livraison, expliquer les compromis et les preuves de verification.",
                     "pourquoi": "Rendre les preuves de verification plus faciles a consulter.",
                     "base": versions_roles.empreinte(self.role["corps"])}
        self.url = "/api/v2/atelier/agents/" + self.role["nom"]
        self.notification = patch("jarvis.notify.telegram", return_value=False)
        self.notification.start()
        self.addCleanup(self.notification.stop)

    def candidate(self):
        self.connecter()
        code, body, _ = self.req("POST", self.url + "/proposer", self.body)
        self.assertEqual(code, 201, body)
        return body["candidat"]

    def test_authentication_required(self):
        self.assertEqual(self.req("GET", "/api/v2/atelier")[0], 401)
        self.assertEqual(self.req("POST", self.url + "/proposer", self.body)[0], 401)

    def test_catalogue_excludes_private_paths(self):
        self.connecter()
        code, data, _ = self.req("GET", "/api/v2/atelier")
        self.assertEqual(code, 200)
        self.assertGreater(len(data["agents"]), 0)
        self.assertNotIn(str(config.CONFIG_DIR), json.dumps(data))
        self.assertNotIn("source", data["agents"][0])
        self.assertEqual(data["politique"]["fournisseurs_defaut"], ["claude", "codex"])
        self.assertEqual(data["politique"]["model_bridge"], "desactive")

    def test_cross_origin_write_refused(self):
        self.connecter()
        self.assertEqual(self.req("POST", self.url + "/proposer", self.body, entetes={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", self.url + "/proposer", self.body, ecriture=False)[0], 403)

    def test_other_tenant_cannot_access_global_roles(self):
        with self.assertRaises(missions.MissionError):
            studio_product.catalogue("other-tenant")

    def test_structural_verification_is_not_model_evaluation(self):
        self.connecter()
        code, data, _ = self.req("POST", self.url + "/verifier", self.body)
        self.assertEqual(code, 200, data)
        self.assertTrue(data["valide"], data)
        self.assertIsNone(data["qualite_modele"])
        self.assertIn("sans_inference", data["evaluation"])
        self.assertIn("+++ proposition", data["diff"])

    def test_stale_base_conflicts(self):
        self.connecter()
        code, _, _ = self.req("POST", self.url + "/proposer", {**self.body, "base": "outdated"})
        self.assertEqual(code, 409)
        self.assertEqual(versions_roles.toutes(), [])

    def test_permission_header_refused(self):
        self.connecter()
        body = {**self.body, "corps": "---\nfournisseur: local\nniveau: 4\n---\n" + self.body["corps"]}
        self.assertEqual(self.req("POST", self.url + "/proposer", body)[0], 403)

    def test_proposal_does_not_activate_or_modify_stable(self):
        before = roles.get(self.role["nom"])["corps"]
        p = self.candidate()
        self.assertEqual(p["statut"], "proposee")
        self.assertEqual(roles.get(self.role["nom"])["corps"], before)
        self.assertIsNone(versions_roles.actif(self.role["nom"]))
        self.assertNotIn("fichier", p)
        code, data, _ = self.req("GET", "/api/v2/atelier/candidats/" + p["id"])
        self.assertEqual(code, 200)
        self.assertIn("diff", data)

    def test_approval_requires_the_exact_reviewed_hash(self):
        p = self.candidate()
        url = "/api/v2/atelier/candidats/" + p["id"] + "/decider"
        self.assertEqual(self.req("POST", url, {"action": "essayer", "empreinte": "wrong"})[0], 409)
        self.assertEqual(versions_roles.get(p["id"])["statut"], "proposee")

    def test_canary_then_withdraw_keeps_stable_unchanged(self):
        before = self.role["corps"]
        p = self.candidate()
        url = "/api/v2/atelier/candidats/" + p["id"] + "/decider"
        code, data, _ = self.req("POST", url, {"action": "essayer", "empreinte": p["empreinte"]})
        self.assertEqual(code, 200, data)
        self.assertEqual(data["candidat"]["statut"], "canari")
        self.assertLessEqual(data["candidat"]["pct"], 50)
        self.assertEqual(roles.get(self.role["nom"])["corps"], before)
        code, data, _ = self.req("POST", url, {"action": "retirer", "empreinte": p["empreinte"]})
        self.assertEqual(code, 200)
        self.assertEqual(data["candidat"]["statut"], "retiree")
        self.assertIsNone(versions_roles.actif(self.role["nom"]))

    def test_stable_promotion_not_exposed(self):
        p = self.candidate()
        url = "/api/v2/atelier/candidats/" + p["id"] + "/decider"
        self.assertEqual(self.req("POST", url, {"action": "promouvoir", "empreinte": p["empreinte"]})[0], 403)

    def test_changed_candidate_cannot_be_approved(self):
        p = self.candidate()
        state = store.read_json(versions_roles.FILE, {})
        state["propositions"][0]["corps"] += " contenu modifie apres revue"
        store.write_json(versions_roles.FILE, state)
        url = "/api/v2/atelier/candidats/" + p["id"]
        self.assertEqual(self.req("GET", url)[0], 400)
        self.assertEqual(self.req("POST", url + "/decider", {"action": "essayer", "empreinte": p["empreinte"]})[0], 409)

    def test_bounded_brief_and_reason(self):
        self.connecter()
        for fields in ({"corps": "short"}, {"corps": "x" * 25000}, {"pourquoi": ""}):
            self.assertEqual(self.req("POST", self.url + "/proposer", {**self.body, **fields})[0], 400)

    def test_unknown_role(self):
        self.connecter()
        self.assertEqual(self.req("POST", "/api/v2/atelier/agents/inconnu/verifier", self.body)[0], 404)


if __name__ == "__main__": unittest.main()
