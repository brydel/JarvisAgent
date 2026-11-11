"""Bibliothèque de références : découpage, recherche (FTS5, repli, vecteurs, RRF), garde anti-SSRF, capture, API, CLI.

Aucun accès à Internet : les sites sont des serveurs locaux factices. Le test « vrai Chromium » est ignoré si node
ou Playwright manquent sur le poste.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import test_jarvis  # noqa: F401 — environnement isolé
import test_missions

from jarvis import capture_site, cli, missions as mi, rag, references, studio_api  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 64 + b"\xff\xd9"


# --- Outils de test --------------------------------------------------------------------------------------

class EmbarqueurFactice:
    """Vecteurs déterministes : sac de racines haché, avec deux synonymes (ce que BM25 ne sait pas rapprocher)."""

    SYNONYMES = {"tarif": "prix", "cout": "prix", "typographi": "polic"}

    def __init__(self, modele: str = "factice-a", dimension: int = 48):
        self.modele, self.dimension, self.appels = modele, dimension, 0

    def embarquer(self, textes):
        self.appels += 1
        sortie = []
        for t in textes:
            v = [0.0] * self.dimension
            for r in rag.termes(t):
                r = self.SYNONYMES.get(r, r)
                v[zlib.crc32((self.modele + r).encode()) % self.dimension] += 1.0
            sortie.append(v)
        return sortie


class EmbarqueurEnPanne:
    modele = "en-panne"

    def __init__(self):
        self.appels = 0

    def embarquer(self, textes):
        self.appels += 1
        raise rag.EmbarqueurIndisponible("service arrêté")


class _Site(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.server.requetes.append(self.path)
        reponse = self.server.pages.get(self.path.split("?")[0])
        if reponse is None:
            self.send_error(404)
            return
        code, entetes, corps = reponse
        self.send_response(code)
        for k, v in entetes.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def site(pages: dict):
    """Serveur HTTP local factice. `pages` : chemin → (code, en-têtes, corps). `.requetes` garde ce qui a été demandé."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    httpd.daemon_threads = True
    httpd.pages, httpd.requetes = pages, []
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def html(corps: bytes):
    return 200, {"Content-Type": "text/html; charset=utf-8"}, corps


def pilote_simule(**surcharges):
    """Pilote de capture sans navigateur : écrit quatre images et rend ce qu'un site aurait donné."""
    appels = []

    def pilote(configuration: dict) -> dict:
        appels.append(configuration)
        dossier = Path(configuration["dossier"])
        for i, role in enumerate(capture_site.FICHIERS):
            (dossier / f"{role}.jpg").write_bytes(JPEG + surcharges.get("grain", b"") + bytes([i]))
        resultat = {
            "titre": "Atelier Lumière — studio de design", "description": "Sites élégants pour marques exigeantes.",
            "langue": "fr", "url_finale": configuration["url"], "statut_http": 200, "bac_a_sable": True,
            "sections": [
                {"titre": "", "niveau": 0, "texte": "Accueil Réalisations Contact", "y": 0, "hauteur": 80},
                {"titre": "Des sites qui respirent", "niveau": 1, "y": 80, "hauteur": 620,
                 "texte": "Nous concevons des interfaces sobres, avec une grande place laissée au blanc."},
                {"titre": "Nos prix", "niveau": 2, "y": 700, "hauteur": 400,
                 "texte": "Trois formules claires, sans frais cachés. Le forfait vitrine démarre à 2 400 €."},
                {"titre": "Typographie", "niveau": 2, "y": 1100, "hauteur": 300,
                 "texte": "Une police à empattement pour les titres, une linéale pour le corps du texte."},
            ],
            "palette": [{"hex": "#f7f3ec", "part": 0.62}, {"hex": "#1c1b19", "part": 0.2}, {"hex": "#C8553D", "part": 0.05}],
            "couleurs_css": {"fond": "rgb(247, 243, 236)", "texte": "rgb(28, 27, 25)", "accent": "rgba(200, 85, 61, 1)", "lien": "rgba(0,0,0,0)"},
            "polices": {"roles": {"corps": "Inter", "titre": "Fraunces"}, "declarees": ["Fraunces", "Inter", "Inter"]},
            "structure": {"entete": True, "navigation": 3, "principal": True, "pied": True, "images": 4, "boutons": 2,
                          "formulaires": 1, "hauteur_page": 1400,
                          "heros": {"titre": "Des sites qui respirent", "appel_action": "Voir nos réalisations", "visible_d_emblee": True}},
            "liens": [{"url": "https://exemple.org/realisations", "texte": "Réalisations", "zone": "entete"},
                      {"url": "javascript:alert(1)", "texte": "piège"}, {"url": "https://exemple.org/realisations", "texte": "doublon"}],
            "fichiers": {r: {"largeur": 1440, "hauteur": 900} for r in capture_site.FICHIERS},
        }
        resultat.update({k: v for k, v in surcharges.items() if k != "grain"})
        return resultat

    pilote.appels = appels
    return pilote


