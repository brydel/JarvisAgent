"""Moteur du chef d'orchestre : Claude Code ou Codex, avec relève automatique.

Le chef n'est plus lié à un seul fournisseur. Un ordre de préférence (`general.chef_moteurs`) dit qui
dirige ; quand l'abonnement du moteur en place est épuisé, le démon passe la direction au suivant
(`releve_check`), et un chef qui s'arrête repart sur le premier moteur disponible.

Les garde-fous restent les mêmes quel que soit le moteur :
- Claude Code : règles allow/deny de `.claude/settings.json` (cmd_chef_preparer) ;
- Codex : bac à sable limité au dossier du chef, sans réseau, aucune demande d'approbation ; les seules
  commandes qui en sortent passent par `bin/jarvis-chef`, qui applique LES MÊMES listes (`verifier`)
  et refuse tout appelant qui ne descend pas de la fenêtre du chef (`appelant_est_chef`).
"""

from __future__ import annotations

import os
import re
import shlex
import time

from . import config, store

MOTEURS = ("claude", "codex")
ETAT = "chef_moteur.json"
RELEVES_MAX = 2  # par heure : au-delà, les deux moteurs se renvoient la balle, c'est une panne à montrer

AUTORISE = (
    "Bash(jarvis etat *)", "Bash(jarvis etat)", "Bash(jarvis projet liste)", "Bash(jarvis fil *)",
    "Bash(jarvis plan nouveau *)", "Bash(jarvis plan liste *)", "Bash(jarvis plan liste)",
    "Bash(jarvis plan voir *)", "Bash(jarvis task *)", "Bash(jarvis capacite)",
    "Bash(jarvis chef-moteur)", "Bash(jarvis demander *)", "Bash(jarvis note *)", "Bash(jarvis journal *)", "Bash(jarvis journal)",
    "Bash(jarvis voir *)", "Bash(jarvis jetons)", "Bash(jarvis jetons *)",
    "Bash(jarvis veille)", "Bash(jarvis veille *)",
    "Bash(jarvis fermer *)", "Bash(jarvis sante)", "Bash(jarvis reparer-git *)",
    "Bash(jarvis reprendre --essai)", "Bash(jarvis admission etat)", "Bash(jarvis pause)",
    "Bash(jarvis pause etat)", "Bash(jarvis pause poser incident *)", "Bash(jarvis lourd liste)",
    "Bash(jarvis audit)", "Bash(jarvis audit *)", "Bash(jarvis profil liste)", "Bash(jarvis profil voir *)",
    "Bash(jarvis diagnostic)", "Bash(jarvis diagnostic *)", "Bash(jarvis politique)", "Bash(jarvis politique *)",
    "Bash(jarvis budget)", "Bash(jarvis budget *)", "Bash(jarvis fournisseurs)", "Bash(jarvis fournisseurs *)",
    "Bash(jarvis proposition *)", "Bash(jarvis memoire)", "Bash(jarvis memoire *)",
    # Bibliothèque de références : lecture seule (capturer un site reste soumis à ton accord).
    "Bash(jarvis reference chercher *)", "Bash(jarvis reference liste)", "Bash(jarvis reference liste *)",
    "Bash(jarvis reference voir *)",
    # File des relectures demandées sur le Board : lecture seule (le verdict est rendu par l'humain).
    "Bash(jarvis board relectures)", "Bash(jarvis board relectures *)",
    # Board : lectures seulement (cartes d'un Board, liste des Boards). Les écritures ne sont pas ouvertes ici.
    "Bash(jarvis board voir)", "Bash(jarvis board voir *)", "Bash(jarvis board espaces)",
    # Aide du chef : la table de ses commandes (lecture seule, lib/jarvis/chef_aide.py).
    "Bash(jarvis aide)", "Bash(jarvis aide *)",
    "Bash(jarvis cout)", "Bash(jarvis cout *)", "Bash(jarvis budget-jetons *)",
    "Bash(jarvis secrets verifier *)", "Bash(jarvis rejouer *)", "Bash(jarvis traces)", "Bash(jarvis traces *)",
    "Bash(jarvis rollback proposer *)", "Bash(jarvis rollback demander *)", "Bash(jarvis eval liste*)",
    "Bash(jarvis eval verifier*)", "Bash(jarvis eval resultats*)", "Bash(jarvis proxy)", "Bash(jarvis proxy voir)",
    "Bash(jarvis skill)", "Bash(jarvis skill liste)", "Bash(jarvis skill auditer)", "Bash(jarvis skill installer *)",
    "Bash(jarvis stockage)", "Bash(jarvis stockage etat)", "Bash(jarvis executant)", "Bash(jarvis executant liste)",
    # Usine : rôles, routeur, registre, bilan, studio et livrables.
    "Bash(jarvis role)", "Bash(jarvis role *)", "Bash(jarvis modele)", "Bash(jarvis modele liste)",
    "Bash(jarvis modele choisir *)", "Bash(jarvis modele proposer *)",
    "Bash(jarvis tache)", "Bash(jarvis tache *)", "Bash(jarvis verdict *)",
    "Bash(jarvis bilan)", "Bash(jarvis bilan *)", "Bash(jarvis usine)",
    "Bash(jarvis studio verifier *)", "Bash(jarvis livrer *)",
    "Bash(jarvis livrables)", "Bash(jarvis livrables *)",
    # Veille concurrentielle : recherche web (lecture seule).
    "WebSearch", "WebFetch",
    "Bash(jarvis os diagnostic)", "Bash(jarvis os schemas)", "Bash(jarvis os preflight *)",
    "Bash(jarvis os communaute *)", "Bash(jarvis os outils *)",
    "Bash(jarvis os runtime *)", "Bash(jarvis os modele voir)", "Bash(jarvis os modele verifier)",
    "Bash(jarvis os oauth liste)",
    "Bash(jarvis os connexions liste)", "Bash(jarvis os connexions decouvrir *)",
    "Bash(workmux status)", "Bash(workmux status *)", "Bash(workmux capture *)",
    "Bash(workmux send *)", "Bash(workmux wait *)",
    "Bash(gh pr view *)", "Bash(gh pr diff *)", "Bash(gh pr checks *)", "Bash(gh pr list *)",
    "mcp__linear-server__*",
)

