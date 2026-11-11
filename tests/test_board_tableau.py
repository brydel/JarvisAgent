"""Objets de tableau blanc du Board V2 (adhésif, texte libre, forme, trait, cadre, flèche) : types acceptés,
apparence bornée côté serveur (couleurs = jetons, traits de taille limitée), versions et événements comme les cartes."""

from __future__ import annotations

import unittest

import test_jarvis  # noqa: F401 — environnement isolé
import test_missions
import test_studio

from jarvis import board, board_tableau as bt, missions as mi  # noqa: E402

POINTS = [0, 0, 50, 12, 8, 60, 30, 20, 100]
TRAIT = {"points": POINTS, "boite": [60, 40], "outil": "crayon", "couleur": "indigo", "epaisseur": 6}
FLECHE = {"points": [0, 0, 1, 1], "pointes": "fin"}


class VerifierTest(unittest.TestCase):
    def test_les_autres_types_ne_sont_pas_concernes(self):
        self.assertIsNone(bt.verifier("note", {"couleur": "n'importe quoi", "points": "x"}))
        self.assertIsNone(bt.verifier("mission", None))

    def test_formes(self):
        for f in bt.FORMES:
            self.assertIsNone(bt.verifier("forme", {"forme": f, "fond": "jaune", "trait": "indigo", "epaisseur": 2}))
        self.assertIn("forme inconnue", bt.verifier("forme", {"forme": "etoile"}))
        self.assertIn("forme inconnue", bt.verifier("forme", {}))

    def test_couleurs_seulement_des_jetons(self):
        # jamais une couleur CSS libre : pas d'injection de style, et le thème clair reste lisible
        for mauvaise in ("#ff0000", "red", "url(javascript:alert(1))", "indigo; background:url(x)", 3, None, ["indigo"]):
            self.assertIn("inconnue", bt.verifier("adhesif", {"couleur": mauvaise}), mauvaise)
            self.assertIn("inconnue", bt.verifier("forme", {"forme": "ellipse", "fond": mauvaise}), mauvaise)
        self.assertIsNone(bt.verifier("adhesif", {"couleur": ""}))

    def test_nombres_bornes(self):
        self.assertIn("épaisseur", bt.verifier("forme", {"forme": "rectangle", "epaisseur": 65}))
        self.assertIn("épaisseur", bt.verifier("forme", {"forme": "rectangle", "epaisseur": True}))
        self.assertIn("épaisseur", bt.verifier("forme", {"forme": "rectangle", "epaisseur": "3"}))
        self.assertIn("police", bt.verifier("texte_libre", {"taille_police": 4}))
        self.assertIn("police", bt.verifier("texte_libre", {"taille_police": float("inf")}))
        self.assertIsNone(bt.verifier("texte_libre", {"taille_police": 48, "couleur": "rose"}))
        self.assertIn("libellé", bt.verifier("fleche", {**FLECHE, "libelle": "x" * 201}))

    def test_trait_borne(self):
        self.assertIsNone(bt.verifier("trait", TRAIT))
        self.assertIsNone(bt.verifier("trait", {**TRAIT, "outil": "surligneur"}))
        self.assertIn("points", bt.verifier("trait", {**TRAIT, "points": [1, 2, 3]}))          # un seul point
        self.assertIn("points", bt.verifier("trait", {**TRAIT, "points": [1, 2, 3, 4]}))       # pas des triplets
        self.assertIn("points", bt.verifier("trait", {**TRAIT, "points": "M0 0L10 10"}))       # pas un chemin libre
        self.assertIn("points", bt.verifier("trait", {**TRAIT, "points": [0] * (3 * bt.POINTS_MAX + 3)}))
        self.assertIsNone(bt.verifier("trait", {**TRAIT, "points": [0] * (3 * bt.POINTS_MAX)}))
        self.assertIn("coordonnée", bt.verifier("trait", {**TRAIT, "points": [0, 0, 0, float("nan"), 1, 1]}))
        self.assertIn("coordonnée", bt.verifier("trait", {**TRAIT, "points": [0, 0, 0, 1e9, 1, 1]}))
        self.assertIn("coordonnée", bt.verifier("trait", {**TRAIT, "points": [0, 0, 0, "1", 1, 1]}))
        self.assertIn("outil", bt.verifier("trait", {**TRAIT, "outil": "aerographe"}))
        self.assertIn("boîte", bt.verifier("trait", {**TRAIT, "boite": [0, 10]}))
        self.assertIn("boîte", bt.verifier("trait", {k: v for k, v in TRAIT.items() if k != "boite"}))

    def test_fleche_extremites_et_ancres_normalisees(self):
        self.assertIsNone(bt.verifier("fleche", FLECHE))
        ancre = {"id": "BO-0123456789ab", "nx": 0.5, "ny": 1}
        self.assertIsNone(bt.verifier("fleche", {**FLECHE, "ancres": {"de": ancre, "vers": ancre}, "pointes": "deux"}))
        self.assertIn("extrémités", bt.verifier("fleche", {"points": [0, 0, 2, 1]}))
        self.assertIn("extrémités", bt.verifier("fleche", {"points": [0, 0, 1]}))
        self.assertIn("pointes", bt.verifier("fleche", {**FLECHE, "pointes": "triple"}))
        self.assertIn("ancre", bt.verifier("fleche", {**FLECHE, "ancres": {"de": {**ancre, "nx": 1.5}}}))
        self.assertIn("ancre", bt.verifier("fleche", {**FLECHE, "ancres": {"de": {**ancre, "id": "../etc/passwd"}}}))
        self.assertIn("ancre", bt.verifier("fleche", {**FLECHE, "ancres": {"de": {**ancre, "script": "x"}}}))
        self.assertIn("ancres", bt.verifier("fleche", {**FLECHE, "ancres": {"milieu": ancre}}))


