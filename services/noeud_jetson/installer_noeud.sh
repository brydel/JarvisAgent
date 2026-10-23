#!/usr/bin/env bash
# Installe ou met à jour le noeud GPU de Jarvis sur une Jetson (JetPack 6, PyTorch CUDA déjà présent).
# Relançable sans effet de bord. À exécuter SUR la Jetson, sans sudo, depuis une copie de ce dossier :
#
#   bash installer_noeud.sh [--modele small] [--cle-jarvis jarvis_noeud.pub]
#
# Prérequis (une fois, par toi) : sudo apt install -y ffmpeg python3.10-venv && sudo loginctl enable-linger "$USER"
# --cle-jarvis ajoute la clé publique de Jarvis à ~/.ssh/authorized_keys avec une commande forcée : cette clé
# ne peut lancer que jarvis_noeud.py (MCP, dépôt, état), jamais un shell ni une redirection de port.
set -euo pipefail

MODELE="small"
LLM="gemma3:4b"
CLE=""
while (($#)); do
  case "$1" in
    --modele) MODELE="$2"; shift 2 ;;
    --llm) LLM="$2"; shift 2 ;;
    --cle-jarvis) CLE="$2"; shift 2 ;;
    *) echo "Option inconnue : $1" >&2; exit 2 ;;
  esac
done
[[ "$MODELE" =~ ^[a-z0-9.-]{1,40}$ ]] || { echo "Nom de modèle invalide." >&2; exit 2; }
[[ "$LLM" =~ ^[a-z0-9._:/-]{1,80}$ ]] || { echo "Nom de modèle local invalide." >&2; exit 2; }

WHISPER_VERSION="20240930"
DIR="$HOME/.local/share/jarvis-noeud"
CONF="$HOME/.config/jarvis-noeud"
UNITE="$HOME/.config/systemd/user/jarvis-noeud.service"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

manque=()
command -v ffmpeg >/dev/null || manque+=(ffmpeg)
python3 -c "import ensurepip" 2>/dev/null || manque+=(python3.10-venv)
if ((${#manque[@]})); then
  echo "Il manque : ${manque[*]}. Lance d'abord : sudo apt install -y ${manque[*]}" >&2
  exit 1
fi
python3 -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" \
  || { echo "PyTorch avec CUDA introuvable dans le Python système (JetPack)." >&2; exit 1; }

mkdir -p "$DIR" "$CONF" "$(dirname "$UNITE")" "$HOME/.cache/jarvis-noeud/entree"
chmod 700 "$CONF" "$HOME/.cache/jarvis-noeud" "$HOME/.cache/jarvis-noeud/entree"
# --system-site-packages : réutilise le PyTorch CUDA de NVIDIA au lieu d'en télécharger un sans GPU
[[ -x "$DIR/venv/bin/python" ]] || python3 -m venv --system-site-packages "$DIR/venv"
"$DIR/venv/bin/pip" install -q --disable-pip-version-check "openai-whisper==$WHISPER_VERSION"
install -m 644 "$SOURCE/service.py" "$DIR/service.py"
install -m 644 "$SOURCE/jarvis_noeud.py" "$DIR/jarvis_noeud.py"
install -m 644 "$SOURCE/banc.py" "$DIR/banc.py"

# Jeton du service local créé une seule fois, lisible par toi seul ; jamais affiché
if ! grep -q '^JARVIS_NOEUD_TOKEN=' "$CONF/env" 2>/dev/null; then
  ( umask 077
    printf 'JARVIS_NOEUD_TOKEN=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> "$CONF/env" )
fi
reglage() {  # reglage CLE VALEUR : remplace ou ajoute une ligne du fichier env
  if grep -q "^$1=" "$CONF/env"; then sed -i "s|^$1=.*|$1=$2|" "$CONF/env"; else printf '%s=%s\n' "$1" "$2" >> "$CONF/env"; fi
}
reglage JARVIS_NOEUD_MODELE "$MODELE"
reglage JARVIS_NOEUD_LLM "$LLM"
reglage JARVIS_NOEUD_ENTREE "$HOME/.cache/jarvis-noeud/entree"
chmod 600 "$CONF/env"

echo "Téléchargement du modèle audio « $MODELE » si absent…"
"$DIR/venv/bin/python" -c "import whisper; whisper.load_model('$MODELE', device='cpu')" >/dev/null
if command -v ollama >/dev/null; then
  echo "Téléchargement du modèle local « $LLM » si absent (Ollama)…"
  ollama pull "$LLM" >/dev/null && echo "✓ modèle local $LLM prêt"
else
  echo "⚠ Ollama absent : texte et image locaux indisponibles. Installe-le (sudo) : curl -fsSL https://ollama.com/install.sh | sh" >&2
fi

cat > "$UNITE" <<EOF
[Unit]
Description=Jarvis : noeud GPU (transcription Whisper, modèle local texte et image)
After=network-online.target ollama.service

[Service]
EnvironmentFile=$CONF/env
ExecStart=$DIR/venv/bin/python $DIR/service.py
Restart=on-failure
RestartSec=10
Nice=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable jarvis-noeud.service >/dev/null
systemctl --user restart jarvis-noeud.service

if [[ -n "$CLE" ]]; then
  read -r type cle _ < "$CLE"
  [[ "$type" == ssh-ed25519 && "$cle" =~ ^[A-Za-z0-9+/=]+$ ]] || { echo "Clé publique ed25519 attendue." >&2; exit 2; }
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  touch "$HOME/.ssh/authorized_keys" && chmod 600 "$HOME/.ssh/authorized_keys"
  cp "$HOME/.ssh/authorized_keys" "$HOME/.ssh/authorized_keys.avant-jarvis-noeud"
  ligne="command=\"/usr/bin/python3 $DIR/jarvis_noeud.py ssh\",restrict $type $cle jarvis-noeud"
  grep -v " $cle " "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.tmp" || true
  printf '%s\n' "$ligne" >> "$HOME/.ssh/authorized_keys.tmp"
  mv "$HOME/.ssh/authorized_keys.tmp" "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
  echo "✓ Clé de Jarvis autorisée (commande forcée, sans shell). Copie de l'ancien fichier : authorized_keys.avant-jarvis-noeud"
fi

echo "✓ Noeud GPU jarvis-noeud (audio $MODELE à la demande, texte/image $LLM) démarré, sur 127.0.0.1 seulement."
echo "  Journal : journalctl --user -u jarvis-noeud -f"
