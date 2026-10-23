"""SDK réel et sandbox ; ces tests ne prouvent pas le replay d'un serveur."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_contrat import exemple

SDK = importlib.util.find_spec("temporalio") is not None
if SDK:
    from temporalio import workflow
    from temporalio.exceptions import ApplicationError
    from temporalio.testing import ActivityEnvironment
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
    from jarvis_temporal.activites import Activites
    from jarvis_temporal.workflow import ProjetWorkflow


@unittest.skipUnless(SDK, "Installer le SDK isolé avec services/workflows_temporal/requirements.txt")
class SDKTests(unittest.IsolatedAsyncioTestCase):
    async def test_definition_acceptee_par_sandbox_sdk(self):
        SandboxedWorkflowRunner().prepare_workflow(workflow._Definition.must_from_class(ProjetWorkflow))

    async def test_dependance_attend_resultat_precedent(self):
        instance = ProjetWorkflow()
        spec = exemple()
        ids = []
        def demarrer(nom, demande, **kw):
            self.assertEqual(nom, "jarvis.appeler_passerelle.v1")
            if ids:
                self.assertEqual(instance.etapes["documentation-python"], "succeeded")
            ids.append(demande["operation_id"])
            f = asyncio.get_running_loop().create_future()
            f.set_result({"status": "succeeded", "operation_id": demande["operation_id"]})
            return f
        with patch("jarvis_temporal.workflow.workflow.start_activity", side_effect=demarrer), \
             patch("jarvis_temporal.workflow.workflow.wait_condition", new=AsyncMock()):
            resultat = await instance.run(spec)
        self.assertEqual(resultat["status"], "succeeded")
        self.assertEqual(set(instance.etapes.values()), {"succeeded"})
        self.assertEqual(len(set(ids)), 2)

    async def test_echec_bloque_etape_dependante(self):
        instance = ProjetWorkflow()
        def demarrer(*args, **kw):
            f = asyncio.get_running_loop().create_future()
            f.set_exception(ApplicationError("effet incertain", type="EffetIncertain", non_retryable=True))
            return f
        with patch("jarvis_temporal.workflow.workflow.start_activity", side_effect=demarrer) as appel, \
             patch("jarvis_temporal.workflow.workflow.wait_condition", new=AsyncMock()):
            with self.assertRaises(ApplicationError):
                await instance.run(exemple())
        self.assertEqual(appel.call_count, 1)
        self.assertEqual(instance.etapes["documentation-python"], "blocked")
        self.assertEqual(instance.etapes["documentation-temporal"], "planned")

    async def test_signal_annulation_empeche_depart(self):
        instance = ProjetWorkflow()
        instance.annuler()
        with patch("jarvis_temporal.workflow.workflow.start_activity") as appel, \
             patch("jarvis_temporal.workflow.workflow.wait_condition", new=AsyncMock()):
            with self.assertRaises(ApplicationError):
                await instance.run(exemple())
        appel.assert_not_called()

    async def test_activite_incertaine_non_reessayable(self):
        controleur = Mock()
        controleur.executer.return_value = {"status": "unknown", "operation_id": "op-1"}
        with self.assertRaises(ApplicationError) as exc:
            ActivityEnvironment().run(Activites(controleur).executer, {"operation_id": "op-1"})
        self.assertTrue(exc.exception.non_retryable)
        self.assertEqual(exc.exception.type, "EffetIncertain")


if __name__ == "__main__":
    unittest.main()