INTERDIT = (
    # Décisions et réglages réservés à l'humain.
    "Bash(jarvis os mandat creer*)", "Bash(jarvis os mandat revoquer*)",
    "Bash(jarvis os connexions creer*)", "Bash(jarvis os connexions revoquer*)",
    "Bash(jarvis os modele configurer*)", "Bash(jarvis os oauth configurer*)",
    "Bash(jarvis os oauth commencer*)", "Bash(jarvis os oauth revoquer*)",
    "Bash(jarvis plan ok *)", "Bash(jarvis plan non *)", "Bash(jarvis plan verifier *)",
    "Bash(jarvis plan relacher *)", "Bash(jarvis regler *)", "Bash(jarvis telegram *)",
    "Bash(jarvis reglage-lire *)", "Bash(jarvis preparer-worktree *)", "Bash(jarvis chef-preparer *)",
    "Bash(jarvis autostart)", "Bash(jarvis autostart *)", "Bash(jarvis reprise-preparer)",
    "Bash(jarvis reprise-preparer *)", "Bash(jarvis reprendre)",
    "Bash(jarvis modele ok *)", "Bash(jarvis modele non *)", "Bash(jarvis modele verifier)",
    "Bash(jarvis modele verifier *)", "Bash(jarvis livrer * --forcer*)", "Bash(jarvis livrer --forcer*)",
    "Bash(jarvis tache-enregistrer *)", "Bash(jarvis tache-annuler *)", "Bash(jarvis lancement-args *)",
    "Bash(jarvis prompt-construire *)", "Bash(jarvis chef-lancer)", "Bash(jarvis chef-lancer *)", "Bash(jarvis chef-etat)",
    "Bash(jarvis web)", "Bash(jarvis web *)", "Bash(jarvis relancer)", "Bash(jarvis relancer *)",
    "Bash(jarvis pause lever *)", "Bash(jarvis pause poser humain*)", "Bash(jarvis pause poser maintenance*)",
    "Bash(jarvis pause poser batterie*)", "Bash(jarvis pause poser quota*)", "Bash(jarvis pause poser ressources*)",
    "Bash(jarvis profil appliquer *)", "Bash(jarvis admission demander *)", "Bash(jarvis admission liberer *)",
    "Bash(jarvis lourd debut *)", "Bash(jarvis lourd exec *)", "Bash(jarvis lourd fin *)",
    "Bash(jarvis politique appliquer *)", "Bash(jarvis politique deleguer *)", "Bash(jarvis budget definir *)",
    "Bash(jarvis tache relancer *)", "Bash(jarvis execution *)", "Bash(jarvis rollback executer *)",
    "Bash(jarvis eval lancer *)", "Bash(jarvis proxy config*)", "Bash(jarvis skill approuver *)",
    "Bash(jarvis skill refuser *)", "Bash(jarvis skill epingler *)",
    "Bash(jarvis role approuver *)", "Bash(jarvis role refuser *)", "Bash(jarvis role promouvoir *)",
    "Bash(jarvis stockage migrer*)", "Bash(jarvis stockage revenir*)", "Bash(jarvis executant declarer *)",
    "Bash(jarvis executant retirer *)",
    "Bash(jarvis board relire *)",  # demander, rendre ou retirer une relecture : l'humain seul
    # Contournements de « jarvis task » et accès directs au noyau.
    "Bash(workmux add *)", "Bash(workmux run *)", "Bash(python *)", "Bash(python3 *)",
    "Bash(env *)", "Bash(script *)",
    # Le chef dirige : il ne fusionne, ne pousse et ne supprime rien.
    "Bash(workmux merge *)", "Bash(workmux remove *)", "Bash(workmux rm *)",
    "Bash(gh pr merge)", "Bash(gh pr merge *)", "Bash(git push)", "Bash(git push *)",
    "Bash(git merge *)", "Bash(git reset *)", "Bash(git -C *)", "Bash(rm *)",
)

