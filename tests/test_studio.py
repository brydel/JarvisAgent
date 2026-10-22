"""Jarvis Next, jalon M2 (local) : API du Studio et page Board. Serveur réel sur 127.0.0.1, sans navigateur."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import re
import stat
import threading
import unittest

import test_jarvis  # noqa: F401 — environnement isolé
import test_missions

from jarvis import adaptateurs as ad, config, coureur, missions as mi, studio_api  # noqa: E402


class StudioTest(unittest.TestCase):
    def setUp(self):
        test_missions._reinitialiser()
        self.org = mi.tenant_local()
        mi.declarer_connexion(self.org, "factice", "factice")
        self.jeton = studio_api.jeton(nouveau=True)
        self.httpd = studio_api.serveur(0)
        self.httpd.intervalle_flux = 0.05
        self.port = self.httpd.server_address[1]
        self.fil = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.fil.start()
        self.cookie = ""

    def tearDown(self):
        self.httpd.arret.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, methode, chemin, corps=None, *, hote=None, entetes=None, ecriture=True, cookie=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": hote or f"localhost:{self.port}"}
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        if methode == "POST" and ecriture:
            h["X-Jarvis-Studio"] = "1"
            h["Content-Type"] = "application/json"
        h.update(entetes or {})
        c.request(methode, chemin, body=json.dumps(corps).encode() if corps is not None else None, headers=h)
        r = c.getresponse()
        brut = r.read()
        c.close()
        try:
            data = json.loads(brut)
        except ValueError:
            data = brut.decode("utf-8", "replace")
        return r.status, data, r

    def connecter(self):
        code, _, r = self.req("POST", "/api/session", {"jeton": self.jeton})
        self.assertEqual(code, 200)
        cookie = r.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.cookie = cookie.split(";", 1)[0]

    # --- sécurité ---
    def test_hote_etranger_refuse(self):
        self.assertEqual(self.req("GET", "/", hote="attaquant.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/board", hote="attaquant.example")[0], 403)

    def test_sans_session_pas_de_donnees(self):
        self.mission_factice()
        code, data, _ = self.req("GET", "/api/board")
        self.assertEqual(code, 401)
        self.assertNotIn("objets", data)
        self.assertEqual(self.req("POST", "/api/board", {"contenu": "x"})[0], 401)

    def test_jeton_invalide_et_ecritures_d_une_autre_origine(self):
        self.assertEqual(self.req("POST", "/api/session", {"jeton": "faux"})[0], 401)
        self.assertEqual(self.req("POST", "/api/session", {"jeton": self.jeton}, ecriture=False,
                                  entetes={"Content-Type": "application/json"})[0], 403)
        self.connecter()
        corps = {"contenu": "Note légitime à analyser par Jarvis"}
        self.assertEqual(self.req("POST", "/api/board", corps, entetes={"Origin": "https://attaquant.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/board", corps, ecriture=False,
                                  entetes={"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.req("POST", "/api/board", corps,
                                  entetes={"Origin": f"http://localhost:{self.port}"})[0], 201)

    def test_nouveau_jeton_ferme_les_sessions(self):
        self.connecter()
        self.assertEqual(self.req("GET", "/api/board")[0], 200)
        studio_api.jeton(nouveau=True)
        self.assertEqual(self.req("GET", "/api/board")[0], 401)
        mode = stat.S_IMODE(os.stat(studio_api.chemin_jeton()).st_mode)
        self.assertEqual(mode, 0o600)

    def test_page_sans_script_en_ligne_et_csp(self):
        code, page, r = self.req("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"))
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page), "aucun script en ligne")
        self.assertNotRegex(page, r"https?://", "aucune ressource externe")
        js = self.req("GET", "/studio.js")[1]
        self.assertNotIn("innerHTML", js, "les contenus sont rendus en texte, jamais en HTML")
        self.assertEqual(self.req("GET", "/connexion")[0], 200)

    # --- parcours ---
    def mission_factice(self):
        return mi.board_ajouter(self.org, "accueil", "note", "Note posée directement dans le moteur", auteur="test")

    def test_note_du_studio_jusqu_a_l_artefact(self):
        self.connecter()
        code, o, _ = self.req("POST", "/api/board", {"type": "note", "contenu": "Compte rendu : démo vendredi.",
                                                     "x": 120, "y": 80})
        self.assertEqual(code, 201)
        self.assertTrue(o["mission_id"])
        rid, secret = mi.enroler_executant(self.org, "poste", capacites=["analyse"], fournisseurs=["factice"])
        self.assertEqual(coureur.Coureur(coureur.TransportLocal(rid, secret), {"factice": ad.Factice()}).tour()["etat"],
                         "fait")
        objets = self.req("GET", "/api/board?espace=accueil")[1]["objets"]
        self.assertEqual((objets[0]["x"], objets[0]["y"]), (120, 80))
        self.assertEqual(objets[0]["mission_statut"], mi.SUCCEEDED)
        self.assertEqual(objets[0]["artefacts"][0]["factice"], 1)
        m = self.req("GET", f"/api/missions/{o['mission_id']}")[1]
        self.assertEqual(m["statut"], mi.SUCCEEDED)
        ex = self.req("GET", "/api/execution")[1]
        self.assertTrue(ex["executants"][0]["actif"])
        self.assertNotIn("secret", json.dumps(ex), "aucun secret d'exécutant exposé")
        # déplacement persistant
        self.assertEqual(self.req("POST", f"/api/board/{o['objet_id']}/position", {"x": 400, "y": 10})[0], 200)
        self.assertEqual(self.req("GET", "/api/board")[1]["objets"][0]["x"], 400)
        self.assertEqual(self.req("POST", "/api/board/BO-000000000000/position", {"x": 1, "y": 1})[0], 404)
        self.assertEqual(self.req("GET", "/api/missions/../../etc")[0], 404)

    def test_approbation_depuis_le_studio(self):
        self.connecter()
        m = mi.creer_mission(self.org, "Envoyer une candidature",
                             [{"niveau": "L3", "capacites": ["analyse"], "travail": {"action": "envoyer"}}],
                             demandeur="chef")
        ap = self.req("GET", "/api/approbations")[1]["approbations"][0]
        self.assertEqual(ap["tache_id"], m["taches"][0])
        self.assertEqual(self.req("POST", f"/api/approbations/{ap['id']}", {"accord": "oui"})[0], 400)
        code, data, _ = self.req("POST", f"/api/approbations/{ap['id']}", {"accord": True})
        self.assertEqual((code, data["statut"]), (200, "accordee"))
        self.assertEqual(self.req("POST", f"/api/approbations/{ap['id']}", {"accord": True})[0], 409)

    def test_flux_sse_reprend_au_dernier_numero(self):
        self.connecter()
        self.mission_factice()
        tous = mi.evenements(self.org)
        self.assertGreater(len(tous), 3)

        def lire(entetes):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            c.request("GET", "/api/flux?apres=0", headers={"Host": f"localhost:{self.port}", "Cookie": self.cookie,
                                                          **entetes})
            r = c.getresponse()
            self.assertEqual(r.getheader("Content-Type").split(";")[0], "text/event-stream")
            ids = []
            while len(ids) < len(tous) and True:
                ligne = r.fp.readline().decode()
                if ligne.startswith("id: "):
                    ids.append(int(ligne[4:]))
                if ids and ids[-1] == tous[-1]["seq"]:
                    break
            c.close()
            return ids

        self.assertEqual(lire({}), [e["seq"] for e in tous])
        milieu = tous[2]["seq"]
        self.assertEqual(lire({"Last-Event-ID": str(milieu)}), [e["seq"] for e in tous if e["seq"] > milieu])

    def test_cli_studio_reserve_au_terminal_humain(self):
        from jarvis import cli
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["mission", "studio"]), 4)


if __name__ == "__main__":
    unittest.main()