class ObjetsTableauTest(unittest.TestCase):
    def setUp(self):
        test_missions._reinitialiser()
        self.org = mi.tenant_local()

    def ajouter(self, type_, meta=None, contenu="", **k):
        return mi.board_ajouter(self.org, "accueil", type_, contenu, auteur="test", meta=meta, largeur=200, hauteur=120, **k)["objet_id"]

    def test_creation_de_chaque_type_sans_contenu_ni_mission(self):
        metas = {"adhesif": {"couleur": "jaune"}, "texte_libre": {"taille_police": 32}, "forme": {"forme": "losange"},
                 "trait": TRAIT, "cadre": {"titre": "Sprint 1"}, "fleche": FLECHE}
        for t in bt.TYPES:
            oid = self.ajouter(t, metas[t])
            o = next(x for x in board.objets(self.org, "accueil")["objets"] if x["id"] == oid)
            self.assertEqual((o["type"], o["version"], o["mission_id"]), (t, 1, None), t)
            self.assertEqual(o["meta"], metas[t])
        # un objet de tableau blanc n'est jamais envoyé à un modèle : ni analyse, ni contextualisation
        self.assertEqual(mi.missions(self.org), [])
        evts = [e for e in mi.evenements(self.org, limite=100) if e["type"] == "board_objet"]
        self.assertEqual(len(evts), len(bt.TYPES))
        self.assertTrue(all(e["donnees"]["version"] == 1 and e["donnees"]["espace"] == "accueil" for e in evts))

    def test_creation_refusee_hors_bornes(self):
        for type_, meta, attendu in (("forme", {"forme": "etoile"}, "forme inconnue"),
                                     ("trait", {**TRAIT, "points": [0] * (3 * bt.POINTS_MAX + 3)}, "points"),
                                     ("adhesif", {"couleur": "#fff"}, "inconnue"),
                                     ("fleche", {"points": [0, 0, 9, 9]}, "extrémités")):
            with self.assertRaises(mi.MissionError) as x:
                self.ajouter(type_, meta)
            self.assertEqual(x.exception.code, "board")
            self.assertIn(attendu, str(x.exception))
        self.assertEqual(board.objets(self.org, "accueil")["objets"], [])

    def test_modification_validee_versionnee_et_texte_borne(self):
        oid = self.ajouter("forme", {"forme": "rectangle"})
        r = board.mettre_a_jour(self.org, oid, {"meta": {"forme": "ellipse", "fond": "vert", "epaisseur": 4}}, version=1, par="test")
        self.assertEqual(r["version"], 2)
        with self.assertRaises(mi.MissionError) as x:  # version périmée : conflit, comme pour une carte
            board.mettre_a_jour(self.org, oid, {"meta": {"forme": "losange"}}, version=1, par="test")
        self.assertEqual(x.exception.code, "conflit")
        with self.assertRaises(mi.MissionError) as x:  # on ne peut pas sortir des bornes par une modification
            board.mettre_a_jour(self.org, oid, {"meta": {"forme": "ellipse", "fond": "javascript:alert(1)"}}, par="test")
        self.assertEqual(x.exception.code, "board")
        lot = board.mettre_a_jour_lot(self.org, [{"id": oid, "champs": {"meta": {"forme": "x"}}}], par="test")
        self.assertEqual((lot[0]["ok"], lot[0]["code"]), (False, "board"))
        o = board.objets(self.org, "accueil")["objets"][0]
        self.assertEqual((o["meta"]["forme"], o["meta"]["fond"], o["version"]), ("ellipse", "vert", 2))
        note = self.ajouter("adhesif", {"couleur": "jaune"})
        board.mettre_a_jour(self.org, note, {"contenu": "<img src=x onerror=alert(1)> reste du texte"}, par="test")
        with self.assertRaises(mi.MissionError):
            board.mettre_a_jour(self.org, note, {"contenu": "x" * 50_001}, par="test")
        self.assertEqual(mi.missions(self.org), [], "écrire dans un adhésif ne lance rien")

    def test_trait_trop_gros_pour_meta(self):
        # 1 500 points à cinq chiffres dépassent 20 000 caractères : la borne générale de meta s'applique aussi
        with self.assertRaises(mi.MissionError) as x:
            self.ajouter("trait", {**TRAIT, "points": [12345.5] * (3 * bt.POINTS_MAX)})
        self.assertIn("volumineuses", str(x.exception))

    def test_suppression_et_restauration(self):
        oid = self.ajouter("cadre", {"titre": "Idées"})
        board.supprimer(self.org, [oid], par="test")
        self.assertEqual(board.objets(self.org, "accueil")["objets"], [])
        board.supprimer(self.org, [oid], par="test", restaurer=True)
        self.assertEqual(board.objets(self.org, "accueil")["objets"][0]["meta"], {"titre": "Idées"})