# Boîtes de dialogue propres à chaque moteur : tant qu'une d'elles est à l'écran, on n'y tape rien.
DIALOGUES = {
    "claude": ("❯ 1.", "❯ 2.", "❯ 3.", "Do you want to proceed", "don't ask again"),
    "codex": ("› 1.", "› 2.", "› 3.", "Press enter to continue", "Allow command?", "Do you trust"),
}


# --- Choix du moteur ----------------------------------------------------------------

def ordre() -> list[str]:
    """Ordre de préférence des moteurs (réglage general.chef_moteurs), sans doublon ni inconnu."""
    brut = str(config.settings()["general"].get("chef_moteurs", "claude,codex"))
    vus: list[str] = []
    for nom in (x.strip().lower() for x in brut.split(",")):
        if nom in MOTEURS and nom not in vus:
            vus.append(nom)
    return vus or ["claude"]


def installe(moteur: str) -> bool:
    from .adaptateurs import binaire_linux
    return binaire_linux(moteur) is not None


def courant() -> str:
    """Moteur du chef en place d'après le dernier lancement (« claude » par défaut : installations d'avant)."""
    m = store.read_json(ETAT, {}).get("moteur")
    return m if m in MOTEURS else "claude"


def etat() -> dict:
    return store.read_json(ETAT, {})


def choisir(resume: dict | None = None, *, eviter: str | None = None) -> tuple[str | None, str]:
    """(moteur, raison). Premier moteur installé dont l'abonnement n'est pas épuisé, dans l'ordre réglé.

    Si tous sont épuisés, on rend quand même le premier installé : un chef qui attend la remise à zéro vaut
    mieux que pas de chef (il ne peut de toute façon rien lancer, l'admission refuse). `eviter` écarte le
    moteur qu'on vient de quitter tant qu'un autre peut diriger.
    """
    from . import usage
    resume = resume if resume is not None else usage.summary()
    presents = [m for m in ordre() if installe(m)]
    if not presents:
        return None, "aucun moteur installé (Claude Code ou Codex)"
    dispo = [m for m in presents if (resume.get(m) or {}).get("niveau") != "epuise"]
    candidats = [m for m in dispo if m != eviter] or dispo
    if candidats:
        m = candidats[0]
        if m == ordre()[0]:
            return m, "moteur préféré"
        avant = [x for x in ordre()[:ordre().index(m)]]
        pourquoi = ", ".join(f"{x} {'épuisé' if x in presents else 'absent'}" for x in avant) or "relève"
        return m, f"relève ({pourquoi})"
    return presents[0], "tous les abonnements sont épuisés : le chef attend la remise à zéro"


