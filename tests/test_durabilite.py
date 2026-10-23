"""Transactions et reprises réelles : décisions Board, outbox/inbox et file du chef."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from unittest import mock

import test_missions
from jarvis import agents, config, missions as mi, outbox, store, synchro


class DecisionsAtomiquesTest(test_missions.Base):
    def objet(self):
        return mi.board_ajouter(self.org, "accueil", "note", "Source à traiter", auteur="test", analyser=False,
                               meta={"jarvis_mission": "generation-1", "propositions": [
                                   {"titre": "Produire une analyse", "niveau": "L1", "statut": "proposee"}]})["objet_id"]

    def compte(self, table):
        return test_missions._sql(self.org, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def test_dix_decisions_concurrentes_ne_creent_qu_une_mission_carte_et_relation(self):
        oid = self.objet()
        def lancer(_):
            try:
                return mi.decider_proposition(self.org, oid, 0, "lancer", par="test")
            except mi.MissionError as exc:
                return exc.code
        with mock.patch.object(mi, "_traiter_effets_locaux"), concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            resultats = list(pool.map(lancer, range(10)))
        self.assertEqual(sum(isinstance(r, dict) for r in resultats), 1)
        self.assertEqual(resultats.count("conflit"), 9)
        self.assertEqual((self.compte("missions"), self.compte("board_objets"), self.compte("board_liens")), (1, 2, 1))
        self.assertEqual(self.compte("effets_outbox"), 1)

    def test_crash_a_chaque_frontiere_annule_toute_la_decision(self):
        oid = self.objet()
        original = mi._evenement
        for type_ in ("mission_creee", "tache_creee", "board_objet", "board_lien", "board_proposition"):
            def panne(c, tenant, sorte, **kw):
                original(c, tenant, sorte, **kw)
                if sorte == type_:
                    raise RuntimeError("arrêt avant commit")
            with self.subTest(frontiere=type_), mock.patch.object(mi, "_evenement", side_effect=panne):
                with self.assertRaises(RuntimeError):
                    mi.decider_proposition(self.org, oid, 0, "lancer", par="test")
            self.assertEqual((self.compte("missions"), self.compte("board_objets"), self.compte("board_liens")), (0, 1, 0))
            self.assertEqual(synchro._objet(self.org, oid)["meta"]["propositions"][0]["statut"], "proposee")
        enregistrer = outbox.enregistrer
        def dernier_commit(*args, **kw):
            enregistrer(*args, **kw)
            raise RuntimeError("arrêt après intention, avant commit")
        with mock.patch.object(outbox, "enregistrer", side_effect=dernier_commit):
            with self.assertRaises(RuntimeError):
                mi.decider_proposition(self.org, oid, 0, "lancer", par="test")
        self.assertEqual((self.compte("missions"), self.compte("effets_outbox")), (0, 0))
        with mock.patch.object(mi, "_traiter_effets_locaux"):
            mi.decider_proposition(self.org, oid, 0, "lancer", par="test")
        self.assertEqual((self.compte("missions"), self.compte("board_objets"), self.compte("board_liens")), (1, 2, 1))

    def test_inbox_acquitte_une_reprise_mais_refuse_un_conflit_de_parametres(self):
        oid = self.objet()
        with mock.patch.object(mi, "_traiter_effets_locaux"):
            a = mi.decider_proposition(self.org, oid, 0, "lancer", par="test", operation_id="operation-1")
            b = mi.decider_proposition(self.org, oid, 0, "lancer", par="test", operation_id="operation-1")
            self.assertEqual(a, b)
            with self.assertRaises(mi.MissionError) as ctx:
                mi.decider_proposition(self.org, oid, 0, "ecarter", par="test", operation_id="operation-1")
        self.assertEqual(ctx.exception.code, "idempotence")
        self.assertEqual((self.compte("missions"), self.compte("effets_inbox")), (1, 1))

    def test_generation_perimee_et_index_booleen_refuses(self):
        oid = self.objet()
        with self.assertRaises(mi.MissionError) as ctx:
            mi.decider_proposition(self.org, oid, 0, "lancer", par="test", generation="ancienne-generation")
        self.assertEqual(ctx.exception.code, "obsolete")
        with self.assertRaises(mi.MissionError):
            mi.decider_proposition(self.org, oid, False, "lancer", par="test")
        self.assertEqual(self.compte("missions"), 0)


class OutboxTest(test_missions.Base):
    def ajouter(self, *, cle="effet-1", sorte="feed", now=100):
        return outbox.ajouter(self.org, sorte, {"type": "chef", "texte": "Un fait vérifiable"}, cle=cle, now=now)

    def effet(self, id_):
        return next(e for e in mi.etat_outbox(self.org)["effets"] if e["id"] == id_)

    def test_arret_bloque_le_prochain_effet_et_rend_une_prise_non_expediee(self):
        a = self.ajouter(cle="stop-1")
        self.ajouter(cle="stop-2")
        with mock.patch.object(outbox, "_executer", return_value={}) as executer:
            mi.traiter_outbox(tenant_id=self.org, now=100, interrompu=mock.Mock(side_effect=[False, True]))
        executer.assert_not_called()
        self.assertEqual((self.effet(a)["statut"], self.effet(a)["essais"]), ("en_attente", 0))
        with mock.patch.object(outbox, "_executer", return_value={}) as executer:
            r = mi.traiter_outbox(tenant_id=self.org, now=100,
                                 interrompu=mock.Mock(side_effect=[False, False, True]))
        self.assertEqual((r["traites"], executer.call_count), (1, 1))
        self.assertEqual(mi.etat_outbox(self.org)["comptes"], {"en_attente": 1, "livre": 1})

    def test_intention_annulee_avec_la_transaction_et_meme_cle_meme_charge(self):
        with self.assertRaises(RuntimeError):
            with mi.transaction(self.org) as c:
                outbox.enregistrer(c, self.org, "feed", {"type": "chef", "texte": "intention"}, cle="annulee")
                raise RuntimeError("avant commit")
        self.assertEqual(mi.etat_outbox(self.org)["comptes"], {})
        a, b = self.ajouter(), self.ajouter()
        self.assertEqual(a, b)
        with self.assertRaises(mi.MissionError) as ctx:
            outbox.ajouter(self.org, "feed", {"texte": "autre"}, cle="effet-1")
        self.assertEqual(ctx.exception.code, "idempotence")

    def test_resultat_commit_sans_callback_repris_par_nouveau_passage(self):
        rid, secret = self.executant()
        oid = mi.board_ajouter(self.org, "accueil", "note", "Une idée à préciser", auteur="test", analyser=False,
                               contextualiser=True)["objet_id"]
        with mock.patch.object(mi, "_traiter_effets_locaux"):
            self.assertEqual(self.coureur(rid, secret).tour()["etat"], "fait")
        self.assertEqual(synchro._objet(self.org, oid)["meta"]["propositions"][0]["statut"], "proposee")
        self.assertEqual(mi.etat_outbox(self.org)["comptes"], {"en_attente": 3})
        # Un nouveau répartiteur retrouve les intentions après le commit ; aucun réseau n'est appelé.
        with mock.patch.object(synchro, "_en_fond") as envoyer:
            r = mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)
        self.assertGreaterEqual(r["remis"], 3)
        self.assertEqual(synchro._objet(self.org, oid)["meta"]["propositions"][0]["statut"], "lancee")
        self.assertTrue(envoyer.called)
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)["traites"], 0)
        self.assertEqual(len(mi.missions(self.org)), 2)

    def test_worker_interrompu_garde_intention_jusqu_a_expiration_du_bail(self):
        eid = self.ajouter()
        with mock.patch.object(outbox, "_executer", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                mi.traiter_outbox(tenant_id=self.org, now=100)
        self.assertEqual(self.effet(eid)["statut"], "en_cours")
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=101)["traites"], 0)
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=161)["remis"], 1)
        self.assertEqual(self.effet(eid)["statut"], "livre")

    def test_deux_workers_n_executent_pas_simultanement_la_meme_intention(self):
        for i in range(12):
            self.ajouter(cle=f"effet-{i}")
        appels, verrou = [], threading.Lock()
        def effectuer(e):
            with verrou:
                appels.append(e["id"])
            time.sleep(0.005)
        with mock.patch.object(outbox, "_executer", side_effect=effectuer), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: mi.traiter_outbox(tenant_id=self.org, now=100, limite=20), range(2)))
        self.assertEqual(len(appels), 12)
        self.assertEqual(len(set(appels)), 12)
        self.assertEqual(mi.etat_outbox(self.org)["comptes"], {"livre": 12})

    def test_reprises_bornees_diagnostic_sans_charge_et_relance_explicite(self):
        eid = self.ajouter()
        with mock.patch.object(outbox, "_executer", side_effect=RuntimeError("secret-ne-doit-pas-etre-conserve")):
            for i in range(5):
                mi.traiter_outbox(tenant_id=self.org, now=100 + 400 * i)
        e = self.effet(eid)
        self.assertEqual((e["statut"], e["essais"]), ("echec", 5))
        self.assertNotIn("secret-ne-doit", json.dumps(e))
        self.assertNotIn("donnees", e)
        mi.relancer_effet(self.org, eid, par="proprietaire", now=3000)
        self.assertEqual((self.effet(eid)["statut"], self.effet(eid)["essais"]), ("en_attente", 0))
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=3000)["remis"], 1)

    def test_effet_externe_inconnu_ne_repart_pas_sans_rapprochement(self):
        eid = self.ajouter(sorte="telegram")
        with mock.patch.object(outbox, "_executer", side_effect=outbox.RemiseIncertaine("remise incertaine")):
            mi.traiter_outbox(tenant_id=self.org, now=100)
        self.assertEqual(self.effet(eid)["statut"], "inconnu")
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=1000)["traites"], 0)
        with self.assertRaises(mi.MissionError) as ctx:
            mi.relancer_effet(self.org, eid, par="proprietaire")
        self.assertEqual(ctx.exception.code, "incertain")
        mi.relancer_effet(self.org, eid, par="proprietaire", confirmer_inconnu=True)
        self.assertEqual(self.effet(eid)["statut"], "en_attente")

    def test_bail_telegram_expire_devient_inconnu_et_tenant_isole(self):
        eid = self.ajouter(sorte="telegram")
        with mock.patch.object(outbox, "_executer", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                mi.traiter_outbox(tenant_id=self.org, now=100)
        self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=161)["traites"], 0)
        self.assertEqual(self.effet(eid)["statut"], "inconnu")
        autre = mi.creer_organisation("Autre")
        self.assertEqual(mi.etat_outbox(autre)["effets"], [])
        with self.assertRaises(mi.MissionError):
            mi.relancer_effet(autre, eid, par="autre")

    def test_notification_persistee_et_enfants_dedoublonnes_a_la_reprise(self):
        parent = {"id": "EF-parent", "tenant_id": self.org}
        token = outbox.CONTEXTE.set(parent)
        try:
            synchro._en_fond("chef", lambda _: None, "Message durable")
            synchro._en_fond("chef", lambda _: None, "Message durable")
        finally:
            outbox.CONTEXTE.reset(token)
        self.assertEqual(mi.etat_outbox(self.org)["comptes"], {"en_attente": 1})
        with mock.patch.object(agents, "chef_inject", return_value=False):
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org)["replanifies"], 1)


class FileChefTest(test_missions.Base):
    def setUp(self):
        super().setUp()
        store.supprimer(agents.CHEF_QUEUE)
        self.addCleanup(store.supprimer, agents.CHEF_QUEUE)
        p = mock.patch.object(agents, "chef_running", return_value=True)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(agents, "chef_has_dialog", return_value=False)
        p.start(); self.addCleanup(p.stop)

    def test_arret_pendant_remise_conserve_entree_persistante(self):
        with mock.patch.object(agents, "_type_into_chef", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                agents.chef_inject("Message avant arrêt")
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), ["Message avant arrêt"])
        with mock.patch.object(agents, "_type_into_chef", return_value=True):
            self.assertEqual(agents.chef_flush_queue(), 1)
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), [])

    def test_acquittement_un_par_un_preserve_reste_et_ordre(self):
        store.write_json(agents.CHEF_QUEUE, ["premier", "deuxieme", "troisieme"])
        with mock.patch.object(agents, "_type_into_chef", side_effect=[True, False]):
            self.assertEqual(agents.chef_flush_queue(), 1)
        self.assertEqual(store.read_json(agents.CHEF_QUEUE, []), ["deuxieme", "troisieme"])

    def test_message_identifie_acquitte_n_est_pas_reinjecte(self):
        with mock.patch.object(agents, "_type_into_chef", return_value=True) as taper:
            self.assertTrue(agents.chef_inject("Un seul message", message_id="EF-1"))
            self.assertTrue(agents.chef_inject("Un seul message", message_id="EF-1"))
            self.assertEqual(taper.call_count, 1)
            with self.assertRaises(ValueError):
                agents.chef_inject("Autre message", message_id="EF-1")
        self.assertTrue(store.read_json(agents.CHEF_QUEUE, [])[0]["recu"])

    def test_registre_corrompu_est_conserve(self):
        if store.en_base(agents.CHEF_QUEUE):
            store.connexion().execute("INSERT INTO etat (nom,valeur,maj) VALUES (?, ?, 0)", (agents.CHEF_QUEUE, '{casse'))
        else:
            store.state_path(agents.CHEF_QUEUE).write_text('{casse')
        with self.assertRaises(ValueError):
            agents.chef_inject("Ne pas écraser les messages")
        if not store.en_base(agents.CHEF_QUEUE):
            self.assertEqual(store.state_path(agents.CHEF_QUEUE).read_text(), '{casse')


class FileChefSQLiteTest(FileChefTest):
    def setUp(self):
        p = mock.patch.dict("os.environ", {"JARVIS_STOCKAGE": "sqlite"})
        p.start(); self.addCleanup(p.stop)
        super().setUp()


class ReprisesProjectionsTest(test_missions.Base):
    def test_ancienne_analyse_terminee_apres_nouvelle_ne_recule_pas_board_ni_actions(self):
        rid, secret = self.executant()
        objet = mi.board_ajouter(self.org, "accueil", "note", "Source", auteur="test", analyser=False, contextualiser=True)
        a = mi.reclamer(rid, secret)
        mi.demarrer(rid, secret, a["tache_id"], a["tentative_id"], a["bail_jeton"])
        b_id = mi.lancer_contextualisation(self.org, objet["objet_id"], auteur="test", relance=True)
        b = mi.reclamer(rid, secret)
        mi.demarrer(rid, secret, b["tache_id"], b["tentative_id"], b["bail_jeton"])
        self.assertEqual(b["mission_id"], b_id)
        from jarvis import protocole_executant as proto
        def resultat(env, titre):
            texte = (f"## Résumé\n{titre}.\n## Contexte\nUn contexte précis.\n## Points clés\n- une preuve\n"
                     "## Actions proposées\n- produire\n```json\n" + json.dumps({"actions": [
                         {"titre": titre, "niveau": "L1", "pourquoi": "preuve", "auto": True}]}) + "\n```")
            return proto.resultat(env, "reussi", contenu=texte, factice=True)
        with mock.patch.object(synchro, "_en_fond"):
            mi.rendre_resultat(rid, secret, resultat(b, "Analyse B actuelle"))
            mi.rendre_resultat(rid, secret, resultat(a, "Analyse A ancienne"))
        meta = synchro._objet(self.org, objet["objet_id"])["meta"]
        self.assertEqual(meta["jarvis_mission"], b_id)
        self.assertEqual(meta["propositions"][0]["titre"], "Analyse B actuelle")
        self.assertEqual(meta["propositions"][0]["statut"], "lancee")
        self.assertEqual(len(mi.missions(self.org)), 3)  # A, B et la seule action de B
        self.assertEqual(len(mi.mission(self.org, objet["mission_id"])["artefacts"]), 1)
        self.assertIn("board_projection_perimee", [e["type"] for e in mi.evenements(self.org)])

    def contexte(self):
        rid, secret = self.executant()
        oid = mi.board_ajouter(self.org, "accueil", "note", "Une analyse après reprise", auteur="test", analyser=False,
                               contextualiser=True)["objet_id"]
        with mock.patch.object(mi, "_traiter_effets_locaux"):
            self.coureur(rid, secret).tour()
        return oid

    def test_ancienne_intention_auto_refusee_pendant_nouvelle_analyse(self):
        oid = self.contexte()
        b_id = mi.lancer_contextualisation(self.org, oid, auteur="test", relance=True)
        with mock.patch.object(synchro, "_en_fond"):
            mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)
        objet = synchro._objet(self.org, oid)
        self.assertEqual(objet["mission_id"], b_id)
        self.assertEqual(objet["meta"]["propositions"][0]["statut"], "proposee")
        self.assertEqual(len(mi.missions(self.org)), 2)

    def test_decision_notifiee_sur_instantane_pas_nouvelle_liste_mutable(self):
        oid = mi.board_ajouter(self.org, "accueil", "note", "Une source historique", auteur="test", analyser=False,
                               meta={"propositions": [
                                   {"titre": "Première", "niveau": "L1", "statut": "proposee"},
                                   {"titre": "Ancienne proposition décidée", "niveau": "L1", "statut": "proposee"}]})["objet_id"]
        with mock.patch.object(mi, "_traiter_effets_locaux"):
            mi.decider_proposition(self.org, oid, 1, "ecarter", par="humain")
        test_missions._sql(self.org, "UPDATE board_objets SET meta=? WHERE tenant_id=? AND id=?",
                           (json.dumps({"propositions": [{"titre": "Nouvelle proposition sans rapport"}]}), self.org, oid))
        with mock.patch.object(synchro, "_en_fond") as envoyer, mock.patch.object(synchro, "_noter") as noter:
            r = mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)
        self.assertEqual(r["remis"], 1)
        self.assertIn("Ancienne proposition décidée", noter.call_args.kwargs["titre"])
        self.assertIn("Ancienne proposition décidée", str(envoyer.call_args_list))
        self.assertNotIn("Nouvelle proposition sans rapport", str(envoyer.call_args_list))

    def test_reglage_desactive_apres_commit_bloque_ancienne_intention_auto(self):
        oid = self.contexte()
        mi.regler_board(self.org, actions_auto=False, par="proprietaire")
        with mock.patch.object(synchro, "_en_fond"):
            mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)
        self.assertEqual(synchro._objet(self.org, oid)["meta"]["propositions"][0]["statut"], "proposee")
        self.assertEqual(len(mi.missions(self.org)), 1)

    def test_echec_memoire_est_replanifie_sans_annuler_resultat(self):
        oid = self.contexte()
        with mock.patch.object(synchro, "_noter", side_effect=OSError("disque indisponible")), mock.patch.object(synchro, "_en_fond"):
            r = mi.traiter_outbox(tenant_id=self.org, sortes=outbox.SORTES_LOCALES)
        self.assertEqual(r["replanifies"], 1)
        self.assertEqual(synchro._objet(self.org, oid)["meta"]["propositions"][0]["statut"], "lancee")
        with mock.patch.object(synchro, "_en_fond"):
            mi.traiter_outbox(tenant_id=self.org, now=time.time() + 300, sortes=outbox.SORTES_LOCALES)
        self.assertNotIn("en_attente", mi.etat_outbox(self.org)["comptes"])

    def test_ajout_memoire_deja_commis_ne_se_duplique_pas(self):
        from jarvis import memoire
        token = outbox.CONTEXTE.set({"id": "EF-memoire-reprise", "tenant_id": self.org})
        try:
            avant = len(memoire.toutes())
            synchro._noter(self.org, titre="Leçon avec reçu", etiquettes=["test-reprise"])
            synchro._noter(self.org, titre="Leçon avec reçu", etiquettes=["test-reprise"])
        finally:
            outbox.CONTEXTE.reset(token)
        self.assertEqual(len(memoire.toutes()), avant + 1)


class RemiseTelegramTest(test_missions.Base):
    def test_exception_inattendue_apres_envoi_n_entraine_pas_de_repetition(self):
        outbox.ajouter(self.org, "telegram", {"args": ["Message interne"]}, cle="telegram-incident", now=100)
        bot = mock.Mock()
        bot.send.side_effect = OSError("incident après remise possible")
        with mock.patch("jarvis.notify.bot_and_chat", return_value=(bot, "chat-configure")):
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=100)["inconnus"], 1)
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=10000)["traites"], 0)
        self.assertEqual(bot.send.call_count, 1)

    def test_recu_minimal_persiste_apres_reponse_fournisseur(self):
        eid = outbox.ajouter(self.org, "telegram", {"args": ["Message interne", None]}, cle="telegram-1", now=100)
        bot = mock.Mock()
        bot.send.return_value = {"message_id": 42, "chat": {"information_privee": "ne-pas-recopier"}}
        with mock.patch("jarvis.notify.bot_and_chat", return_value=(bot, "chat-configure")):
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=100)["remis"], 1)
        bot.send.assert_called_once_with("chat-configure", "Message interne", None)
        recu = test_missions._sql(self.org, "SELECT resultat FROM effets_inbox WHERE consommateur='outbox' AND cle=?", (eid,))[0]
        self.assertEqual(json.loads(recu["resultat"]), {"remis": True, "destination": "telegram", "message_id": 42})

    def test_erreur_reseau_ne_fuit_pas_url_authentifiee_et_ne_reessaie_pas(self):
        from jarvis.telegram import TelegramError
        outbox.ajouter(self.org, "telegram", {"args": ["Message interne"]}, cle="telegram-2", now=100)
        bot = mock.Mock()
        bot.send.side_effect = TelegramError("https://service/botSECRET-CONFIGURE/sendMessage")
        with mock.patch("jarvis.notify.bot_and_chat", return_value=(bot, "chat-configure")):
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=100)["inconnus"], 1)
            self.assertEqual(mi.traiter_outbox(tenant_id=self.org, now=10000)["traites"], 0)
        self.assertEqual(bot.send.call_count, 1)
        self.assertNotIn("SECRET-CONFIGURE", json.dumps(mi.etat_outbox(self.org)))
