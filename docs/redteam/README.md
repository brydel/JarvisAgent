# Jarvis RedTeam Node — premier incrément

Base demandée : `feat/board-dessin`, commit `5fd52b8`. Ce changement ajoute un moteur SAST et son intégration
CLI/MCP ; il ne remplace ni le chef, ni l'audio Jetson, ni le Board. Bibliothèque standard dans `lib/jarvis`.

## Fonctionnement vérifié

`jarvis redteam local` → collecte Python bornée → Semgrep réel → preuves → rapport → demande de revue dans
la communauté Jarvis. Le chemin passerelle d'outils → mandat → MCP stdio → moteur Docker → rapport → communauté
est également testé localement. Le premier test utilisait un processus local ; le [parcours SSH/MCP réel
sur la Jetson ARM64](VALIDATION_JETSON.md) est désormais validé avec les fixtures synthétiques et un mandat de laboratoire.

Une seule règle est livrée : appels `subprocess` avec `shell=True` (CWE-78, piste OWASP A03). Le résultat est un
**constat d'outil**, pas une injection exploitable confirmée. Les états `lab_reproduced` et `impact_confirmed`
restent faux. La vérification actuelle porte sur la réussite technique de l'outil ; elle ne reproduit pas l'exploitation.
La fixture synthétique et sa variante corrigée ne sont jamais exécutées par le scanner.

## Installation de laboratoire locale

Depuis la racine du dépôt, avec Docker disponible :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f services/noeud_jetson/Dockerfile.redteam \
  -t jarvis-redteam-semgrep:1.141.1 services/noeud_jetson
mkdir -p work/redteam
python3 - <<'PY'
import json, time
from pathlib import Path
Path('work/redteam/demande.json').write_text(json.dumps({
    'mission_id': 'RT-lab-001', 'deadline': time.time() + 600}))
PY
export JARVIS_REDTEAM_ROOT="$PWD/services/noeud_jetson/labs/python-shell"
export JARVIS_REDTEAM_STATE="$PWD/work/redteam/node-state"
export JARVIS_REDTEAM_IMAGE=jarvis-redteam-semgrep:1.141.1
# Un état de labo distinct évite de solliciter les agents d'un poste de travail actif.
export JARVIS_STATE_DIR="$PWD/work/redteam/jarvis-state"
bin/jarvis redteam local work/redteam/demande.json --projet redteam-lab
bin/jarvis redteam liste
```

La réponse contient un fil `review_thread`. Le chef peut lire cette demande via la communauté existante,
répondre avec un verdict et ses références ; `jarvis redteam revue local-redteam:RT-lab-001` relit le fil.
`delivery=published` signifie publication durable ; cela ne prouve pas qu'un agent actif l'a reçue ou traitée.
Les notifications existantes de la communauté restent responsables de réveiller le chef sur un vrai poste actif.
Aucune réponse de modèle ni message du réseau ne promeut automatiquement un constat en vulnérabilité confirmée.

Pour un diagnostic SAST en processus hôte, installer `requirements-redteam.txt` dans un venv séparé et configurer
`JARVIS_REDTEAM_SEMGREP` vers son exécutable, sans `JARVIS_REDTEAM_IMAGE`. Le rapport porte alors
`host_process` et `network_isolated=false`. Ce mode n'est pas l'isolation du noeud distant.

## Branchement sur une Jetson existante

La [reprise locale du 23 octobre 2026](VALIDATION_WSL.md) a vérifié les accès SSH et le matériel réel :
Orin Nano 8 Go, JetPack 6.2.1, CUDA 12.6. Le propriétaire a ensuite accordé l'accès Docker : l'image ARM64,
l'extension et le parcours SAST distant sont [validés en laboratoire](VALIDATION_JETSON.md).
Après un premier échec mémoire, une inférence Gemma complète a réussi
avec une sortie bornée à 256 jetons ; cela ne valide pas le scan distant ni le partage de mémoire avec Whisper.

Pour refaire l'inventaire sans modifier le nœud, depuis un **accès administratif configuré** (la clé Jarvis
à commande forcée ne permet pas cette commande) :

```bash
ssh ACCES_ADMINISTRATIF 'python3 -' < services/noeud_jetson/inventaire_redteam.py
```

Le script ne lance ni sudo, ni inférence, ni téléchargement. Il relève matériel, versions, accès Docker,
modèles du catalogue présents, digests et empreinte des licences ; il ne mesure pas la mémoire GPU.
La sortie `aptitude_scan_distant` ne certifie jamais un déploiement opérationnel.

**Préserver le service installé.** Sur la Jetson reconnue, le point d'entrée MCP possède déjà les outils texte/image
d'une version plus récente. L'installateur de cette branche le remplacerait par sa version audio/RedTeam.
Ne pas relancer cet installateur sur ce service : utiliser l'installation ciblée ci-dessous.
Aucun module de `feat/jetson-extension` n'a été importé dans cette branche.

### Extension ciblée d'un service existant

`installer_redteam.py` ajoute les modules et le point d'entrée `jarvis_redteam.py`, qui délègue les commandes
et outils existants au module installé. Il conserve `jarvis_noeud.py`, `service.py` et la configuration audio,
sans pip, sudo ni redémarrage. Sa politique est dans un fichier séparé `~/.config/jarvis-noeud/redteam.env`.

Préparer une copie de ce dossier sur la Jetson ainsi que la **clé publique** dédiée de Jarvis. Le compte doit
déjà avoir accès à Docker et l'image doit avoir été construite localement sur ARM64. Depuis cette copie :

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f Dockerfile.redteam -t jarvis-redteam-semgrep:1.141.1 .
python3 installer_redteam.py \
  --racine "$PWD/labs/python-shell" \
  --etat "$HOME/.local/state/jarvis-redteam" \
  --image jarvis-redteam-semgrep:1.141.1 \
  --cle-jarvis /chemin/vers/jarvis_noeud.pub
```