def enregistrer(moteur: str, raison: str, now: float | None = None) -> dict:
    """Note le moteur lancé. Renvoie l'état précédent (pour savoir s'il y a eu changement)."""
    now = now or time.time()
    avant = store.read_json(ETAT, {})
    nouveau = {"moteur": moteur, "raison": raison, "depuis": now, "precedent": avant.get("moteur"),
               "releve_demandee": 0}
    if avant.get("moteur") == moteur:
        nouveau["depuis"] = avant.get("depuis", now)
        nouveau["precedent"] = avant.get("precedent")
    store.write_json(ETAT, nouveau)
    return avant


def note_releve(avant: dict, moteur: str, raison: str) -> str:
    """Phrase ajoutée au message de démarrage quand le chef change de moteur."""
    ancien = avant.get("moteur")
    if not ancien or ancien == moteur:
        return ""
    return (f"RELÈVE : tu prends la direction à la place du chef {ancien.capitalize()} ({raison}). Tu n'as pas sa "
            "conversation : ta seule mémoire est « jarvis journal », « jarvis memoire chercher », « jarvis etat » "
            "et « jarvis plan liste ». Ne relance rien qui tourne déjà, ne repropose pas un plan déjà en attente.")


# --- Garde des commandes (moteur Codex) ---------------------------------------------

def _motif(regle: str) -> str | None:
    return regle[5:-1] if regle.startswith("Bash(") and regle.endswith(")") else None


def _correspond(motif: str, commande: str) -> bool:
    """« * » vaut n'importe quelle suite ; un « " *" » final accepte aussi la commande sans argument."""
    fin = ""
    if motif.endswith(" *"):
        motif, fin = motif[:-2], "( .*)?"
    return re.fullmatch(".*".join(re.escape(x) for x in motif.split("*")) + fin, commande, re.DOTALL) is not None


def verifier(argv: list[str]) -> tuple[bool, str]:
    """La commande est-elle permise au chef ? Mêmes listes que les permissions du chef Claude.

    Interdit d'abord, puis autorisation explicite exigée : rien n'est permis par défaut.
    """
    if not argv:
        return False, "commande vide"
    if os.path.basename(argv[0]) != argv[0]:
        return False, "donne le nom de la commande, pas un chemin"
    if any("\n" in a or "\r" in a for a in argv):
        return False, "saut de ligne dans la commande"
    commande = " ".join(argv)
    for regle in INTERDIT:
        m = _motif(regle)
        if m and _correspond(m, commande):
            return False, f"réservé à ton humain ou interdit au chef ({m})"
    for regle in AUTORISE:
        m = _motif(regle)
        if m and _correspond(m, commande):
            return True, m
    return False, "cette commande ne fait pas partie des outils du chef"


