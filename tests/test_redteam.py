"""Contrats, périmètre, reprise et véritable Semgrep lorsque l'outil est installé."""
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
sys.path.insert(0, str(ROOT / 'services/noeud_jetson'))
import redteam_engine as engine
import redteam_models as models
import jarvis_noeud
from jarvis import redteam, config, store


class RedTeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'source'
        self.root.mkdir()
        self.state = base / 'state'
        self.policy = engine.Policy(self.root, self.state, os.environ.get('JARVIS_REDTEAM_TEST_SEMGREP', 'semgrep'))
        self.req = {'mission_id': 'RT-test', 'deadline': time.time() + 300}
        (self.root / 'test.py').write_text('import subprocess\nsubprocess.run(user_input, shell=True)\n')

    def test_scope_and_deadline(self):
        for bad in ({**self.req, 'root': '/'}, {**self.req, 'tools': ['shell']},
                    {**self.req, 'deadline': float('nan')}, {**self.req, 'deadline': True},
                    {**self.req, 'deadline': time.time() - 1}, {**self.req, 'mission_id': '../evil'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                engine.request(bad)
        with self.assertRaises(ValueError):
            engine.Policy(self.root, self.root / 'state').validate()

    def test_snapshot_omits_links_and_configs(self):
        outside = self.root.parent / 'outside.py'
        outside.write_text('secret')
        (self.root / 'linked.py').symlink_to(outside)
        (self.root / 'linked-dir').symlink_to(self.root.parent, target_is_directory=True)
        (self.root / '.semgrep.yml').write_text('untrusted config')
        dest = self.root.parent / 'snapshot'
        dest.mkdir()
        manifest = engine.snapshot(self.policy, dest)
        self.assertEqual([f['path'] for f in manifest], ['test.py'])
        self.assertEqual((dest / 'test.py').read_bytes(), (self.root / 'test.py').read_bytes())

    def test_oversize_is_failure(self):
        (self.root / 'test.py').write_bytes(b'a' * 1_000_001)
        with self.assertRaises(ValueError):
            engine.snapshot(self.policy, self.root.parent / 'copy')

    def test_resume_and_idempotency(self):
        audit = {'tool': 'unit-test-double', 'findings': []}
        with patch.object(engine, 'scan', return_value=audit) as scan:
            with self.assertRaises(InterruptedError):
                engine.Engine(self.policy).run(self.req, interrupt_after='EXECUTE')
            result = engine.Engine(self.policy).run(self.req)
            self.assertEqual(result['steps'], ['PLAN', 'EXECUTE', 'OBSERVE', 'VERIFY', 'REFLECT', 'DELEGATE', 'REPORT'])
            self.assertEqual(scan.call_count, 1)
            self.assertEqual(result, engine.Engine(self.policy).run(self.req))
            self.assertEqual(scan.call_count, 1)
            self.assertFalse(result['verification']['impact_confirmed'])
            self.assertEqual(result['delegation']['authorization_scope']['tools'], [])
            with self.assertRaises(ValueError):
                engine.Engine(self.policy).run({**self.req, 'deadline': time.time() + 500})

    def test_error_is_not_success(self):
        with patch.object(engine, 'scan', side_effect=RuntimeError('tool unavailable')):
            with self.assertRaises(RuntimeError):
                engine.Engine(self.policy).run(self.req)
        with sqlite3.connect(self.state / 'missions.sqlite3') as db:
            value = json.loads(db.execute('SELECT result FROM missions').fetchone()[0])
        self.assertEqual(value['status'], 'running')
        self.assertNotIn('EXECUTE', value['steps'])

    def test_mcp_refuses_unconfigured_scope(self):
        with self.assertRaises(jarvis_noeud.ErreurNoeud):
            jarvis_noeud.appeler_outil('redteam_auditer', self.req, {})

    def test_timeout_is_structured_failure(self):
        import subprocess
        executable = self.root.parent / "slow-tool"
        executable.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
        executable.chmod(0o700)
        policy = engine.Policy(self.root, self.state, str(executable), timeout_s=1)
        with self.assertRaises(RuntimeError):
            engine.scan(policy, self.root)

    def test_proof_publication_atomic(self):
        folder = self.root.parent / "proofs"
        folder.mkdir()
        content = b"synthetic evidence"
        with patch.object(Path, "replace", side_effect=InterruptedError("test")):
            with self.assertRaises(InterruptedError):
                engine.preserve(folder, content)
        self.assertEqual(list(folder.iterdir()), [])
        engine.preserve(folder, content)
        engine.preserve(folder, content)
        self.assertEqual((folder / engine.digest(content)).read_bytes(), content)

    def test_locked_node_fails_promptly(self):
        import fcntl
        node = engine.Engine(self.policy)
        with (self.state / "engine.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                node.run(self.req)

    @unittest.skipUnless(os.environ.get('JARVIS_REDTEAM_TEST_IMAGE'), 'Image Docker réelle non configurée')
    def test_real_gateway_mandate_and_review(self):
        from jarvis import connexions, missions, noeud, outils, mandats
        conf = self.root.parent / "node.env"
        conf.write_text(f"JARVIS_REDTEAM_ROOT={self.root}\nJARVIS_REDTEAM_STATE={self.state}\n"
                        f"JARVIS_REDTEAM_IMAGE={os.environ['JARVIS_REDTEAM_TEST_IMAGE']}\n")
        with patch.object(config, 'STATE_DIR', self.root.parent / 'jarvis'), \
             patch.dict(os.environ, {'JARVIS_STOCKAGE': 'json', 'JARVIS_NOEUD_CONF': str(conf)}), \
             patch.object(missions, 'tenant_local', return_value='local'), \
             patch.object(noeud, 'reglages', return_value={'actif': True, 'connexion': 'local-rt'}):
            connexions.enregistrer({'id': 'local-rt', 'nom': 'MCP local de test, sans SSH', 'type': 'mcp_stdio',
                'command': sys.executable, 'args': [str(ROOT / 'services/noeud_jetson/jarvis_noeud.py'), 'mcp'],
                'env_allowlist': ['JARVIS_NOEUD_CONF', 'PATH'], 'outils_autorises': []}, par='test')
            authorization = redteam.authorize('local-rt', 'lab')
            result = redteam.remote(self.req, project='lab', mandate=authorization['mandat'])
            self.assertEqual(result['report']['status'], 'reported')
            self.assertTrue(result['report']['audit']['sandbox']['network_isolated'])
            self.assertEqual(result['delivery'], 'published')
            operation = outils.operation('redteam:' + self.req['mission_id'])
            self.assertEqual(operation['status'], 'succeeded')

    def test_model_parameters_before_network(self):
        with self.assertRaises(ValueError):
            models.Ollama(temperature=float('nan')).analyze({})
        with self.assertRaises(ValueError):
            models.Ollama(model='untrusted/community').analyze({})

    @unittest.skipUnless(os.environ.get('JARVIS_REDTEAM_TEST_SEMGREP'), 'Semgrep réel non configuré')
    def test_real_semgrep_and_fixed_regression(self):
        result = engine.Engine(self.policy).run(self.req)
        self.assertEqual(len(result['audit']['findings']), 1)
        self.assertEqual(result['audit']['findings'][0]['status'], 'tool_result')
        (self.root / 'test.py').write_text('import subprocess\nsubprocess.run(["uname"], shell=False)\n')
        corrected = engine.Engine(self.policy).run({**self.req, 'mission_id': 'RT-fixed'})
        self.assertEqual(corrected['audit']['findings'], [])

    @unittest.skipUnless(os.environ.get('JARVIS_REDTEAM_TEST_IMAGE'), 'Image Docker réelle non configurée')
    def test_real_mcp_call(self):
        result = jarvis_noeud.appeler_outil('redteam_auditer', self.req,
            {'redteam_root': str(self.root), 'redteam_state': str(self.state), 'redteam_semgrep': self.policy.semgrep,
             'redteam_image': os.environ.get('JARVIS_REDTEAM_TEST_IMAGE', '')})
        self.assertEqual(result['status'], 'reported')
        self.assertEqual(len(result['audit']['findings']), 1)

    def test_jarvis_publication_idempotent_and_reply(self):
        state = self.root.parent / 'jarvis-state'
        with patch.object(config, 'STATE_DIR', state), patch.dict(os.environ, {'JARVIS_STOCKAGE': 'json'}):
            from jarvis import communaute, missions
            with patch.object(engine, 'scan', return_value={'tool': 'unit-test-double', 'findings': []}):
                report = engine.Engine(self.policy).run(self.req)
            with patch.object(missions, 'tenant_local', return_value='local'):
                first = redteam.retain(report, node='test', project='lab')
                second = redteam.retain(report, node='test', project='lab')
                self.assertEqual(first['review_thread'], second['review_thread'])
                communaute.publier('lab', '{"verdict":"insufficient_evidence","evidence":[]}', auteur='qa-test',
                    type='revue', parent_id=first['review_thread'], tenant_id='local')
                thread = redteam.reviews('test:RT-test')
                self.assertTrue(thread)
                self.assertEqual(redteam.overview()[0]['delivery'], 'published')
                self.assertFalse(report['verification']['impact_confirmed'])


if __name__ == '__main__':
    unittest.main()
