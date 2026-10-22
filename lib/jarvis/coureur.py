"""Exécutant de missions (« runner ») : réclame une tâche, l'exécute avec un adaptateur, rend le résultat.

L'exécutant ne décide de rien : il reçoit une enveloppe (une donnée qu'il valide), travaille sous bail, renouvelle
ce bail par battements, et s'arrête si le plan de contrôle dit que la tâche n'est plus la sienne.

Pas de travail terminé dupliqué au redémarrage : le résultat est écrit dans un journal local AVANT d'être envoyé.
Un exécutant qui redémarre renvoie d'abord ses résultats non acquittés ; si son bail est encore valide, le résultat
est accepté sans réexécution ; s'il a expiré, le plan de contrôle l'a déjà replanifiée (essai suivant) et
l'ancien résultat est refusé comme périmé.

Arrêt local : une pause Jarvis active (`jarvis pause poser humain`) ou le fichier `coureur/STOP` empêche toute
nouvelle réclamation. Le transport d'aujourd'hui est local (même processus que la base) ; M3 ajoutera un
transport HTTPS sortant avec la même interface (docs/jarvis-next/RUNNER_PROTOCOL.md).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Callable

from . import adaptateurs as ad, config, missions, pauses, protocole_executant as proto


class TransportLocal:
    """Appels directs au moteur de missions (même machine). Interface du futur transport réseau."""

    def __init__(self, executant_id: str, secret: str):
        self.id, self._secret = executant_id, secret

    def reclamer(self):
        return missions.reclamer(self.id, self._secret)

    def demarrer(self, env):
        missions.demarrer(self.id, self._secret, env["tache_id"], env["tentative_id"], env["bail_jeton"])

    def battement(self, env):
        return missions.battement(self.id, self._secret, env["tache_id"], env["tentative_id"], env["bail_jeton"])

    def rendre(self, resultat):
        return missions.rendre_resultat(self.id, self._secret, resultat)


def _dossier():
    d = config.STATE_DIR / "coureur"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ecrire_atomique(chemin, data) -> None:
    tmp = chemin.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, chemin)


def arret_local() -> str:
    if (_dossier() / "STOP").exists():
        return "fichier coureur/STOP présent"
    if pauses.active():
        return "pause Jarvis active"
    return ""


class Coureur:
    def __init__(self, transport, adaptateurs: dict[str, ad.Adaptateur], *,
                 avant_envoi: Callable[[dict], None] | None = None, intervalle_battement: float | None = None):
        self.transport, self.adaptateurs = transport, adaptateurs
        self.avant_envoi = avant_envoi  # crochet de test : simuler un plantage entre exécution et envoi
        self.intervalle = intervalle_battement or missions.BAIL_S / 3
        self.journal = _dossier() / f"{transport.id}.json"

    # -- journal des résultats non acquittés --
    def _en_attente(self) -> list[dict]:
        try:
            return json.loads(self.journal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _garder(self, resultat: dict) -> None:
        _ecrire_atomique(self.journal, [r for r in self._en_attente()
                                        if r["cle_idempotence"] != resultat["cle_idempotence"]] + [resultat])

    def _oublier(self, cle: str) -> None:
        _ecrire_atomique(self.journal, [r for r in self._en_attente() if r["cle_idempotence"] != cle])

    def vider_en_attente(self) -> list[dict]:
        """Renvoie les résultats déjà calculés mais non acquittés (redémarrage)."""
        sorties = []
        for r in self._en_attente():
            try:
                sorties.append(self.transport.rendre(r))
                self._oublier(r["cle_idempotence"])
            except missions.MissionError as exc:
                if exc.code in ("perime", "inconnue"):
                    self._oublier(r["cle_idempotence"])
                    sorties.append({"acquitte": False, "raison": str(exc)})
                else:
                    raise
        return sorties

    # -- un tour --
    def tour(self) -> dict:
        arret = arret_local()
        if arret:
            return {"etat": "arret", "raison": arret}
        repris = self.vider_en_attente()
        env = self.transport.reclamer()
        if env is None:
            return {"etat": "vide", "repris": repris}
        try:
            env = proto.valider_tache(env)
        except proto.EnveloppeInvalide as exc:
            # rien n'est exécuté ; le bail expirera et le plan de contrôle comptera l'essai
            return {"etat": "invalide", "raison": str(exc)}
        adaptateur = self.adaptateurs.get(env["fournisseur"])
        self.transport.demarrer(env)
        perdu = threading.Event()
        fin = threading.Event()

        def battre():
            while not fin.wait(self.intervalle):
                try:
                    if not self.transport.battement(env).get("continuer"):
                        perdu.set()
                        return
                except missions.MissionError:
                    perdu.set()
                    return

        fil = threading.Thread(target=battre, daemon=True)
        fil.start()
        try:
            if adaptateur is None:
                sortie = {"issue": "fournisseur_indisponible", "contenu": "",
                          "erreur": f"adaptateur « {env['fournisseur']} » absent de cet exécutant", "factice": False}
            else:
                try:
                    sortie = adaptateur.executer(env)
                except ValueError as exc:
                    sortie = {"issue": "echec", "contenu": "", "erreur": str(exc), "factice": False}
        finally:
            fin.set()
            fil.join(timeout=5)
        resultat = proto.resultat(env, sortie["issue"], contenu=sortie.get("contenu", ""),
                                  erreur=sortie.get("erreur", ""), fournisseur=env["fournisseur"],
                                  factice=bool(sortie.get("factice")))
        try:
            proto.valider_resultat(resultat)
        except proto.EnveloppeInvalide as exc:  # réponse vide, trop longue… : un échec, pas un résultat
            resultat.update(issue="echec", contenu="", erreur=str(exc))
        self._garder(resultat)  # écrit AVANT l'envoi : un plantage ici ne perd pas le travail
        if self.avant_envoi:
            self.avant_envoi(resultat)
        try:
            accuse = self.transport.rendre(resultat)
        except missions.MissionError as exc:
            if exc.code in ("perime", "inconnue"):
                self._oublier(resultat["cle_idempotence"])
                return {"etat": "perime", "tache_id": env["tache_id"], "raison": str(exc), "bail_perdu": perdu.is_set()}
            raise
        self._oublier(resultat["cle_idempotence"])
        return {"etat": "fait", "tache_id": env["tache_id"], "accuse": accuse}