def appelant_est_chef(pid: int | None = None) -> bool:
    """Vrai si le processus descend d'un volet de la fenêtre « chef ».

    C'est ce qui réserve `jarvis-chef` au chef : un agent Codex de l'usine partage les mêmes règles
    d'exécution, mais il ne descend pas de cette fenêtre.
    """
    from . import agents as ag
    volets = set()
    for win in ag._chef_wins():
        try:
            res = ag._run(["tmux", "list-panes", "-t", win, "-F", "#{pane_pid}"], timeout=5)
        except Exception:  # noqa: BLE001 — tmux absent ou muet : on refuse
            continue
        volets |= {int(x) for x in res.stdout.split() if x.isdigit()}
    if not volets:
        return False
    pid = pid or os.getpid()
    for _ in range(64):
        if pid in volets:
            return True
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
                stat = fh.read()
            pid = int(stat[stat.rfind(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            return False
        if pid <= 1:
            return False
    return False


# --- Rôle et lancement (moteur Codex) -----------------------------------------------

PREAMBULE_CODEX = """# Moteur : Codex — à lire avant tout

Tu diriges l'usine avec **Codex**. Le rôle ci-dessous est celui du chef, écrit pour tes outils : ses règles
absolues s'appliquent à toi sans exception.

## Tes commandes passent par `jarvis-chef`

Ton bac à sable ne peut écrire que dans ce dossier et n'a pas de réseau.
Toute commande `jarvis`, `workmux` ou `gh` s'écrit donc **précédée de `jarvis-chef`**, seule, sur sa ligne :

    jarvis-chef jarvis etat
    jarvis-chef workmux status --all
    jarvis-chef gh pr view 12

Pas de `;`, `&&`, `|`, de redirection ni de variable devant : `jarvis-chef` applique tes permissions de chef et
refuse le reste. Un refus est une information, jamais un obstacle à contourner. Les exemples ci-dessous sont déjà
écrits ainsi.

## Ce que tu as, ce que tu n'as pas

- **La table de tes commandes** : `jarvis-chef jarvis aide chef` (ou `jarvis-chef jarvis aide chef board` pour un
  seul sujet). Elle marque « hors porte » les commandes décrites dans ce rôle que `jarvis-chef` te refuse
  aujourd'hui (écrire sur le Board, noeud GPU). Pour celles-là, n'essaie pas autrement : dis à ton humain ce que
  tu voulais faire, dans ton bilan (`jarvis-chef jarvis note "…" --envoyer`).
- **Recherche web** : ton outil natif. **Linear** : ses outils MCP. **Fichiers de ton dossier** (`./boite/`,
  `./consignes/`) : tes outils habituels de lecture et d'écriture.
- **Personne à qui déléguer dans ta conversation.** La contre-expertise d'un plan (étape 3) est une deuxième passe
  que tu mènes toi-même, par écrit, selon la procédure donnée. Ce que tu ne peux pas faire seul devient une tâche
  d'agent dans un plan.
- **Tu ne fermes pas un agent en tapant une commande dans sa fenêtre.** Tu lui demandes de s'arrêter
  (`jarvis-chef workmux send`), puis `jarvis-chef jarvis fermer` quand il est terminé.

---

"""

# Ce que le rôle écrit pour Claude Code ne peut pas demander à Codex : outils nommés autrement, pas de
# délégation dans la conversation, pas de commande à barre oblique à faire taper par un agent. Chaque couple
# (texte du rôle, texte pour Codex) est appliqué par `role_codex` ; `traductions_manquantes` dit lesquels ne
# trouvent plus leur texte source (un test échoue alors : le rôle a été reformulé sans mettre à jour ce tableau).
CONTRE_EXPERTISE_CODEX = """Puis mène toi-même la **contre-expertise en deuxième passe**. Tu n'as personne à qui la confier : c'est une relecture séparée de la pré-mortem, faite par écrit, dans cet ordre.

1. **Écris le plan tel que tu comptes le proposer** dans `./consignes/contre-expertise.md` : titre, éléments (`projet:ISSUE:agent@rôle+taille:desc`), fichiers ou dossiers de chacun, critères d'acceptation de chacun.
2. **Change de rôle.** Relis ce fichier comme s'il venait d'un autre chef, avec ce mandat : « Attaque ce plan. Trouve les dépendances cachées, les conflits de fichiers, les critères d'acceptation invérifiables, ce qui devrait revenir à l'humain, et une meilleure répartition. »
3. **Réponds par écrit, dans le même fichier, aux cinq questions**, élément par élément. « Rien » est une réponse permise, seulement après avoir regardé :
   - *Dépendances cachées* : de quel autre élément, de quelle PR non fusionnée ou de quel agent en cours celui-ci a-t-il besoin pour démarrer ? Vérifie avec `jarvis etat` et `jarvis plan liste`, pas de mémoire.
   - *Conflits de fichiers* : deux éléments (ou un élément et un agent en cours) citent-ils le même fichier ou le même dossier ? Si oui, redécoupe ou mets en séquence.
   - *Critères invérifiables* : pour chaque critère, quelle commande, quel test ou quelle capture le prouve ? Aucun : réécris le critère ou retire-le.
   - *Ce qui revient à l'humain* : issue `human-review-required`, décision de produit, de budget ou de recrutement, action de niveau 2 ou 3 (`jarvis politique verifier`), secret, production.
   - *Meilleure répartition* : rôle, taille et ordre de chaque élément ; un élément trop gros à découper ; une contre-relecture qui manque ; une leçon de `jarvis memoire chercher` que le plan ignore.
4. **Tranche.** Corrige le plan avec ce que tu retiens, et rejette explicitement le reste, une ligne par objection : « retenu : … » ou « rejeté : … parce que … ».
5. **Dis-le dans `--pourquoi`** : une phrase sur ce que la deuxième passe a changé, ou « contre-expertise : rien retenu ». Si elle ne trouve rien sur un plan de trois éléments ou plus, refais-la sur l'élément le plus risqué avant de proposer : une passe qui ne trouve jamais rien n'a pas été faite."""

TRADUCTIONS_CODEX: tuple[tuple[str, str], ...] = (
    ("Puis lance un **sous-agent avocat du diable** (outil Task) avec ce mandat : « Attaque ce plan. Trouve les "
     "dépendances cachées, les conflits de fichiers, les critères d'acceptation invérifiables, ce qui devrait "
     "revenir à l'humain, et une meilleure répartition. » Corrige le plan avec ce que tu retiens, et rejette "
     "explicitement le reste.",
     CONTRE_EXPERTISE_CODEX),
    ("| WebSearch, WebFetch | Recherche web pour la veille concurrentielle |",
     "| Ta recherche web native | Recherche web pour la veille concurrentielle |"),
    ("**Toi aussi, tu consommes des jetons Claude** : sois bref, évite de relire inutilement de gros fichiers, "
     "délègue la lecture lourde à un sous-agent seulement si elle est nécessaire.",
     "**Toi aussi, tu consommes des jetons Codex** : sois bref, évite de relire inutilement de gros fichiers, ne "
     "fais une lecture lourde que si elle est nécessaire, et seulement la partie utile."),
    ("\"Arrête-toi : commente l'état dans Linear puis /exit\"",
     "\"Arrête-toi : commente l'état dans Linear, puis termine ton tour sans rien entreprendre d'autre\""),
    ("La veille est donc une **vraie tâche**, jamais un sous-agent rapide.",
     "La veille est donc une **vraie tâche**, jamais une recherche rapide que tu ferais toi-même."),
    ("Fais-la seulement si la marge Claude est confortable.",
     "Fais-la seulement si la marge de ton moteur (Codex) est confortable."),
    ("Ouvre-le avec l'outil Read.",
     "Ouvre-le avec ton outil de lecture de fichier (ou d'affichage d'image, pour une image)."),
)

# Termes qu'un chef Codex ne peut pas suivre : s'il en reste un dans le rôle généré, c'est un défaut (test).
TERMES_CLAUDE = (r"\bWebSearch\b", r"\bWebFetch\b", r"\bRead\b", r"\bTask\b", r"/exit\b", r"\bsous-agents?\b",
                 r"\bTodoWrite\b", r"\bGrep\b", r"\bGlob\b", r"/clear\b", r"/compact\b")

_OUTILS_CHEF = ("jarvis ", "workmux ", "gh pr ")
_BLOC_BASH = re.compile(r"(?ms)^```(?:bash|sh)\n(.*?)^```")


def prefixer_codex(texte: str) -> str:
    """Écrit les commandes du chef pour la porte : `jarvis …` → `jarvis-chef jarvis …`.

    Deux formes : la commande entre accents graves, et la ligne de commande d'un bloc ```bash.
    """
    for outil in _OUTILS_CHEF:
        texte = texte.replace("`" + outil, "`jarvis-chef " + outil)

    def bloc(m: re.Match) -> str:
        lignes = [("jarvis-chef " + ligne if ligne.startswith(_OUTILS_CHEF) else ligne)
                  for ligne in m.group(1).split("\n")]
        return m.group(0).replace(m.group(1), "\n".join(lignes))
    return _BLOC_BASH.sub(bloc, texte)


def traductions_manquantes(texte: str) -> list[str]:
    """Textes sources de TRADUCTIONS_CODEX absents du rôle : la traduction correspondante ne s'applique plus."""
    return [source for source, _cible in TRADUCTIONS_CODEX if source not in texte]


def termes_claude(texte: str) -> list[str]:
    """Termes propres à Claude Code encore présents dans un rôle destiné à Codex."""
    return sorted({m.group(0) for motif in TERMES_CLAUDE for m in re.finditer(motif, texte)})


def role_codex(texte: str) -> str:
    """Le rôle du chef pour Codex : consignes traduites pour ses outils, commandes écrites pour `jarvis-chef`."""
    for source, cible in TRADUCTIONS_CODEX:
        texte = texte.replace(source, cible)
    return PREAMBULE_CODEX + prefixer_codex(texte)


def commande(moteur: str, message: str) -> str:
    """Ligne de commande tmux qui lance le chef sur `moteur` avec son message de démarrage."""
    s = config.settings()["general"]
    env = f"env JARVIS_ROLE=chef JARVIS_CHEF_MOTEUR={moteur}"
    if moteur == "codex":
        return f"{env} {shlex.quote(str(config.JARVIS_HOME / 'bin' / 'jarvis-chef-codex'))} {shlex.quote(message)}"
    mode = str(s.get("chef_permission_mode", "auto") or "")
    if mode not in ("", "default", "manual", "plan", "auto", "acceptEdits"):
        raise ValueError(f"general.chef_permission_mode « {mode} » refusé : le chef ne peut pas contourner ses permissions.")
    options = (f" --permission-mode {mode}" if mode else "")
    if s.get("chef_remote_control"):
        options += " --remote-control JARVIS-CHEF"
    return f"{env} CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false claude{options} {shlex.quote(message)}"


# --- Relève automatique (appelée par le démon) --------------------------------------

def releve_check(now: float | None = None) -> str | None:
    """Passe la direction à un autre moteur quand celui du chef en place est épuisé.

    Deux temps : (1) le chef en place reçoit l'ordre d'écrire son bilan ; (2) après le délai de grâce
    (`general.chef_releve_grace_s`), sa fenêtre est fermée et le suivant démarre. Un chef épuisé qui ne
    répond plus n'empêche donc pas la relève. Renvoie « demandee », « faite », « echec » ou None.
    """
    import subprocess
    from . import admission, agents as ag, notify, usage
    now = now or time.time()
    s = config.settings()["general"]
    if not s.get("chef_releve_auto", True) or store.paused() or not ag.chef_running():
        return None
    actuel = courant()
    resume = usage.summary(now)
    if (resume.get(actuel) or {}).get("niveau") != "epuise":
        st = store.read_json(ETAT, {})
        if st.get("releve_demandee"):  # rétabli pendant le délai de grâce : on annule
            st["releve_demandee"] = 0
            store.write_json(ETAT, st)
        return None
    suivant, raison = choisir(resume, eviter=actuel)
    if not suivant or suivant == actuel:
        return None  # personne pour prendre la relève : la pause « quota » fait le reste
    st = store.read_json(ETAT, {})
    if not st.get("releve_demandee"):
        if not admission.relance_autorisee("chef-releve", RELEVES_MAX, now)[0]:
            return None
        st.update(moteur=actuel, releve_demandee=now)
        store.write_json(ETAT, st)
        ag.chef_inject(f"[JARVIS relève] Ton abonnement {actuel.capitalize()} est épuisé : un chef "
                       f"{suivant.capitalize()} prend ta place dans quelques minutes. Écris MAINTENANT ton bilan "
                       "(jarvis note) : agents en cours, plans en attente, prochaine action prévue. Ne lance plus rien.")
        store.feed_add("chef", f"relève demandée : {actuel} épuisé, {suivant} va diriger")
        return "demandee"
    if now - float(st["releve_demandee"]) < float(s.get("chef_releve_grace_s", 180)):
        return None
    jarvis = str(config.JARVIS_HOME / "bin" / "jarvis")
    try:
        res = subprocess.run([jarvis, "chef-lancer", "--releve"], capture_output=True, text=True, timeout=180)
        ok = res.returncode == 0 and ag.chef_running()
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    st = store.read_json(ETAT, {})
    st["releve_demandee"] = 0
    store.write_json(ETAT, st)
    if ok:
        notify.alert("systeme", f"Relève du chef : {actuel.capitalize()} est épuisé, {courant().capitalize()} dirige "
                                "l'usine. Les plans approuvés et les agents en cours continuent.",
                     title="JARVIS · chef", windows=False)
        store.feed_add("chef", f"relève faite : {actuel} → {courant()}")
        return "faite"
    notify.alert("erreur", f"Relève du chef impossible ({actuel.capitalize()} épuisé, {suivant.capitalize()} n'a pas "
                           "démarré). Sur ton PC : jarvis chef", title="JARVIS · chef")
    return "echec"


def texte() -> str:
    from . import usage
    resume = usage.summary()
    st = etat()
    lignes = [f"Ordre de préférence : {' → '.join(ordre())}"]
    for m in ordre():
        niveau = (resume.get(m) or {}).get("niveau", "inconnu")
        lignes.append(f"  {m:<7} {'installé' if installe(m) else 'ABSENT':<9} jetons : {niveau}")
    if st.get("moteur"):
        depuis = time.strftime("%d/%m %H:%M", time.localtime(st.get("depuis", 0)))
        lignes.append(f"Dernier chef lancé : {st['moteur']} ({st.get('raison', '?')}, depuis le {depuis})")
    m, raison = choisir(resume)
    lignes.append(f"Prochain lancement : {m or 'aucun'} ({raison})")
    return "\n".join(lignes)
