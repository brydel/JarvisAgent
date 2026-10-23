# Première boucle cognitive outillée durable

`lib/jarvis/agent_runtime.py` relie les contrats, un adaptateur de modèle contrôlé et la passerelle d'outils.
Le runtime est local et utilise uniquement la bibliothèque standard. Il ne réclame aucune mission historique
et n'active pas implicitement le profil outillé des anciennes missions documentaires du Board.

## Parcours réel du contrôleur

1. Le propriétaire choisit un AgentSpec, un TaskSpec et son mandat. Fournisseur, modèle, enveloppes de jetons,
   durée et coût prévu sont explicites. Les outils requis doivent appartenir au profil.
2. Un tour prépare une identité stable d'appel de modèle et la conserve avant le départ. La réservation
   porte sur `model.<provider>.inference`, le projet et la destination de l'adaptateur contrôlé. Un alias ou
   un nom de modèle écrit dans le texte n'est pas une capacité disponible.
3. Le modèle renvoie des appels structurés parmi les outils du catalogue, ou un livrable final. Ses outils
   passent par `outils.executer`, avec une identité stable choisie par le contrôleur et le mandat de la tâche.
4. Chaque résultat d'outil devient une observation explicitement non fiable et un checkpoint. Les sorties
   du fournisseur ne décident ni de leur propre autorisation ni des critères de réussite.
5. Une sortie finale place le run en `awaiting_review`. Une personne ou un relecteur autorisé distinct de
   l'agent exécutant examine les critères et fournit son commentaire et ses références. Seule cette décision
   produit `succeeded` ou `failed`. Un refus ne déclenche pas une correction ni un nouveau coût automatique.

Le propriétaire qui a formulé l'objectif peut relire le résultat de son agent ; son identité ne se confond
pas avec celle de l'exécutant. L'API qui appelle `evaluer()` doit contrôler l'identité du relecteur. La chaîne
`par` ne constitue pas, à elle seule, une authentification système.

## Contrat Python

```python
run = agent_runtime.creer(
    agent_spec, tache_spec, par=identite_controlee,
    max_tours=8, reserve_model_cents=1, max_model_output_tokens=1000,
    source="cli", operation_id="requete-proprietaire-1",
)
run = agent_runtime.executer_tour(run["id"], adaptateur, par=identite_controlee)
agent_runtime.voir(run["id"])
agent_runtime.lister(project="projet", limite=50)
agent_runtime.pauser(run["id"], par=identite_controlee)  # pause() est aussi disponible
agent_runtime.reprendre(run["id"], par=identite_controlee)
agent_runtime.annuler(run["id"], par=identite_controlee)
```

Le callable d'adaptateur expose les métadonnées de contrôle `provider`, `model`, `destination` et `factice`.
Il reçoit `(contexte, operation_id=..., annulation=...)`. Le contexte comporte `instructions`, `objectif`,
`messages`, `outils` et `max_output_tokens`. Le retour normalisé comporte :

```json
{
  "type": "outils",
  "contenu": "Je consulte la source nécessaire.",
  "appels": [{"id": "call_source", "outil": "web.fetch", "arguments": {"url": "https://pypi.org/"}}],
  "usage": {"input_tokens": 120, "output_tokens": 45}
}
```

Un retour `final` ne comporte aucun appel et doit contenir un livrable non vide. Les outils absents du
catalogue ou du profil, les identifiants d'appels déjà observés et les réponses fournisseur dupliquées sont
refusés avant tout nouvel effet. Le modèle ne dispose pas de l'action de revue dans son catalogue.

## Reprise, concurrence et arrêt

Le run et son checkpoint résident dans des tables dédiées de `jarvis.db`, même si les anciens états utilisent
JSON. Une clé de création peut dédupliquer la requête du propriétaire. Chaque tour prend un verrou de fichier
non bloquant ; une deuxième commande concurrente reçoit `occupe` et ne devient pas un tour supplémentaire.
Une génération et un bail vérifiés lors de chaque commit protègent contre les résultats périmés.

Les appels réseau et réservations de mandats restent hors transaction SQLite. Le runtime refuse même un tour
appelé à l'intérieur d'une transaction du thread : la transaction imbriquable du store ne doit pas retenir
une écriture distante sous son verrou SQL.

