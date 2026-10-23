"""Service GPU résident et point d'entrée SSH du noeud ; moteur factice, ni modèle, ni GPU, ni réseau externe."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

DOSSIER = Path(__file__).resolve().parents[1]


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, DOSSIER / fichier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


service = charger("jarvis_noeud_service", "service.py")
noeud = charger("jarvis_noeud_entree", "jarvis_noeud.py")
JETON = "test-only-not-a-real-secret-" * 2


class MoteurFactice:
    nom = "factice"

    def __init__(self):
        self.appels, self.liberer, self.erreur = [], threading.Event(), None
        self.liberer.set()

    def transcrire(self, chemin, langue):
        self.appels.append((Path(chemin).read_bytes(), langue))
        self.liberer.wait(3)
        if self.erreur:
            raise self.erreur
        return {"texte": " Bonjour Jarvis. ", "langue": langue, "segments": 1}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-noeud-"))
        self.entree = self.tmp / "entree"
        self.moteur = MoteurFactice()
        self.srv = service.serveur(service.Reglages(jeton=JETON, port=0, entree=str(self.entree)), self.moteur)
        self.fil = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.fil.start()
        conf = self.tmp / "env"
        conf.write_text(f"JARVIS_NOEUD_TOKEN={JETON}\nJARVIS_NOEUD_PORT={self.srv.server_port}\n"
                        f"JARVIS_NOEUD_ENTREE={self.entree}\nJARVIS_NOEUD_MAX_MO=1\n")
        env = patch.dict(os.environ, {"JARVIS_NOEUD_CONF": str(conf)})
        env.start()
        self.addCleanup(env.stop)
        self.r = noeud.reglages()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.fil.join(2)

    def deposer(self, octets=b"RIFF....WAVE"):
        sha = hashlib.sha256(octets).hexdigest()
        self.assertEqual(noeud.depot(sha, len(octets), io.BytesIO(octets), self.r)["depose"], sha)
        return sha

    def mcp(self, *messages):
        entree = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        sortie = io.StringIO()
        noeud.serveur_mcp(entree, sortie)
        return [json.loads(l) for l in sortie.getvalue().splitlines()]

    def appel(self, nom, args, ident=2):
        rep = self.mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                       {"jsonrpc": "2.0", "method": "notifications/initialized"},
                       {"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": nom, "arguments": args}})
        return rep[-1]["result"]


class FileTests(Base):
    def test_transcription_de_bout_en_bout_par_mcp(self):
        sha = self.deposer()
        soumis = self.appel("audio_transcrire", {"fichier": sha, "langue": "fr"})
        self.assertFalse(soumis["isError"])
        ident = soumis["structuredContent"]["id"]
        fini = self.appel("audio_resultat", {"travail": ident, "attente_s": 5})["structuredContent"]
        self.assertEqual(fini["statut"], "termine")
        self.assertEqual(fini["resultat"]["texte"], "Bonjour Jarvis.")
        self.assertEqual(self.moteur.appels, [(b"RIFF....WAVE", "fr")])
        self.assertFalse((self.entree / sha).exists(), "aucun fichier conservé après traitement")

    def test_demande_identique_ne_relance_pas_le_gpu(self):
        sha = self.deposer()
        a = self.appel("audio_transcrire", {"fichier": sha})["structuredContent"]["id"]
        self.appel("audio_resultat", {"travail": a, "attente_s": 5})
        b = self.appel("audio_transcrire", {"fichier": sha})["structuredContent"]["id"]
        self.assertEqual(a, b)
        self.assertEqual(len(self.moteur.appels), 1)

    def test_attente_bornee_rend_en_cours(self):
        self.moteur.liberer.clear()
        sha = self.deposer()
        ident = self.appel("audio_transcrire", {"fichier": sha})["structuredContent"]["id"]
        etat = self.appel("audio_resultat", {"travail": ident, "attente_s": 0})["structuredContent"]
        self.assertIn(etat["statut"], ("en_attente", "en_cours"))
        self.assertTrue(self.appel("noeud_sante", {})["structuredContent"]["occupe"])
        self.moteur.liberer.set()

    def test_fichier_non_depose_refuse(self):
        r = self.appel("audio_transcrire", {"fichier": "0" * 64})
        self.assertTrue(r["isError"])
        self.assertEqual(self.moteur.appels, [])

    def test_audio_illisible_ne_bloque_pas_la_file(self):
        self.moteur.erreur = RuntimeError("décodage")
        ident = self.appel("audio_transcrire", {"fichier": self.deposer()})["structuredContent"]["id"]
        self.assertEqual(self.appel("audio_resultat", {"travail": ident, "attente_s": 5})["structuredContent"]["statut"], "echec")
        self.moteur.erreur = None
        ident = self.appel("audio_transcrire", {"fichier": self.deposer(b"autre")})["structuredContent"]["id"]
        self.assertEqual(self.appel("audio_resultat", {"travail": ident, "attente_s": 5})["structuredContent"]["statut"], "termine")

    def test_audio_trop_long_echoue_sans_moteur(self):
        with patch.object(service, "duree_audio", return_value=99_999.0):
            ident = self.appel("audio_transcrire", {"fichier": self.deposer()})["structuredContent"]["id"]
            etat = self.appel("audio_resultat", {"travail": ident, "attente_s": 5})["structuredContent"]
        self.assertEqual(etat["statut"], "echec")
        self.assertIn("trop long", etat["erreur"])
        self.assertEqual(self.moteur.appels, [])

    def test_service_exige_le_jeton(self):
        mauvais = {**self.r, "jeton": "faux"}
        with self.assertRaises(noeud.ErreurNoeud):
            noeud._service(mauvais, "GET", "/health")


class McpTests(Base):
    def test_protocole_et_catalogue(self):
        rep = self.mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                       {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                       {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                       {"jsonrpc": "2.0", "id": 4, "method": "shell/exec"})
        self.assertIn("error", rep[0], "aucun outil avant initialize")
        self.assertEqual(rep[1]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual({t["name"] for t in rep[2]["result"]["tools"]}, {"audio_transcrire", "audio_resultat", "noeud_sante"})
        self.assertEqual(rep[3]["error"]["code"], -32601)

    def test_schemas_dans_le_sous_ensemble_de_la_passerelle(self):
        supportes = {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "minimum",
                     "maximum", "minLength", "maxLength", "minItems", "maxItems", "description"}

        def cles(s):
            yield from s
            for v in (s.get("properties") or {}).values():
                yield from cles(v)
        for outil in noeud.OUTILS:
            self.assertLessEqual(set(cles(outil["inputSchema"])), supportes, outil["name"])

    def test_arguments_hors_contrat_refuses(self):
        for nom, args in (("audio_transcrire", {"fichier": "../../etc/passwd"}),
                          ("audio_transcrire", {"fichier": "a" * 64, "chemin": "/tmp"}),
                          ("audio_resultat", {"travail": "TR-x", "attente_s": 99}),
                          ("noeud_sante", {"x": 1}), ("inconnu", {})):
            with self.subTest(nom=nom, args=args):
                self.assertTrue(self.appel(nom, args)["isError"])


class DepotTests(Base):
    def test_empreinte_fausse_refusee_et_rien_garde(self):
        with self.assertRaises(noeud.ErreurNoeud):
            noeud.depot("0" * 64, 5, io.BytesIO(b"12345"), self.r)
        self.assertEqual([f for f in self.entree.iterdir()], [])

    def test_taille_bornee_et_flux_trop_long_refuse(self):
        with self.assertRaises(noeud.ErreurNoeud):
            noeud.depot("0" * 64, 2 * 1024 * 1024, io.BytesIO(b""), self.r)
        octets = b"abc"
        with self.assertRaises(noeud.ErreurNoeud):
            noeud.depot(hashlib.sha256(octets).hexdigest(), 3, io.BytesIO(octets + b"en trop"), self.r)

    def test_commande_forcee_ne_donne_aucun_shell(self):
        for demande in ("bash", "mcp; rm -rf ~", "depot ../x 3", "sante extra", ""):
            with self.subTest(demande=demande), patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": demande}):
                sortie = io.StringIO()
                self.assertNotEqual(noeud.principal(["ssh"], stdin=io.StringIO(""), stdout=sortie), 0)
                self.assertIn("erreur", json.loads(sortie.getvalue()))

    def test_commande_forcee_depot(self):
        octets = b"memo"
        sha = hashlib.sha256(octets).hexdigest()
        with patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": f"depot {sha} {len(octets)}"}):
            sortie = io.StringIO()
            self.assertEqual(noeud.principal(["ssh"], stdin=io.BytesIO(octets), stdout=sortie), 0)
        self.assertTrue((self.entree / sha).is_file())
        self.assertEqual(oct((self.entree / sha).stat().st_mode & 0o777), "0o600")


class ReglagesTests(unittest.TestCase):
    def test_jeton_court_refuse(self):
        with self.assertRaises(ValueError):
            service.Reglages(jeton="court", entree="/tmp/x").valider()


if __name__ == "__main__":
    unittest.main()
