---
name: jarvis-studio
description: Studio de l'usine Jarvis — fabrique une vraie vidéo de présentation d'un produit (enregistrement de l'application, scènes animées, montage, contrôle qualité) et les visuels d'une campagne publicitaire. À utiliser dès qu'une tâche demande une vidéo, une démo filmée, un teaser, une présentation animée (« motion »), des visuels d'annonce, une campagne publicitaire ou de lancement, même si la demande ne parle que de « marketing » ou de « contenu ». Ne pas utiliser pour écrire seulement un texte, ni pour diffuser ou publier quoi que ce soit.
---

# Jarvis Studio

Tu fabriques ici des livrables qu'un fondateur peut diffuser demain : une vidéo de produit, des
visuels, un dossier de campagne. Pas un texte qui décrit une vidéo : la vidéo.

Tout se fait avec des outils locaux et gratuits : Chromium (Playwright) pour filmer et dessiner,
ffmpeg pour monter. Les scripts sont dans `scripts/`, à côté de ce fichier
(`$JARVIS_HOME/skills/jarvis-studio/scripts`). Lance-les tels quels : ne les copie pas et ne les
réécris pas.

```bash
STUDIO="$JARVIS_HOME/skills/jarvis-studio/scripts"
```

## Où ranger

- **Sources** (scénarios, storyboards, montages, captures) : dans le dépôt, sous
  `marketing/<ISSUE>/`. Elles partent dans ta PR : la prochaine vidéo repartira de là.
- **Résultats** (vidéos, images finales, dossier de campagne) : dans `$JARVIS_LIVRABLES`. Jamais
  dans git : une vidéo dans l'historique alourdit le dépôt pour toujours.
- Les fichiers intermédiaires lourds (films bruts) : dans `$JARVIS_LIVRABLES/brouillons/`.

**Chemins dans les fichiers JSON** (scénario, storyboard, montage) : un chemin relatif part du dossier
du fichier JSON lui-même, pas du dossier courant. Pour désigner un fichier des livrables, écris
`"$JARVIS_LIVRABLES/…"` : les scripts développent cette variable.

## La chaîne vidéo

Compte trois passes. La première version n'est presque jamais la bonne : c'est en regardant le
résultat qu'on voit ce qui ne va pas.

### 1. Scénario

Écris `marketing/<ISSUE>/scenario-video.md` avant de toucher aux outils. Une vidéo de produit
tient en 20 à 45 secondes :

| Moment | Durée | Contenu |
| --- | --- | --- |
| Accroche | 3 s | Le bénéfice, en une phrase que la cible reconnaît |
| Démonstration | 12 à 30 s | 2 ou 3 moments du produit, un seul message par plan |
| Preuve | 3 à 5 s | Ce qui rend la promesse crédible (liste courte, chiffre vrai) |
| Appel à l'action | 3 s | Une seule action, l'adresse |

Tout ce que la vidéo affirme doit être vrai dans le produit tel qu'il est aujourd'hui. Pas de
chiffre, de client ni de témoignage inventé : une publicité mensongère engage ton humain, pas toi.

### 2. Filmer le produit

Lance l'application **en local**, avec des données de démonstration. Jamais la production, jamais
de vraies données de clients ; s'il n'existe pas de jeu de démonstration, crée-le (comptes et noms
fictifs). Puis décris le parcours dans `scenario.json` et filme :

```bash
node "$STUDIO/enregistrer.cjs" marketing/<ISSUE>/scenario.json "$JARVIS_LIVRABLES/brouillons/parcours.webm"
```

```json
{ "largeur": 1600, "hauteur": 1000,
  "etapes": [
    { "aller": "http://localhost:3000/dashboard" },
    { "masquer": ".email-utilisateur" },
    { "attendre": 900 },
    { "capture": "captures/tableau.png" },
    { "ecrire": { "dans": "#poste", "texte": "Développeur React" } },
    { "cliquer": "text=Générer une lettre" },
    { "attendre": 1800 }
  ] }
```

Une étape contient une seule action : `aller`, `attendre` (ms), `attendre_selecteur`, `cliquer`,
`survoler`, `ecrire`, `touche`, `defiler` (px), `masquer`, `capture` (image fixe, sans le curseur).
Le film de sortie est un `.webm`. Le curseur est dessiné et se déplace à vitesse humaine. Laisse une
attente après chaque action importante : le spectateur a besoin de voir le résultat.

`masquer` prend un **sélecteur CSS** (`.email`, `#compte`, `[data-prive]`), pas un sélecteur de texte.
La zone reste floutée sur toutes les pages suivantes. Place-le juste après le premier `aller`, puis
vérifie sur la planche-contact que rien de sensible n'est lisible : c'est toi qui en réponds.

Si l'application ne peut pas tourner (dépendance absente, base inaccessible), ne l'invente pas :
dis-le dans Linear (`❓ QUESTION :`) et propose une vidéo faite de captures existantes.

### 3. Scènes animées

Titres, captures mises en scène, arguments et écran de fin se décrivent dans un `storyboard.json`,
rendu image par image (fluide et identique à chaque rendu) :

```bash
node "$STUDIO/rendre.cjs" marketing/<ISSUE>/storyboard.json "$JARVIS_LIVRABLES/presentation.mp4"
node "$STUDIO/rendre.cjs" marketing/<ISSUE>/storyboard.json "$JARVIS_LIVRABLES/vertical.mp4" --format 9:16
```

Le script refuse un storyboard mal formé (type de scène inconnu, champ manquant, fichier introuvable)
avant de rendre quoi que ce soit, et te prévient quand un plan est trop long.

Formats : `16:9` (site, YouTube), `9:16` (TikTok, Reels, Shorts), `1:1` et `4:5` (fils
d'actualité). Rends chaque format directement avec `--format` : les scènes se recomposent toutes
seules. Compte environ 5 secondes de calcul par seconde de vidéo.

```json
{ "marque": { "nom": "JobPilot", "accent": "#5B8CFF", "fond": "#0B0D12", "logo": "logo.png" },
  "scenes": [
    { "type": "titre", "duree": 3.4, "sur_titre": "Nouveau", "titre": "Ton copilote emploi",
      "sous_titre": "Suivi, relances et lettres au même endroit." },
    { "type": "capture", "duree": 5, "image": "captures/tableau.png", "url": "jobpilot.app",
      "titre": "Tout ton suivi d'un coup d'œil",
      "zoom": { "de": 1, "a": 1.12, "vers": [30, 30] },
      "reperes": [ { "x": 17, "y": 27, "texte": "Candidatures envoyées", "a": 1.3 } ] },
    { "type": "capture", "duree": 6.5, "video": "$JARVIS_LIVRABLES/brouillons/parcours.webm", "debut": 0.7,
      "titre": "Une lettre en un clic" },
    { "type": "points", "duree": 4.6, "titre": "Pourquoi JobPilot",
      "points": ["Toutes tes candidatures suivies", "Relances préparées pour toi"] },
    { "type": "fin", "duree": 3.5, "titre": "Reprends la main", "bouton": "Essayer", "url": "jobpilot.app" }
  ] }
```

Le détail de chaque type de scène (`titre`, `capture`, `points`, `chiffre`, `fin`) et de ses
champs est dans `reference.md`. Ici `captures/tableau.png` est à côté du storyboard (c'est là que
l'action `capture` l'a écrit) et le film vient des livrables. Reprends les couleurs de la marque
dans le code du projet (jetons du thème), pas au hasard.

Une image seule (visuel d'annonce, vignette) sort du même storyboard :

```bash
node "$STUDIO/rendre.cjs" marketing/<ISSUE>/storyboard.json "$JARVIS_LIVRABLES/visuels/annonce-carre.png" --image 2.8 --format 1:1
```

### 4. Monter

Pour enchaîner plusieurs séquences (scènes rendues, film brut, autre format) :

```bash
python3 "$STUDIO/monter.py" marketing/<ISSUE>/montage.json "$JARVIS_LIVRABLES/video-finale.mp4"
```

```json
{ "format": "16:9", "transition": 0.4,
  "segments": [
    { "fichier": "$JARVIS_LIVRABLES/presentation.mp4", "fin": 8.4 },
    { "fichier": "$JARVIS_LIVRABLES/brouillons/parcours.webm", "vitesse": 1.2 },
    { "fichier": "$JARVIS_LIVRABLES/presentation.mp4", "debut": 19.5 }
  ] }
```

`debut`, `fin` (secondes) et `vitesse` sont facultatifs. Un film d'`enregistrer.cjs` est rogné
seul à sa partie utile. Une séquence aux mauvaises proportions est posée sur un fond flouté :
utile pour un film d'écran dans une vidéo verticale, laid pour une scène animée (rends-la plutôt
au bon format). Le son des séquences n'est pas repris : la bande-son est la musique, ou le silence.
Musique : seulement un fichier fourni par ton humain ou dont la licence autorise
l'usage commercial (`"musique": {"fichier": "…", "volume": 0.25}`) ; sinon, pas de musique.

Souvent le storyboard suffit : il sait déjà intégrer un clip du produit dans une scène
`capture`. Le montage sert quand tu assembles des morceaux d'origines différentes.

### 5. Contrôler, puis regarder

```bash
python3 "$STUDIO/verifier.py" "$JARVIS_LIVRABLES/video-finale.mp4" --duree-min 15 --duree-max 60
```

Le contrôle technique vérifie ce qui se mesure : durée, définition, fluidité, compatibilité,
taille (49 Mo au plus pour Telegram), intégrité du fichier, écran noir, image figée. Il ne sait pas
juger une scène animée : un plan vide ou hors sujet passe le contrôle. Il écrit une **planche-contact**
(`video-finale.planche.png`, douze vignettes). **Ouvre-la avec ton outil de lecture d'image** :
un fichier peut être techniquement parfait et raté. Vérifie à l'œil :

- le texte est lisible et rien n'est coupé par un bord ;
- chaque plan montre ce que son titre annonce ;
- aucun écran vide, aucune page d'erreur, aucun état de chargement ;
- aucune donnée sensible à l'image (courriel réel, clé, nom d'un vrai client) ;
- le rythme : pas de plan qui traîne, l'appel à l'action reste assez longtemps pour être lu.

Pour voir un instant précis en grand : `--image <secondes>` sur le storyboard, ou
`ffmpeg -ss 7.2 -i video.mp4 -frames:v 1 image.jpg`. Corrige, relance, recontrôle. Tu as fini
quand le verdict est `PRÊT` **et** que tu as regardé la planche-contact de cette version-là.

### 6. Rendre compte

Dans ton commentaire `✅ TERMINÉ` : la liste des fichiers déposés dans `$JARVIS_LIVRABLES`, le
verdict du contrôle, ce que tu as corrigé entre les passes, et ce qui reste discutable. Tu
n'envoies rien toi-même à ton humain et tu ne publies rien : le chef d'orchestre fait relire,
puis livre.

## Campagne

Une campagne publicitaire est un dossier complet dans `$JARVIS_LIVRABLES`, pas un texte :

| Fichier | Contenu |
| --- | --- |
| `brief.md` | Cible, problème, promesse, preuves, ton, objections et réponses |
| `annonces.md` | Trois angles × les formats demandés, dans les limites de chaque plateforme |
| `visuels/` | Les images d'annonce, rendues avec `rendre.cjs --image` aux formats utiles |
| `scenario-video.md` | Le scénario de la vidéo, plan par plan, prêt pour le motion designer |
| `diffusion.md` | Canaux, budget conseillé, calendrier, indicateurs à suivre |

Avant d'écrire : parcours le produit en local et relis la veille concurrentielle du projet
(document Linear). Le positionnement vient de ce que le produit fait mieux que les autres,
preuves à l'appui, pas d'une liste de fonctionnalités. Trois angles différents valent mieux que
dix variantes du même : ton humain choisira ce qu'il teste.

Les limites de caractères des plateformes changent : vérifie-les dans leur documentation
officielle le jour où tu écris, et cite la source dans `annonces.md`.

La diffusion (dépenser, publier, envoyer un courriel à des clients) n'est jamais ton travail :
`diffusion.md` prépare la décision, ton humain la prend.

## En cas de problème

| Symptôme | Cause probable | Quoi faire |
| --- | --- | --- |
| `Playwright introuvable` ou `Chromium ne démarre pas` | Studio pas installé sur ce poste | `❓ QUESTION :` dans Linear : demander `./install.sh --studio` |
| `fichier(s) introuvable(s) à côté du storyboard` | Chemin relatif faux | Les chemins partent du dossier du storyboard |
| `étape N : … Timeout` | Sélecteur absent ou application pas prête | Ajoute `attendre_selecteur` avant, vérifie le sélecteur dans le code |
| Verdict « image figée » | Un film du produit resté immobile (page bloquée, attente trop longue) | Raccourcis l'attente ou refais l'enregistrement |
| Verdict « intégrité » | Fichier tronqué, ou image plus courte que le son | Relance le rendu ou le montage jusqu'au bout |
| Texte coupé sur la planche-contact | Titre trop long | Raccourcis : 6 mots au plus pour un titre |
| Fichier trop lourd | Vidéo longue en haute définition | Passe-la par `monter.py` : il réencode sous 49 Mo, ou dit qu'il faut raccourcir |
