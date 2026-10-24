# Audit, décisions et prochaines étapes

Ce document conserve les décisions et limites de la livraison cloud. Les observations de la vraie Jetson,
l'extension préparée et la première inférence Gemma réussie sont dans la [validation WSL](VALIDATION_WSL.md).

## Reconnaissance

Le checkout initial était `work` à `b4cc7f7` (main). Les branches distantes ont été récupérées, notamment
`feat/jarvis-board-v2` (`81a875a`), `feat/jetson-extension` (`ef6afd1`) et la base explicitement demandée
`feat/board-dessin` (`5fd52b8`). Les premiers ajouts isolés ont été reportés sur cette dernière. Aucun code
multimodal de l'autre branche n'a été importé. Aucune modification du rôle `chef/CLAUDE.md`, des assets ou du design.

Inventaire du dépôt, historique, services et tests examinés ; analyse ciblée de l'orchestration `missions`,
`coureur`, `agent_runtime`, des exécutants, contrats, mandats, connexions, passerelle, transport MCP, communauté,
mémoire, stockage et service Jetson. Les assets générés du frontend n'ont pas été relus intégralement.

`executants.py` est un registre avec expiration, pas un ordonnanceur distribué. Le transport distant existant
est `noeud.commande_ssh` : clé dédiée, hôte connu, commande forcée sans shell, MCP sous mandat. Le noeud de cette
branche sert l'audio Whisper ; la version Ollama multimodale appartient à une autre branche. L'absence d'accès SSH
configuré a empêché toute reconnaissance matérielle réelle ; aucune adresse personnelle ou clé n'a été supposée.

## Décisions

1. **Extension du monolithe modulaire** : client dans `lib/jarvis/redteam.py`, moteur autonome installable avec le
   service Jetson. Aucun nouveau plan de contrôle ni dashboard ; CLI et communauté existantes réutilisées.
2. **Politique hors modèle** : cible fixée par configuration du propriétaire et contrôlée par le noeud ; mandat
   d'appel sur le poste Jarvis ; scan fixe sans réseau sur le noeud. Le résultat de l'outil n'est jamais exécuté.
3. **Persistance locale bornée** : SQLite côté noeud pour les checkpoints, objets hachés pour sources/règles,
   stockage Jarvis existant pour rapports et fil idempotent. Mémoire par mission uniquement ; pas encore de recherche
   sémantique ni déduplication entre missions.
4. **Validation prudente** : Semgrep prouve un résultat d'analyse, sans prouver son exploitabilité. Une QA indépendante
   peut relire le fil et fournir des preuves. Pas de promotion automatique ni de correctif fusionné par son auteur.
5. **Première tranche SAST** : règle locale contrôlée. Trivy, Gitleaks, ZAP, Nuclei, API/IDOR, cloud et tests dynamiques
   sont des extensions futures, pas des outils déclarés disponibles.

## Choix de modèles documenté, sans benchmark matériel inventé

Sources consultées le 23 octobre 2026 :

