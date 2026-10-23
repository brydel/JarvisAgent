"""PKCE, coffre privé, renouvellement et révocation sans compte Google ni jeton réel."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from jarvis import config, oauth  # noqa: E402

READ = "https://www.googleapis.com/auth/gmail.readonly"
SEND = "https://www.googleapis.com/auth/gmail.send"
COMPOSE = "https://www.googleapis.com/auth/gmail.compose"


def reponse_token(**valeurs):
    data = {"token_type": "Bearer", "access_token": "access-confidentiel", "refresh_token": "refresh-confidentiel", "expires_in": 3600}
    data.update(valeurs)
    return {"status": 200, "contenu": json.dumps(data).encode(), "entetes": {"content-type": "application/json"}}


class OAuthBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="jarvis-oauth-")
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        patch = mock.patch.object(config, "STATE_DIR", self.state)
        patch.start(); self.addCleanup(patch.stop)

    def configurer(self, scopes=None, **modifs):
        spec = {"id": "google", "nom": "Google test", "provider": "google_gmail", "client_id": "client-test.apps.googleusercontent.com",
                "redirect_uri": "http://localhost:7718/api/v2/oauth/callback", "scopes": scopes or [READ, SEND, COMPOSE],
                "adresse_expediteur": "expediteur@example.test"}
        spec.update(modifs)
        return oauth.configurer(spec, par="proprietaire")

    def flux(self):
        f = oauth.commencer("google", par="proprietaire")
        self.params = parse_qs(urlsplit(f["authorization_url"]).query)
        return self.params["state"][0]

    def connecter(self, **reponse):
        state = self.flux()
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token(**reponse)):
            return oauth.callback(state, "code-prive")


class OAuthTest(OAuthBase):
    def test_flux_pkce_unique_code_secret_coffre_et_metadata(self):
        self.configurer()
        state = self.flux()
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token()) as http:
            public = oauth.callback(state, "code-prive")
        appel = http.call_args
        self.assertEqual(appel.args, ("https://oauth2.googleapis.com/token",))
        formulaire = appel.kwargs["formulaire"]
        verifier = formulaire["code_verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(self.params["code_challenge"], [challenge])
        self.assertEqual(formulaire["redirect_uri"], self.params["redirect_uri"][0])
        self.assertEqual(self.params["include_granted_scopes"], ["false"])
        self.assertEqual(public["etat"], "connectee")
        for prive in (state, verifier, "access-confidentiel", "refresh-confidentiel", "code-prive"):
            self.assertNotIn(prive, json.dumps(public))
        coffre = self.state / "oauth_prive" / "registre.json"
        self.assertEqual(coffre.stat().st_mode & 0o777, 0o600)
        self.assertEqual(coffre.parent.stat().st_mode & 0o777, 0o700)
        self.assertIn("access-confidentiel", coffre.read_text())
        self.assertNotIn(state, coffre.read_text())
        self.assertEqual(oauth.jeton_acces("google", [READ]), "access-confidentiel")

    def test_callback_usage_unique_concurrent_et_pas_rejeu_apres_timeout(self):
        self.configurer(); state = self.flux()
        barriere = threading.Barrier(8)
        def retourner(_):
            barriere.wait()
            try:
                oauth.callback(state, "code-prive")
                return True
            except oauth.OAuthError:
                return False
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token()) as http, ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(retourner, range(8))), 1)
            self.assertEqual(http.call_count, 1)
        state = self.flux()
        with mock.patch.object(oauth.outils_http, "requete", side_effect=ValueError("token-prive")) as http:
            for _ in range(2):
                with self.assertRaises(oauth.OAuthError) as ctx:
                    oauth.callback(state, "code-prive")
                self.assertNotIn("token-prive", str(ctx.exception))
            self.assertEqual(http.call_count, 1)

    def test_callback_expire_remplace_revoque_et_etat_imprevisible(self):
        self.configurer(); a = self.flux(); b = self.flux()
        self.assertNotEqual(a, b)
        with mock.patch.object(oauth.outils_http, "requete") as http:
            with self.assertRaises(oauth.OAuthError): oauth.callback(a, "code")
            with mock.patch.object(oauth.time, "time", return_value=time.time() + 601):
                with self.assertRaises(oauth.OAuthError): oauth.callback(b, "code")
            oauth.revoquer("google", par="proprietaire")
            with self.assertRaises(oauth.OAuthError): oauth.callback(b, "code")
            http.assert_not_called()

    def test_retour_tardif_ne_reactive_pas_connexion_revoquee(self):
        self.configurer(); state = self.flux()
        parti, finir = threading.Event(), threading.Event()
        def reseau(*_, **__):
            parti.set(); finir.wait(2)
            return reponse_token()
        with mock.patch.object(oauth.outils_http, "requete", side_effect=reseau), ThreadPoolExecutor(max_workers=1) as pool:
            f = pool.submit(oauth.callback, state, "code")
            self.assertTrue(parti.wait(1))
            oauth.revoquer("google", par="proprietaire")
            finir.set()
            with self.assertRaises(oauth.OAuthError): f.result()
        self.assertEqual(oauth.etat("google")["etat"], "revoquee")

    def test_scopes_reels_partiels_pas_de_droit_induit(self):
        self.configurer(scopes=[READ, SEND]); self.connecter(scope=READ)
        oauth.verifier("google", [READ])
        with self.assertRaises(oauth.OAuthError): oauth.verifier("google", [SEND])
        with mock.patch.object(oauth.time, "time", return_value=time.time() + 4000), \
             mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token(access_token="nouvel-access", refresh_token="")):
            self.assertEqual(oauth.jeton_acces("google", [READ]), "nouvel-access")
        self.assertEqual(oauth.etat("google")["scopes_accordes"], [READ])
        with self.assertRaises(oauth.OAuthError): oauth.verifier("google", [SEND])

    def test_renouvellement_rotation_et_concurrence_un_seul_appel(self):
        self.configurer(); self.connecter()
        ancien = time.time()
        with mock.patch.object(oauth.time, "time", return_value=ancien + 4000), \
             mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token(access_token="access-neuf", refresh_token="refresh-neuf")) as http, \
             ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(lambda _: oauth.jeton_acces("google", [READ]), range(8))), ["access-neuf"] * 8)
            self.assertEqual(http.call_count, 1)
        self.assertIn("refresh-neuf", (self.state / "oauth_prive/registre.json").read_text())
        self.assertNotIn("refresh-confidentiel", (self.state / "oauth_prive/registre.json").read_text())

    def test_renouvellement_ne_reactive_pas_generation_remplacee(self):
        self.configurer(); self.connecter()
        ancien = time.time()
        def reseau(*_, **__):
            oauth.revoquer("google", par="proprietaire")
            return reponse_token(access_token="access-tardif")
        # Révocation pendant refresh appelle elle-même Google : fournir son reçu séparément.
        appels = 0
        def deux_appels(*a, **kw):
            nonlocal appels
            appels += 1
            if a[0].endswith('/revoke'):
                return {"status": 200, "contenu": b''}
            return reseau(*a, **kw)
        with mock.patch.object(oauth.time, "time", return_value=ancien + 4000), mock.patch.object(oauth.outils_http, "requete", side_effect=deux_appels):
            with self.assertRaises(oauth.OAuthError): oauth.jeton_acces("google", [READ])
        self.assertEqual(oauth.etat("google")["etat"], "revoquee")
        self.assertNotIn("access-tardif", (self.state / "oauth_prive/registre.json").read_text())

    def test_revoquer_reste_localement_effectif_quand_google_echoue(self):
        self.configurer(); self.connecter()
        with mock.patch.object(oauth.outils_http, "requete", side_effect=ValueError("secret-reflete")):
            public = oauth.revoquer("google", par="proprietaire")
        self.assertEqual((public["etat"], public["revocation_distante"]), ("revoquee", "non_confirmee"))
        self.assertNotIn("confidentiel", (self.state / "oauth_prive/registre.json").read_text())
        with self.assertRaises(oauth.OAuthError): oauth.jeton_acces("google", [READ])

    def test_secret_client_par_reference_et_absence_expurgation(self):
        self.configurer(client_secret_env="JARVIS_OAUTH_TEST_SECRET")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(oauth.OAuthError): self.flux()
        with mock.patch.dict(os.environ, {"JARVIS_OAUTH_TEST_SECRET": "secret-client-prive"}):
            state = self.flux()
            self.assertNotIn("secret-client-prive", json.dumps(oauth.etat("google")))
            with mock.patch.object(oauth.outils_http, "requete", return_value=reponse_token()) as http:
                oauth.callback(state, "code")
            self.assertEqual(http.call_args.kwargs["formulaire"]["client_secret"], "secret-client-prive")
        self.assertNotIn("secret-client-prive", (self.state / "oauth_prive/registre.json").read_text())

    def test_configuration_immuable_et_redirect_scope_corrompus_refuses(self):
        self.configurer()
        with self.assertRaises(oauth.OAuthError): self.configurer()
        for changements in ({"id": "autre", "redirect_uri": "https://example.test/retour"},
                             {"id": "autre", "redirect_uri": "http://localhost:7718/autre"},
                             {"id": "autre", "scopes": ["https://mail.google.com/"]},
                             {"id": "../secret"}, {"id": "autre", "adresse_expediteur": "a@example.test,b@example.test"}):
            with self.assertRaises(oauth.OAuthError): self.configurer(**changements)

    def test_coffre_corrompu_ou_permissions_larges_refuse_sans_effacer(self):
        self.configurer()
        fichier = self.state / "oauth_prive/registre.json"
        fichier.write_text('{invalide')
        with self.assertRaises(oauth.OAuthError): oauth.lister()
        self.assertEqual(fichier.read_text(), '{invalide')
        fichier.write_text(json.dumps(oauth._vide())); fichier.chmod(0o644)
        with self.assertRaises(oauth.OAuthError): oauth.lister()
        self.assertEqual(fichier.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
