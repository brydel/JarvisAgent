# Noeud GPU (Jetson) : une extension de Jarvis

La Jetson **étend** Jarvis d'outils GPU ; elle ne le duplique pas. Elle n'héberge ni plan de contrôle Jarvis, ni Board, ni chef, ni agent,
ni secret de Jarvis, et ne prend aucune initiative. Jarvis (sur le poste principal) reste le seul plan de contrôle :
missions, mandats, budgets, journal et Board. Éteindre, réinstaller ou remplacer la Jetson retire des capacités,
jamais des données.

Pas d'agents de code sur le noeud : Claude Code et Codex calculent dans le cloud, la Jetson n'y apporterait que
ses 8 Go et obligerait à copier dépôts, worktrees et secrets. Le noeud sert au calcul GPU local : transcription
(Whisper) et **modèle local multimodal** (Gemma 3 4B par défaut, via Ollama) pour les petites et moyennes tâches
texte et la lecture d'images. Ensuite : embeddings (calculés ici, stockés par Jarvis).

**Mémoire** : 8 Go partagés CPU/GPU, donc **un seul modèle lourd à la fois**. Whisper est chargé au premier audio
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

- **Transport** : la connexion MCP `mcp_stdio` de la passerelle lance `/usr/bin/ssh … mcp`. Aucun port n'est ouvert
  sur la Jetson ; le service GPU n'écoute que sur 127.0.0.1. La clé de Jarvis est **limitée à une commande forcée** :
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

Sur la Jetson, une fois, avec sudo (toi) — Ollama, puis la **mémoire unifiée** sans laquelle le GPU ne voit que la
mémoire hors cache disque et le modèle tourne surtout sur le CPU (mesuré : 7/35 couches et 1,5 jeton/s sans, 35/35
et 11,7 jetons/s avec, Gemma 3 4B en 15 W) :

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
bash installer_noeud.sh --cle-jarvis jarvis_noeud.pub      # --modele turbo d'après le banc d'essai
```

L'installateur (sans sudo, relançable) crée un venv qui réutilise le PyTorch CUDA de JetPack, installe
`openai-whisper`, génère le jeton du service local, démarre le service systemd utilisateur `jarvis-noeud` et
ajoute la clé avec sa commande forcée (copie de l'ancien `authorized_keys` à côté). Relance ensuite
`jarvis noeud config …` : connexion enregistrée, outils découverts et autorisés, mandat créé.

```bash
jarvis noeud etat                    # modèles audio et texte, contexte, occupation, mémoire, températures
jarvis regler noeud.actif false      # retour exact au comportement sans noeud
```

Réserve l'adresse IP de la Jetson dans ta box : WSL ne résout pas les noms `.local`.

## Réglages du modèle local et de l'audio

Tous passent par l'installateur (relançable ; une option absente garde le réglage déjà présent dans
`~/.config/jarvis-noeud/env`) :

| Option | Réglage | Défaut |
|---|---|---|
| `--llm` | modèle Ollama texte et image | `gemma3:4b` |
| `--contexte` | taille du contexte (2048 à 32768) | `4096` |
| `--reflexion oui\|non` | réflexion des modèles qui en ont une | `non` pour les Qwen, sinon défaut du modèle |
| `--moteur-audio` | `whisper` (PyTorch) ou `faster-whisper` (CTranslate2) | `whisper` |
| `--modele` | modèle audio (`small`, `turbo`, `large-v3-turbo`…) | `small` |

Passage à Qwen 3.5 une fois le banc favorable :

```bash
ollama pull qwen3.5:4b
bash installer_noeud.sh --llm qwen3.5:4b --contexte 8192
```

Les roues CTranslate2 de PyPI pour ARM64 n'ont pas CUDA : l'installateur prévient si faster-whisper tournerait
sur le processeur, et `banc.py` affiche l'appareil réellement utilisé. Plus de mémoire pour un plus grand contexte :
bureau désactivé (`sudo systemctl set-default multi-user.target`, environ 800 Mo) et JetPack 6.2.2, qui corrige
l'échec d'allocation CUDA de L4T 36.4.7.

## Bancs d'essai

Audio, moteurs et modèles (`moteur:modèle`, un nom seul vaut `whisper:nom`) :

```bash
systemctl --user stop jarvis-noeud
~/.local/share/jarvis-noeud/venv/bin/python ~/.local/share/jarvis-noeud/banc.py memo.m4a small turbo faster-whisper:small
systemctl --user start jarvis-noeud
```

Modèles texte et image, sur cinq tâches du noeud vérifiées automatiquement (résumé, extraction JSON, classement,
injection ignorée, aiguille dans un document qui remplit 70 % du contexte), avec chargement, jetons/s, mémoire libre
minimale et températures :

```bash
ollama pull qwen3.5:4b
python3 ~/.local/share/jarvis-noeud/banc_modeles.py gemma3:4b qwen3.5:4b --contexte 4096 8192 \
  --image capture.png --json ~/banc-$(date +%F).json
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
Le [parcours SSH/MCP ARM64 réel](../../docs/redteam/VALIDATION_JETSON.md) est validé sur les fixtures synthétiques,
avec une extension qui préserve le module audio/texte/image installé.
