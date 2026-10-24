# Preuves privées et exemples publics

Publier les contrats, prérequis, versions épinglées des dépendances, restrictions SSH et chemins génériques nécessaires à l'installation.
Conserver en privé les inventaires réels, versions installées, hôtes, utilisateurs, empreintes de déploiement, identifiants de mission, mesures et journaux.
Un chemin de jeton n'est pas sa valeur ; le contenu des fichiers de configuration et des clés reste privé.

Les exemples de `exemples/` sont fictifs et explicitement marqués ; ils n'attestent aucun test réel.
Placer les futurs rapports hors du checkout, ou dans `docs/redteam/prive/` ou `work/redteam/` ignorés par Git.
Avant retrait, conserver une archive privée et vérifier sa restauration. Ne pas publier l'archive ou un patch contenant les suppressions originales.
`.gitignore` ne protège pas un fichier déjà suivi, un ajout forcé ou les descriptions de PR.

## Contrôle reproductible sans API payante

Utiliser Gitleaks **8.24.3**, archive de release vérifiée contre ses checksums, ou compilation du tag correspondant.
La configuration étend toutes les règles standard : aucune exclusion globale des documents ou fixtures.
Depuis la racine, avec les rapports stockés dans un répertoire privé hors dépôt :

```bash
gitleaks dir --config=.gitleaks.toml --redact=100 --report-format=json --report-path=/CHEMIN_PRIVE/arbre.json .
gitleaks git --config=.gitleaks.toml --redact=100 --log-opts=--all --report-format=json --report-path=/CHEMIN_PRIVE/historique.json .
```

La configuration pre-commit est proposée, sans installation automatique. Le contrôle de l'index nécessite une activation distincte.
Un scan sans résultat ne prouve pas l'absence de secret. Revoir les faux positifs sans publier leur contenu.
Source : https://github.com/gitleaks/gitleaks/blob/v8.24.3/README.md

Le retrait dans une nouvelle révision laisse les anciennes branches, commits, références de PR, clones et caches accessibles.
Traiter séparément les descriptions/commentaires de PR. Toute publication, modification de visibilité, protection GitHub ou réécriture d'historique exige une décision distincte.
L'écoute locale d'un service et l'isolation d'un conteneur ne prouvent pas une faible exposition réseau de l'hôte.
