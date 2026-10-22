#!/usr/bin/env bash
# JarvisAgent — installation du poste de pilotage des agents IA
# Cible : Ubuntu sous WSL2 (fonctionne aussi sur Ubuntu natif).
# Idempotent : tu peux le relancer sans risque, il saute ce qui est déjà fait.
#
# Usage :  ./install.sh              installation complète (studio vidéo compris)
#          ./install.sh --no-mcp     sans brancher Linear aux agents
#          ./install.sh --no-studio  sans le studio vidéo (ffmpeg, Playwright, Chromium)

set -euo pipefail

JARVIS_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINEAR_MCP_URL="https://mcp.linear.app/mcp"
WITH_MCP=1
WITH_STUDIO=1

for arg in "$@"; do
  case "$arg" in
    --no-mcp) WITH_MCP=0 ;;
    --no-studio) WITH_STUDIO=0 ;;
    --studio) WITH_STUDIO=1 ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

# --- Affichage --------------------------------------------------------------
C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
step() { printf '\n%s▶ %s%s\n' "$C_CYAN" "$1" "$C_OFF"; }
ok()   { printf '  %s✓%s %s\n' "$C_GREEN" "$C_OFF" "$1"; }
warn() { printf '  %s!%s %s\n' "$C_YELLOW" "$C_OFF" "$1"; }
fail() { printf '  %s✗%s %s\n' "$C_RED" "$C_OFF" "$1" >&2; exit 1; }
# Sous WSL, le PATH contient aussi les programmes Windows (/mnt/c/...).
# Un « codex » ou « claude » installé côté Windows ne marche pas dans Linux :
# on ne compte donc que les programmes Linux.
has()  { local p; p="$(command -v "$1" 2>/dev/null)" || return 1; [[ "$p" != /mnt/* ]]; }

TODO=()   # actions manuelles à faire à la fin

# --- 0. Vérifications -------------------------------------------------------
step "Vérifications"
[[ "$(uname -s)" == "Linux" ]] || fail "Ce script tourne dans Linux (Ubuntu/WSL). Voir le README, étape 1."
has apt-get || fail "apt-get introuvable : il faut Ubuntu ou Debian."
if [[ "$JARVIS_HOME" == /mnt/* ]]; then
  warn "Le dépôt est sur le disque Windows ($JARVIS_HOME)."
  warn "Clone-le plutôt dans Linux : ~/projets/JarvisAgent (beaucoup plus rapide)."
fi
if grep -qi microsoft /proc/version 2>/dev/null; then ok "WSL détecté"; else ok "Linux natif"; fi

# --- 1. PATH utilisateur ----------------------------------------------------
step "PATH utilisateur"
mkdir -p "$HOME/.local/bin" "$HOME/.npm-global/bin"
BASHRC="$HOME/.bashrc"
MARK="# >>> JarvisAgent >>>"
if ! grep -qF "$MARK" "$BASHRC" 2>/dev/null; then
  cat >>"$BASHRC" <<EOF

$MARK
export PATH="\$HOME/.local/bin:\$HOME/.npm-global/bin:$JARVIS_HOME/bin:\$PATH"
alias wm='workmux'
# <<< JarvisAgent <<<
EOF
  ok "PATH ajouté à ~/.bashrc"
else
  ok "PATH déjà configuré"
fi
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$JARVIS_HOME/bin:$PATH"

# --- 2. Paquets système -----------------------------------------------------
step "Paquets système (git, tmux, gh…)"
# bubblewrap : bac à sable de Codex sous Linux/WSL.
PKGS=(git tmux curl unzip build-essential ca-certificates gh jq bubblewrap)
MISSING=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
if ((${#MISSING[@]})); then
  sudo apt-get update -y
  sudo apt-get install -y "${MISSING[@]}"
  ok "Installé : ${MISSING[*]}"
else
  ok "Tout est déjà là"
fi

# --- 3. Node.js 22 + pnpm ---------------------------------------------------
step "Node.js"
NODE_MAJOR=0
if has node; then NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"; fi
if ((NODE_MAJOR < 20)); then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
  ok "Node $(node --version) installé"
else
  ok "Node $(node --version) déjà présent"
fi
# Paquets npm globaux sans sudo
if [[ "$(npm config get prefix)" != "$HOME/.npm-global" ]]; then
  npm config set prefix "$HOME/.npm-global"
fi
if has pnpm; then ok "pnpm déjà présent"; else npm install -g pnpm >/dev/null && hash -r && ok "pnpm installé"; fi

# --- 4. Agents : Claude Code + Codex ----------------------------------------
step "Claude Code"
if has claude; then
  ok "Claude Code déjà installé ($(claude --version 2>/dev/null | head -1))"
else
  curl -fsSL https://claude.ai/install.sh | bash
  hash -r
  ok "Claude Code installé (version Linux)"
  TODO+=("Lance « claude », choisis le thème sombre puis « Claude account with subscription ».")
fi

step "Codex CLI"
if has codex; then
  ok "Codex déjà installé ($(codex --version 2>/dev/null | head -1))"
else
  npm install -g @openai/codex >/dev/null
  hash -r
  ok "Codex installé (version Linux)"
  TODO+=("Lance « codex » et choisis « Sign in with ChatGPT ».")
fi

# --- 5. workmux -------------------------------------------------------------
step "workmux (tour de contrôle)"
if has workmux; then
  ok "workmux déjà installé"
else
  curl -fsSL https://raw.githubusercontent.com/raine/workmux/main/scripts/install.sh | bash
  has workmux || fail "workmux introuvable après installation. Ouvre un nouveau terminal puis relance ./install.sh"
  ok "workmux installé"
fi

# --- 6. Fichiers de configuration (liens symboliques) -----------------------
step "Configurations"
link() {  # link <source> <cible>
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then
    ok "$dst déjà lié"
    return
  fi
  if [[ -e "$dst" || -L "$dst" ]]; then
    local bak
    bak="$dst.bak.$(date +%Y%m%d-%H%M%S)"
    mv "$dst" "$bak"
    warn "Ancien fichier sauvegardé : $bak"
  fi
  ln -s "$src" "$dst"
  ok "$dst → $src"
}
link "$JARVIS_HOME/config/tmux.conf" "$HOME/.tmux.conf"
link "$JARVIS_HOME/config/workmux/config.yaml" "$HOME/.config/workmux/config.yaml"
chmod +x "$JARVIS_HOME/bin/"* 2>/dev/null || true

# Règles Codex : commits, push de branche et PR sans demande ; fusion et push forcé interdits.
RULES_DST="$HOME/.codex/rules/jarvis.rules"
link "$JARVIS_HOME/config/codex/jarvis.rules" "$RULES_DST"
if has codex; then
  if codex execpolicy check --rules "$RULES_DST" -- git commit -m test >/dev/null 2>&1; then
    ok "Règles Codex valides"
  else
    rm -f "$RULES_DST"
    warn "Codex refuse les règles Jarvis (version de Codex ?) : lien retiré, Codex redemandera pour les commits."
  fi
fi

# --- 7. Hooks de statut des agents ------------------------------------------
step "Hooks de statut workmux (🤖 / 💬 / ✅)"
if [[ ! -d "$HOME/.claude" || ! -d "$HOME/.codex" ]]; then
  # workmux ne détecte un agent qu'après son premier lancement (dossier de config créé)
  warn "Claude Code ou Codex n'a jamais été lancé : les statuts seront activés après la connexion."
  TODO+=("Après t'être connecté à Claude Code et Codex, lance « workmux setup » pour activer les statuts 🤖/💬/✅.")
elif workmux setup; then
  ok "Hooks installés"
else
  warn "« workmux setup » a échoué. Relance-le après t'être connecté à Claude Code et Codex."
  TODO+=("Relance « workmux setup » pour activer les statuts des agents.")
fi

# --- 8. Linear (MCP) --------------------------------------------------------
if ((WITH_MCP)); then
  step "Brancher Linear aux agents"
  if has claude; then
    if claude mcp get linear-server >/dev/null 2>&1; then
      ok "Claude Code : Linear déjà ajouté"
    elif claude mcp add --transport http --scope user linear-server "$LINEAR_MCP_URL" >/dev/null 2>&1; then
      ok "Claude Code : Linear ajouté"
      TODO+=("Dans « claude », tape /mcp → linear-server → Authenticate (choisis l'espace Repriceo).")
    else
      warn "Claude Code : ajout de Linear impossible pour l'instant (connecte-toi d'abord)."
      TODO+=("claude mcp add --transport http --scope user linear-server $LINEAR_MCP_URL")
    fi
  fi
  if has codex; then
    if codex mcp get linear >/dev/null 2>&1; then
      ok "Codex : Linear déjà ajouté"
    elif codex mcp add linear --url "$LINEAR_MCP_URL" >/dev/null 2>&1; then
      ok "Codex : Linear ajouté"
      TODO+=("Lance « codex mcp login linear » et autorise dans le navigateur.")
    else
      warn "Codex : ajout de Linear impossible pour l'instant."
      TODO+=("codex mcp add linear --url $LINEAR_MCP_URL  puis  codex mcp login linear")
    fi
  fi
fi

# --- 9. GitHub --------------------------------------------------------------
step "GitHub CLI"
if gh auth status >/dev/null 2>&1; then
  ok "gh déjà connecté"
else
  TODO+=("Lance « gh auth login » → GitHub.com → HTTPS → Login with a web browser.")
  warn "gh n'est pas encore connecté"
fi
# --- 9 bis. Surveillance des jetons Claude -----------------------------------
step "Surveillance des jetons Claude (barre d'état)"
chmod +x "$JARVIS_HOME/bin/jarvis-statusline"
sl_out="$(PYTHONPATH="$JARVIS_HOME/lib" python3 -m jarvis installer-statusline 2>&1)" && sl_rc=0 || sl_rc=$?
case "$sl_rc" in
  0) ok "Barre d'état Jarvis $sl_out" ;;
  3) warn "$sl_out"
     TODO+=("Pour suivre les jetons Claude, remplace ta barre d'état par $JARVIS_HOME/bin/jarvis-statusline (~/.claude/settings.json → statusLine).") ;;
  *) warn "Barre d'état non installée : $sl_out" ;;
esac

# --- 9 ter. Studio : vidéo de produit, visuels, montage ------------------------
step "Compétences des agents (skills)"
# Claude Code lit ~/.claude/skills, Codex lit ~/.agents/skills : même dossier, deux liens.
for skill in jarvis-studio jarvis-veille jarvis-design; do
  link "$JARVIS_HOME/skills/$skill" "$HOME/.claude/skills/$skill"
  link "$JARVIS_HOME/skills/$skill" "$HOME/.agents/skills/$skill"
done

if ((WITH_STUDIO)); then
  step "Studio (ffmpeg, Playwright, Chromium)"
  STUDIO_PKGS=()
  for p in ffmpeg fonts-inter fonts-noto-color-emoji; do dpkg -s "$p" >/dev/null 2>&1 || STUDIO_PKGS+=("$p"); done
  if ((${#STUDIO_PKGS[@]})); then
    sudo apt-get update -y >/dev/null || true
    for p in "${STUDIO_PKGS[@]}"; do
      sudo apt-get install -y "$p" >/dev/null 2>&1 && ok "$p installé" || warn "$p non installé (le studio fonctionne sans, sauf ffmpeg)"
    done
  else
    ok "ffmpeg et polices déjà là"
  fi
  if NODE_PATH="$(npm root -g 2>/dev/null)" node -e 'require("playwright")' >/dev/null 2>&1; then
    ok "Playwright déjà présent"
  elif npm install -g playwright >/dev/null 2>&1; then
    hash -r
    ok "Playwright installé"
  else
    warn "Playwright non installé : relance ./install.sh quand le réseau est disponible."
  fi
  if compgen -G "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}/chromium-*" >/dev/null; then
    ok "Chromium du studio déjà là"
  elif has playwright; then
    # --with-deps installe aussi les bibliothèques système de Chromium (demande sudo).
    if playwright install --with-deps chromium >/dev/null 2>&1; then
      ok "Chromium du studio prêt"
    else
      warn "Chromium du studio non installé."
      TODO+=("Pour le studio vidéo : playwright install --with-deps chromium")
    fi
  fi
else
  warn "Studio non installé (--no-studio) : les rôles vidéo et marketing ne pourront pas produire de vidéo."
fi

# --- 10. Superagent ---------------------------------------------------------
step "Superagent (chef d'orchestre, cockpit, Telegram)"
if python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
else
  fail "Python 3.11 ou plus est requis pour le superagent."
fi
if [[ -z "$("$JARVIS_HOME/bin/jarvis" projet liste 2>/dev/null | grep '^P[0-9]' || true)" ]]; then
  TODO+=("Enregistre tes projets : jarvis projet ajouter repriceo ~/projets/repriceo --linear \"Repriceo\" --priorite 1")
else
  ok "Projets déjà enregistrés"
fi
if [[ -z "$(PYTHONPATH="$JARVIS_HOME/lib" python3 -m jarvis reglage-lire telegram.chat_id 2>/dev/null)" ]]; then
  TODO+=("Relie ton téléphone : jarvis telegram config")
fi
if PYTHONPATH="$JARVIS_HOME/lib" python3 -m jarvis modele liste 2>/dev/null | grep -q "pas encore essayé"; then
  TODO+=("Une fois connecté à Claude Code et Codex : jarvis modele verifier (essaie chaque modèle avec tes abonnements ; le démon le refait seul chaque semaine).")
fi
if [[ -n "${WSL_DISTRO_NAME:-}" ]] && ! "$JARVIS_HOME/bin/jarvis" autostart etat 2>/dev/null | grep -q actif; then
  TODO+=("Pour que Jarvis reparte seul après un redémarrage de Windows : jarvis autostart installer")
fi

if [[ -z "$(git config --global user.name || true)" ]]; then
  TODO+=("git config --global user.name \"Ton Nom\" && git config --global user.email \"ton@courriel.com\"")
fi

# --- Fin --------------------------------------------------------------------
printf '\n%s━━━ JarvisAgent installé ━━━%s\n' "$C_CYAN" "$C_OFF"
if ((${#TODO[@]})); then
  printf '\n%sÀ faire maintenant (une seule fois) :%s\n' "$C_YELLOW" "$C_OFF"
  i=1
  for t in "${TODO[@]}"; do printf '  %d. %s\n' "$i" "$t"; i=$((i + 1)); done
fi
cat <<EOF

Ensuite :
  1. Ouvre un nouveau terminal (pour charger le PATH)
  2. jarvis doctor     → vérifie que tout est vert
  3. jarvis start      → ouvre le cockpit (et le démon en arrière-plan)
  4. jarvis chef       → lance le chef d'orchestre
  5. http://localhost:7717 → le plan de l'usine dans ton navigateur
EOF
