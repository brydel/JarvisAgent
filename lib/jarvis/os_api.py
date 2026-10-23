"""Routes du réseau interne et de la passerelle, derrière la session du Studio."""
from __future__ import annotations

import re


def _champs(corps: dict, permis: set[str]) -> None:
    if set(corps) - permis:
        raise ValueError("Champs inconnus dans la demande.")


def lire(route: str, query: dict, tenant: str):
    """Retourne (code HTTP, JSON), ou None si la route appartient à un autre module."""
    if route == "/api/v2/runtime":
        from . import agent_runtime
        return 200, {"runs": agent_runtime.lister(project=(query.get("projet") or [None])[0])}
    if m := re.fullmatch(r"/api/v2/runtime/(AR-[0-9a-f]{24})", route):
        from . import agent_runtime
        return 200, agent_runtime.voir(m.group(1))
    if route == "/api/v2/modeles-runtime":
        from . import pilotage
        return 200, pilotage.modele()
    if route == "/api/v2/oauth":
        from . import oauth
        return 200, {"connexions": oauth.lister()}
    if route.startswith("/api/v2/communaute"):
        from . import communaute
        projet = (query.get("projet") or [""])[0]
        limite = int((query.get("limite") or ["50"])[0])
        if route == "/api/v2/communaute/vie":
            from . import vie_sociale
            return 200, {"mode": vie_sociale._mode_effectif(), "modes": list(vie_sociale.MODES),
                         "personnages": [{k: p[k] for k in ("nom", "titre", "equipe", "fournisseur")} for p in vie_sociale.personnages()]}
        if route == "/api/v2/communaute":
            return 200, communaute.fils(projet, salon=(query.get("salon") or [None])[0],
                                        limite=limite, avant=(query.get("avant") or [None])[0], tenant_id=tenant)
        if m := re.fullmatch(r"/api/v2/communaute/fils/(CM-[0-9a-f]{24})", route):
            return 200, communaute.fil(projet, m.group(1), limite=limite,
                                      apres=(query.get("apres") or [None])[0], tenant_id=tenant)
    elif route == "/api/v2/connexions":
        from . import connexions
        return 200, {"connexions": connexions.lister()}
    elif route == "/api/v2/outils":
        from . import outils
        return 200, outils.catalogue()
    elif route == "/api/v2/outils/operations":
        from . import outils
        return 200, {"operations": outils.operations(project=(query.get("projet") or [None])[0],
                                                      limite=int((query.get("limite") or ["100"])[0]))}
    elif m := re.fullmatch(r"/api/v2/outils/operations/([A-Za-z0-9_.:-]{1,200})", route):
        from . import outils
        valeur = outils.operation(m.group(1))
        return (200, valeur) if valeur is not None else (404, {"erreur": "Opération inconnue."})
    elif route == "/api/v2/os/outbox":
        from . import missions
        return 200, missions.etat_outbox(tenant)
    return None


