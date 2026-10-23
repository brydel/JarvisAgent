"""Contrats agent/tâche/run : bornes, références, copies et empreintes stables."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from jarvis import contrats


class ContratsTest(unittest.TestCase):
    def agent(self, **champs):
        return {"version": 1, "id": "AG-analyste", "role": "recherche", "profile": "documentaire", **champs}

    def tache(self, **champs):
        return {"version": 1, "id": "TK-analyse", "agent_id": "AG-analyste", "objective": "Analyser les sources du projet",
                "project": "projet-personnel", "acceptance": ["Chaque conclusion cite une source consultée."], **champs}

    def execution(self, **champs):
        return {"version": 1, "id": "RUN-analyse", "agent_id": "AG-analyste", "task_id": "TK-analyse",
                "status": "planned", "source": "board", **champs}

    def test_demande_documentaire_normalisee_sans_accorder_capacite(self):
        a = contrats.valider_agent(self.agent())
        self.assertEqual(a["tools"], [])
        self.assertEqual(a["required_capabilities"], [])
        self.assertEqual(a["provider"], "auto")
        self.assertEqual(a["budget"], {"max_tokens": None, "max_cost_cents": None, "max_duration_s": 300})
        self.assertEqual(a["delegation"], {"max_depth": 0, "max_children": 0})
        self.assertEqual(a, contrats.valider_agent(a))

    def test_demande_outillee_copie_les_limites_et_references(self):
        entree = self.agent(profile="outille", tools=["web.search", "mcp:linear:get_issue"],
                             required_capabilities=["network", "tool_calls"], budget={"max_tokens": 50_000},
                             delegation={"max_children": 2})
        avant = copy.deepcopy(entree)
        a = contrats.valider_agent(entree)
        a["tools"].append("mail.send")
        a["budget"]["max_tokens"] = 1
        self.assertEqual(entree, avant)
        self.assertEqual(a["delegation"], {"max_depth": 0, "max_children": 2})

    def test_tache_explicite_et_defauts_locaux(self):
        t = contrats.valider_tache(self.tache(inputs=["artifact://sources-1"], depends_on=["TK-recherche"]))
        self.assertEqual(t["max_attempts"], 1)
        self.assertEqual(t["execution_engine"], "local")
        self.assertIsNone(t["mandate_id"])
        self.assertEqual(t["required_tools"], [])
        self.assertEqual(t["depends_on"], ["TK-recherche"])
        self.assertEqual(contrats.valider_tache(self.tache(project=""))["project"], "")

    def test_run_ne_fabrique_ni_session_ni_preuve(self):
        r = contrats.valider_run(self.execution())
        self.assertIsNone(r["session_ref"])
        self.assertEqual(r["evidence"], [])
        entree = self.execution(status="succeeded", source="workmux", session_ref="tmux://jarvis/wm-ticket-1",
                          evidence=["artifact://tests-1", "git:sha256:abcdef"])
        r = contrats.valider_run(entree)
        r["evidence"].clear()
        self.assertEqual(len(entree["evidence"]), 2)

    def test_champs_obligatoires_et_versions_majeures_refuses(self):
        for validator, base in ((contrats.valider_agent, self.agent()), (contrats.valider_tache, self.tache()),
                                (contrats.valider_run, self.execution())):
            for key in ("version", "id"):
                with self.subTest(validator=validator.__name__, absent=key):
                    value = {k: v for k, v in base.items() if k != key}
                    with self.assertRaises(contrats.ContratError):
                        validator(value)
            for version in (True, 1.0, "1", 0, 2):
                with self.subTest(validator=validator.__name__, version=version):
                    with self.assertRaises(contrats.ContratError):
                        validator({**base, "version": version})

    def test_types_numeriques_stricts_et_bornes(self):
        for budget in ({"max_tokens": True}, {"max_cost_cents": -1}, {"max_duration_s": 0},
                       {"max_cost_cents": float("nan")}, {"max_tokens": float("inf")},
                       {"max_tokens": 2.0}, {"max_duration_s": 86401}):
            with self.subTest(budget=budget):
                with self.assertRaises(contrats.ContratError):
                    contrats.valider_agent(self.agent(budget=budget))
        for value in (False, 0, -1, 101):
            with self.subTest(max_attempts=value):
                with self.assertRaises(contrats.ContratError):
                    contrats.valider_tache(self.tache(max_attempts=value))
        with self.assertRaises(contrats.ContratError):
            contrats.valider_agent(self.agent(delegation={"max_depth": True}))

    def test_champs_inconnus_authentifiants_et_disponibilite_refuses(self):
        secret = "valeur-privee-ne-jamais-imprimer"
        for value in (self.agent(token=secret), self.agent(available=True),
                      self.agent(budget={"secret": secret}), self.agent(delegation={"credential": secret})):
            with self.subTest(champs=list(value)):
                with self.assertRaises(contrats.ContratError) as erreur:
                    contrats.valider_agent(value)
                self.assertNotIn(secret, str(erreur.exception))
        for validator, value in ((contrats.valider_tache, self.tache(api_key=secret)),
                                  (contrats.valider_run, self.execution(credentials={"token": secret}))):
            with self.assertRaises(contrats.ContratError):
                validator(value)

    def test_elements_inconnus_et_listes_dupliquees_refuses(self):
        for tools in (["web.search", "web.search"], [42], [True], [{"id": "web.search"}], "web.search"):
            with self.subTest(tools=tools):
                with self.assertRaises(contrats.ContratError):
                    contrats.valider_agent(self.agent(tools=tools))
        with self.assertRaises(contrats.ContratError):
            contrats.valider_tache(self.tache(acceptance=[]))
        with self.assertRaises(contrats.ContratError):
            contrats.valider_tache(self.tache(acceptance=[" "]))

    def test_auto_dependance_refusee(self):
        with self.assertRaises(contrats.ContratError):
            contrats.valider_tache(self.tache(depends_on=["TK-analyse"]))

    def test_enum_identifiants_et_tailles_invalides_refuses(self):
        for value in (self.agent(profile="illimite"), self.agent(provider=""), self.agent(id=""),
                      self.agent(id="AG\nagent"), self.agent(role="\x00"), self.agent(tools=["x"] * 257)):
            with self.assertRaises(contrats.ContratError):
                contrats.valider_agent(value)
        with self.assertRaises(contrats.ContratError):
            contrats.valider_tache(self.tache(execution_engine="non_installe"))
        with self.assertRaises(contrats.ContratError):
            contrats.valider_run(self.execution(source="invente"))
        with self.assertRaises(contrats.ContratError):
            contrats.valider_run(self.execution(session_ref=""))

    def test_budget_inconnu_distinct_de_zero_et_fournisseur_factice(self):
        inconnu = contrats.valider_agent(self.agent(provider="factice"))
        zero = contrats.valider_agent(self.agent(budget={"max_tokens": 0, "max_cost_cents": 0}))
        self.assertIsNone(inconnu["budget"]["max_tokens"])
        self.assertEqual(zero["budget"]["max_tokens"], 0)
        self.assertEqual(zero["budget"]["max_cost_cents"], 0)
        self.assertEqual(inconnu["provider"], "factice")
        historique = contrats.valider_agent(self.agent(budget={"max_duration_s": None}))
        self.assertIsNone(historique["budget"]["max_duration_s"])

    def test_schemas_publiables_et_non_mutables_par_un_appelant(self):
        s = contrats.schemas()
        self.assertEqual(s["version"], 1)
        self.assertFalse(s["agent"]["additionalProperties"])
        json.dumps(s, ensure_ascii=False, allow_nan=False)
        s["agent"]["properties"]["tools"]["default"].append("mail.send")
        self.assertEqual(contrats.valider_agent(self.agent())["tools"], [])
        self.assertEqual(contrats.schemas()["agent"]["properties"]["tools"]["default"], [])

    def test_empreinte_stable_sur_ordre_des_cles_et_sensible_aux_limites(self):
        a = contrats.valider_agent(self.agent())
        b = dict(reversed(list(a.items())))
        self.assertEqual(contrats.empreinte(a), contrats.empreinte(b))
        b["budget"] = {**a["budget"], "max_cost_cents": 5}
        self.assertNotEqual(contrats.empreinte(a), contrats.empreinte(b))
        self.assertEqual(len(contrats.empreinte(a)), 64)

    def test_empreinte_refuse_valeurs_non_json_et_nombres_non_finis(self):
        for value in ({"x": float("nan")}, {"x": float("inf")}, {1: "texte"}, {"x": {1, 2}}, {"x": (1, 2)}):
            with self.subTest(value_type=type(value)):
                with self.assertRaises(contrats.ContratError):
                    contrats.empreinte(value)
        boucle = []
        boucle.append(boucle)
        with self.assertRaises(contrats.ContratError):
            contrats.empreinte(boucle)


if __name__ == "__main__":
    unittest.main()
