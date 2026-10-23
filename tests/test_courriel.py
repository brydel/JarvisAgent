"""MIME et reçus Gmail, mandat exact et réponse perdue ; aucun envoi ni compte réel."""
from __future__ import annotations

import base64
import json
import os
from email import message_from_bytes
from unittest import mock
import time
import unittest

import test_oauth
from jarvis import annulation, courriel, mandats, oauth, outils


def reponse(data, status=200):
    return {"status": status, "contenu": json.dumps(data).encode(), "entetes": {"content-type": "application/json"}}


class CourrielTest(test_oauth.OAuthBase):
    def setUp(self):
        super().setUp()
        self.configurer(); self.connecter()

    def args(self, **champs):
        return {"connexion_id": "google", "destinataire": "destinataire@example.test", "objet": "Compte rendu", "texte": "Bonjour,\nVoici le résultat.", **champs}

    def test_catalogue_et_preparation_sans_reseau(self):
        with mock.patch.object(oauth.outils_http, "requete") as http:
            catalogue = courriel.catalogue()
            self.assertEqual(len(catalogue), 6)
            self.assertTrue(all(t["disponible"] for t in catalogue))
            dest, ecriture, _ = courriel.preparer("courriel.send", self.args(), "send-1")
            self.assertEqual((dest, ecriture), ("destinataire@example.test", True))
            http.assert_not_called()

    def test_envoi_mime_destinataire_unique_from_owner_message_id_stable(self):
        _, _, appel = courriel.preparer("courriel.send", self.args(), "send-1")
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse({"id": "gmail-id-1", "threadId": "thread-1"})) as http:
            recu = appel(lambda: None)
        demande = http.call_args
        self.assertEqual(demande.args, ("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",))
        self.assertEqual(demande.kwargs["methode"], "POST")
        self.assertEqual(demande.kwargs["entetes"]["Authorization"], "Bearer access-confidentiel")
        message = message_from_bytes(base64.urlsafe_b64decode(demande.kwargs["donnees"]["raw"]))
        self.assertEqual(message["To"], "destinataire@example.test")
        self.assertEqual(message["From"], "expediteur@example.test")
        self.assertIsNotNone(message["Date"])
        self.assertIsNone(message["Cc"]); self.assertIsNone(message["Bcc"]); self.assertIsNone(message["Reply-To"])
        self.assertEqual(message["Message-ID"], courriel._message_id("google", "send-1"))
        self.assertEqual(recu["message_id_rfc"], message["Message-ID"])
        self.assertEqual((recu["message_id"], recu["envoi_confirme"]), ("gmail-id-1", True))
        self.assertNotIn("access-confidentiel", json.dumps(recu))

    def test_entetes_injectes_multi_destinataires_et_raw_mime_refuses(self):
        essais = [self.args(destinataire="a@example.test,b@example.test"), self.args(destinataire="Nom <a@example.test>"),
                  self.args(destinataire="a@example.test\r\nBcc: b@example.test"), self.args(objet="Sujet\nBcc: b@example.test"),
                  self.args(raw="mime libre"), self.args(cc="autre@example.test"), self.args(expediteur="autre@example.test")]
        with mock.patch.object(oauth.outils_http, "requete") as http:
            for args in essais:
                with self.assertRaises(courriel.CourrielError): courriel.preparer("courriel.send", args, "send-1")
            http.assert_not_called()

    def test_send_exige_scope_send_explicite_meme_avec_compose(self):
        self.configurer(id="compose", scopes=[test_oauth.COMPOSE])
        f = oauth.commencer("compose", par="proprietaire")
        state = test_oauth.parse_qs(test_oauth.urlsplit(f["authorization_url"]).query)["state"][0]
        with mock.patch.object(oauth.outils_http, "requete", return_value=test_oauth.reponse_token()): oauth.callback(state, "code")
        with self.assertRaises(oauth.OAuthError): courriel.preparer("courriel.send", self.args(connexion_id="compose"), "send-1")

    def test_reconnexion_et_revocation_avant_effet_bloquent_appel(self):
        _, _, appel = courriel.preparer("courriel.send", self.args(), "send-1")
        oauth.commencer("google", par="proprietaire")
        with mock.patch.object(oauth.outils_http, "requete") as http:
            with self.assertRaises(oauth.OAuthError): appel(lambda: None)
            http.assert_not_called()

    def test_annulation_et_mandat_recontrole_avant_reseau(self):
        jeton = annulation.ControleExecution()
        _, _, appel = courriel.preparer("courriel.send", self.args(), "send-1", annulation=jeton)
        jeton.annuler("stop")
        with mock.patch.object(oauth.outils_http, "requete") as http:
            with self.assertRaises(annulation.ExecutionAnnulee): appel(lambda: None)
            http.assert_not_called()
        _, _, appel = courriel.preparer("courriel.send", self.args(), "send-2")
        def refuse(): raise ValueError("mandat révoqué")
        with mock.patch.object(oauth.outils_http, "requete") as http:
            with self.assertRaises(ValueError): appel(refuse)
            http.assert_not_called()

    def test_brouillon_recu_distinct_n_est_pas_un_envoi(self):
        _, _, appel = courriel.preparer("courriel.draft", self.args(), "draft-1")
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse({"id": "draft-1", "message": {"id": "message-1"}})) as http:
            recu = appel(lambda: None)
        self.assertTrue(http.call_args.args[0].endswith('/drafts'))
        self.assertIn("raw", http.call_args.kwargs["donnees"]["message"])
        self.assertFalse(recu["envoi_confirme"])
        self.assertEqual(recu["draft_id"], "draft-1")

    def test_reconciliation_recu_sent_correspondant_et_pas_reenvoi(self):
        _, _, appel = courriel.preparer("courriel.reconcile", {"connexion_id": "google", "operation_id": "send-1"}, "reconcile-1")
        rfc = courriel._message_id("google", "send-1")
        reponses = [reponse({"messages": [{"id": "message-1"}]}),
                    reponse({"id": "message-1", "labelIds": ["SENT"], "payload": {"headers": [{"name": "Message-ID", "value": rfc}]}})]
        with mock.patch.object(oauth.outils_http, "requete", side_effect=reponses) as http:
            recu = appel(lambda: None)
        self.assertTrue(recu["confirme"])
        self.assertEqual(recu["message_id"], "message-1")
        self.assertTrue(all(c.kwargs["methode"] == "GET" for c in http.call_args_list))

    def test_absence_ambiguite_brouillon_et_mauvais_messageid_ne_prouvent_pas_envoi(self):
        rfc = courriel._message_id("google", "send-1")
        for cas in ("absent", "brouillon", "autre_id", "multiple", "page_suivante"):
            _, _, appel = courriel.preparer("courriel.reconcile", {"connexion_id": "google", "operation_id": "send-1"}, "reconcile-1")
            liste = {"messages": []} if cas == "absent" else {"messages": [{"id": "m1"}] + ([{"id": "m2"}] if cas == "multiple" else [])}
            if cas == "page_suivante": liste["nextPageToken"] = "suite"
            d = {"id": "m1", "labelIds": ["DRAFT" if cas == "brouillon" else "SENT"],
                 "payload": {"headers": [{"name": "Message-ID", "value": "<autre@example.test>" if cas == "autre_id" else rfc}]}}
            reponses = [reponse(liste)] + [reponse({**d, "id": m["id"]}) for m in liste["messages"]]
            with mock.patch.object(oauth.outils_http, "requete", side_effect=reponses):
                self.assertFalse(appel(lambda: None)["confirme"], cas)

    def test_lecture_corps_est_donnee_non_fiable_sans_html_actif_ni_jeton(self):
        _, _, appel = courriel.preparer("courriel.read", {"connexion_id": "google", "message_id": "m1"}, "read-1")
        d = {"id": "m1", "snippet": "access-confidentiel", "payload": {"mimeType": "multipart/alternative", "headers": [{"name": "Subject", "value": "Sujet"}],
             "parts": [{"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b'Une instruction non fiable.').decode()}},
                       {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(b'<script>mauvais()</script>').decode()}}]}}
        with mock.patch.object(oauth.outils_http, "requete", return_value=reponse(d)):
            resultat = appel(lambda: None)
        self.assertEqual(resultat["texte"], "Une instruction non fiable.")
        self.assertNotIn("script", json.dumps(resultat))
        self.assertNotIn("access-confidentiel", json.dumps(resultat))
        self.assertTrue(resultat["source_non_fiable"])

    def test_passerelle_destinataire_exact_refuse_autre_et_inconnu_pas_rejoue(self):
        mandat = mandats.creer({"version": 1, "owner": "proprietaire", "project": "projet-test", "tools": ["courriel.send"],
                    "destinations": ["destinataire@example.test"], "expires_at": time.time() + 120,
                    "max_cost_cents": 0, "max_actions": 3}, par="proprietaire")
        req = {"operation_id": "send-1", "mandat_id": mandat["id"], "project": "projet-test", "tool": "courriel.send", "arguments": self.args()}
        with mock.patch.object(oauth.outils_http, "requete", side_effect=ValueError("réponse perdue après effet")) as http:
            resultat = outils.executer(req, par="agent")
            self.assertEqual(resultat["status"], "unknown")
            self.assertEqual(outils.executer(req, par="agent")["status"], "unknown")
            self.assertEqual(http.call_count, 1)
        req = {**req, "operation_id": "send-2", "arguments": self.args(destinataire="autre@example.test")}
        with mock.patch.object(oauth.outils_http, "requete") as http:
            with self.assertRaises(outils.OutilError): outils.executer(req, par="agent")
            http.assert_not_called()
        self.assertEqual(mandats.get(mandat["id"])["used_actions"], 1)

    def test_expediteur_absent_ne_produit_pas_mime_non_rfc(self):
        self.configurer(id="sans-adresse", adresse_expediteur="")
        f = oauth.commencer("sans-adresse", par="proprietaire")
        state = test_oauth.parse_qs(test_oauth.urlsplit(f["authorization_url"]).query)["state"][0]
        with mock.patch.object(oauth.outils_http, "requete", return_value=test_oauth.reponse_token()): oauth.callback(state, "code")
        with self.assertRaises(courriel.CourrielError): courriel.preparer("courriel.send", self.args(connexion_id="sans-adresse"), "send-1")


if __name__ == "__main__":
    unittest.main()