Sans `--cle-jarvis`, l'installation prépare seulement les fichiers. Avec cette option, elle raccorde l'unique
clé existante dont la commande forcée correspond à `jarvis_noeud.py ssh` ; `restrict`, les autres clés et
les trois commandes acceptées restent conservés. Une configuration SSH personnalisée ou ambiguë est refusée.
Chaque fichier modifié est sauvegardé dans un répertoire voisin `NOM.avant-redteam-*`, privé ; un rejeu identique
ne le réécrit pas. Pour revenir à l'ancien point d'entrée, restaurer la sauvegarde d'`authorized_keys` après
comparaison avec les éventuelles modifications intervenues depuis ; les modules ajoutés peuvent rester inactifs.

Cette voie est activée sur la Jetson : les fichiers d'origine et les six outils sont conservés, la santé
répond et le scan ARM64 passe. Voir les [preuves de déploiement](VALIDATION_JETSON.md).
Le nouveau mandat a été créé par le propriétaire dans un état Jarvis de laboratoire distinct.

### Branchement et mandat

1. Reprendre le branchement SSH à commande forcée décrit dans `services/noeud_jetson/README.md`. Pour une
   installation neuve, l'installateur copie aussi les modules RedTeam. Pour un service existant, comparer
   et sauvegarder ses fichiers avant toute mise à jour ; son mandat audio reste distinct.
2. Construire l'image sur le matériel cible, puis mesurer mémoire et temps. Installer Docker et ses droits
   pour le compte du noeud selon la politique du poste. Ne pas exposer son socket sur le réseau.
3. Sauvegarder le fichier privé `~/.config/jarvis-noeud/env`, puis y ajouter des chemins locaux absolus, par exemple :

   ```text
   JARVIS_REDTEAM_ROOT=/srv/jarvis-labs/python-shell
   JARVIS_REDTEAM_STATE=/srv/jarvis-redteam/state
   JARVIS_REDTEAM_IMAGE=jarvis-redteam-semgrep:1.141.1
   ```

   Avec l'extension ciblée, employer `redteam.env` au lieu d'`env` ; l'installateur ciblé renseigne ces trois valeurs.
   Le compte du noeud doit pouvoir lire la cible et écrire son état. L'état doit rester hors de la cible.
   Sans ces trois réglages, l'outil distant refuse de lancer un audit. Le fichier est relu à chaque session MCP.
