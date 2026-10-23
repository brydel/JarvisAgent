"""Contrat pur : ces tests ne demandent ni SDK ni serveur Temporal."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis_temporal.contrat import groupes, operation, valider, workflow_id


def exemple():
    return json.loads((Path(__file__).resolve().parents[1] / "exemples/projet.json").read_text())


class ContratTests(unittest.TestCase):
    def test_exemple_et_copie(self):
        spec = exemple()
        copie = valider(spec)
        copie["steps"][0]["operation"]["arguments"]["url"] = "modifiée"
        self.assertNotEqual(copie, spec)
        self.assertEqual([[s["id"] for s in g] for g in groupes(spec["steps"])],
                         [["documentation-python"], ["documentation-temporal"]])

    def test_identite_stable_hors_numero_de_tentative(self):
        spec = exemple()
        requete = operation(spec, spec["steps"][0])
        self.assertEqual(requete, operation(copy.deepcopy(spec), copy.deepcopy(spec["steps"][0])))
        self.assertNotEqual(requete["operation_id"], operation(spec, spec["steps"][1])["operation_id"])
        self.assertEqual(requete["project"], spec["project"])
        self.assertEqual(workflow_id(spec), "jarvis-prototype-recherche-documentation")

    def test_pas_de_propriete_locale_implicite(self):
        for moteur in ("local", "temporal", "handoff_pending"):
            with self.subTest(moteur=moteur), self.assertRaises(ValueError):
                spec = exemple(); spec["engine"] = moteur; valider(spec)
        with self.assertRaises(ValueError):
            spec = exemple(); spec["mission_id"] = "MI-123"; valider(spec)

    def test_dag_invalide(self):
        def verifier(modifier):
            spec = exemple(); modifier(spec)
            with self.assertRaises(ValueError):
                valider(spec)
        verifier(lambda s: s["steps"][0]["depends_on"].append("absente"))
        verifier(lambda s: s["steps"][0]["depends_on"].append("documentation-temporal"))
        verifier(lambda s: s["steps"][1]["depends_on"].append("documentation-python"))
        verifier(lambda s: s["steps"][0]["depends_on"].append("documentation-python"))
        verifier(lambda s: s["steps"].append(copy.deepcopy(s["steps"][0])))

    def test_types_stricts_et_bornes(self):
        modifications = [
            lambda s: s.update(version=True),
            lambda s: s.update(project=""),
            lambda s: s.update(steps=[]),
            lambda s: s["steps"][0].update(timeout_s=True),
            lambda s: s["steps"][0].update(timeout_s=301),
            lambda s: s["steps"][0].update(phase=[]),
            lambda s: s["steps"][0]["operation"].update(cost_cents=-1),
            lambda s: s["steps"][0]["operation"].update(operation_id="imposée"),
            lambda s: s["steps"][0]["operation"]["arguments"].update(grand="x" * 48_000),
            lambda s: s["steps"][0]["operation"]["arguments"].update(nombre=float("nan")),
        ]
        for modifier in modifications:
            with self.subTest(modifier=modifier):
                spec = exemple(); modifier(spec)
                with self.assertRaises(ValueError):
                    valider(spec)

    def test_secret_interdit_dans_historique(self):
        for cle in ("password", "Authorization", "cookie", "api_key", "jeton"):
            spec = exemple(); spec["steps"][0]["operation"]["arguments"]["imbrique"] = [{cle: "fixture"}]
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                valider(spec)


if __name__ == "__main__":
    unittest.main()
