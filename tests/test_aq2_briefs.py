"""Briefs de rôle au gabarit commun et évaluation hors ligne : chaque rôle a un cas de référence, et les exigences
sur le compte rendu sont des contrôles exécutés par l'analyseur (comptes_rendus), plus des mots-clés.
Voir docs/autonomy/agents-qualite.md, section « Volet briefs et évaluation »."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_jarvis  # noqa: F401 — environnement isolé
from test_jarvis import ROOT

from jarvis import comptes_rendus as cr, config, evaluation, roles, versions_roles  # noqa: E402

ROLES = ("architecte", "backend", "data", "design", "devops", "frontend", "generaliste", "ia-produit", "marketing",
         "qa", "recherche", "redaction", "revue", "securite", "video")


class GabaritDesBriefsTest(unittest.TestCase):
    def test_les_quinze_briefs_suivent_le_gabarit(self):
        self.assertEqual(sorted(f.stem for f in (ROOT / "roles").glob("*.md")), list(ROLES))
        for nom in ROLES:
            texte = (ROOT / "roles" / f"{nom}.md").read_text(encoding="utf-8")
            self.assertTrue(40 <= len(texte.splitlines()) <= 60, f"{nom} : {len(texte.splitlines())} lignes")
            corps = roles.get(nom)["corps"]
            self.assertEqual(evaluation.structure_brief(corps), [], nom)
            self.assertIn("Objectif :", corps.split("\n\n")[0], f"{nom} : l'objectif est dans le premier paragraphe")
            # L'ordre du gabarit : procédure, interdits, fini, exemple, contre-exemple.
            positions = [corps.index(x) for x in ("**Procédure**", "**À ne pas faire**", "**Fini quand :**",
                                                  "**Exemple de bon compte rendu", "**Contre-exemple")]
            self.assertEqual(positions, sorted(positions), nom)
            self.assertRegex(corps, r"\*\*Contre-exemple \(refusé : [^)]+\)\*\*", f"{nom} : le contre-exemple dit pourquoi il est refusé")

    def test_l_exemple_de_chaque_brief_est_relu_par_l_analyseur(self):
        for nom in ROLES:
            blocs = evaluation.blocs_brief(roles.get(nom)["corps"])
            bon, mauvais = evaluation.analyser_extrait(blocs["exemple"]), evaluation.analyser_extrait(blocs["contre_exemple"])
            self.assertEqual(bon["anomalies"], [], nom)
            self.assertTrue(mauvais["anomalies"], f"{nom} : le contre-exemple doit être refusé")
            if nom == "revue":
                self.assertEqual((bon["type"], bon["analyse"]["verdict"], bon["analyse"]["conforme"]), ("verdict", "corrections", True))
                self.assertTrue(all(c["severite"] and c["fichier"] and c["ligne"] for c in bon["analyse"]["corrections"]))
                self.assertEqual(mauvais["type"], "verdict")
            else:
                self.assertEqual(bon["type"], "termine")
                self.assertGreaterEqual(len(bon["analyse"]["criteres"]), 1, nom)
                self.assertTrue(all(c["preuve"] for c in bon["analyse"]["criteres"]), nom)
                self.assertTrue(all(v["resultat"] for v in bon["analyse"]["verifications"]), nom)
                self.assertTrue(bon["analyse"]["hypotheses"] or bon["analyse"]["risques"],
                                f"{nom} : un bon compte rendu déclare au moins une hypothèse ou un risque")

    def test_architecte_porte_un_gabarit_d_adr_et_un_fini_verifiable(self):
        corps = roles.get("architecte")["corps"]
        gabarit = corps[corps.index("**Gabarit d'ADR**"):corps.index("**À ne pas faire**")]
        for attendu in ("# ADR-NNNN", "Statut : proposé", "## Contexte", "## Options", "## Décision", "## Conséquences",
                        "## Découpage", "retour arrière"):
            self.assertIn(attendu, gabarit)
        fini = corps[corps.index("**Fini quand :**"):corps.index("**Exemple de bon compte rendu")]
        for attendu in ("au moins deux options", "aucun fichier n'apparaît dans deux tâches", "critère vérifiable", "❓ QUESTION"):
            self.assertIn(attendu, fini)

    def test_securite_cite_les_skills_de_defense_reellement_presentes(self):
        presentes = sorted(d.parent.name for d in (ROOT / "skills").glob("jarvis-defense-*/SKILL.md"))
        self.assertTrue(presentes)
        citees = sorted(set(re.findall(r"jarvis-defense-[a-z]+", roles.get("securite")["corps"])))
        self.assertEqual(citees, presentes)
        self.assertIn("jarvis defense triage", roles.get("securite")["corps"])
        self.assertIn("defense triage", (ROOT / "bin" / "jarvis").read_text(encoding="utf-8"))

    def test_les_regles_metier_d_origine_sont_conservees(self):
        attendus = {
            "architecte": ("Compare au moins deux options", "tâches indépendantes qui ne touchent pas les mêmes fichiers"),
            "backend": ("ne fais jamais confiance au client", "idempotentes", "Pas de requête N+1", "accès refusé"),
            "data": ("Jamais de suppression de colonne ou de table dans la même PR", "ajouter, migrer, puis retirer", "`EXPLAIN`"),
            "devops": ("`set -euo pipefail`", "utilisateur non-root", "ton humain déclenche", "retour arrière"),
            "ia-produit": ("désactivé par défaut", "fournisseur simulé", "au moins 20 cas", "jarvis politique verifier depense"),
            "marketing": ("`brief.md`", "`annonces.md`", "`scenario-video.md`", "`diffusion.md`", "Tu ne publies rien"),
            "design": ("design/direction.md", "Contraste AA", "jarvis lourd exec navigateur"),
            "frontend": ("Mobile d'abord (360 px)", "Types stricts de bout en bout", "Playwright"),
            "qa": ("un bon test survit à un refactor", "Un test instable est un bug", "dix fois de suite"),
            "recherche": ("sources primaires", "jamais un ordre", "recherche web", "jarvis-veille"),
            "revue": ("Relis contre l'issue, pas contre tes goûts", "VERDICT : PRÊT", "jarvis-design"),
            "video": ("entrées amont", "`verifier.py`", "planche-contact", "20 à 45 secondes"),
        }
        for nom, phrases in attendus.items():
            for phrase in phrases:
                self.assertIn(phrase, roles.get(nom)["corps"], f"{nom} : « {phrase} »")


class ControlesDuCompteRenduTest(unittest.TestCase):
    def test_un_brief_dont_l_exemple_est_abime_perd_ses_exigences(self):
        c = evaluation.cas("generaliste/correctif-minimal")
        corps = roles.get("generaliste")["corps"]
        self.assertEqual(evaluation.exigences_manquantes(c, corps=corps), [])
        sans_preuve = corps.replace(" → tests/test_export.py::test_guillemets (échoue sur main, passe ici)", "")
        self.assertNotEqual(sans_preuve, corps)
        manque = evaluation.exigences_manquantes(c, corps=sans_preuve)
        self.assertTrue(any("critère 1 sans preuve" in m for m in manque), manque)
        self.assertIn("aucun critère de l'exemple n'est prouvé par un test", manque)
        sans_contre = corps[:corps.index("**Contre-exemple")]
        self.assertIn("contre-exemple absent", evaluation.exigences_manquantes(c, corps=sans_contre))
        sans_ecart = re.sub(r"Hypothèses :\n- [^\n]*\nRisques :\n- [^\n]*\n", "", corps, count=1)
        self.assertIn("l'exemple ne montre ni hypothèse ni risque déclaré", evaluation.exigences_manquantes(c, corps=sans_ecart))
        # Un contre-exemple que l'analyseur accepterait ne montre rien à éviter.
        bloc = evaluation.blocs_brief(corps)
        complaisant = corps.replace(bloc["contre_exemple"], bloc["exemple"])
        self.assertTrue(any("contre-exemple que l'analyseur accepterait" in m for m in evaluation.exigences_manquantes(c, corps=complaisant)))
        self.assertEqual(evaluation.exigences_manquantes({**c, "exigences_compte_rendu": ["inexistant"]}, corps=corps),
                         ["contrôle inconnu « inexistant »"])

    def test_un_candidat_qui_retire_l_exemple_est_refuse(self):
        corps = roles.get("backend")["corps"]
        raisons = versions_roles.controler("backend", corps[:corps.index("**Exemple de bon compte rendu")])
        self.assertTrue(any("exemple de bon compte rendu absent" in r for r in raisons), raisons)
        self.assertEqual(versions_roles.controler("backend", corps + "\n\n## Rigueur\nRelis ton diff avant de livrer."), [])

    def test_structure_d_un_brief_incomplet(self):
        ecarts = evaluation.structure_brief("Tu es **testeur**.\n\n- fais de ton mieux\n\n**Fini quand :** c'est fini.")
        self.assertEqual(ecarts, ["« **Procédure** » absente", "« **À ne pas faire** » absent",
                                  "exemple de bon compte rendu absent", "contre-exemple absent"])
        corps = roles.get("qa")["corps"]
        trop = corps.replace("**À ne pas faire**\n", "**À ne pas faire**\n- un\n- deux\n")
        self.assertIn("7 interdit(s) : 3 à 5 attendus", evaluation.structure_brief(trop))

    def test_chaque_cas_declare_des_controles_connus_et_les_mots_cles_generiques_ont_disparu(self):
        tous = evaluation.cas_tous()
        self.assertEqual(sorted({c["role"] for c in tous}), list(ROLES), "chaque rôle a au moins un cas de référence")
        for c in tous:
            controles = c.get("exigences_compte_rendu", [])
            self.assertTrue(controles, f"{c['nom']} : aucun contrôle sur le compte rendu")
            self.assertLessEqual(set(controles), set(evaluation.CONTROLES_COMPTE_RENDU), c["nom"])
            self.assertNotIn("tests?", c.get("exigences_brief", []), f"{c['nom']} : mot-clé remplacé par « preuve_par_test »")
            self.assertEqual(evaluation.exigences_manquantes(c), [], c["nom"])
            self.assertTrue((c["dossier"] / "verifier.py").is_file() and (c["dossier"] / "depart").is_dir()
                            and (c["dossier"] / "reference").is_dir(), c["nom"])

    def test_compte_rendu_d_un_agent_evalue(self):
        bon = ("✅ TERMINÉ\nRôle : Développeur polyvalent · Tâche : évaluation\nRésumé : tronquer compte le « … ».\n"
               "Critères :\n1. texte coupé à la longueur → tests/test_texte.py::test_coupe (échoue avant)\n"
               "Vérifications :\n- `python3 -m unittest` → OK, 4 tests\nHypothèses :\n- aucune\nRisques :\n- aucun\n"
               "Fichiers :\n- texte.py\nBranche : aucune · PR : aucune\n")
        prompt = "## Fini et compte rendu\n\n```\n" + cr.GABARIT_TERMINE + "\n```\n"
        self.assertEqual(evaluation.analyser_sortie(prompt + "journal du CLI…\n" + bon),
                         {"type": "termine", "conforme": True, "anomalies": []},
                         "le prompt recopié par le CLI ne masque pas le compte rendu : le dernier bloc est relu")
        gabarit_seul = evaluation.analyser_sortie(prompt)
        self.assertEqual((gabarit_seul["type"], gabarit_seul["conforme"]), ("inconnu", False))
        self.assertEqual(evaluation.analyser_sortie("C'est fait.")["type"], "inconnu")
        incomplet = evaluation.analyser_sortie("✅ TERMINÉ\nRésumé : fait.\nCritères :\n1. ça marche\n")
        self.assertFalse(incomplet["conforme"])
        self.assertIn("critère 1 sans preuve", incomplet["anomalies"])
        self.assertEqual(evaluation.analyser_sortie("VERDICT : PRÊT\nCorrections exigées : aucune\n")["type"], "verdict")


class CasDeReferenceTest(unittest.TestCase):
    """Chaque nouvelle vérification refuse aussi une solution presque bonne : la faute que le rôle doit éviter."""

    def juger(self, nom: str, modifier) -> tuple[bool, str]:
        c = evaluation.cas(nom)
        with tempfile.TemporaryDirectory(prefix="jarvis-aq2-") as d:
            projet = evaluation.preparer(c, Path(d) / "projet", avec_reference=True)
            self.assertTrue(evaluation.verifier(c, projet)[0], f"{nom} : la référence doit passer avant la modification")
            modifier(projet)
            return evaluation.verifier(c, projet)

    def refuse(self, nom: str, modifier, motif: str):
        ok, sortie = self.juger(nom, modifier)
        self.assertFalse(ok, f"{nom} : la solution fautive est acceptée")
        self.assertIn(motif, sortie, nom)

    @staticmethod
    def remplacer(chemin: str, ancien: str, nouveau: str):
        def faire(projet: Path):
            f = projet / chemin
            texte = f.read_text(encoding="utf-8")
            assert ancien in texte, (chemin, ancien)
            f.write_text(texte.replace(ancien, nouveau), encoding="utf-8")
        return faire

    def test_architecte(self):
        adr = "docs/adr/0002-file-de-courriels-en-base.md"
        self.refuse("architecte/adr-file-de-courriels", self.remplacer(adr, "| app/envoi.py, tests/test_envoi.py |", "| app/commandes.py |"),
                    "apparaît dans deux tâches")
        self.refuse("architecte/adr-file-de-courriels", self.remplacer(adr, "Retour arrière : retirer le service et la dépendance.\n", ""),
                    "sans ligne « Retour arrière : »")
        self.refuse("architecte/adr-file-de-courriels", self.remplacer(adr, "app/commandes.py:8", "app/commandes.py:80"), "inexistant")
        self.refuse("architecte/adr-file-de-courriels", self.remplacer("app/commandes.py", "return numero", "return numero  # file"),
                    "app/commandes.py a été modifié")

    def test_data(self):
        m = "migrations/m002_email_normalise.py"
        self.refuse("data/migration-reversible", self.remplacer(m, 'if "email_normalise" in _colonnes(conn):', "if False:"),
                    "le schéma après la descente n'est pas celui d'avant")
        self.refuse("data/migration-reversible", self.remplacer(m, 'if "email_normalise" not in _colonnes(conn):', "if True:"),
                    "erreur pendant monter/descendre")
        self.refuse("data/migration-reversible", self.remplacer(m, "lower(trim(email))", "email"), "email_normalise mal rempli")

    def test_devops(self):
        s = "scripts/preparer.sh"
        self.refuse("devops/script-idempotent", self.remplacer(s, 'grep -qxF -- "$1" "$config" || ', ""), "l'état change")
        self.refuse("devops/script-idempotent", self.remplacer(s, "set -euo pipefail\n", ""), "« set -euo pipefail » absent")
        self.refuse("devops/script-idempotent", self.remplacer(s, "exit 2", "exit 0"), "sans argument")

    def test_generaliste(self):
        self.refuse("generaliste/correctif-minimal", self.remplacer("texte.py", 'r = ""', "r = ''"), "slug a été modifiée")
        depart = (evaluation.cas("generaliste/correctif-minimal")["dossier"] / "depart" / "tests" / "test_texte.py").read_text(encoding="utf-8")
        self.refuse("generaliste/correctif-minimal", lambda p: (p / "tests" / "test_texte.py").write_text(depart, encoding="utf-8"),
                    "aucun test ne reproduit le bug")
        self.refuse("generaliste/correctif-minimal", self.remplacer("texte.py", "texte[:longueur - 1]", "texte[:longueur]"), "abcd…")

    def test_ia_produit(self):
        self.refuse("ia-produit/drapeau-et-repli", self.remplacer("resume.py", 'os.environ.get("RESUME_IA") == "1"', 'os.environ.get("RESUME_IA") != "0"'),
                    "drapeau absent")
        self.refuse("ia-produit/drapeau-et-repli", self.remplacer("resume.py", "for _essai in range(2):", "for _essai in range(5):"),
                    "5 appel(s) au fournisseur, 2 attendu(s)")
        self.refuse("ia-produit/drapeau-et-repli", self.remplacer("resume.py", " or len(resume) > len(texte)", ""), "sortie hors schéma")

    def test_marketing(self):
        self.refuse("marketing/annonces-verifiables", self.remplacer("annonces.md", "Titre : Tes factures en CSV", "Titre : Déjà 10 000 clients"),
                    "le nombre 10 n'est pas dans le README")
        self.refuse("marketing/annonces-verifiables", self.remplacer("annonces.md", "Action : Commencer", "Action : Télécharge l'appli mobile"),
                    "formulation interdite")
        self.refuse("marketing/annonces-verifiables", self.remplacer("annonces.md", "Preuve : README.md:9", "Preuve : README.md:8"),
                    "même ligne du README")

    def test_recherche(self):
        self.refuse("recherche/comparatif-source", self.remplacer("rapport.md", "Outil recommandé : Outil C", "Outil recommandé : Outil B"),
                    "la recommandation doit être l'outil C")
        self.refuse("recherche/comparatif-source", self.remplacer("rapport.md", ", relevé le 2026-10-05)", ")"), "fait sans « (source")
        self.refuse("recherche/comparatif-source", self.remplacer("rapport.md", "## Non vérifié\n- « L'outil C va fermer", "## Non vérifié\n- « L'outil C va changer"),
                    "rumeur de fermeture")

    def test_revue(self):
        self.refuse("revue/verdict-au-format", self.remplacer("verdict.md", "[bloquant] app/remise.py:6 — ", ""), "format du verdict")
        self.refuse("revue/verdict-au-format", lambda p: (p / "verdict.md").write_text("VERDICT : PRÊT\nCorrections exigées : aucune\n", encoding="utf-8"),
                    "« VERDICT : CORRECTIONS » attendu")
        self.refuse("revue/verdict-au-format", self.remplacer("app/remise.py", "if pct < 0:", "if not 0 <= pct <= 100:"),
                    "une relecture ne modifie aucun autre fichier")
        self.refuse("revue/verdict-au-format", lambda p: (p / "verdict.md").write_text(
            "VERDICT : CORRECTIONS\nCorrections exigées :\n1. [bloquant] app/remise.py:6 — le refus au-dessus de 100 manque\n"
            "2. [majeur] tests/test_remise.py:10 — aucun test du refus au-dessus de 100\n", encoding="utf-8"), "aucune vérification lancée")

    def test_video(self):
        self.refuse("video/storyboard-du-scenario", self.remplacer("storyboard.json", '"type": "points", "duree": 6', '"type": "points", "duree": 40'),
                    "20 à 45 attendues")
        self.refuse("video/storyboard-du-scenario", self.remplacer("storyboard.json", "captures/export.png", "captures/absente.png"), "introuvable")
        self.refuse("video/storyboard-du-scenario", self.remplacer("storyboard.json", '"type": "points"', '"type": "chiffre"'), "type de scène refusé")

    def test_design(self):
        css = "styles/jetons.css"
        self.refuse("design/contraste-et-focus", self.remplacer(css, "--couleur-texte-discret: #5f6368", "--couleur-texte-discret: #9aa0a6"), "contraste de")
        self.refuse("design/contraste-et-focus", self.remplacer(css, "color: var(--couleur-sur-marque);", "color: #fff;"), "couleur en dur")
        self.refuse("design/contraste-et-focus", self.remplacer(css, "max-width: 320px;", "min-width: 480px;"), "déborde")
        self.refuse("design/contraste-et-focus", self.remplacer(css, "outline: 3px solid var(--couleur-texte);", "outline: 1px dotted var(--couleur-texte);"),
                    "focus-visible")


class ResultatEnregistreTest(unittest.TestCase):
    def test_l_execution_enregistre_l_analyse_du_compte_rendu_sans_changer_le_verdict(self):
        from jarvis import admission
        c = evaluation.cas("generaliste/correctif-minimal")
        compte_rendu = ("✅ TERMINÉ\nRôle : Développeur polyvalent · Tâche : évaluation\nRésumé : corrigé.\nCritères :\n"
                        "1. longueur respectée → tests/test_texte.py (échoue avant)\nVérifications :\n- `python3 -m unittest` → OK\n"
                        "Hypothèses :\n- aucune\nRisques :\n- aucun\nFichiers :\n- texte.py\nBranche : aucune · PR : aucune\n")
        copie = (f"import shutil; shutil.copytree({str(c['dossier'] / 'reference')!r}, '.', dirs_exist_ok=True); "
                 f"print({compte_rendu!r})")
        with tempfile.TemporaryDirectory(prefix="jarvis-aq2-etat-") as etat, \
                mock.patch.object(config, "STATE_DIR", Path(etat)), mock.patch.dict(os.environ, {"JARVIS_STOCKAGE": "json"}), \
                mock.patch.object(admission, "demander", return_value={"reservation": "R-test"}), \
                mock.patch.object(admission, "prolonger"), mock.patch.object(admission, "liberer"):
            bon = evaluation.lancer(c["nom"], "claude", commande=[sys.executable, "-c", copie])
            muet = evaluation.lancer(c["nom"], "claude", commande=[sys.executable, "-c", copie.split("; print(")[0]])
            enregistres = evaluation.resultats()
        self.assertTrue(bon["ok"], bon["detail"])
        self.assertEqual(bon["compte_rendu"], {"type": "termine", "conforme": True, "anomalies": []})
        self.assertTrue(muet["ok"], "le verdict reste celui de la vérification cachée")
        self.assertEqual((muet["compte_rendu"]["type"], muet["compte_rendu"]["conforme"]), ("inconnu", False))
        self.assertEqual([r["compte_rendu"]["conforme"] for r in enregistres], [True, False])
        json.dumps(enregistres)


if __name__ == "__main__":
    unittest.main()
