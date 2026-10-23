"""Noeud GPU (Jetson) comme extension : connexion MCP stdio, passerelle sous mandat, audio du Board, pannes.

Un faux `ssh` lance localement le vrai point d'entrée du noeud (services/noeud_jetson/jarvis_noeud.py, commande
forcée comprise) branché sur le vrai service résident avec un moteur factice : ni GPU, ni réseau, ni SSH réel.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

import test_board_v2 as tb

from jarvis import adaptateurs as ad, cli, config, coureur, mandats, missions as mi, noeud, outils  # noqa: E402

RACINE = Path(__file__).resolve().parents[1] / "services" / "noeud_jetson"
_spec = importlib.util.spec_from_file_location("jarvis_noeud_service_test", RACINE / "service.py")
service = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = service
_spec.loader.exec_module(service)
JETON = "test-only-not-a-real-secret-" * 2

FAUX_SSH = """#!{python}
# Faux ssh : ignore les options, garde la commande distante et la passe à la commande forcée du noeud.
import os, sys
sys.path.insert(0, {racine!r})
os.environ["JARVIS_NOEUD_CONF"] = {conf!r}
distant = sys.argv[sys.argv.index("--") + 2:]
os.environ["SSH_ORIGINAL_COMMAND"] = " ".join(distant)
import jarvis_noeud
sys.exit(jarvis_noeud.principal(["ssh"]))
"""


class MoteurFactice:
    """Faux Whisper (interface de service.Whisper)."""
    nom, charge = "factice-small", False

    def __init__(self):
        self.appels = 0

    def transcrire(self, chemin, langue):
        self.appels += 1
        return {"texte": "Rappelle-moi d'envoyer le devis à Repriceo vendredi.", "langue": langue, "segments": 1}

    def decharger(self):
        pass


class LlmFactice:
    """Faux modèle local (interface de service.Ollama)."""
    nom, charge = "local-factice:4b", False

    def __init__(self):
        self.appels = []

    def present(self):
        return True

    def discuter(self, consigne, document, max_jetons, image=None):
        self.appels.append((consigne, document, image))
        texte = "Texte visible : Maquette — Page d'accueil" if image else "Résumé : envoyer le devis vendredi."
        return {"texte": texte, "jetons_entree": 30, "jetons_sortie": 8, "modele": self.nom}

    def decharger(self):
        pass


class NoeudTest(tb.Base):
    def setUp(self):
        super().setUp()
        mi.declarer_connexion(self.org, "factice", "factice")
        rid, secret = mi.enroler_executant(self.org, "poste", capacites=["analyse"], fournisseurs=["factice"])
        self.capteur = tb.Capteur()
        self.cr = coureur.Coureur(coureur.TransportLocal(rid, secret), {"factice": self.capteur})
        d = Path(tempfile.mkdtemp(prefix="jarvis-noeud-test-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.moteur, self.llm = MoteurFactice(), LlmFactice()
        reglages = service.Reglages(jeton=JETON, port=0, entree=str(d / "entree"))
        self.srv = service.serveur(reglages, service.Moteurs(reglages, whisper=self.moteur, llm=self.llm))
        fil = threading.Thread(target=self.srv.serve_forever, daemon=True)
        fil.start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close(), fil.join(2)))
        conf = d / "env"
        conf.write_text(f"JARVIS_NOEUD_TOKEN={JETON}\nJARVIS_NOEUD_PORT={self.srv.server_port}\n"
                        f"JARVIS_NOEUD_ENTREE={d / 'entree'}\n")
        ssh = d / "faux-ssh"
        ssh.write_text(FAUX_SSH.format(python=sys.executable, racine=str(RACINE), conf=str(conf)))
        ssh.chmod(0o755)
        self.addCleanup(config.save_settings, config.settings())
        data = config.settings()
        data["noeud"].update(commande=str(ssh), cle=str(d / "cle"))
        config.save_settings(data)
        self.branche = noeud.brancher("test@noeud", par="humain")

    def deposer_audio(self):
        a = self.fichier(tb.wav(), "memo.wav")
        mi.board_ajouter(self.org, "accueil", "audio", "", auteur="test", asset_id=a["id"], contextualiser=True)
        self.assertEqual(self.cr.tour()["etat"], "fait")
        return self.capteur.vu

    def regler(self, **valeurs):
        data = config.settings()
        data["noeud"].update(valeurs)
        config.save_settings(data)

    def test_branchement_cree_connexion_outils_et_mandat_etroit(self):
        r = noeud.reglages()
        self.assertTrue(r["actif"])
        ident = self.branche["connexion"]
        catalogue = {o["id"] for o in outils.catalogue()["outils"]}
        self.assertLessEqual({f"mcp.{ident}.{o}" for o in noeud.OUTILS}, catalogue)
        m = mandats.get(self.branche["mandat"])
        self.assertEqual(m["project"], noeud.PROJET_BOARD)
        self.assertEqual(m["destinations"], [f"mcp:{ident}"])
        self.assertEqual(sorted(m["tools"]), sorted(f"mcp.{ident}.{o}" for o in noeud.OUTILS_BOARD),
                         "le mandat du Board ne couvre que la transcription")

    def test_audio_du_board_transcrit_par_le_noeud_sous_mandat(self):
        vu = self.deposer_audio()
        p = vu["pieces"]
        self.assertEqual(p["transcription"], "Rappelle-moi d'envoyer le devis à Repriceo vendredi.")
        self.assertEqual(p["note"], "")
        self.assertEqual(self.moteur.appels, 1)
        self.assertIn("transcription (noeud GPU)", [o["outil"] for o in coureur.outils_prepares(p)])
        consigne = ad._consigne(vu)
        self.assertLess(consigne.index("<<<ELEMENT"), consigne.index("devis à Repriceo"))
        self.assertLess(consigne.index("devis à Repriceo"), consigne.index("ELEMENT>>>"))
        ops = outils.operations(noeud.PROJET_BOARD)
        self.assertTrue(ops and all(o["status"] == "succeeded" and o["acteur"] == "jarvis:noeud" for o in ops),
                        "chaque appel est journalisé par la passerelle")

    def test_desactive_garde_le_comportement_actuel(self):
        self.regler(actif=False)
        p = self.deposer_audio()["pieces"]
        self.assertNotIn("transcription", p)
        self.assertIn("seuls les métadonnées sont connues", p["note"])
        self.assertEqual(self.moteur.appels, 0)

    def test_noeud_eteint_ne_bloque_pas_la_mission(self):
        self.srv.shutdown()
        self.srv.server_close()
        p = self.deposer_audio()["pieces"]
        self.assertNotIn("transcription", p)
        self.assertIn("transcription impossible", p["note"])
        self.assertIn("memo.wav", p["note"])

    def test_mandat_revoque_coupe_le_noeud(self):
        mandats.revoquer(self.branche["mandat"], par="humain")
        p = self.deposer_audio()["pieces"]
        self.assertIn("transcription impossible", p["note"])
        self.assertEqual(self.moteur.appels, 0)

    def test_image_du_board_lue_par_le_modele_local(self):
        a = self.fichier(tb.png(20, 20), "capture.png")
        mi.board_ajouter(self.org, "accueil", "image", "", auteur="test", asset_id=a["id"], contextualiser=True)
        self.assertEqual(self.cr.tour()["etat"], "fait")
        vu = self.capteur.vu
        p = vu["pieces"]
        self.assertEqual(self.moteur.appels, 0, "une image ne passe jamais par Whisper")
        self.assertEqual(p["fichier"], "piece.png", "l'image reste jointe au modèle principal")
        self.assertIn("Maquette", p["vision"])
        self.assertIsNotNone(self.llm.appels[-1][2])
        self.assertIn("lecture d'image (noeud GPU)", [o["outil"] for o in coureur.outils_prepares(p)])
        consigne = ad._consigne(vu)
        self.assertLess(consigne.index("<<<ELEMENT"), consigne.index("Maquette"))
        self.assertLess(consigne.index("Maquette"), consigne.index("ELEMENT>>>"))

    def test_image_sans_noeud_reste_lue_par_le_modele_principal(self):
        self.srv.shutdown()
        self.srv.server_close()
        a = self.fichier(tb.png(20, 20), "capture.png")
        mi.board_ajouter(self.org, "accueil", "image", "", auteur="test", asset_id=a["id"], contextualiser=True)
        self.assertEqual(self.cr.tour()["etat"], "fait")
        p = self.capteur.vu["pieces"]
        self.assertEqual(p["fichier"], "piece.png")
        self.assertNotIn("vision", p)
        self.assertIn("impossible", p["vision_note"])

    def test_petite_tache_texte_par_la_passerelle(self):
        r = noeud.generer_texte("Résume en une phrase.", "Il faut envoyer le devis à Repriceo vendredi.",
                                cle_operation="test:texte", max_jetons=128)
        self.assertEqual(r["texte"], "Résumé : envoyer le devis vendredi.")
        self.assertEqual(r["modele"], "local-factice:4b")
        self.assertEqual(self.llm.appels[-1][:2], ("Résume en une phrase.", "Il faut envoyer le devis à Repriceo vendredi."))
        ops = [o for o in outils.operations(noeud.PROJET_BOARD) if o["operation_id"].startswith("test:texte:")]
        self.assertIn("texte_generer", {o["tool"].split(".")[-1] for o in ops})
        self.assertTrue(all(o["status"] == "succeeded" for o in ops), "chaque appel journalisé et réussi")

    def test_cli_demander(self):
        with mock.patch("builtins.print") as imprime:
            self.assertEqual(cli.cmd_noeud_demander(mock.Mock(consigne=["Classe", "ce", "texte."], fichier=None,
                                                              image=None, max_jetons=64)), 0)
        self.assertEqual(imprime.call_args_list[0].args[0], "Résumé : envoyer le devis vendredi.")

    def test_rebranchement_revoque_l_ancien_mandat(self):
        ancien = self.branche["mandat"]
        nouveau = noeud.brancher("test@noeud", par="humain")
        self.assertNotEqual(nouveau["connexion"], self.branche["connexion"])
        self.assertIsNotNone(mandats.get(ancien)["revoked_at"])

    def test_regler_ne_touche_ni_cible_ni_mandat(self):
        with mock.patch.object(cli, "_human_only", return_value=None):
            for cle in ("noeud.cible", "noeud.mandat_board", "noeud.commande", "noeud.cle"):
                with self.subTest(cle=cle):
                    self.assertNotEqual(cli.cmd_regler(mock.Mock(cle=cle, valeur="x")), 0)
            self.assertEqual(cli.cmd_regler(mock.Mock(cle="noeud.actif", valeur="false")), 0)
        self.assertFalse(noeud.reglages()["actif"])
        self.assertEqual(noeud.reglages()["cible"], "test@noeud")

    def test_sante(self):
        s = noeud.sante()
        self.assertEqual((s["protocole"], s["modele"], s["occupe"]), (1, "factice-small", False))


if __name__ == "__main__":
    import unittest
    unittest.main()
