# Protocole de validation WSL — modèle public

Ce document est un protocole à remplir en privé, pas une attestation de déploiement.
Les anciennes observations du laboratoire ont été retirées de cette version publique.
Voir l'[exemple synthétique](exemples/rapport-synthetique.json) et la
[politique des preuves](CONFIDENTIALITE.md).

À consigner dans un rapport privé : commit testé, environnement, prérequis,
commandes autorisées, résultats attendus et observés, erreurs et limites.
Comparer fixture vulnérable et corrigée, vérifier le rejeu dans un autre processus,
les restrictions de mandat et la conservation des fonctions existantes.
Distinguer moteur factice, processus local, conteneur et parcours distant.
Une fixture synthétique ne rend pas publics l'inventaire ou les accès du poste.

Les tests locaux sans modèle sont décrits dans le README du service.
Les essais distants, Docker et inférences demandent une validation séparée de leur périmètre.
Aucun accès matériel ni exposition réseau n'est vérifié par ce document.
Un constat d'outil ne prouve ni exploitabilité ni impact.
