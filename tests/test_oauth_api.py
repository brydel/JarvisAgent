"""OAuth dans le vrai serveur Studio : session, callback PKCE, annulation et coffre privé.

Les ports sont éphémères et STATE_DIR est isolé. Seul l'échange Google est injecté ; aucun compte,
code d'autorisation ou jeton réel n'est utilisé.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit

import test_studio
from jarvis import annulation, config, oauth

READ = "https://www.googleapis.com/auth/gmail.readonly"


def jetons():
    return {"status": 200, "contenu": json.dumps({"token_type": "Bearer", "access_token": "access-prive-test",
            "refresh_token": "refresh-prive-test", "expires_in": 3600, "scope": READ}).encode()}


class OAuthApiTest(unittest.TestCase):
    req = test_studio.StudioTest.req
    connecter = test_studio.StudioTest.connecter

    def setUp(self):
        temporaire = tempfile.TemporaryDirectory(prefix="jarvis-oauth-api-")
        self.addCleanup(temporaire.cleanup)
        self.state = Path(temporaire.name)
        patch = mock.patch.object(config, "STATE_DIR", self.state)
        patch.start(); self.addCleanup(patch.stop)
        patch_env = mock.patch.dict(os.environ, {"JARVIS_OAUTH_API_TEST_SECRET": "client-prive-test"})
        patch_env.start(); self.addCleanup(patch_env.stop)
        test_studio.StudioTest.setUp(self)

    def tearDown(self):
        test_studio.StudioTest.tearDown(self)
        self.fil.join(timeout=2)

    def spec(self):
        return {"id": "gmail-test", "nom": "Gmail test", "provider": "google_gmail",
                "client_id": "client-public-test.apps.googleusercontent.com",
                "client_secret_env": "JARVIS_OAUTH_API_TEST_SECRET", "scopes": [READ],
                "redirect_uri": f"http://localhost:{self.port}/api/v2/oauth/callback",
                "adresse_expediteur": "expediteur@example.test"}

    def configurer(self):
        self.connecter()
        code, public, _ = self.req("POST", "/api/v2/oauth", self.spec())
        self.assertEqual(code, 201, public)
        self.assertEqual(public["id"], "gmail-test")
        return public

    def commencer(self):
        code, lancement, _ = self.req("POST", "/api/v2/oauth/gmail-test/commencer", {})
        self.assertEqual(code, 200, lancement)
        p = parse_qs(urlsplit(lancement["authorization_url"]).query)
        self.assertEqual(p["code_challenge_method"], ["S256"])
        self.assertEqual(p["redirect_uri"], [self.spec()["redirect_uri"]])
        return p["state"][0]

    def retour(self, state, *, code="code-prive-test", **params):
        return self.req("GET", "/api/v2/oauth/callback?" + urlencode({"state": state, "code": code, **params}),
                        cookie=False, ecriture=False)

    def verifier_public(self, valeur, *prives):
        texte = json.dumps(valeur, ensure_ascii=False)
        for prive in ("access-prive-test", "refresh-prive-test", "client-prive-test", "code-prive-test", *prives):
            self.assertNotIn(prive, texte)

    def test_session_proprietaire_exigee_pour_liste_configuration_lancement_revocation(self):
        self.assertEqual(self.req("GET", "/api/v2/oauth")[0], 401)
        for route, corps in (("/api/v2/oauth", self.spec()), ("/api/v2/oauth/gmail-test/commencer", {}),
                             ("/api/v2/oauth/gmail-test/revoquer", {})):
            self.assertEqual(self.req("POST", route, corps)[0], 401)
        self.assertFalse((self.state / "oauth_prive/registre.json").exists())
        self.configurer()
        self.assertEqual(self.req("POST", "/api/v2/oauth/gmail-test/commencer", {}, cookie=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/v2/oauth/gmail-test/revoquer", {}, cookie=False)[0], 401)
        self.assertEqual(oauth.etat("gmail-test")["etat"], "configuree")

    def test_origine_etrangere_refusee_avant_modification(self):
        self.configurer()
        origine = {"Origin": "https://ailleurs.example.test"}
        for route, corps in (("/api/v2/oauth", {**self.spec(), "id": "autre"}),
                             ("/api/v2/oauth/gmail-test/commencer", {}), ("/api/v2/oauth/gmail-test/revoquer", {})):
            self.assertEqual(self.req("POST", route, corps, entetes=origine)[0], 403)
        self.assertEqual(len(oauth.lister()), 1)
        self.assertEqual(oauth.etat("gmail-test")["generation"], 1)

    def test_callback_sans_cookie_et_parametres_google_legitimes_acceptes_sans_fuite(self):
        self.configurer(); state = self.commencer()
        journaux = io.StringIO()
        with mock.patch.object(oauth.outils_http, "requete", return_value=jetons()) as http, \
             contextlib.redirect_stderr(journaux), contextlib.redirect_stdout(journaux):
            code, page, reponse = self.retour(state, scope=READ, authuser="0", prompt="consent", hd="example.test",
                                              iss="https://accounts.google.com")
        self.assertEqual(code, 200, page)
        self.assertIn("text/html", reponse.getheader("Content-Type"))
        self.assertIn("no-store", reponse.getheader("Cache-Control"))
        self.assertEqual(http.call_count, 1)
        formulaire = http.call_args.kwargs["formulaire"]
        self.assertEqual(formulaire["code"], "code-prive-test")
        self.assertEqual(formulaire["client_secret"], "client-prive-test")
        self.assertGreaterEqual(len(formulaire["code_verifier"]), 43)
        self.assertIsInstance(http.call_args.kwargs["annulation"], annulation.ControleExecution)
        self.verifier_public(page, state, formulaire["code_verifier"])
        self.verifier_public(journaux.getvalue(), state, formulaire["code_verifier"])
        code, metadata, _ = self.req("GET", "/api/v2/oauth")
        self.assertEqual(code, 200)
        self.assertEqual(metadata["connexions"][0]["etat"], "connectee")
        self.verifier_public(metadata, state, formulaire["code_verifier"])

    def test_etat_invente_duplique_et_query_ambigue_ne_refont_pas_echange(self):
        self.configurer(); state = self.commencer()
        with mock.patch.object(oauth.outils_http, "requete", return_value=jetons()) as http:
            self.assertEqual(self.retour(secrets.token_urlsafe(32))[0], 400)
            query = urlencode({"state": state, "code": "code-prive-test"}) + "&state=" + state
            self.assertEqual(self.req("GET", "/api/v2/oauth/callback?" + query, cookie=False)[0], 400)
            self.assertEqual(self.retour(state, config="non-acceptee")[0], 400)
            http.assert_not_called()
            self.assertEqual(self.retour(state)[0], 200)
            self.assertEqual(self.retour(state)[0], 400)
            self.assertEqual(http.call_count, 1)

    def test_mauvais_hote_callback_refuse_sans_consumer_etat(self):
        self.configurer(); state = self.commencer()
        query = urlencode({"state": state, "code": "code-prive-test"})
        with mock.patch.object(oauth.outils_http, "requete", return_value=jetons()) as http:
            self.assertEqual(self.req("GET", "/api/v2/oauth/callback?" + query, cookie=False, hote="ailleurs.example.test")[0], 403)
            http.assert_not_called()
            self.assertEqual(self.retour(state)[0], 200)

    def test_annulation_callback_descend_au_transport_et_ne_connecte_pas(self):
        self.configurer(); state = self.commencer()
        def echange(*_, **kwargs):
            controle = kwargs["annulation"]
            self.assertIsInstance(controle, annulation.ControleExecution)
            controle.verifier()
            self.httpd.arret.set()
            controle.verifier()
            raise AssertionError("Le contrôle doit annuler avant cette ligne.")
        journaux = io.StringIO()
        with mock.patch.object(oauth.outils_http, "requete", side_effect=echange), contextlib.redirect_stderr(journaux):
            code, page, _ = self.retour(state)
        self.assertIn(code, (400, 503))
        self.assertEqual(oauth.etat("gmail-test")["etat"], "configuree")
        self.verifier_public(page, state)
        self.assertNotIn("Traceback", journaux.getvalue())

    def test_annulation_revocation_http_ne_perd_pas_tombstone_locale(self):
        self.configurer(); state = self.commencer()
        with mock.patch.object(oauth.outils_http, "requete", return_value=jetons()):
            self.assertEqual(self.retour(state)[0], 200)
        def revoke(*_, **kwargs):
            controle = kwargs["annulation"]
            self.assertIsInstance(controle, annulation.ControleExecution)
            self.assertEqual(oauth.etat("gmail-test")["etat"], "revoquee")
            self.httpd.arret.set()
            controle.verifier()
            raise AssertionError("Le contrôle doit annuler avant cette ligne.")
        journaux = io.StringIO()
        with mock.patch.object(oauth.outils_http, "requete", side_effect=revoke), contextlib.redirect_stderr(journaux):
            code, data, _ = self.req("POST", "/api/v2/oauth/gmail-test/revoquer", {})
        # La révocation locale a réussi avant l'interruption distante : le reçu 200 décrit ce résultat.
        self.assertEqual(code, 200, data)
        self.assertEqual(data["etat"], "revoquee")
        self.assertEqual(data["revocation_distante"], "non_confirmee")
        self.verifier_public(data)
        self.assertNotIn("Traceback", journaux.getvalue())
        self.assertEqual(oauth.etat("gmail-test")["etat"], "revoquee")
        self.assertNotIn("access-prive-test", (self.state / "oauth_prive/registre.json").read_text())
        self.assertNotIn("refresh-prive-test", (self.state / "oauth_prive/registre.json").read_text())

    def test_arret_avant_requete_post_refuse_sans_modifier_connexion(self):
        self.configurer(); state = self.commencer()
        with mock.patch.object(oauth.outils_http, "requete", return_value=jetons()):
            self.assertEqual(self.retour(state)[0], 200)
        avant = (self.state / "oauth_prive/registre.json").read_bytes()
        self.httpd.arret.set()
        with mock.patch.object(oauth.outils_http, "requete") as http:
            code, data, _ = self.req("POST", "/api/v2/oauth/gmail-test/revoquer", {})
            self.assertEqual(code, 503, data)
            self.verifier_public(data)
            http.assert_not_called()
        self.assertEqual((self.state / "oauth_prive/registre.json").read_bytes(), avant)

    def test_coffre_corrompu_preserve_et_signale_503_sans_donnees_privees(self):
        self.configurer(); state = self.commencer()
        fichier = self.state / "oauth_prive/registre.json"
        corrompu = b'{"access_token":"ne-pas-retourner-au-client",CORROMPU'
        fichier.write_bytes(corrompu)
        for methode, route, corps in (("GET", "/api/v2/oauth", None),
                                      ("POST", "/api/v2/oauth/gmail-test/commencer", {}),
                                      ("POST", "/api/v2/oauth/gmail-test/revoquer", {})):
            code, data, _ = self.req(methode, route, corps)
            self.assertEqual(code, 503, data)
            self.assertNotIn("ne-pas-retourner", json.dumps(data))
            self.assertNotIn(str(fichier), json.dumps(data))
            self.assertEqual(fichier.read_bytes(), corrompu)
        with mock.patch.object(oauth.outils_http, "requete") as http:
            code, page, _ = self.retour(state)
            self.assertEqual(code, 503, page)
            self.verifier_public(page, state, "ne-pas-retourner-au-client")
            http.assert_not_called()
        self.assertEqual(fichier.read_bytes(), corrompu)


if __name__ == "__main__":
    unittest.main()
