# Noeud GPU (Jetson) : une extension de Jarvis

La Jetson **étend** Jarvis d'outils GPU ; elle ne le duplique pas. Elle n'héberge ni plan de contrôle Jarvis, ni Board, ni chef, ni agent,
ni secret de Jarvis, et ne prend aucune initiative. Jarvis (sur le poste principal) reste le seul plan de contrôle :
missions, mandats, budgets, journal et Board. Éteindre, réinstaller ou remplacer la Jetson retire des capacités,
jamais des données.

Pas d'agents de code sur le noeud : Claude Code et Codex calculent dans le cloud, la Jetson n'y apporterait que
sa mémoire limitée et obligerait à copier dépôts, worktrees et secrets. Le noeud sert au calcul GPU local : transcription
(Whisper) et **modèle local multimodal** (Gemma 3 4B par défaut, via Ollama) pour les petites et moyennes tâches
texte et la lecture d'images. Ensuite : embeddings (calculés ici, stockés par Jarvis).

**Mémoire** : mémoire partagée CPU/GPU, donc **un seul modèle lourd à la fois**. Whisper est chargé au premier audio
et libéré après 5 min sans travail ; avant un travail texte ou image, Whisper est libéré, et avant un audio le
modèle local l'est. Les travaux passent par une seule file, un par un.

## Architecture

```
Jarvis (poste)                                         Jetson
 coureur / agent_runtime                                ~/.ssh/authorized_keys : clé jarvis-noeud
   └─ outils.executer  ── mandat, journal ──┐             command="python3 jarvis_noeud.py ssh",restrict
        mcp.<connexion>.audio_transcrire     │
                                             ├─ ssh … mcp ──▶ jarvis_noeud.py : serveur MCP stdio
   noeud.deposer(fichier) ─ ssh … depot ─────┘               └─ HTTP 127.0.0.1:7741 ─▶ service.py
                                                                  (modèle chargé, file de travaux)
```

- **Transport** : la connexion MCP `mcp_stdio` de la passerelle lance `/usr/bin/ssh … mcp`. Le service GPU est configuré pour écouter sur la boucle locale.
  Cela ne vérifie ni l'exposition de SSH ni les règles réseau de l'hôte. La clé de Jarvis est **limitée à une commande forcée** :
  elle ne donne ni shell, ni redirection de port. Seules `mcp`, `depot <sha256> <taille>` et `sante` sont acceptées.
- **Outils MCP** (tous asynchrones : une session MCP stdio est bornée à 30 s) :
  `audio_transcrire`, `texte_generer` (consigne ≤ 4 000 caractères, texte-donnée ≤ 24 000, 16 à 2 048 jetons),
  `image_decrire` (image déposée, PNG/JPEG/WEBP/GIF reconnus par leurs octets), `travail_resultat` /
  `audio_resultat` (attendent 15 s au plus), `noeud_sante` (lecture seule). Le modèle local n'a aucun outil : il
  lit une donnée délimitée et rend du texte, que Jarvis traite à son tour comme une donnée.
- **Usages côté Jarvis** : audio du Board transcrit ; images du Board lues (texte visible et description) en plus
  de l'image jointe au chef ; `jarvis noeud demander "…" [--fichier F | --image I]` pour le chef, les agents ou toi
  (résumer, extraire, classer, lire une capture) sans jeton Claude ni Codex.
- **Fichiers lourds** : déposés à part (`depot`), vérifiés par taille et empreinte, désignés ensuite par leur
  SHA-256. Effacés après traitement ; ceux qui n'ont pas servi sont purgés au bout d'une heure.
- **Mandat** : `jarvis noeud config` crée un mandat d'un an pour le projet `jarvis-board`, limité aux outils du
  noeud et à la destination `mcp:<connexion>`. Le révoquer coupe aussitôt Jarvis du noeud. Un mandat ne s'élargit
  pas : après l'ajout d'outils, relancer `jarvis noeud config` (nouvelle connexion, nouveau mandat, l'ancien révoqué).
- **Pannes** : noeud éteint, délai dépassé, mandat révoqué → l'audio garde ses métadonnées et le modèle le signale ;
  la mission continue. Aucun rejeu aveugle : chaque appel a un identifiant d'opération stable.

## Installation

Sur une installation autorisée, vérifier les prérequis Ollama et mémoire unifiée selon le matériel.
Les commandes ci-dessous sont une procédure générique, sans mesure de performance ni attestation du Lab :

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="GGML_CUDA_ENABLE_UNIFIED_MEMORY=1"\n' | sudo tee /etc/systemd/system/ollama.service.d/jetson.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

Puis :

```bash
sudo apt install -y ffmpeg python3.10-venv && sudo loginctl enable-linger "$USER"
```

Sur le poste, dans Ubuntu (WSL) : `jarvis noeud config utilisateur@ADRESSE-DE-LA-JETSON`. La première fois, la
commande crée la clé `~/.ssh/jarvis_noeud_ed25519` et affiche les deux lignes à lancer sur la Jetson, depuis une copie
de ce dossier :

```bash
echo 'ssh-ed25519 AAAA… jarvis-noeud' > jarvis_noeud.pub
bash installer_noeud.sh --cle-jarvis jarvis_noeud.pub
```

L'installateur (sans sudo, relançable) crée un venv qui réutilise le PyTorch CUDA de JetPack, installe
`openai-whisper`, génère le jeton du service local, démarre le service systemd utilisateur `jarvis-noeud` et
ajoute la clé avec sa commande forcée (copie de l'ancien `authorized_keys` à côté). Relance ensuite
`jarvis noeud config …` : connexion enregistrée, outils découverts et autorisés, mandat créé.

```bash
jarvis noeud etat                    # modèle, occupation, mémoire et températures
jarvis regler noeud.actif false      # retour exact au comportement sans noeud
```

Réserve l'adresse IP de la Jetson dans ta box : WSL ne résout pas les noms `.local`.

## Banc d'essai

```bash
systemctl --user stop jarvis-noeud
~/.local/share/jarvis-noeud/venv/bin/python ~/.local/share/jarvis-noeud/banc.py memo.m4a small turbo
systemctl --user start jarvis-noeud
```

## Vérification sans GPU

```bash
python3 -m unittest discover -s services/noeud_jetson/tests -v
python3 -m unittest discover -s tests -p 'test_noeud.py' -v
```

Moteur factice et faux `ssh` qui lance le vrai point d'entrée : ni modèle, ni GPU, ni réseau.

## Extension RedTeam

Le moteur d’audit autorisé est optionnel et possède un mandat distinct de l’audio.
Voir [installation, périmètre et limites](../../docs/redteam/README.md).
Ses checkpoints SQLite et preuves sont locaux au moteur ; ils ne remplacent pas les données du poste Jarvis.
Le [protocole de validation](../../docs/redteam/VALIDATION_JETSON.md) décrit les contrôles à consigner en privé.

Les chemins sous `$HOME`, le fichier de configuration du jeton et les restrictions de clé décrivent
le contrat d'installation générique ; ils ne contiennent pas de valeur secrète. Ne jamais publier leur contenu.
