# Modèles de la boucle outillée : OpenAI Responses

`lib/jarvis/modeles_runtime.py` est un adaptateur standard Python vers l'API Responses. Il ne lance pas de
CLI, ne copie pas ses credentials et ne suppose aucun modèle disponible à partir d'un nom commercial.
Le contrôleur doit réserver le budget, vérifier le mandat puis journaliser le départ avant de l'appeler.

## Configuration propriétaire

```json
{
  "provider": "openai_responses",
  "model": "ID_EXPLICITE_DU_COMPTE",
  "api_key_env": "JARVIS_OPENAI_API_KEY",
  "max_output_tokens": 4096,
  "timeout_s": 90,
  "max_turns": 12
}
```

Remplacer l'identifiant par celui du compte réellement connecté. La clé est fournie dans la variable
d'environnement nommée ; sa valeur ne fait partie ni de cette configuration ni du navigateur. L'hôte de
l'API est fixé à `api.openai.com`, avec TLS vérifié. Aucun endpoint personnalisable ne peut recevoir la clé.
Le proxy explicite de l'installation doit autoriser cet hôte lorsque le cloud l'exige.

Les bornes sont 1–32 768 jetons de sortie, 1–120 secondes par appel et 1–64 tours. Les défauts sont
4 096, 90 et 12. La limite de tours est une information contrôlée par le runtime ; cet adaptateur ne boucle
pas lui-même. Le budget restant du tour peut abaisser le plafond de sortie.

`public_configuration()` expose la référence et sa présence, jamais la valeur. `verifier()` fait seulement
`GET /v1/models/{model}`. Authentification et accès au modèle deviennent vérifiés uniquement après une
réponse 200 contenant ce même identifiant. Ce contrôle n'est pas une inférence et n'en apporte aucune preuve.

## Interface du contrôleur

```python
modele = OpenAIResponses(configuration)
reponse = modele(
    {
        "instructions": instructions_controlees,
        "objectif": objectif,
        "messages": historique_prive,
        "outils": catalogue_controle,
        "max_output_tokens": plafond_restant,
    },
    operation_id=identite_stable_du_tour,
    annulation=jeton_local,
)
```

Métadonnées du callable : `provider`, `model`, `destination` et `factice=False` en production. Une injection
de transport pour un test marque l'instance et son retour `factice=True`. Le retour normalisé contient
`type` (`outils` ou `final`), `appels` (`id`, `outil`, `arguments`), `contenu`, `usage`, `response_id`, `provider`
et `model`. Un texte final propose un livrable ; il ne signifie pas que la tâche est acceptée.

Les outils viennent uniquement du catalogue du contrôleur. Leurs identifiants Jarvis, qui peuvent contenir
des points ou dépasser 64 caractères, deviennent des noms de fonctions opaques et stables compatibles avec
l'API. Le retour est reconverti vers l'identifiant exact. Un nom inconnu ou un appel dupliqué est refusé.
La passerelle conserve la validation des arguments et l'autorisation avant tout effet.

L'objectif est un message utilisateur. Les sorties d'outils sont des `function_call_output`, liées à leur
`call_id`, et restent des données non fiables. Aucun message documentaire ne devient une instruction système.
Un historique avec sortie orpheline, appel dupliqué ou appel sans résultat est refusé avant départ.

## Continuation privée des modèles de raisonnement

Les requêtes utilisent `store:false` et demandent `reasoning.encrypted_content`. Le retour inclut un champ
**privé** `_continuation`, destiné au seul état du runtime. Il conserve dans l'ordre les éléments fournisseur
nécessaires au tour suivant : capsules opaques chiffrées, appels de fonctions et messages assistant normalisés.
Chaque capsule de raisonnement ne conserve que `id`, `encrypted_content`, `type` et `summary:[]`. Les textes
et résumés de raisonnement sont supprimés ; le contenu chiffré n'est ni décodé ni interprété.

Le runtime inscrit un message privé `{role:"provider",contenu:"",continuation:[...]}`, suivi des sorties
d'outils. L'adaptateur reconstruit alors l'ordre exact reasoning → function_call → function_call_output.
Ce champ et ces messages privés ne doivent jamais être renvoyés par les API publiques, affichés dans le
Board, publiés dans le réseau des agents ou copiés dans les traces lisibles. Un raisonnement non continuable
accompagné d'un appel d'outil est refusé avant que cet outil soit exécuté.

Cette continuité est nécessaire à l'orchestration stateless documentée par OpenAI :
https://github.com/openai/openai-cookbook/blob/main/examples/reasoning_function_calls.ipynb
(section « Manual conversation orchestration »). Elle ne prouve pas la disponibilité d'un modèle précis
sur le compte ; aucun modèle distant n'a été appelé pendant cette livraison.

## Erreurs, coût et annulation

L'adaptateur ne réessaie aucun appel. `ModeleError.incertain=True` indique qu'une requête facturable a pu
partir : timeout, interruption réseau, 408/5xx ou réponse 200 malformée, incomplète ou sans usage exploitable.
L'identifiant `X-Client-Request-Id` facilite le rapprochement mais n'est pas une garantie de déduplication
fournisseur. Le contrôleur doit conserver les réservations et bloquer le rejeu automatique de cet état.

Le comptage d'entrée/sortie est obligatoire, entier, borné et cohérent. Le plafond de sortie inclut les
jetons de raisonnement facturés par le fournisseur. Un coût réservé est prévisionnel : cette couche ne
dispose pas d'une preuve du tarif ou du montant de la facture réelle.

Le jeton d'annulation est vérifié avant et après le réseau et transmis au transport borné. Une annulation
après départ ne fait pas disparaître un calcul déjà réalisé côté fournisseur. Les erreurs publiques sont
fixes et expurgées ; aucun corps d'erreur distant, valeur de clé ni raisonnement lisible n'est conservé.

## Vérification

```bash
python3 -m unittest discover -s tests -p test_modeles_runtime.py -v
```

Les tests utilisent un vrai serveur HTTP contrôlé et adaptent uniquement la frontière TLS. Ils couvrent
fonctions et finales, deux tours avec continuation chiffrée, corrélation des résultats, noms injectés,
sorties mixtes, usage invalide, refus et timeout, résolution renouvelée de credential et masquage récursif.
Il ne s'agit pas d'un test d'inférence sur un compte OpenAI réel.
