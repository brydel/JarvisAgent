# MCP stdio local

`lib/jarvis/mcp_stdio.py` ajoute un transport MCP standard par processus local et JSON-RPC délimité par
des lignes UTF-8. Il n'ajoute aucune dépendance au cœur Python.

## Configuration du propriétaire

Le propriétaire fournit un exécutable absolu, une liste d'arguments, les noms des seules variables
d'environnement à transmettre et, facultativement, un répertoire de travail absolu existant :

```json
{
  "command": "/usr/bin/python3",
  "args": ["/chemin/du/serveur_mcp.py"],
  "env_allowlist": ["JARVIS_SERVICE_TOKEN"],
  "cwd": "/chemin/du/projet"
}
```

Les exemples de chemins sont à adapter. Le transport ne cherche pas un exécutable par son nom et
n'utilise pas `shell=True`. Une demande d'outil ou le texte d'un modèle ne configurent jamais la commande.
Les arguments ne doivent pas contenir de secret : utiliser une variable référencée par son nom.

Le serveur reçoit `PATH=os.defpath`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8` et `PYTHONUNBUFFERED=1`, puis les seules
variables explicitement autorisées présentes dans l'environnement du contrôleur. Il n'hérite pas
implicitement de HOME, des proxies, des clés du modèle ni des variables des autres sessions. Un serveur
qui dépend d'un PATH particulier doit recevoir ce nom explicitement après décision du propriétaire.

**Une découverte stdio lance réellement du code local.** Le serveur possède les droits Linux de
l'utilisateur qui le démarre, même avant `tools/call`. La configuration d'un serveur vaut donc autorisation
de démarrer cet exécutable. Ce mécanisme n'est pas un bac à sable contre un serveur malveillant ; il faut
un utilisateur système, conteneur ou autre isolation adaptée pour ce besoin.

## Interface utilisée par le contrôleur

```python
from jarvis import mcp_stdio

spec = mcp_stdio.valider_configuration(configuration_du_proprietaire)
catalogue = mcp_stdio.decouvrir(spec, verifier=connexion_toujours_active)
resultat = mcp_stdio.appeler(
    spec, nom_outil, arguments,
    verifier=connexion_et_selection_toujours_valides,
    avant_effet=mandat_toujours_valide,
    annulation=jeton_local,
)
```

`verifier` et `avant_effet` sont des fonctions du contrôleur qui lèvent une exception lors d'un refus.
Elles ne viennent ni du serveur ni du modèle. Le contrôleur assure l'identité, la sélection courante des
outils, le mandat exact et le journal d'opérations. Le transport recontrôle `verifier` avant de démarrer le
processus, pendant ses attentes et avant chaque message, dont `tools/call` après le handshake.

La découverte renvoie des descripteurs `{name, description, inputSchema}`. Le contrôleur ajoute leur
sélection `autorise` depuis sa propre configuration courante. Les schémas distants ne donnent aucun droit.
Le résultat d'un appel est un objet MCP avec sa liste `content` ; `isError` reste un résultat d'outil à
traiter explicitement par l'appelant.

`Client` est également disponible comme gestionnaire de contexte : `initialiser()`, `appel()`,
`decouvrir()` et `diagnostic()`. Une seule requête est en vol par session. Les helpers ouvrent et ferment
une session pour chaque opération ; ils ne conservent pas de processus de serveur en arrière-plan.

## Protocole et limites

- Handshake `initialize`, négociation parmi les versions 2025-03-26, 2025-06-18 et 2025-11-25, puis
  `notifications/initialized` avant les autres méthodes.
- Pagination `tools/list` bornée à dix pages et 128 outils distincts, avec contrôle des curseurs cycliques.
- Corrélation JSON-RPC stricte des identifiants entiers ; réponse erronée, JSON non standard et erreur
  fournisseur donnent une erreur expurgée, sans renvoyer le contenu privé du serveur.
- Aucune capacité sampling, elicitation ou roots n'est annoncée. Les requêtes serveur de capacités non
  prises en charge sont refusées par `-32601` ; le ping reçoit une réponse vide. Les notifications sont
  bornées et ne provoquent aucune exécution.
- Un message de sortie contient au plus 1 Mo, la session au plus 8 Mo et une requête au plus 128 Ko.
  Les deux sorties sont drainées ensemble ; stderr est jeté, avec seulement un compteur saturé et un
  indicateur de dépassement de 64 Ko. Son contenu ne part ni au navigateur ni dans l'erreur.
- Délai total monotone de vingt secondes par défaut, trente au maximum ; il couvre handshake, écriture,
  lecture, pagination et outils. Le jeton d'annulation est vérifié au plus toutes les 100 ms.
- Le groupe POSIX du processus reçoit TERM puis KILL à la fermeture, y compris si son parent est déjà
  sorti. Le nettoyage dispose de deux délais supplémentaires d'une seconde. Un enfant qui change
  volontairement de groupe/session dépasse cette garantie et exige une isolation système.

La lecture du registre utilise `valider_configuration(spec, verifier_fichiers=False)` pour valider sa
structure même après suppression d'un binaire ou d'un répertoire. L'enregistrement et `Client` vérifient
leur présence avant lancement. Une installation disparue peut ainsi toujours être consultée ou révoquée.

`metadata()` expose seulement le nom de l'exécutable, sa disponibilité locale et les noms/présence des variables configurées.
Les arguments, chemins de travail et valeurs d'environnement restent privés. Les valeurs explicitement
transmises sont expurgées d'un résultat si le serveur les renvoie telles quelles. Cela ne peut pas empêcher
un programme local malveillant de transformer ou d'exfiltrer un secret auquel son propriétaire lui a donné accès.

## Effets incertains

Il n'existe aucun retry dans ce transport. Si `tools/call` est parti et que le serveur meurt ou perd sa
réponse, l'effet peut déjà avoir eu lieu. La passerelle doit conserver l'opération `unknown`, sans relancer
le programme ou le même appel automatiquement. Un timeout, une annulation ou une erreur JSON ne prouvent
pas l'absence d'effet. La découverte seule n'appelle pas d'outil, mais le démarrage du programme peut
produire des effets propres à ce programme.

## Vérification

```bash
python3 -m unittest discover -s tests -p test_mcp_stdio.py -v
```

Les 19 tests passent sur de vrais processus Python locaux : protocole, pagination, environnement minimal,
expurgation, erreurs et réponses non corrélées, serveur bavard ou bloqué, réponse perdue, retrait de scope,
annulation et arrêt de descendants qui ignorent TERM. Aucun compte externe, modèle ou envoi réel n'est utilisé.
L'intégration du registre des connexions, de la passerelle et de l'interface est vérifiée séparément par
leurs tests respectifs.
