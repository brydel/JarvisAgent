"""Mandats personnels : limites réelles, persistance, corruption et réservations concurrentes."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from jarvis import config, mandats, store  # noqa: E402


class CasMandats:
    backend = "json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-mandats-")
        self.addCleanup(self.tmp.cleanup)
        self.chemin = Path(self.tmp.name)
        self.statedir = mock.patch.object(config, "STATE_DIR", self.chemin)
        self.statedir.start()
        self.addCleanup(self.statedir.stop)
        self.env = mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": self.backend})
        self.env.start()
        self.addCleanup(self.env.stop)
        ancien = store._local
        store._local = threading.local()

        def fermer():
            c = getattr(store._local, "conn", None)
            if c is not None:
                c.close()
            store._local = ancien

        self.addCleanup(fermer)

    def spec(self, **champs):
        return {"version": 1, "owner": "proprietaire", "project": "projet-test", "tools": ["email.send"],
                "destinations": ["essai@example.invalid"], "expires_at": 2000,
                "max_cost_cents": 10, "max_actions": 2, **champs}

    def demande(self, **champs):
        return {"project": "projet-test", "tool": "email.send", "destination": "essai@example.invalid",
                "cost_cents": 3, **champs}

    def creer(self, **champs):
        return mandats.creer(self.spec(**champs), par="humain", now=1000)

    def test_lecture_absente_ne_cree_pas_de_mandat(self):
        self.assertEqual(mandats.lister(), [])
        self.assertIsNone(mandats.get("MA-inconnu"))
        self.assertFalse(mandats.autoriser("MA-inconnu", self.demande(), now=1000)["admis"])
        self.assertFalse(store.existe(mandats.FICHIER))

    def test_creation_persiste_et_ne_mute_pas_entrees_ni_sorties(self):
        spec = self.spec(tools=["web.search", "email.send"])
        avant = copy.deepcopy(spec)
        m = mandats.creer(spec, par="humain", now=1000)
        self.assertEqual(spec, avant)
        self.assertEqual(mandats.get(m["id"])["tools"], ["email.send", "web.search"])
        m["tools"].append("admin.all")
        self.assertNotIn("admin.all", mandats.get(m["id"])["tools"])
        self.assertEqual(mandats.lister()[0]["created_by"], "humain")

    def test_preflight_ne_consomme_aucun_quota(self):
        m = self.creer()
        for _ in range(5):
            decision = mandats.autoriser(m["id"], self.demande(), now=1500)
            self.assertTrue(decision["admis"])
            self.assertFalse(decision["reservee"])
        self.assertEqual(mandats.get(m["id"])["used_actions"], 0)
        self.assertEqual(mandats.get(m["id"])["used_cost_cents"], 0)

    def test_projet_outil_et_destination_exacts(self):
        m = self.creer()
        for champs in ({"project": "autre"}, {"tool": "email.read"},
                       {"destination": "autre@example.invalid"}, {"destination": "example.invalid"},
                       {"destination": None}):
            with self.subTest(champs=champs):
                self.assertFalse(mandats.autoriser(m["id"], self.demande(**champs), now=1500)["admis"])
        self.assertTrue(mandats.autoriser(m["id"], self.demande(), now=1500)["admis"])

    def test_operation_locale_sans_destination_seulement(self):
        m = self.creer(tools=["repo.test"], destinations=[])
        d = {"project": "projet-test", "tool": "repo.test"}
        self.assertTrue(mandats.autoriser(m["id"], d, now=1500)["admis"])
        d["destination"] = "example.invalid"
        self.assertFalse(mandats.autoriser(m["id"], d, now=1500)["admis"])

    def test_normalise_domaines_sans_confondre_adresses(self):
        m = self.creer(destinations=["essai@EXAMPLE.INVALID", "API.EXAMPLE.INVALID."])
        self.assertTrue(mandats.autoriser(m["id"], self.demande(destination="essai@example.invalid"), now=1500)["admis"])
        self.assertTrue(mandats.autoriser(m["id"], self.demande(destination="api.example.invalid"), now=1500)["admis"])
        self.assertFalse(mandats.autoriser(m["id"], self.demande(destination="sub.api.example.invalid"), now=1500)["admis"])

    def test_revoquer_est_idempotent_et_bloque_la_reservation_suivante(self):
        m = self.creer()
        mandats.reserver(m["id"], "op-1", self.demande(), now=1500)
        r = mandats.revoquer(m["id"], par="humain", now=1600)
        again = mandats.revoquer(m["id"], par="autre-humain", now=1700)
        self.assertEqual(again, r)
        self.assertFalse(mandats.autoriser(m["id"], self.demande(), now=1600)["admis"])
        self.assertFalse(mandats.reserver(m["id"], "op-2", self.demande(), now=1600)["admis"])
        # Un rejeu n'accorde pas le droit de refaire l'effet après révocation.
        self.assertFalse(mandats.reserver(m["id"], "op-1", self.demande(), now=1600)["admis"])
        self.assertEqual(mandats.get(m["id"])["used_actions"], 1)

    def test_expiration_est_fermee_a_la_frontiere(self):
        m = self.creer()
        self.assertTrue(mandats.autoriser(m["id"], self.demande(), now=1999.999)["admis"])
        for now in (2000, 2001):
            self.assertFalse(mandats.autoriser(m["id"], self.demande(), now=now)["admis"])
            self.assertFalse(mandats.reserver(m["id"], "op-1", self.demande(), now=now)["admis"])

    def test_reserver_consomme_exactement_une_fois_meme_au_quota(self):
        m = self.creer(max_actions=1, max_cost_cents=3)
        avant = self.demande()
        r = mandats.reserver(m["id"], "op-1", avant, now=1500)
        self.assertTrue(r["admis"])
        self.assertTrue(r["reservee"])
        self.assertFalse(r["doublon"])
        replay = mandats.reserver(m["id"], "op-1", avant, now=1501)
        self.assertTrue(replay["admis"])
        self.assertTrue(replay["doublon"])
        self.assertFalse(mandats.reserver(m["id"], "op-2", avant, now=1501)["admis"])
        self.assertEqual(mandats.get(m["id"])["used_cost_cents"], 3)
        self.assertEqual(avant, self.demande())

    def test_identifiant_operation_ne_peut_pas_changer_parametres_ni_mandat(self):
        m = self.creer()
        mandats.reserver(m["id"], "op-1", self.demande(), now=1500)
        decision = mandats.reserver(m["id"], "op-1", self.demande(cost_cents=4), now=1500)
        self.assertFalse(decision["admis"])
        autre = self.creer()
        self.assertFalse(mandats.reserver(autre["id"], "op-1", self.demande(), now=1500)["admis"])
        self.assertEqual(mandats.get(m["id"])["used_cost_cents"], 3)
        self.assertEqual(mandats.get(autre["id"])["used_actions"], 0)

    def test_budget_est_reverifie_lors_de_la_reservation(self):
        m = self.creer(max_actions=5, max_cost_cents=5)
        self.assertTrue(mandats.autoriser(m["id"], self.demande(), now=1500)["admis"])
        mandats.reserver(m["id"], "op-1", self.demande(), now=1500)
        d = mandats.reserver(m["id"], "op-2", self.demande(), now=1500)
        self.assertFalse(d["admis"])
        self.assertIn("budget", d["raison"])
        self.assertEqual(mandats.get(m["id"])["used_actions"], 1)

    def test_reservations_concurrentes_respectent_quota_et_idempotence(self):
        m = self.creer(max_actions=4, max_cost_cents=100)

        def reserver(i):
            try:
                return mandats.reserver(m["id"], f"op-{i}", self.demande(), now=1500)
            finally:
                c = getattr(store._local, "conn", None)
                if c is not None:
                    c.close()
                    store._local.conn = None

        with ThreadPoolExecutor(max_workers=8) as pool:
            resultats = list(pool.map(reserver, list(range(10)) * 2))
        self.assertEqual(sum(r["admis"] and not r["doublon"] for r in resultats), 4)
        self.assertEqual(mandats.get(m["id"])["used_actions"], 4)
        self.assertEqual(mandats.get(m["id"])["used_cost_cents"], 12)

    def test_rejette_contrats_et_dates_invalides(self):
        changements = [dict(version=True), dict(version=2), dict(owner=" "), dict(project=""), dict(tools=[]),
                        dict(tools=["email.*"]), dict(tools=["email.send", "email.send"]),
                        dict(destinations=["https://example.invalid"]), dict(destinations=["example.invalid:443"]),
                        dict(destinations=["*.example.invalid"]), dict(destinations=["*@example.invalid"]),
                        dict(destinations=["example.invalid/path"]), dict(expires_at=float("nan")),
                        dict(expires_at=float("inf")), dict(expires_at=1000), dict(max_actions=True),
                        dict(max_actions=0), dict(max_cost_cents=-1), dict(max_cost_cents=0.5),
                        dict(secret="valeur-interdite")]
        for changements_ in changements:
            with self.subTest(changements=changements_), self.assertRaises(mandats.MandatError):
                self.creer(**changements_)
        for now in (float("nan"), float("inf"), True):
            with self.subTest(now=now), self.assertRaises(mandats.MandatError):
                mandats.creer(self.spec(), par="humain", now=now)
        self.assertEqual(mandats.lister(), [])

    def test_rejette_demande_invalide_sans_elargir(self):
        m = self.creer()
        for champs in (dict(cost_cents=True), dict(cost_cents=-1), dict(destination="https://example.invalid"),
                       dict(tool="email.*"), dict(credential="non")):
            with self.subTest(champs=champs), self.assertRaises(mandats.MandatError):
                mandats.autoriser(m["id"], self.demande(**champs), now=1500)
        self.assertEqual(mandats.get(m["id"])["used_actions"], 0)

    def _brut(self, texte):
        if self.backend == "sqlite":
            store.connexion().execute("INSERT OR REPLACE INTO etat (nom,valeur,maj) VALUES (?,?,0)", (mandats.FICHIER, texte))
        else:
            store.state_path(mandats.FICHIER).write_text(texte)

    def _lire_brut(self):
        if self.backend == "sqlite":
            return store.connexion().execute("SELECT valeur FROM etat WHERE nom=?", (mandats.FICHIER,)).fetchone()[0]
        return store.state_path(mandats.FICHIER).read_text()

    def test_json_corrompu_ne_reinitialise_pas_le_registre(self):
        self._brut('{"version":')
        avant = self._lire_brut()
        for f in (mandats.lister, lambda: self.creer(),
                  lambda: mandats.reserver("MA-inconnu", "op-1", self.demande(), now=1500)):
            with self.assertRaises(mandats.MandatError):
                f()
            self.assertEqual(self._lire_brut(), avant)

    def test_compteur_corrompu_refuse_toute_autorisation_sans_ecraser(self):
        m = self.creer()
        data = json.loads(self._lire_brut())
        data["mandats"][m["id"]]["used_actions"] = 0
        data["mandats"][m["id"]]["used_cost_cents"] = 1
        self._brut(json.dumps(data))
        avant = self._lire_brut()
        with self.assertRaises(mandats.MandatError):
            mandats.autoriser(m["id"], self.demande(), now=1500)
        with self.assertRaises(mandats.MandatError):
            self.creer()
        self.assertEqual(self._lire_brut(), avant)


class MandatsJsonTest(CasMandats, unittest.TestCase):
    backend = "json"


class MandatsSqliteTest(CasMandats, unittest.TestCase):
    backend = "sqlite"


if __name__ == "__main__":
    unittest.main()
