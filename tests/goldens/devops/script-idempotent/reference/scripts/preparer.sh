#!/bin/bash
# Prépare le dossier de déploiement passé en argument : releases/, partage/config.env et le lien config.env.
# Relançable : une deuxième exécution laisse le dossier dans le même état.
set -euo pipefail

if [[ $# -lt 1 || -z "${1:-}" ]]; then
  echo "usage : preparer.sh <dossier cible>" >&2
  exit 2
fi

cible=$1
config="$cible/partage/config.env"
mkdir -p "$cible/releases" "$cible/partage"
touch "$config"

ajouter() {
  grep -qxF -- "$1" "$config" || printf '%s\n' "$1" >> "$config"
}
ajouter "APP_ENV=production"
ajouter "APP_PORT=8080"

ln -sfn "$config" "$cible/config.env"
echo "prêt"