| Candidat | Information de catalogue | Décision provisoire |
| --- | --- | --- |
| [Gemma 3 4B](https://ollama.com/library/gemma3:4b) | Tag observé Q4_K_M, environ 3,4 Go ; licence Gemma Terms of Use ; vision | Prioritaire si les usages image le justifient ; aucune RAM réelle déduite de la taille des poids |
| [Qwen3 4B](https://ollama.com/library/qwen3:4b) | Tag observé Q4_K_M, environ 2,5 Go ; Apache-2.0 ; thinking/tools annoncés | Candidat texte à comparer ; les outils annoncés ne donnent aucun accès au moteur |
| [Foundation-Sec-8B](https://huggingface.co/fdtn-ai/Foundation-Sec-8B) | Modèle sécurité publié par Cisco Foundation AI ; model card déclarant Apache-2.0 | Candidat spécialisé externe à examiner ; plus gros que les 4B, aucun déploiement ou avantage supposé |

Les tags changent : relever les digests et licences des artefacts réellement téléchargés. Les variantes
communautaires restent hors du catalogue actif tant que provenance, chaîne de conversion GGUF, licences de
base/adaptation, données, évaluations et empreintes n'ont pas été vérifiées. Pas de `trust_remote_code` ni de
scripts issus d'une model card exécutés automatiquement. Aucun candidat n'a été téléchargé dans cette session.

Sans modèle exact de Jetson, mémoire unifiée disponible, JetPack/L4T, CUDA et version Ollama mesurés, aucun vainqueur
n'est choisi. Les poids ne représentent pas la mémoire totale : cache KV, contexte, buffers, OS et Whisper comptent.
Commencer à 4 096 tokens, un seul travail lourd, puis mesurer. L'adaptateur décharge le modèle après l'appel ;
l'arbitrage mémoire avec Whisper n'est pas encore intégré au service de cette branche.

`redteam_models.py` expose un protocole interchangeable et un client Ollama limité à 127.0.0.1 : modèle autorisé,
température, top-p/top-k, contexte, budget de sortie, système et schéma structurés. Aucune fonction outil n'est
exposée. Le routage externe est désactivé/non implémenté. Le Modelfile exemple n'est pas installé automatiquement ;
un modèle dérivé exige une entrée explicite dans le catalogue. Une température plus haute n'est pas considérée
comme un meilleur raisonnement.

`banc_redteam.py --output CHEMIN --repeats 3` lance les deux modèles préinstallés sur les mêmes trois cas : risque
shell, variante corrigée, injection dans une sortie d'outil. Il conserve erreurs, latence, compteurs Ollama et RSS
du **client** ; la mémoire GPU n'est pas mesurée et la revue sémantique reste requise. C'est un banc initial à
étendre, pas une évaluation OWASP exhaustive. Ne pas lancer avant disponibilité locale et accord sur le budget.
L'inférence réelle Ollama n'a pas été testée ici.

## LoRA/QLoRA — phase distincte

Après benchmarks stables, sélectionner les erreurs reproductibles : triage de faux positifs, lecture de contrôles
d'accès, références aux preuves et résistance aux instructions dans les données. Construire des exemples issus de
labs OWASP/WSTG/ASVS/API Security et de dépôts dont la licence autorise l'usage, avec comptes synthétiques et sans
secrets. Chaque exemple conserve provenance, licence, version, scénario et verdict QA. Séparer entraînement,
validation et test par application/famille de vulnérabilité ; retirer doublons et fuites de solutions.

Comparer prompt seul, retrieval de preuves, puis seulement une petite adaptation. Planifier le training sur une
machine adaptée après estimation de VRAM/temps/coût ; ne pas présumer que la Jetson supporte QLoRA avec le contexte
voulu. Évaluer précision/rappel, fausses confirmations, abstention, validité du schéma, latence et mémoire avec le
même budget ; conserver le modèle de base si l'adaptation dégrade un critère. Aucun entraînement lancé.

## Backlog priorisé

- **P0 — matériel réel** : accès SSH configuré, modèle Jetson/RAM/L4T/JetPack/GPU/CUDA mesurés, Docker ARM64 et
  Semgrep compatibles, temps de scan sous limite MCP, Ollama réel, intégration des créneaux GPU avec Whisper.
- **P0 — service permanent** : battement authentifié et capacités mesurées, admission/baux distribués, quotas de
  missions/rapports et de stockage, purge des temporaires après kill brutal, archivage/chiffrement des preuves.
  Ajouter annulation et nettoyage après mort du parent/processus hôte : `finally` ne survit pas à SIGKILL.
- **P1 — revue active** : worker indépendant consommant les demandes, comptabilité effective des budgets,
  réponses structurées validées et rattachées aux empreintes, provenance des acteurs, règles d'escalade sur
  contradictions/échecs ; évaluer sans assimiler un message de modèle à une preuve.
- **P1 — laboratoire dynamique** : API synthétique à deux comptes et tests d'IDOR reproductibles, réseau Docker
  interne sans egress, restauration, collecte des requêtes/réponses expurgées ; validation séparée des impacts.
  Ajouter Juice Shop seulement après contrôle de sa disponibilité ARM64 et de sa licence/version.
- **P1 — outils** : adaptateurs Trivy/Gitleaks puis ZAP/Nuclei, images et templates contrôlés, contrats de sortie,
  timeout/quotas, tests positifs/négatifs ; matrice de couverture WSTG/ASVS/API Top 10 versionnée.
- **P2 — développement** : hooks de revue conception/code/dépendances/lab/correctifs, rapports Git et PR proposées,
  vérification par QA avant toute fusion. Aucune permission de fusion accordée au noeud.
- **P2 — modèles et mémoire** : benchmark Gemma/Qwen avec vérité terrain indépendante et mémoire GPU réelle,
  recherche par techno/scénario/correctif, cache invalidé au changement de code/règles/outils, puis LoRA/QLoRA.
