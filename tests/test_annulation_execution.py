"""Arrêt réel des CLI et de leurs enfants : aucun appel de modèle ni service externe."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import test_missions
from jarvis import adaptateurs as ad, coureur, missions as mi
from jarvis.annulation import ControleExecution, ExecutionAnnulee, executer_processus


PROCESSUS_LONG = r'''import json, os, signal, subprocess, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
enfant = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"])
Path(sys.argv[1]).write_text(json.dumps([os.getpid(), enfant.pid]))
while True:
    time.sleep(0.02)
'''


def vivant(pid):
    try:
        # Un petit-enfant tué peut rester zombie jusqu'au passage de l'init du conteneur.
        etat = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0]
        return etat not in ("Z", "X")
    except FileNotFoundError:
        return False


def tous_arretes(pids):
    # SIGKILL est asynchrone : attendre sa livraison aux petits-enfants, que Python ne peut pas waitpid().
    limite = time.monotonic() + 0.5
    while any(vivant(pid) for pid in pids) and time.monotonic() < limite:
        time.sleep(0.01)
    return not any(vivant(pid) for pid in pids)


class ProcessusAnnulationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-annulation-")
        self.addCleanup(self.tmp.cleanup)
        self.pids = Path(self.tmp.name) / "pids.json"

    def annuler_apres_demarrage(self, jeton):
        def attendre():
            limite = time.monotonic() + 3
            while not self.pids.exists() and time.monotonic() < limite:
                time.sleep(0.01)
            jeton.annuler("annulation du test")
        fil = threading.Thread(target=attendre)
        fil.start()
        self.addCleanup(fil.join, 4)

    def verifier_arret(self):
        pids = json.loads(self.pids.read_text())
        self.assertTrue(pids)
        self.assertTrue(tous_arretes(pids), f"processus encore actif : {pids}")

    def test_annulation_tue_le_groupe_meme_si_term_est_ignore(self):
        jeton = ControleExecution()
        self.annuler_apres_demarrage(jeton)
        debut = time.monotonic()
        with self.assertRaises(ExecutionAnnulee):
            executer_processus([sys.executable, "-c", PROCESSUS_LONG, str(self.pids)], timeout=20, annulation=jeton)
        self.assertLess(time.monotonic() - debut, 3)
        self.verifier_arret()

    def test_timeout_tue_aussi_les_enfants(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            executer_processus([sys.executable, "-c", PROCESSUS_LONG, str(self.pids)], timeout=0.3)
        self.verifier_arret()

    def test_jeton_annule_interdit_un_nouveau_processus(self):
        jeton = ControleExecution()
        jeton.annuler("bail perdu")
        with self.assertRaises(ExecutionAnnulee):
            executer_processus([sys.executable, "-c", PROCESSUS_LONG, str(self.pids)], timeout=2, annulation=jeton)
        self.assertFalse(self.pids.exists())

    def test_un_cli_termine_ne_garde_pas_un_outil_en_arriere_plan(self):
        script = ("import json,os,subprocess,sys; from pathlib import Path; "
                  "enfant=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
                  "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
                  "Path(sys.argv[1]).write_text(json.dumps([os.getpid(),enfant.pid])); print('terminé')")
        r = executer_processus([sys.executable, "-c", script, str(self.pids)], timeout=2)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "terminé")
        self.verifier_arret()

    def test_les_deux_adaptateurs_propaguent_le_jeton(self):
        faux = Path(self.tmp.name) / "faux-cli"
        faux.write_text("#!/usr/bin/env python3\nimport os, signal, time\nfrom pathlib import Path\n"
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        "Path(os.environ['JARVIS_TEST_STOP']).write_text(str(os.getpid()))\n"
                        "time.sleep(60)\n")
        faux.chmod(0o755)
        for classe in (ad.ClaudeCode, ad.Codex):
            with self.subTest(adaptateur=classe.nom):
                self.pids.unlink(missing_ok=True)
                jeton = ControleExecution()
                self.annuler_apres_demarrage(jeton)
                with mock.patch.dict(os.environ, {"JARVIS_TEST_STOP": str(self.pids)}):
                    with self.assertRaises(ExecutionAnnulee):
                        classe(binaire=str(faux)).executer({"travail": {"type": "analyse_document", "document": "test"},
                                                           "delai_s": 20, "_annulation": jeton})
                self.assertTrue(tous_arretes([int(self.pids.read_text())]))

    def test_la_preparation_web_est_interrompue_avant_le_modele(self):
        jeton = ControleExecution(expire=time.time() + 0.2)
        env = {"travail": {"type": "contextualiser", "url": "https://example.invalid/"},
               "delai_s": 20, "_annulation": jeton}
        debut = time.monotonic()
        with mock.patch.object(coureur, "_LECTURE_PAGE", "import time; time.sleep(60)"):
            with self.assertRaises(ExecutionAnnulee):
                coureur.preparer_pieces(env, Path(self.tmp.name))
        self.assertLess(time.monotonic() - debut, 2)


class ProcessusTestAdaptateur(ad.Adaptateur):
    nom = "factice"
    capacites = {"analyse": True, "annulation": True}

    def __init__(self, pids):
        self.pids = pids
        self.appels = 0

    def executer(self, env):
        self.appels += 1
        ad.executer_processus([sys.executable, "-c", PROCESSUS_LONG, str(self.pids)], timeout=30,
                             annulation=ad.controle(env))
        return {"issue": "reussi", "contenu": "## Résumé\nrésultat tardif\n## Points clés\n- test", "factice": True}


class CoureurAnnulationTest(test_missions.Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-coureur-arret-")
        self.addCleanup(self.tmp.cleanup)
        self.pids = Path(self.tmp.name) / "pids.json"

    def preparer(self, **kw):
        m = self.mission_simple()
        rid, secret = self.executant()
        transport = coureur.TransportLocal(rid, secret)
        adaptateur = ProcessusTestAdaptateur(self.pids)
        cr = coureur.Coureur(transport, {"factice": adaptateur}, intervalle_battement=0.03, **kw)
        return m, transport, adaptateur, cr

    def test_annulation_mission_stoppe_processus_sans_artefact_tardif(self):
        m, transport, adaptateur, cr = self.preparer()
        battement = transport.battement

        def battre(env):
            if self.pids.exists():
                mi.annuler_mission(self.org, m["mission_id"], par="test")
            return battement(env)

        debut = time.monotonic()
        with mock.patch.object(transport, "battement", side_effect=battre), mock.patch.object(transport, "rendre") as rendre:
            r = cr.tour()
        self.assertLess(time.monotonic() - debut, 3)
        self.assertEqual(r["etat"], "perime")
        self.assertTrue(r["execution_arretee"])
        self.assertEqual(adaptateur.appels, 1)
        self.assertEqual(mi.mission(self.org, m["mission_id"])["statut"], mi.CANCELLED)
        self.assertEqual(mi.mission(self.org, m["mission_id"])["artefacts"], [])
        self.assertEqual(cr._en_attente(), [])
        rendre.assert_not_called()
        self.assertTrue(tous_arretes(json.loads(self.pids.read_text())))

    def test_panne_du_battement_interrompt_au_lieu_de_laisser_un_thread_mort(self):
        _, transport, _, cr = self.preparer()
        battement = transport.battement

        def battre(env):
            if self.pids.exists():
                raise OSError("transport hors ligne")
            return battement(env)

        with mock.patch.object(transport, "battement", side_effect=battre), mock.patch.object(transport, "rendre") as rendre:
            r = cr.tour()
        self.assertEqual(r["etat"], "perime")
        self.assertIn("battement indisponible", r["raison"])
        rendre.assert_not_called()
        self.assertTrue(tous_arretes(json.loads(self.pids.read_text())))

    def test_battement_bloque_ne_retarde_pas_l_expiration_locale(self):
        _, transport, _, cr = self.preparer()
        battement = transport.battement
        liberer = threading.Event()
        appels = 0

        def battre(env):
            nonlocal appels
            appels += 1
            if appels == 1:
                return {**battement(env), "bail_expire": time.time() + 0.3}
            liberer.wait(5)
            return {"continuer": True, "bail_expire": time.time() + 30}

        debut = time.monotonic()
        try:
            with mock.patch.object(transport, "battement", side_effect=battre), mock.patch.object(transport, "rendre") as rendre:
                r = cr.tour()
                rendre.assert_not_called()
        finally:
            liberer.set()
        self.assertLess(time.monotonic() - debut, 3)
        self.assertEqual(r["etat"], "perime")
        self.assertIn("expiré localement", r["raison"])
        self.assertTrue(tous_arretes(json.loads(self.pids.read_text())))

    def test_refus_initial_ne_lance_aucun_adaptateur(self):
        _, transport, adaptateur, cr = self.preparer()
        with mock.patch.object(transport, "battement", return_value={"continuer": False, "raison": "annulée"}):
            r = cr.tour()
        self.assertEqual(r["etat"], "perime")
        self.assertEqual(adaptateur.appels, 0)
        self.assertFalse(self.pids.exists())

    def test_stop_du_service_interrompt_un_processus_en_cours(self):
        stop = threading.Event()
        _, transport, _, cr = self.preparer(stop=stop)

        def demander_arret():
            limite = time.monotonic() + 3
            while not self.pids.exists() and time.monotonic() < limite:
                time.sleep(0.01)
            stop.set()

        fil = threading.Thread(target=demander_arret)
        fil.start()
        self.addCleanup(fil.join, 4)
        with mock.patch.object(transport, "rendre") as rendre:
            r = cr.tour()
        self.assertEqual(r["etat"], "perime")
        self.assertIn("arrêt du service", r["raison"])
        rendre.assert_not_called()
        self.assertTrue(tous_arretes(json.loads(self.pids.read_text())))

    def test_stop_pose_avant_tour_ne_reclame_rien(self):
        stop = threading.Event()
        stop.set()
        _, transport, adaptateur, cr = self.preparer(stop=stop)
        with mock.patch.object(transport, "reclamer") as reclamer:
            self.assertEqual(cr.tour()["etat"], "arret")
        reclamer.assert_not_called()
        self.assertEqual(adaptateur.appels, 0)

    def test_sigterm_du_pilote_laisse_le_nettoyage_du_cli_se_terminer(self):
        programme = '''import json, signal, sys, threading, time
from jarvis import adaptateurs as ad, coureur
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
env = {"version":1,"tenant_id":"O","mission_id":"M","tache_id":"T","tentative_id":"A",
       "correlation_id":"C","capacites":["analyse"],"niveau":"L1","fournisseur":"factice",
       "travail":{"type":"analyse_document","document":"test"},"delai_s":30,"limites":{},"bail_jeton":1,
       "bail_expire":time.time()+10,"cle_idempotence":"T:1","decision_politique":"test"}
class Transport:
    id = "pilote-test"
    def reclamer(self): return env
    def demarrer(self, env): pass
    def battement(self, env): return {"continuer":True,"bail_expire":time.time()+10}
    def rendre(self, resultat): raise RuntimeError("aucun résultat après arrêt")
class Fournisseur(ad.Adaptateur):
    def executer(self, env):
        ad.executer_processus([sys.executable,"-c",sys.argv[1],sys.argv[2]],timeout=30,annulation=ad.controle(env))
        raise RuntimeError("le CLI aurait dû être interrompu")
r = coureur.Coureur(Transport(), {"factice":Fournisseur()}, stop=stop, intervalle_battement=0.03).tour()
print(json.dumps(r))
'''
        env = {**os.environ, "PYTHONPATH": str(Path(coureur.__file__).resolve().parents[1]),
               "JARVIS_STATE_DIR": str(Path(self.tmp.name) / "etat-pilote")}
        pilote = subprocess.Popen([sys.executable, "-c", programme, PROCESSUS_LONG, str(self.pids)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            limite = time.monotonic() + 3
            while not self.pids.exists() and pilote.poll() is None and time.monotonic() < limite:
                time.sleep(0.01)
            self.assertTrue(self.pids.exists(), "le CLI du pilote n'a pas démarré")
            pilote.send_signal(signal.SIGTERM)
            stdout, stderr = pilote.communicate(timeout=4)
            self.assertEqual(pilote.returncode, 0, stderr)
            r = json.loads(stdout)
            self.assertEqual(r["etat"], "perime")
            self.assertTrue(r["execution_arretee"])
            self.assertTrue(tous_arretes(json.loads(self.pids.read_text())))
        finally:
            if pilote.poll() is None:
                pilote.kill()
                pilote.communicate(timeout=2)


if __name__ == "__main__":
    unittest.main()