def ecrire(route: str, corps: dict, tenant: str, *, stop=None):
    """L'auteur provient de la session propriétaire, jamais du contenu publié."""
    from .annulation import ControleExecution
    controle = ControleExecution(interruption=lambda: "arrêt du Studio" if stop.is_set() else "") if stop is not None else None
    if controle is not None:
        controle.verifier()
    if route == "/api/v2/modeles-runtime":
        from . import pilotage
        return 200, pilotage.configurer_modele(corps, par="proprietaire")
    if route == "/api/v2/modeles-runtime/verifier":
        from . import pilotage
        _champs(corps, set())
        return 200, pilotage.verifier_modele(annulation=controle)
    if route == "/api/v2/runtime":
        from . import pilotage
        return 201, pilotage.creer_run(corps, par="proprietaire", source="board")
    if m := re.fullmatch(r"/api/v2/runtime/(AR-[0-9a-f]{24})/(executer|pause|reprendre|annuler)", route):
        from . import pilotage
        _champs(corps, set())
        return (202 if m.group(2) in ("executer", "reprendre") else 200), pilotage.commander(
            m.group(1), m.group(2), par="proprietaire", stop=stop)
    if m := re.fullmatch(r"/api/v2/runtime/(AR-[0-9a-f]{24})/evaluer", route):
        from . import agent_runtime
        _champs(corps, {"accepte", "preuves", "commentaire"})
        return 200, agent_runtime.evaluer(m.group(1), par="proprietaire", accepte=corps.get("accepte"),
            preuves=corps.get("preuves"), commentaire=corps.get("commentaire", ""))
    if route == "/api/v2/os/mandats":
        from . import mandats
        return 201, mandats.creer(corps, par="proprietaire")
    if m := re.fullmatch(r"/api/v2/os/mandats/([A-Za-z0-9_-]{1,128})/revoquer", route):
        from . import mandats
        _champs(corps, set())
        return 200, mandats.revoquer(m.group(1), par="proprietaire")
    if route == "/api/v2/oauth":
        from . import oauth
        return 201, oauth.configurer(corps, par="proprietaire")
    if m := re.fullmatch(r"/api/v2/oauth/([a-z][a-z0-9_-]{0,39})/(commencer|revoquer)", route):
        from . import oauth
        _champs(corps, set())
        if m.group(2) == "commencer":
            return 200, oauth.commencer(m.group(1), par="proprietaire")
        return 200, oauth.revoquer(m.group(1), par="proprietaire", annulation=controle)
    if route == "/api/v2/communaute/fils" or re.fullmatch(r"/api/v2/communaute/fils/CM-[0-9a-f]{24}/messages", route):
        from . import communaute
        _champs(corps, {"projet", "contenu", "type", "titre", "salon", "tache_id", "preuves", "operation_id"})
        parent = route.split("/")[5] if route.endswith("/messages") else None
        message = communaute.publier(
            corps.get("projet", ""), corps.get("contenu", ""), auteur="proprietaire",
            type=corps.get("type", "discussion"), titre=corps.get("titre", ""),
            salon=corps.get("salon", "general"), tache_id=corps.get("tache_id", ""),
            parent_id=parent, preuves=corps.get("preuves"), operation_id=corps.get("operation_id"), tenant_id=tenant)
        return 201, message
    if route == "/api/v2/communaute/vie":
        from . import vie_sociale
        _champs(corps, {"mode"})
        return 200, {"mode": vie_sociale.regler(str(corps.get("mode", "")))}
    if route == "/api/v2/communaute/debat":
        from . import vie_sociale
        _champs(corps, {"sujet", "projet", "salon"})
        try:
            return 201, vie_sociale.lancer_debat(str(corps.get("sujet", "")), projet=str(corps.get("projet", ""))[:80],
                                                 salon=str(corps.get("salon", "general"))[:80])
        except ValueError as exc:  # la raison (coupée, en pause, plafond du jour) est montrée telle quelle
            return 409, {"erreur": str(exc)}
    if m := re.fullmatch(r"/api/v2/communaute/messages/(CM-[0-9a-f]{24})/evaluation", route):
        from . import communaute
        _champs(corps, {"projet", "decision", "contenu", "preuves", "operation_id"})
        return 200, communaute.evaluer(
            corps.get("projet", ""), m.group(1), auteur="proprietaire", decision=corps.get("decision", ""),
            contenu=corps.get("contenu", ""), preuves=corps.get("preuves"),
            operation_id=corps.get("operation_id"), tenant_id=tenant)
    if route == "/api/v2/connexions":
        from . import connexions
        return 201, connexions.enregistrer(corps, par="studio:humain")
    if m := re.fullmatch(r"/api/v2/connexions/([A-Za-z0-9_-]{1,64})/outils", route):
        from . import connexions
        _champs(corps, {"outils_autorises"})
        return 200, connexions.configurer_outils(m.group(1), corps.get("outils_autorises"), par="studio:humain")
    if m := re.fullmatch(r"/api/v2/connexions/([A-Za-z0-9_-]{1,64})/(decouvrir|revoquer)", route):
        from . import connexions
        _champs(corps, set())
        if m.group(2) == "decouvrir":
            return 200, connexions.decouvrir(m.group(1), annulation=controle)
        return 200, connexions.revoquer(m.group(1), par="studio:humain")
    if route == "/api/v2/outils/executer":
        from . import outils
        return 200, outils.executer(corps, par="studio:humain", annulation=controle)
    return None
