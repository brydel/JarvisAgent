# Noeud GPU (Jetson) : une extension de Jarvis

La Jetson **étend** Jarvis d'outils GPU ; elle ne le duplique pas. Elle n'héberge ni plan de contrôle Jarvis, ni Board, ni chef, ni agent,
ni secret de Jarvis, et ne prend aucune initiative. Jarvis (sur le poste principal) reste le seul plan de contrôle :
missions, mandats, budgets, journal et Board. Éteindre, réinstaller ou remplacer la Jetson retire des capacités,
jamais des données.

Pas d'agents de code sur le noeud : Claude Code et Codex calculent dans le cloud, la Jetson n'y apporterait que
ses 8 Go et obligerait à copier dépôts, worktrees et secrets. Le noeud sert au calcul GPU local : transcription
aujourd'hui ; vision, embeddings (calculés ici, stockés par Jarvis) et petit modèle local ensuite.

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
- **Outils MCP** : `audio_transcrire` (dépose un travail, répond tout de suite), `audio_resultat` (attend 15 s au
  plus), `noeud_sante` (lecture seule). Une session MCP stdio est bornée à 30 s : la transcription est asynchrone.
- **Fichiers lourds** : déposés à part (`depot`), vérifiés par taille et empreinte, désignés ensuite par leur
  SHA-256. Effacés après traitement ; ceux qui n'ont pas servi sont purgés au bout d'une heure.
- **Mandat** : `jarvis noeud config` crée un mandat d'un an pour le projet `jarvis-board`, limité aux deux outils de
  transcription et à la destination `mcp:<connexion>`. Le révoquer coupe aussitôt le Board du noeud.
- **Pannes** : noeud éteint, délai dépassé, mandat révoqué → l'audio garde ses métadonnées et le modèle le signale ;
  la mission continue. Aucun rejeu aveugle : chaque appel a un identifiant d'opération stable.

## Installation

Sur la Jetson, une fois, avec sudo (toi) :

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
Le [parcours SSH/MCP ARM64 réel](../../docs/redteam/VALIDATION_JETSON.md) est validé sur les fixtures synthétiques,
avec une extension qui préserve le module audio/texte/image installé.