def node_et_playwright() -> bool:
    if not shutil.which("node"):
        return False
    essai = ("try{require('playwright')}catch(_){require(require('path').join(process.argv[1],'studio','board-v2',"
             "'node_modules','playwright'))}")
    try:
        return subprocess.run(["node", "-e", essai, str(capture_site.PILOTE.parents[1])], capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# --- Briques pures ---------------------------------------------------------------------------------------

class RagTest(unittest.TestCase):
    def test_normalisation_et_racines_francaises(self):
        self.assertEqual(rag.normaliser("Élégance du CŒUR — Noël"), "elegance du coeur — noel")
        self.assertEqual(rag.termes("Quelles sont les couleurs de la marque ?"), ["couleur", "marqu"])
        self.assertEqual(rag.termes("le la les"), ["le", "la", "les"], "tout en mots vides : on garde tout")
        self.assertEqual(rag.requete_fts("Polices élégantes"), '"polic"* OR "elegant"*')
        self.assertEqual(rag.requete_fts('") OR 1=1 --'), '"or"*')
        self.assertNotIn('")', rag.requete_fts('") NEAR( x'), "aucune syntaxe FTS de l'utilisateur ne passe")

    def test_decoupage_par_sections_borne_et_recouvrant(self):
        long = " ".join(f"Phrase numéro {i} sur la mise en page." for i in range(120))
        fragments = rag.decouper([{"titre": "Intro", "niveau": 1, "texte": "Court."},
                                  {"titre": "Mise en page", "niveau": 2, "texte": long, "zone": {"y": 300, "hauteur": 900}},
                                  {"titre": "Titre seul", "niveau": 3, "texte": ""}])
        self.assertEqual([f["position"] for f in fragments], list(range(len(fragments))))
        self.assertEqual(fragments[0], {"position": 0, "section": "Intro", "niveau": 1, "texte": "Court.", "zone": None})
        corps = [f for f in fragments if f["section"] == "Mise en page"]
        self.assertGreater(len(corps), 3)
        self.assertTrue(all(len(f["texte"]) <= rag.FRAGMENT_MAX for f in corps))
        self.assertTrue(all(f["zone"] == {"y": 300, "hauteur": 900} for f in corps))
        self.assertTrue(all(f["texte"].endswith(".") for f in corps), "coupé en fin de phrase")
        self.assertIn(corps[0]["texte"][-30:], corps[1]["texte"], "recouvrement entre fragments voisins")
        self.assertEqual(fragments[-1]["texte"], "Titre seul", "un titre sans texte reste trouvable")
        self.assertEqual("".join(f["texte"] for f in rag.decouper([{"titre": "", "texte": "a\x00b"}])), "ab")

    def test_plafond_de_fragments(self):
        fragments = rag.decouper([{"titre": f"S{i}", "texte": "x"} for i in range(rag.FRAGMENTS_MAX + 50)])
        self.assertEqual(len(fragments), rag.FRAGMENTS_MAX)

    def test_sections_d_un_markdown(self):
        s = rag.sections_de_texte("Préambule\n# Un\ntexte un\n## Deux\ntexte deux\n#### pas un titre retenu\n")
        self.assertEqual([(x["titre"], x["niveau"]) for x in s], [("", 0), ("Un", 1), ("Deux", 2)])
        self.assertIn("#### pas un titre retenu", s[2]["texte"])

    def test_bm25_de_repli_classe_par_pertinence(self):
        docs = [("a", "la palette de couleurs est sobre"), ("b", "couleurs couleurs couleur vive et palette"),
                ("c", "rien a voir avec le sujet")]
        classement = rag.bm25_python(docs, "couleur palette")
        self.assertEqual([i for i, _ in classement], ["b", "a"])
        self.assertEqual(rag.bm25_python(docs, "zzz"), [])
        self.assertEqual(rag.bm25_python([], "couleur"), [])

    def test_fusion_rrf(self):
        fusion = rag.fusion_rrf([["a", "b", "c"], ["c", "a", "d"]])
        self.assertEqual([i for i, _ in fusion], ["a", "c", "b", "d"])
        self.assertAlmostEqual(dict(fusion)["a"], 1 / 61 + 1 / 62)
        self.assertEqual(rag.fusion_rrf([]), [])

    def test_vecteurs_blob_et_cosinus(self):
        v = [0.5, -1.25, 3.0]
        blob = rag.emballer(v)
        self.assertEqual(len(blob), 12, "float32")
        self.assertEqual(list(rag.deballer(blob)), v)
        self.assertAlmostEqual(rag.cosinus([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(rag.cosinus([1, 0], [0, 1]), 0.0)
        self.assertEqual(rag.cosinus([1, 0], [1, 0, 0]), 0.0, "dimensions différentes : jamais comparées")
        self.assertEqual(rag.cosinus([0, 0], [1, 0]), 0.0)
        proches = rag.plus_proches([1.0, 0.0], [("x", rag.emballer([0.9, 0.1])), ("y", rag.emballer([0.0, 1.0])),
                                                ("z", rag.emballer([1.0, 0.0]))], limite=2)
        self.assertEqual([i for i, _ in proches], ["z", "x"])

    def test_extrait_surligne_sans_accents(self):
        texte = "Avant-propos. " * 30 + "Les Polices élégantes font le cœur de la marque. " + "Suite. " * 40
        e = rag.extrait(texte, "police elegante coeur")
        self.assertLessEqual(len(e["texte"]), 270)
        surlignes = [e["texte"][a:b] for a, b in e["surlignages"]]
        self.assertEqual(surlignes, ["Polices", "élégantes", "cœur"])
        self.assertEqual(rag.marquer({"texte": "une police", "surlignages": [[4, 10]]}), "une **police**")
        self.assertEqual(rag.extrait("texte sans rapport", "zzz")["surlignages"], [])

    def test_embarqueur_desactive_par_defaut_et_ollama_en_panne(self):
        self.assertIsNone(rag.embarqueur_configure(), "aucun embarqueur sans réglage explicite")
        with self.assertRaises(ValueError):
            rag.EmbarqueurOllama("file:///etc/passwd")
        prise = socket.socket()
        prise.bind(("127.0.0.1", 0))  # port réservé mais jamais écouté : connexion refusée
        try:
            e = rag.EmbarqueurOllama(f"http://127.0.0.1:{prise.getsockname()[1]}", "bge-m3", delai_s=2)
            with self.assertRaises(rag.EmbarqueurIndisponible):
                e.embarquer(["bonjour"])
        finally:
            prise.close()

    def test_embarqueur_ollama_parle_le_protocole_attendu(self):
        recus = []

        class Ollama(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                recus.append((self.path, corps))
                reponse = json.dumps({"embeddings": [[1.0, 2.0, 3.0] for _ in corps["input"]]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(reponse)))
                self.end_headers()
                self.wfile.write(reponse)

            def log_message(self, *args):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            e = rag.EmbarqueurOllama(f"http://127.0.0.1:{httpd.server_address[1]}", "bge-m3")
            self.assertEqual(e.embarquer(["a", "b"]), [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]])
            self.assertEqual(recus, [("/api/embed", {"model": "bge-m3", "input": ["a", "b"]})])
        finally:
            httpd.shutdown()
            httpd.server_close()


# --- Garde anti-SSRF -------------------------------------------------------------------------------------

class GardeTest(unittest.TestCase):
    def test_adresses_privees_refusees(self):
        garde = capture_site.Garde()
        for hote in ("127.0.0.1", "localhost", "10.0.0.8", "192.168.1.1", "172.16.4.4", "169.254.169.254", "::1",
                     "[::ffff:127.0.0.1]", "0.0.0.0", "2130706433", "fd00::1", "100.64.0.1"):
            with self.assertRaises(capture_site.CaptureRefusee, msg=hote):
                garde.verifier(hote, 80)
        self.assertGreaterEqual(len(garde.refus), 12)

    def test_resolution_dns_verifiee_et_epinglee(self):
        reponses = {"public.test": ["93.184.216.34"], "interne.test": ["10.1.2.3"],
                    "double.test": ["93.184.216.34", "127.0.0.1"], "vide.test": []}
        garde = capture_site.Garde(resolveur=lambda h, p: reponses[h])
        self.assertEqual(garde.verifier("public.test", 443), "93.184.216.34")
        self.assertEqual(garde.verifier("PUBLIC.test.", 80), "93.184.216.34")
        for hote in ("interne.test", "double.test", "vide.test"):
            with self.assertRaises(capture_site.CaptureRefusee, msg=hote):
                garde.verifier(hote, 443)
        with self.assertRaisesRegex(capture_site.CaptureRefusee, "port non standard"):
            garde.verifier("public.test", 8080)
        with self.assertRaises(capture_site.CaptureRefusee):
            garde.verifier("", 80)

    def test_exception_de_test_limitee_a_un_couple_adresse_port(self):
        garde = capture_site.Garde(exceptions=[("127.0.0.1", 4444)])
        self.assertEqual(garde.verifier("127.0.0.1", 4444), "127.0.0.1")
        with self.assertRaises(capture_site.CaptureRefusee):
            garde.verifier("127.0.0.1", 4445)

    def _ouvreur(self, mandataire):
        # urllib contourne tout mandataire pour 127.0.0.1 si no_proxy le demande (d'autres tests le règlent) :
        # ici chaque requête DOIT passer par le mandataire de garde
        from unittest import mock
        correctif = mock.patch("urllib.request.proxy_bypass", lambda hote: False)
        correctif.start()
        self.addCleanup(correctif.stop)
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": mandataire.adresse}))

    def test_mandataire_relaie_le_public_et_bloque_la_redirection_vers_le_prive(self):
        with site({"/secret": html(b"donnees internes")}) as interne:
            prive = f"http://127.0.0.1:{interne.server_address[1]}/secret"
            with site({"/": html(b"<h1>Bonjour</h1>"),
                       "/vers-prive": (302, {"Location": prive}, b""),
                       "/vers-metadonnees": (302, {"Location": "http://169.254.169.254/latest/meta-data/"}, b"")}) as public:
                base = f"http://127.0.0.1:{public.server_address[1]}"
                garde = capture_site.Garde(exceptions=[("127.0.0.1", public.server_address[1])])
                with capture_site.MandataireGarde(garde) as mandataire:
                    ouvreur = self._ouvreur(mandataire)
                    reponse = ouvreur.open(base + "/", timeout=10)
                    self.assertEqual(reponse.read(), b"<h1>Bonjour</h1>")
                    self.assertEqual(reponse.headers.get_all("Connection"), ["close"], "connexion jamais réutilisée")
                    for chemin in ("/vers-prive", "/vers-metadonnees"):
                        with self.assertRaises(urllib.error.HTTPError) as ctx:
                            ouvreur.open(base + chemin, timeout=10)
                        self.assertEqual(ctx.exception.code, 403, chemin)
                        ctx.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        ouvreur.open(prive, timeout=10)
                    self.assertEqual(ctx.exception.code, 403)
                    ctx.exception.close()
                    self.assertGreater(mandataire.octets, 0)
                self.assertEqual(interne.requetes, [], "le serveur interne n'a jamais été contacté")
                self.assertIn(("127.0.0.1", interne.server_address[1]), [(h, p) for h, p, _ in garde.refus])
                self.assertIn("169.254.169.254", [h for h, _, _ in garde.refus])

    def test_mandataire_refuse_le_tunnel_vers_le_prive_et_les_requetes_malformees(self):
        with site({"/": html(b"interne")}) as interne, capture_site.MandataireGarde(capture_site.Garde()) as mandataire:
            port = mandataire.server_address[1]
            for requete in (f"CONNECT 127.0.0.1:{interne.server_address[1]} HTTP/1.1\r\n\r\n",
                            "CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n",
                            "GET ftp://exemple.org/ HTTP/1.1\r\n\r\n", "GET /chemin-relatif HTTP/1.1\r\n\r\n",
                            "GET http://utilisateur:secret@exemple.org/ HTTP/1.1\r\n\r\n"):
                with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
                    s.sendall(requete.encode())
                    self.assertTrue(s.recv(200).startswith(b"HTTP/1.1 403"), requete)
            self.assertEqual(interne.requetes, [])

    def test_mandataire_borne_le_volume_et_les_connexions(self):
        with site({"/gros": html(b"x" * 400_000)}) as public:
            garde = capture_site.Garde(exceptions=[("127.0.0.1", public.server_address[1])])
            adresse = f"http://127.0.0.1:{public.server_address[1]}/gros"
            with capture_site.MandataireGarde(garde, octets_max=50_000) as mandataire:
                with self.assertRaises((http.client.HTTPException, urllib.error.URLError, ConnectionError)):
                    self._ouvreur(mandataire).open(adresse, timeout=10).read()
                self.assertLess(mandataire.octets, 200_000, "le relais s'arrête dès le plafond dépassé")
            with capture_site.MandataireGarde(garde, connexions_max=1) as mandataire:
                self.assertEqual(len(self._ouvreur(mandataire).open(adresse, timeout=10).read()), 400_000)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self._ouvreur(mandataire).open(adresse, timeout=10)
                self.assertEqual(ctx.exception.code, 429)
                ctx.exception.close()


# --- Capture ---------------------------------------------------------------------------------------------

class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-test-capture-"))
        self.addCleanup(shutil.rmtree, self.dossier, True)

    def test_refus_avant_tout_lancement(self):
        pilote = pilote_simule()
        for url in ("http://127.0.0.1/", "http://169.254.169.254/latest", "ftp://exemple.org", "file:///etc/passwd",
                    "http://utilisateur:mdp@exemple.org/", "http://[::1]/", "javascript:alert(1)", "http://localhost:7718/"):
            with self.assertRaises(capture_site.CaptureRefusee, msg=url):
                capture_site.capturer(url, self.dossier, pilote=pilote)
        self.assertEqual(pilote.appels, [], "le navigateur n'est jamais lancé pour une adresse refusée")

    def test_pilote_simule_resultat_valide_et_borne(self):
        pilote = pilote_simule(titre="T" * 5000, statut_http="200", inconnu={"x": 1},
                               fichiers={"bureau_vue": {"largeur": 1440, "hauteur": 900}, "bureau_page": {"largeur": "x"},
                                         "mobile_vue": "pas un objet", "../../etc/passwd": {"largeur": 1}})
        c = capture_site.capturer("http://exemple.test/page", self.dossier, pilote=pilote,
                                  resolveur=lambda h, p: ["93.184.216.34"])
        conf = pilote.appels[0]
        self.assertRegex(conf["mandataire"], r"^http://127\.0\.0\.1:\d+$")
        self.assertEqual(conf["gabarits"], {"bureau": (1440, 900), "mobile": (390, 844)})
        self.assertEqual(len(c["titre"]), 200)
        self.assertNotIn("inconnu", c)
        self.assertEqual(c["statut_http"], 0, "un type inattendu est ignoré, pas converti")
        self.assertEqual([s["titre"] for s in c["sections"]], ["", "Des sites qui respirent", "Nos prix", "Typographie"])
        self.assertEqual(c["sections"][2]["zone"], {"y": 700, "hauteur": 400})
        self.assertEqual([p["hex"] for p in c["palette"]], ["#f7f3ec", "#1c1b19", "#c8553d"])
        self.assertEqual(c["couleurs_css"], {"fond": "#f7f3ec", "texte": "#1c1b19", "accent": "#c8553d"},
                         "une couleur transparente n'est pas retenue")
        self.assertEqual(c["polices"], {"roles": {"corps": "Inter", "titre": "Fraunces"}, "declarees": ["Fraunces", "Inter"]})
        self.assertEqual([l["url"] for l in c["liens"]], ["https://exemple.org/realisations"], "ni javascript: ni doublon")
        self.assertTrue(c["liens"][0]["externe"])
        self.assertEqual(c["structure"]["heros"]["appel_action"], "Voir nos réalisations")
        self.assertEqual(c["structure"]["sections"], ["Des sites qui respirent", "Nos prix", "Typographie"])
        self.assertEqual(sorted(c["fichiers"]), ["bureau_page", "bureau_vue"], "seuls les rôles connus et bien formés")
        for f in c["fichiers"].values():
            self.assertRegex(f["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(f["chemin"].parent, self.dossier.resolve())
        self.assertIn("DONNÉE non fiable", c["avertissement"])

    def test_pilote_en_erreur_ou_sans_image(self):
        def muet(configuration):
            return {"titre": "sans capture", "fichiers": {"bureau_vue": {"largeur": 1, "hauteur": 1}}}
        with self.assertRaisesRegex(capture_site.CaptureRefusee, "aucune capture"):
            capture_site.capturer("http://exemple.test/", self.dossier, pilote=muet, resolveur=lambda h, p: ["93.184.216.34"])

        def lien_symbolique(configuration):
            (Path(configuration["dossier"]) / "bureau_vue.jpg").symlink_to("/etc/hostname")
            return {"fichiers": {"bureau_vue": {"largeur": 1, "hauteur": 1}}}
        with self.assertRaisesRegex(capture_site.CaptureRefusee, "aucune capture"):
            capture_site.capturer("http://exemple.test/", self.dossier, pilote=lien_symbolique,
                                  resolveur=lambda h, p: ["93.184.216.34"])

    def test_redirection_finale_vers_le_prive_refusee(self):
        pilote = pilote_simule(url_finale="http://10.0.0.5/admin")
        reponses = {"exemple.test": ["93.184.216.34"], "10.0.0.5": ["10.0.0.5"]}
        with self.assertRaises(capture_site.CaptureRefusee):
            capture_site.capturer("http://exemple.test/", self.dossier, pilote=pilote, resolveur=lambda h, p: reponses[h])

    @unittest.skipUnless(node_et_playwright(), "node ou Playwright absents : capture réelle non testée")
    def test_vrai_chromium_sous_ressources_privees_bloquees(self):
        with site({"/pixel": (200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\n"), "/api": html(b"secret")}) as interne:
            prive = f"http://127.0.0.1:{interne.server_address[1]}"
            # 450 liens longs : le résultat du pilote dépasse 64 Ko (tampon d'un tube), il doit arriver entier
            liens = "".join(f'<a href="https://exemple.org/archives/{i:04d}/{"x" * 90}">Archive numéro {i}</a> ' for i in range(450))
            page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Boutique Aurore</title>
                <meta name="description" content="Bougies artisanales."><style>body{{background:#103050;color:#fff;font-family:Georgia,serif}}
                h1{{font-family:Verdana,sans-serif}}</style></head><body><header><nav><a href="https://exemple.org/a-propos">À propos</a></nav></header>
                <main><h1>Des bougies qui durent</h1><p>Cire végétale coulée à la main.</p><button>Commander</button>
                <h2>Livraison</h2><p>Expédition sous deux jours ouvrés.</p><img src="{prive}/pixel" alt="">
                <script>fetch("{prive}/api").catch(()=>0); fetch("http://169.254.169.254/latest/meta-data/").catch(()=>0);
                const i = new Image(); i.src = "http://localhost:{interne.server_address[1]}/pixel";</script></main>
                <footer>Mentions {liens}</footer></body></html>""".encode()
            with site({"/": html(page), "/saut": (302, {"Location": prive + "/api"}, b"")}) as public:
                port = public.server_address[1]
                try:
                    c = capture_site.capturer(f"http://127.0.0.1:{port}/", self.dossier, exceptions=[("127.0.0.1", port)])
                except capture_site.CaptureRefusee as exc:
                    if "Chromium ne démarre pas" in str(exc) or "Playwright introuvable" in str(exc):
                        self.skipTest(str(exc))
                    raise
                self.assertEqual(interne.requetes, [], "aucune sous-ressource privée n'a atteint le serveur interne")
                self.assertEqual(c["titre"], "Boutique Aurore")
                self.assertEqual(c["description"], "Bougies artisanales.")
                self.assertEqual([s["titre"] for s in c["sections"] if s["titre"]], ["Des bougies qui durent", "Livraison"])
                self.assertIn("Cire végétale", c["sections"][1]["texte"])
                self.assertEqual(c["couleurs_css"]["fond"], "#103050")
                self.assertEqual(c["polices"]["roles"]["titre"], "Verdana")
                dominante = bytes.fromhex(c["palette"][0]["hex"][1:])
                self.assertTrue(all(abs(a - b) <= 12 for a, b in zip(dominante, (0x10, 0x30, 0x50))),
                                f"la couleur dominante est le fond bleu nuit ({c['palette'][0]['hex']})")
                self.assertGreater(c["palette"][0]["part"], 0.5)
                self.assertTrue(c["structure"]["entete"] and c["structure"]["pied"])
                self.assertEqual(c["structure"]["heros"]["appel_action"], "Commander")
                self.assertEqual(c["liens"][0]["url"], "https://exemple.org/a-propos")
                self.assertEqual(len(c["liens"]), capture_site.LIENS_MAX, "liens bornés")
                self.assertEqual(sorted(c["fichiers"]), sorted(capture_site.FICHIERS))
                self.assertEqual((c["fichiers"]["mobile_vue"]["largeur"], c["fichiers"]["bureau_vue"]["largeur"]), (390, 1440))
                for f in c["fichiers"].values():
                    self.assertEqual(f["chemin"].read_bytes()[:3], b"\xff\xd8\xff")
                # la page elle-même, si elle redirige vers le privé, est refusée sans toucher le serveur interne
                autre = Path(tempfile.mkdtemp(prefix="jarvis-test-capture-"))
                self.addCleanup(shutil.rmtree, autre, True)
                with self.assertRaises(capture_site.CaptureRefusee):
                    capture_site.capturer(f"http://127.0.0.1:{port}/saut", autre, exceptions=[("127.0.0.1", port)])
                self.assertEqual(interne.requetes, [])


# --- Stockage et recherche -------------------------------------------------------------------------------

GUIDE = """# Guide de style Aurore
Notre identité repose sur des couleurs sobres et un rythme aéré.

## Palette
Le fond crème et l'encre noire dominent ; l'orange brûlé sert d'accent, avec parcimonie.

## Typographie
Les polices élégantes à empattement portent les titres ; le cœur du texte reste en linéale.

## Prix
Trois formules claires, affichées sans astérisque.
"""


class StockageTest(unittest.TestCase):
    def setUp(self):
        test_missions._reinitialiser()
        references.FORCER_REPLI = False
        references.utiliser_embarqueur(None)
        self.org = mi.tenant_local()

    def tearDown(self):
        references.attendre(20)
        references.FORCER_REPLI = False
        references.utiliser_embarqueur()

    def guide(self, **options):
        return references.ajouter(self.org, texte=GUIDE, auteur="test", **options)

    def test_texte_indexe_et_trouve_avec_citation_complete(self):
        ref = self.guide(collection="marque", etiquettes=["Design", "design", " UI "])
        self.assertRegex(ref["id"], r"^RF-[0-9a-f]{12}$")
        self.assertEqual((ref["statut"], ref["titre"], ref["etiquettes"]), ("prete", "Guide de style Aurore", ["design", "ui"]))
        self.assertEqual(ref["index"]["fragments"], 4)
        self.assertEqual(ref["index"]["vecteurs"], 0)
        r = references.chercher(self.org, "Quelle police élégante pour les titres ?")
        self.assertEqual((r["mode"], r["vecteurs"], r["nature"]), ("bm25", "desactive", "donnee_non_fiable"))
        premier = r["resultats"][0]
        self.assertRegex(premier["fragment_id"], r"^FR-[0-9a-f]{12}$")
        self.assertEqual(premier["section"], "Typographie")
        self.assertIn("polices", [premier["extrait"]["texte"][a:b] for a, b in premier["extrait"]["surlignages"]])
        cite = premier["citation"]
        self.assertEqual((cite["reference_id"], cite["titre"], cite["collection"], cite["section"]),
                         (ref["id"], "Guide de style Aurore", "marque", "Typographie"))
        self.assertIsNotNone(cite["capture_le"])
        self.assertIn(ref["id"], cite["lien"])
        entier = references.fragment(self.org, premier["fragment_id"])
        self.assertIn("linéale", entier["texte"])
        self.assertEqual(references.chercher(self.org, "")["resultats"], [])
        self.assertEqual(references.chercher(self.org, "zygomatique")["resultats"], [])

    def test_fts5_desaccentue_prefixes_et_pluriels(self):
        if mi.backend().nom != "sqlite":
            self.skipTest("FTS5 est propre à SQLite")
        self.assertTrue(references.fts5_disponible(self.org), "FTS5 attendu sur ce poste")
        self.guide()
        for question, section in (("coeur", "Typographie"), ("ELEGANT", "Typographie"), ("typo", "Typographie"),
                                  ("accent orange", "Palette"), ("creme", "Palette"), ("formule", "Prix")):
            r = references.chercher(self.org, question)
            self.assertEqual(r["moteur_mots"], "fts5")
            self.assertTrue(r["resultats"], question)
            self.assertEqual(r["resultats"][0]["section"], section, question)
        # une question hostile reste une question : aucune syntaxe FTS n'est interprétée
        for question in ('") OR tenant_id:x', "NEAR(a b) *", "titre : ^palette", '"'):
            references.chercher(self.org, question)

    def test_repli_sans_fts5_meme_resultats(self):
        references.FORCER_REPLI = True
        self.guide()
        r = references.chercher(self.org, "polices élégantes des titres")
        self.assertEqual(r["moteur_mots"], "python")
        self.assertEqual(r["resultats"][0]["section"], "Typographie")
        self.assertEqual(references.chercher(self.org, "creme")["resultats"][0]["section"], "Palette")
        self.assertEqual(references.etat_moteur(self.org)["mots"], "python")

    def test_isolation_par_tenant(self):
        a = mi.creer_organisation("A", id_="ORG-a")
        b = mi.creer_organisation("B", id_="ORG-b")
        ra = references.ajouter(a, texte="# Secret de A\nLa recette confidentielle du nougat.", auteur="test")
        rb = references.ajouter(b, texte="# Note de B\nLe nougat se vend bien.", auteur="test")
        self.assertEqual([x["id"] for x in references.lister(a)["references"]], [ra["id"]])
        self.assertEqual({x["reference_id"] for x in references.chercher(a, "nougat")["resultats"]}, {ra["id"]})
        self.assertEqual({x["reference_id"] for x in references.chercher(b, "nougat")["resultats"]}, {rb["id"]})
        self.assertEqual(references.chercher(b, "confidentielle")["resultats"], [])
        fragment_a = references.chercher(a, "nougat")["resultats"][0]["fragment_id"]
        for appel in (lambda: references.voir(b, ra["id"]), lambda: references.fragment(b, fragment_a),
                      lambda: references.supprimer(b, ra["id"], par="test"), lambda: references.reindexer(b, ra["id"]),
                      lambda: references.modifier(b, ra["id"], titre="volé"),
                      lambda: references.poser_sur_board(b, ra["id"], auteur="test")):
            with self.assertRaises(mi.MissionError) as ctx:
                appel()
            self.assertEqual(ctx.exception.code, "inconnue")
        references.FORCER_REPLI = True
        self.assertEqual({x["reference_id"] for x in references.chercher(b, "nougat")["resultats"]}, {rb["id"]})

    def test_collections_etiquettes_et_suppression_douce(self):
        un = self.guide(collection="marque", etiquettes=["design"])
        deux = references.ajouter(self.org, texte="# Concurrent\nPalette criarde, prix flous.", collection="veille",
                                  etiquettes=["design", "prix"], auteur="test")
        liste = references.lister(self.org)
        self.assertEqual([c["nom"] for c in liste["collections"]], ["marque", "veille"])
        self.assertEqual(liste["etiquettes"][0], {"nom": "design", "n": 2})
        self.assertEqual([r["id"] for r in references.lister(self.org, collection="veille")["references"]], [deux["id"]])
        self.assertEqual([r["id"] for r in references.lister(self.org, etiquette="prix")["references"]], [deux["id"]])
        self.assertEqual([r["id"] for r in references.lister(self.org, q="aurore")["references"]], [un["id"]])
        self.assertEqual({x["reference_id"] for x in references.chercher(self.org, "palette", collection="veille")["resultats"]}, {deux["id"]})
        self.assertEqual({x["reference_id"] for x in references.chercher(self.org, "palette", etiquette="prix")["resultats"]}, {deux["id"]})
        references.supprimer(self.org, deux["id"], par="test")
        self.assertEqual([r["id"] for r in references.lister(self.org)["references"]], [un["id"]])
        self.assertEqual({x["reference_id"] for x in references.chercher(self.org, "palette")["resultats"]}, {un["id"]})
        with self.assertRaises(mi.MissionError):
            references.voir(self.org, deux["id"])
        self.assertEqual([r["id"] for r in references.lister(self.org, supprimees=True)["references"]], [deux["id"]])
        references.supprimer(self.org, deux["id"], restaurer=True, par="test")
        self.assertEqual(len(references.chercher(self.org, "palette")["resultats"]), 2)
        modifie = references.modifier(self.org, un["id"], titre="Charte Aurore", collection="charte", etiquettes="a, b")
        self.assertEqual((modifie["titre"], modifie["collection"], modifie["etiquettes"]), ("Charte Aurore", "charte", ["a", "b"]))
        self.assertEqual(references.chercher(self.org, "charte")["resultats"][0]["citation"]["titre"], "Charte Aurore")

    def test_entrees_invalides(self):
        for options in ({}, {"url": "https://exemple.org", "texte": "x"}, {"texte": "   "}, {"url": "ftp://exemple.org"},
                        {"url": "pas une adresse"}, {"objet_id": "BO-000000000000"}, {"texte": "x" * (references.TEXTE_MAX + 1)}):
            with self.assertRaises(mi.MissionError, msg=options):
                references.ajouter(self.org, auteur="test", **options)

    def test_vecteurs_optionnels_fusion_hybride_et_reindexation(self):
        e = EmbarqueurFactice("factice-a", 48)
        references.utiliser_embarqueur(e)
        ref = self.guide()
        self.assertEqual(ref["index"], {"fragments": 4, "vecteurs": 4, "modele": "factice-a", "dimension": 48,
                                        "version_index": rag.VERSION_INDEX})
        self.assertEqual(references.etat_moteur(self.org)["fragments_vectorises"], 4)
        # « tarifs » n'est écrit nulle part : seuls les vecteurs rapprochent la question de la section « Prix »
        r = references.chercher(self.org, "tarifs")
        self.assertEqual((r["mode"], r["vecteurs"]), ("hybride", "ok"))
        self.assertEqual(r["resultats"][0]["section"], "Prix")
        self.assertEqual(r["resultats"][0]["rangs"], {"mots": None, "vecteurs": 1})
        r = references.chercher(self.org, "polices des titres")
        self.assertEqual(r["resultats"][0]["section"], "Typographie")
        self.assertEqual(r["resultats"][0]["rangs"], {"mots": 1, "vecteurs": 1})
        # changement de modèle : les anciens vecteurs ne sont plus comparés, la ré-indexation les remplace
        references.utiliser_embarqueur(EmbarqueurFactice("factice-b", 32))
        r = references.chercher(self.org, "tarifs")
        self.assertEqual((r["mode"], r["vecteurs"], r["resultats"]), ("bm25", "vide", []))
        bilan = references.reindexer(self.org)
        self.assertEqual((bilan["references"], bilan["fragments"], bilan["vecteurs"], bilan["etat_vecteurs"]), (1, 4, 4, "ok"))
        self.assertEqual(references.voir(self.org, ref["id"])["index"]["modele"], "factice-b")
        self.assertEqual(references.voir(self.org, ref["id"])["index"]["dimension"], 32)
        self.assertEqual(references.chercher(self.org, "tarifs")["resultats"][0]["section"], "Prix")

    def test_embarqueur_en_panne_la_recherche_continue_par_mots(self):
        panne = EmbarqueurEnPanne()
        references.utiliser_embarqueur(panne)
        ref = self.guide()  # l'indexation réussit sans vecteurs
        self.assertEqual((ref["statut"], ref["index"]["vecteurs"]), ("prete", 0))
        r = references.chercher(self.org, "polices élégantes")
        self.assertEqual((r["mode"], r["vecteurs"]), ("bm25", "indisponible"))
        self.assertEqual(r["resultats"][0]["section"], "Typographie")
        appels = panne.appels
        references.chercher(self.org, "palette")
        self.assertEqual(panne.appels, appels, "après une panne, l'embarqueur n'est plus sollicité pendant un délai")
        self.assertEqual(references.reindexer(self.org)["etat_vecteurs"], "indisponible")
        # l'embarqueur revient : les vecteurs manquants se rattrapent par une ré-indexation
        references.utiliser_embarqueur(EmbarqueurFactice())
        self.assertEqual(references.reindexer(self.org)["vecteurs"], 4)
        self.assertEqual(references.chercher(self.org, "tarifs")["mode"], "hybride")

    def test_capture_simulee_etats_assets_dedoublonnes_et_carte_du_board(self):
        pilote = pilote_simule()
        ref = references.ajouter(self.org, url="exemple.org/studio", collection="inspiration", etiquettes=["studio"], auteur="test")
        self.assertEqual((ref["statut"], ref["source"], ref["type"]), ("en_attente", "https://exemple.org/studio", "site"))
        deja = references.ajouter(self.org, url="https://exemple.org/studio", collection="inspiration", auteur="test")
        self.assertEqual((deja["id"], deja["deja"]), (ref["id"], True))
        ref = references.traiter(self.org, ref["id"], pilote=pilote, exceptions=(), autoriser_prives=True)
        self.assertEqual((ref["statut"], ref["raison"]), ("prete", ""))
        self.assertEqual(ref["titre"], "Atelier Lumière — studio de design")
        self.assertEqual(sorted(ref["fichiers"]), sorted(capture_site.FICHIERS))
        self.assertEqual(ref["vignette_url"], ref["fichiers"]["bureau_vue"]["url"])
        self.assertEqual([p["hex"] for p in ref["palette"]], ["#f7f3ec", "#1c1b19", "#c8553d"])
        self.assertEqual(ref["polices"], {"corps": "Inter", "titre": "Fraunces"})
        self.assertEqual([s["titre"] for s in ref["sections"]], ["Présentation", "", "Des sites qui respirent", "Nos prix", "Typographie"])
        self.assertRegex(ref["empreinte"], r"^[0-9a-f]{64}$")
        self.assertIn("DONNÉE non fiable", ref["avertissement"])
        etats = [json.loads(e["donnees"] if isinstance(e["donnees"], str) else json.dumps(e["donnees"])).get("statut")
                 for e in test_missions._sql(self.org, "SELECT donnees FROM evenements WHERE tenant_id=? AND type='reference_etat' "
                                             "ORDER BY seq", (self.org,))]
        self.assertEqual(etats, ["en_attente", "capture", "indexation", "prete"])
        r = references.chercher(self.org, "combien coûte le forfait vitrine ?")
        cite = r["resultats"][0]["citation"]
        self.assertEqual((cite["url"], cite["section"], cite["collection"]), ("https://exemple.org/studio", "Nos prix", "inspiration"))
        self.assertEqual(cite["capture_url"], ref["fichiers"]["bureau_page"]["url"])
        self.assertEqual(cite["zone"], {"y": 700, "hauteur": 400}, "renvoi vers la zone de la capture")
        # même site capturé dans une autre collection : mêmes octets, mêmes fichiers (dédoublonnage sha256)
        autre = references.ajouter(self.org, url="https://exemple.org/studio", collection="veille", auteur="test")
        autre = references.traiter(self.org, autre["id"], pilote=pilote, autoriser_prives=True)
        self.assertEqual({k: v["asset_id"] for k, v in autre["fichiers"].items()}, {k: v["asset_id"] for k, v in ref["fichiers"].items()})
        from jarvis import board
        chemin, info = board.fichier(self.org, ref["fichiers"]["bureau_vue"]["asset_id"])
        self.assertEqual((info["mime"], chemin.read_bytes()[:3]), ("image/jpeg", b"\xff\xd8\xff"))
        self.assertEqual(list((references._dossier_travail()).iterdir()), [], "le dossier de travail est vidé")
        # carte du Board reliée à la référence, sans mission lancée
        pose = references.poser_sur_board(self.org, ref["id"], espace="accueil", x=100, y=80, auteur="test")
        carte = next(o for o in board.objets(self.org, "accueil")["objets"] if o["id"] == pose["objet_id"])
        self.assertEqual((carte["type"], carte["meta"]["reference_id"], carte["meta"]["titre"]),
                         ("capture", ref["id"], "Atelier Lumière — studio de design"))
        self.assertEqual(carte["asset"]["id"], ref["fichiers"]["bureau_vue"]["asset_id"])
        self.assertIsNone(carte.get("mission"))

    def test_echec_de_capture_consultable_puis_relance(self):
        ref = references.ajouter(self.org, url="http://127.0.0.1:9/", auteur="test")
        ref = references.traiter(self.org, ref["id"])  # vraie garde : refus avant tout navigateur
        self.assertEqual(ref["statut"], "echec")
        self.assertRegex(ref["raison"], "port non standard|non publique")
        self.assertEqual(references.chercher(self.org, "atelier")["resultats"], [])
        with self.assertRaises(mi.MissionError):
            references.reindexer(self.org, ref["id"])

        def casse(configuration):
            raise RuntimeError("pilote cassé")
        autre = references.ajouter(self.org, url="https://exemple.org/", auteur="test")
        autre = references.traiter(self.org, autre["id"], pilote=casse, autoriser_prives=True)
        self.assertEqual((autre["statut"], autre["raison"]), ("echec", "erreur interne (RuntimeError)"))
        self.assertEqual(references.recapturer(self.org, autre["id"])["statut"], "en_attente")
        autre = references.traiter(self.org, autre["id"], pilote=pilote_simule(), autoriser_prives=True)
        self.assertEqual(autre["statut"], "prete")

    def test_file_de_captures_bornee(self):
        for i in range(references.FILE_MAX):
            references.ajouter(self.org, url=f"https://exemple.org/page-{i}", auteur="test")
        with self.assertRaises(mi.MissionError) as ctx:
            references.ajouter(self.org, url="https://exemple.org/de-trop", auteur="test")
        self.assertEqual(ctx.exception.code, "conflit")
        self.guide()  # un texte s'indexe toujours : il ne passe pas par la file de capture

    def test_capture_interrompue_declaree_en_echec(self):
        ref = references.ajouter(self.org, url="https://exemple.org/", auteur="test")
        test_missions._sql(self.org, "UPDATE board_references SET statut='capture', maj=? WHERE id=? AND tenant_id=?",
                           (time.time() - references.INTERROMPUE_S - 5, ref["id"], self.org))
        liste = references.lister(self.org)["references"]
        self.assertEqual((liste[0]["statut"], "interrompue" in liste[0]["raison"]), ("echec", True))

    def test_carte_du_board_comme_reference(self):
        o = mi.board_ajouter(self.org, "accueil", "note", "Le héros doit montrer le produit, pas un slogan.", auteur="test",
                             meta={"titre": "Principe du héros"}, analyser=False)
        ref = references.ajouter(self.org, objet_id=o["objet_id"], collection="principes", auteur="test")
        self.assertEqual((ref["type"], ref["titre"], ref["source"]), ("carte", "Principe du héros", f"board:{o['objet_id']}"))
        self.assertEqual(references.chercher(self.org, "slogan")["resultats"][0]["reference_id"], ref["id"])
        pose = references.poser_sur_board(self.org, ref["id"], auteur="test")
        from jarvis import board
        carte = next(x for x in board.objets(self.org, "accueil")["objets"] if x["id"] == pose["objet_id"])
        self.assertEqual((carte["type"], carte["meta"]["reference_id"]), ("note", ref["id"]))


# --- API -------------------------------------------------------------------------------------------------

class ApiTest(unittest.TestCase):
    def setUp(self):
        test_missions._reinitialiser()
        references.FORCER_REPLI = False
        references.utiliser_embarqueur(None)
        self.org = mi.tenant_local()
        self.jeton = studio_api.jeton(nouveau=True)
        self.httpd = studio_api.serveur(0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.cookie = ""

    def tearDown(self):
        references.attendre(20)
        references.utiliser_embarqueur()
        self.httpd.arret.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, methode, chemin, corps=None, *, entetes=None, ecriture=True, hote=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Host": hote or f"localhost:{self.port}"}
        if self.cookie:
            h["Cookie"] = self.cookie
        if methode == "POST":
            h["Content-Type"] = "application/json"
            if ecriture:
                h["X-Jarvis-Studio"] = "1"
        h.update(entetes or {})
        c.request(methode, chemin, body=json.dumps(corps).encode() if corps is not None else None, headers=h)
        r = c.getresponse()
        brut = r.read()
        c.close()
        try:
            return r.status, json.loads(brut)
        except ValueError:
            return r.status, brut.decode("utf-8", "replace")

    def connecter(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        c.request("POST", "/api/session", body=json.dumps({"jeton": self.jeton}).encode(),
                  headers={"Host": f"localhost:{self.port}", "Content-Type": "application/json", "X-Jarvis-Studio": "1"})
        r = c.getresponse()
        r.read()
        self.cookie = r.getheader("Set-Cookie").split(";", 1)[0]
        c.close()

    def attendre_etat(self, rid, finals=("prete", "echec")):
        vus = []
        fin = time.time() + 20
        while time.time() < fin:
            code, ref = self.req("GET", f"/api/v2/references/{rid}")
            self.assertEqual(code, 200)
            if not vus or vus[-1] != ref["statut"]:
                vus.append(ref["statut"])
            if ref["statut"] in finals:
                return ref, vus
            time.sleep(0.02)
        self.fail(f"capture jamais terminée : {vus}")

    def test_session_origine_et_entete_exiges(self):
        texte = {"texte": GUIDE}
        for chemin in ("/api/v2/references", "/api/v2/references/recherche?q=palette", "/api/v2/references/RF-000000000000"):
            self.assertEqual(self.req("GET", chemin)[0], 401, chemin)
        self.assertEqual(self.req("POST", "/api/v2/references", texte)[0], 401)
        self.assertEqual(self.req("GET", "/api/v2/references", hote="attaquant.example")[0], 403)
        self.connecter()
        self.assertEqual(self.req("POST", "/api/v2/references", texte, ecriture=False)[0], 403, "en-tête X-Jarvis-Studio exigé")
        self.assertEqual(self.req("POST", "/api/v2/references", texte, entetes={"Origin": "https://attaquant.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/v2/references", texte, hote="attaquant.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/v2/references")[1]["references"], [], "aucune écriture refusée n'a laissé de trace")
        code, ref = self.req("POST", "/api/v2/references", texte, entetes={"Origin": f"http://localhost:{self.port}"})
        self.assertEqual((code, ref["statut"]), (201, "prete"))

    def test_parcours_texte_liste_recherche_modification_suppression(self):
        self.connecter()
        code, ref = self.req("POST", "/api/v2/references", {"texte": GUIDE, "collection": "marque", "etiquettes": ["design"]})
        self.assertEqual(code, 201)
        code, liste = self.req("GET", "/api/v2/references?collection=marque&etiquette=design")
        self.assertEqual((code, [r["id"] for r in liste["references"]]), (200, [ref["id"]]))
        self.assertEqual(liste["moteur"]["vecteurs"], False)
        self.assertIn(liste["moteur"]["mots"], ("fts5", "python"))
        self.assertEqual(self.req("GET", "/api/v2/references?collection=autre")[1]["references"], [])
        code, r = self.req("GET", "/api/v2/references/recherche?q=polices%20%C3%A9l%C3%A9gantes&n=3")
        self.assertEqual((code, r["mode"], r["resultats"][0]["section"]), (200, "bm25", "Typographie"))
        self.assertEqual(r["resultats"][0]["citation"]["reference_id"], ref["id"])
        fid = r["resultats"][0]["fragment_id"]
        self.assertIn("linéale", self.req("GET", f"/api/v2/references/fragments/{fid}")[1]["texte"])
        self.assertEqual(self.req("GET", "/api/v2/references/recherche?q=polices&n=abc")[0], 400)
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}", {"titre": "Charte", "inconnu": 1})[0], 400)
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}", {"titre": "Charte"})[1]["titre"], "Charte")
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}/reindexer", {})[1]["fragments"], 4)
        self.assertEqual(self.req("POST", "/api/v2/references/reindexer", {})[1]["references"], 1)
        code, pose = self.req("POST", f"/api/v2/references/{ref['id']}/poser", {"espace": "accueil", "x": 40, "y": 40})
        self.assertEqual(code, 201)
        objets = self.req("GET", "/api/v2/board")[1]["objets"]
        self.assertEqual([o["meta"].get("reference_id") for o in objets if o["id"] == pose["objet_id"]], [ref["id"]])
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}/supprimer", {})[1], {"id": ref["id"], "supprime": True})
        self.assertEqual(self.req("GET", "/api/v2/references")[1]["references"], [])
        self.assertEqual(self.req("GET", "/api/v2/references/recherche?q=polices")[1]["resultats"], [])
        self.assertEqual([r["id"] for r in self.req("GET", "/api/v2/references?corbeille=1")[1]["references"]], [ref["id"]])
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}/supprimer", {"restaurer": True})[0], 200)
        self.assertEqual(len(self.req("GET", "/api/v2/references")[1]["references"]), 1)

    def test_erreurs_lisibles(self):
        self.connecter()
        self.assertEqual(self.req("GET", "/api/v2/references/RF-000000000000")[0], 404)
        self.assertEqual(self.req("GET", "/api/v2/references/n-importe-quoi")[0], 404)
        self.assertEqual(self.req("POST", "/api/v2/references/RF-000000000000/supprimer", {})[0], 404)
        self.assertEqual(self.req("POST", "/api/v2/references/RF-000000000000/poser", {})[0], 404)
        for corps in ({"url": "ftp://exemple.org"}, {"url": "https://exemple.org", "texte": "x"}, {"texte": 12},
                      {"url": "https://exemple.org", "role": "admin"}, {"titre": "rien d'autre"}):
            code, data = self.req("POST", "/api/v2/references", corps)
            self.assertEqual(code, 400, corps)
            self.assertIn("erreur", data)

    def test_capture_hors_du_fil_de_la_requete_avec_etats(self):
        self.connecter()
        depart, fin = threading.Event(), threading.Event()
        simule = pilote_simule()

        def pilote_lent(configuration):
            depart.set()
            fin.wait(10)
            return simule(configuration)
        self.httpd.references_pilote = pilote_lent
        self.httpd.references_prives = True
        code, ref = self.req("POST", "/api/v2/references", {"url": "https://exemple.org/studio", "collection": "inspiration"})
        self.assertEqual((code, ref["statut"]), (202, "en_attente"), "la requête répond avant la fin de la capture")
        self.assertTrue(depart.wait(10))
        self.assertEqual(self.req("GET", f"/api/v2/references/{ref['id']}")[1]["statut"], "capture")
        self.assertEqual(self.req("POST", "/api/v2/references", {"url": "https://exemple.org/studio", "collection": "inspiration"})[0], 200,
                         "même site, même collection : pas de doublon ni de seconde capture")
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}/reindexer", {"recapturer": True})[0], 409)
        self.assertEqual(self.req("POST", f"/api/v2/references/{ref['id']}/poser", {})[0], 409)
        fin.set()
        prete, vus = self.attendre_etat(ref["id"])
        self.assertEqual(prete["statut"], "prete")
        self.assertEqual(vus[0], "capture")
        self.assertEqual(len(simule.appels), 1)
        code, image = self.req("GET", prete["fichiers"]["bureau_vue"]["url"])
        self.assertEqual(code, 200)
        r = self.req("GET", "/api/v2/references/recherche?q=forfait%20vitrine")[1]
        self.assertEqual(r["resultats"][0]["citation"]["url"], "https://exemple.org/studio")
        code, relance = self.req("POST", f"/api/v2/references/{ref['id']}/reindexer", {"recapturer": True})
        self.assertEqual(code, 202)
        self.assertEqual(self.attendre_etat(ref["id"])[0]["statut"], "prete")
        self.assertEqual(len(simule.appels), 2)

    def test_adresse_privee_etat_echec_avec_raison(self):
        self.connecter()  # serveur réel, sans option de test : la garde s'applique
        with site({"/": html(b"<h1>interne</h1>")}) as interne:
            for url in (f"http://127.0.0.1:{interne.server_address[1]}/", "http://169.254.169.254/latest/meta-data/",
                        "http://[::1]/", "http://10.0.0.1/"):
                code, ref = self.req("POST", "/api/v2/references", {"url": url})
                self.assertEqual(code, 202, url)
                echec, _ = self.attendre_etat(ref["id"])
                self.assertEqual(echec["statut"], "echec", url)
                self.assertRegex(echec["raison"], "non publique|port non standard", url)
            self.assertEqual(interne.requetes, [])


# --- Ligne de commande -----------------------------------------------------------------------------------

class CliTest(unittest.TestCase):
    def setUp(self):
        test_missions._reinitialiser()
        references.FORCER_REPLI = False
        references.utiliser_embarqueur(None)
        self.org = mi.tenant_local()

    def tearDown(self):
        references.utiliser_embarqueur()

    def jarvis(self, *args, entree: str = ""):
        sortie, erreurs = io.StringIO(), io.StringIO()
        import sys
        ancien = sys.stdin
        sys.stdin = io.StringIO(entree)
        try:
            with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreurs):
                code = cli.main(["reference", *args])
        finally:
            sys.stdin = ancien
        return code, sortie.getvalue(), erreurs.getvalue()

    def test_ajouter_chercher_liste_voir(self):
        code, sortie, _ = self.jarvis("ajouter", "--texte", "-", "--collection", "marque", "--etiquette", "design", "ui", entree=GUIDE)
        self.assertEqual(code, 0)
        rid = sortie.split()[0]
        self.assertRegex(rid, r"^RF-[0-9a-f]{12}$")
        code, sortie, _ = self.jarvis("chercher", "polices élégantes", "--collection", "marque", "-n", "2")
        self.assertEqual(code, 0)
        self.assertRegex(sortie, r"\[1\] FR-[0-9a-f]{12} · Guide de style Aurore \(" + rid + r"\) · section « Typographie »")
        self.assertIn("**polices** **élégantes**", sortie)
        self.assertRegex(sortie, r"à citer : \[" + rid + r"#FR-[0-9a-f]{12}\] Guide de style Aurore")
        self.assertIn("DONNÉE non fiable", sortie)
        code, sortie, _ = self.jarvis("chercher", "polices", "--json")
        donnees = json.loads(sortie)
        self.assertEqual((donnees["nature"], donnees["resultats"][0]["reference_id"]), ("donnee_non_fiable", rid))
        code, sortie, _ = self.jarvis("liste")
        self.assertIn(rid, sortie)
        self.assertIn("#design #ui", sortie)
        code, sortie, _ = self.jarvis("voir", rid)
        self.assertIn("## Typographie", sortie)
        self.assertEqual(self.jarvis("voir", donnees["resultats"][0]["fragment_id"])[0], 0)
        self.assertEqual(self.jarvis("supprimer", rid)[0], 0)
        self.assertIn("Aucun passage", self.jarvis("chercher", "polices")[1])
        self.assertEqual(self.jarvis("restaurer", rid)[0], 0)
        self.assertEqual(self.jarvis("reindexer")[0], 0)

    def test_erreurs_en_francais_sans_trace(self):
        code, sortie, erreurs = self.jarvis("voir", "RF-000000000000")
        self.assertEqual((code, sortie), (1, ""))
        self.assertIn("référence inconnue", erreurs)
        self.assertEqual(self.jarvis("chercher")[0], 1)
        self.assertEqual(self.jarvis("ajouter")[0], 1)
        code, _, erreurs = self.jarvis("ajouter", "http://169.254.169.254/latest/meta-data/")
        self.assertEqual(code, 1)
        self.assertIn("non publique", erreurs)
        self.assertIn("Bibliothèque vide", self.jarvis("liste", "--collection", "inexistante")[1])


if __name__ == "__main__":
    unittest.main()