4. Sur le poste Jarvis, depuis le terminal du propriétaire :

   ```bash
   jarvis redteam autoriser --connexion jetson --projet mon-labo
   jarvis redteam distant demande.json --projet mon-labo --mandat ID_RENVOYE
   ```

   Utiliser l'identifiant réel de connexion. `autoriser` redécouvre l'outil puis crée un mandat distinct : une
   heure, dix appels, aucun coût API. Une ancienne Jetson non mise à jour refuse cette activation ; son branchement
   audio continue de fonctionner. La commande interactive suit la règle humaine déjà présente dans Jarvis.
   Révoquer avec `jarvis os mandat revoquer ID_RENVOYE` ; le registre de connexions peut aussi être révoqué.

Après un **appel distant réussi**, `jarvis executant liste` contient `redteam-jetson`. C'est une observation
ponctuelle, expirant selon le registre existant, pas un battement permanent ni une mesure GPU.

## Périmètre, preuves et reprise

- Une mission ne contient que `mission_id` et `deadline`. Elle ne peut choisir ni racine, ni commande, ni règle,
  ni modèle, ni réseau. Aucun test de production ou cible HTTP arbitraire n'est implémenté.
- Collecte : au plus 200 fichiers Python, 1 Mo par fichier, 10 Mo au total, 5 000 entrées parcourues, trois secondes.
  Liens symboliques exclus ; ouverture `openat/O_NOFOLLOW` sur les composants. Une erreur de lecture échoue l'audit.
- Docker distant obligatoire : réseau `none`, racine en lecture seule, utilisateur 65534, capacités supprimées,
  pas de nouveaux privilèges, 768 Mo, un CPU, 128 PID, `/tmp` éphémère 64 Mo. Aucun code cible exécuté.
  Le conteneur est supprimé après réussite ou échec ; un nettoyage incertain remonte comme erreur.
- Le tag configuré est résolu en identifiant d'image pour chaque scan, sans téléchargement implicite. L'identifiant
  effectivement utilisé est conservé. Reproduire avec cet identifiant ; les tags et dépendances transitives peuvent changer.
- L'état propriétaire est privé (0700), contient la base SQLite et les sources/règles dans `evidence/<sha256>`.
  Les objets sont synchronisés puis publiés atomiquement ; leur intégrité est vérifiée. Ces sources peuvent contenir
  des données sensibles : archivage/chiffrement et rétention restent à configurer par le propriétaire. Quota de preuves : 200 Mo.
- Les étapes PLAN, EXECUTE, OBSERVE, VERIFY, REFLECT, DELEGATE, REPORT sont enregistrées. Rejouer exactement la même
  demande reprend les étapes manquantes. EXECUTE acquis n'est pas relancé. Un arrêt avant son commit peut refaire
  le scan : garantie au moins une fois à cette frontière, pas exactement une fois.
- Réutiliser un identifiant avec une autre demande/politique est refusé. Pour auditer une modification, créer un
  nouvel identifiant : le rejeu d'un ancien identifiant conserve volontairement son ancien snapshot.
- Aucun agent ne reçoit des droits d'exécution supplémentaires : la demande de revue a outils/réseau vides,
  un seul saut déclaré, et aucun mécanisme de délégation récursive ou de fusion. Son budget de jetons est descriptif,
  tant qu'aucun worker de revue n'est raccordé pour le débiter.

Les limites Semgrep sont quinze secondes et 512 Mo par analyseur ; la collecte et les opérations Docker ajoutent
leur propre délai borné. Aucun daemon de scan permanent, ordonnanceur autonome ou UI supplémentaire n'est livré.

## Modèles et suite

Voir [audit et décisions](ARCHITECTURE.md) pour les modèles, limites matérielles, benchmark et backlog.
L'adaptateur Ollama est séparé du moteur : son texte ne donne aucun droit et ne confirme aucune vulnérabilité.