class ApiTableauTest(unittest.TestCase):
    setUp = test_studio.StudioTest.setUp
    tearDown = test_studio.StudioTest.tearDown
    req = test_studio.StudioTest.req
    connecter = test_studio.StudioTest.connecter

    def test_api_cree_valide_et_borne(self):
        self.assertEqual(self.req("POST", "/api/v2/objets", {"type": "forme", "meta": {"forme": "ellipse"}}, cookie=False)[0], 401)
        self.connecter()
        code, r, _ = self.req("POST", "/api/v2/objets", {"type": "trait", "x": 10, "y": 20, "largeur": 60, "hauteur": 40, "meta": TRAIT})
        self.assertEqual(code, 201)
        self.assertIsNone(r["mission_id"], "un trait n'est jamais contextualisé")
        code, r2, _ = self.req("POST", "/api/v2/objets", {"type": "trait", "meta": {**TRAIT, "points": [0] * (3 * bt.POINTS_MAX + 3)}})
        self.assertEqual(code, 400)
        self.assertIn("points", r2["erreur"])
        self.assertEqual(self.req("POST", "/api/v2/objets", {"type": "forme", "meta": {"forme": "ellipse", "fond": "red"}})[0], 400)
        lot = self.req("POST", "/api/v2/objets/lot", {"modifications": [
            {"id": r["objet_id"], "version": 1, "champs": {"meta": {**TRAIT, "couleur": "rose"}}}]})[1]["resultats"]
        self.assertEqual((lot[0]["ok"], lot[0]["version"]), (True, 2))
        etat = self.req("GET", "/api/v2/board")[1]
        self.assertEqual([(o["type"], o["meta"]["couleur"]) for o in etat["objets"]], [("trait", "rose")])


if __name__ == "__main__":
    unittest.main()