- Crash après départ du modèle sans réponse conservée : `model_unknown`, aucun nouvel appel automatique.
- Crash après un outil réussi mais avant notre checkpoint : la passerelle retourne son reçu existant ;
  l'outil n'est pas exécuté une deuxième fois.
- Effet d'outil incertain : `tool_unknown`, continuation bloquée jusqu'à rapprochement. Cette tranche
  ne fournit pas une commande qui transforme un résultat inconnu en réussite supposée.
- Refus prouvé avant départ du modèle : reprise manuelle sous la même identité, au plus `max_attempts`
  de la tâche. Ce plafond ne se confond pas avec le nombre de tours du run.
- Pause, annulation ou révocation du mandat du modèle : le jeton descend à l'adaptateur et aux outils.
  Une écriture déjà partie reste un effet à rapprocher ; l'annulation n'efface pas son existence.

Un adaptateur personnalisé doit coopérer avec le jeton. Un thread Python arbitraire qui l'ignore ne peut
pas être tué par cette seule abstraction ; son résultat reste clôturé par la génération du contrôleur.

## Enveloppes et preuves

Un run comprend au plus 32 tours et huit appels d'outils par réponse. La durée totale court depuis son
premier tour, pauses comprises. La taille de contexte est bornée et une estimation conservatrice de son
volume réduit les sorties admissibles avant le départ. L'usage retourné doit être explicite et valide ;
absence d'usage ne signifie jamais zéro. Le runtime n'engage plus de nouveaux effets si le fournisseur
déclare dépasser l'enveloppe.

`reserved_cost_cents` est une **réservation prévisionnelle choisie par le contrôleur**, pas une mesure de
facturation OpenAI ni un plafond fournisseur prouvé. Le prix réel dépend du compte et du modèle ; cette
tranche ne prétend pas le déduire d'une réponse textuelle. Les quotas du mandat restent consommés après
annulation ou panne, conformément au registre des mandats.

Les références `operation:...` attestent seulement un reçu de la passerelle. Elles ne prouvent pas à elles
seules qu'un objectif métier est satisfait. La revue séparée conserve les critères, sa décision, son auteur
et les références qu'il a examinées.

## Continuité des modèles de raisonnement

L'adaptateur Responses utilise `store:false`. Pour poursuivre un appel d'outil avec un modèle de raisonnement,
il peut fournir `_continuation` : éléments fournisseur ordonnés, avec capsules `encrypted_content` opaques.
Le runtime ne lit ni ne décode ces capsules. Il refuse un résumé de raisonnement en clair et conserve les
capsules uniquement dans l'historique privé nécessaire à l'adaptateur suivant. Les textes publics et les
appels contrôlés restent disponibles séparément.

Les réponses de `voir()`, `lister()`, `executer_tour()` et les projections de contrats utilisent une liste
blanche de champs publics. Les capsules, les checkpoints privés et les identifiants de réponse fournisseur
internes ne traversent ni ces sorties ni les traces publiques. Les clés d'authentification ne font pas
partie du contrat ni de ce registre ; l'adaptateur les résout depuis sa configuration propriétaire.

## Limites de cette tranche

Ce runtime traite une tâche locale indépendante. Un `execution_engine=temporal` ou des dépendances non
résolues sont refusés explicitement. Aucun transfert de propriétaire ni ordonnanceur de projet n'est
simulé. Les missions historiques et les agents workmux gardent leur propre mécanisme.

Les conversations de l'usine restent libres sur tous les sujets. Le prompt du runtime explique ce contexte ;
les outils de communauté peuvent figurer dans son catalogue quand ils sont configurés. Une opinion issue
du réseau ne devient jamais une permission ou une réussite prouvée.

## Vérification

```bash
python3 -m unittest discover -s tests -p test_agent_runtime.py -v
```

Les tests utilisent un modèle factice déclaré, un journal de passerelle réel et un transport de test explicite
pour l'adaptateur OpenAI Responses. Ils couvrent deux tours, la continuité chiffrée privée, les checkpoints,
crashes, concurrence, budgets, révocation, annulation et revue. Aucun modèle distant ni compte réel n'est
présenté comme vérifié par ces tests.
