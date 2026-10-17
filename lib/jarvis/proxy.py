"""Configuration d'un proxy LiteLLM pour les fonctions IA DES PRODUITS (rôle ia-produit), désactivé par défaut.

Pourquoi pas pour les agents : Claude Code et Codex tournent sur tes abonnements. Les faire passer par un proxy
LiteLLM les ferait utiliser des clés d'API payantes à la place, ce qui abandonne l'abonnement. Le routeur des
agents reste `modeles.choisir`. Le proxy sert à une application que l'usine construit et qui appelle un modèle :
elle parle à http://localhost:4000 et LiteLLM gère nouvelles tentatives, replis et délais.

`jarvis proxy config` écrit la configuration (JSON, donc YAML valide) à partir du catalogue : un modèle par entrée
qui a un identifiant d'API (`api_id`), replis tirés de `repli` (Claude) puis du niveau inférieur du même
fournisseur. Les clés ne sont jamais écrites : `os.environ/ANTHROPIC_API_KEY`, `os.environ/OPENAI_API_KEY`.
Activer réellement le proxy (installer LiteLLM, le lancer) est ton choix et une dépense d'API : désactivé tant que
`[proxy] actif = true` n'est pas posé dans ton catalogue personnel et qu'aucun budget « services » n'existe.
"""

from __future__ import annotations

import json
import tomllib

from . import config

PREFIXE = {"claude": ("anthropic/", "os.environ/ANTHROPIC_API_KEY"), "codex": ("openai/", "os.environ/OPENAI_API_KEY")}


def reglages() -> dict:
    """[proxy] du catalogue du dépôt, complété par le catalogue personnel."""
    from . import modeles
    out = {"actif": False, "port": 4000, "nouvelles_tentatives": 2, "delai_s": 120}
    for chemin in (modeles.CATALOGUE_DEFAUT, modeles.CATALOGUE_PERSO):
        try:
            with open(chemin, "rb") as fh:
                out.update(tomllib.load(fh).get("proxy") or {})
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return out


def configuration() -> dict:
    from . import modeles
    r = reglages()
    cat = {n: m for n, m in modeles.catalogue().items() if m.get("api_id") and m["actif"]}
    model_list = []
    for nom, m in sorted(cat.items()):
        prefixe, cle = PREFIXE[m["fournisseur"]]
        model_list.append({"model_name": nom, "litellm_params": {"model": prefixe + m["api_id"], "api_key": cle,
                                                                 "timeout": int(r["delai_s"])}})
    replis = []
    for nom, m in sorted(cat.items()):
        suite = [x for x in m.get("repli", "").split(",") if x in cat]
        if not suite:
            suite = [n for n, x in sorted(cat.items(), key=lambda kv: -kv[1]["niveau"])
                     if x["fournisseur"] == m["fournisseur"] and x["niveau"] < m["niveau"]][:1]
        if suite:
            replis.append({nom: suite})
    return {
        "model_list": model_list,
        "router_settings": {"num_retries": int(r["nouvelles_tentatives"]), "timeout": int(r["delai_s"]), "fallbacks": replis},
        "litellm_settings": {"drop_params": True},
        "general_settings": {"port": int(r["port"])},
    }


def ecrire() -> str:
    chemin = config.CONFIG_DIR / "litellm.yaml"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(configuration(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(chemin)
