#!/usr/bin/env bash
# Installe PostgreSQL et psycopg (paquets Ubuntu) pour le service de contrôle Jarvis Next, puis crée ton rôle.
# À lancer par TOI (sudo demande ton mot de passe). Idempotent : relançable sans effet de bord.
#
# Ce que ça fait :
#   1. apt : postgresql (serveur, démarré par systemd) et python3-psycopg (pilote, pas de pip) ;
#   2. un rôle PostgreSQL à ton nom d'utilisateur Linux, connexion locale par socket (« peer », sans mot de passe),
#      avec CREATEDB et CREATEROLE pour que `python3 -m controle_pg preparer` crée la base et le rôle applicatif
#      jarvis_app (sans connexion, soumis à la RLS). Ton rôle n'est PAS superutilisateur : la RLS s'applique.
set -euo pipefail

if ! dpkg -s postgresql python3-psycopg >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y postgresql python3-psycopg
fi
sudo systemctl enable --now postgresql >/dev/null 2>&1 || true

moi="$(id -un)"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${moi}'" | grep -q 1; then
  sudo -u postgres createuser --createdb --createrole "$moi"
fi

pg_isready
psql -d postgres -tAc "SELECT 'Connexion OK : ' || current_user || ', superutilisateur = ' || rolsuper FROM pg_roles WHERE rolname = current_user"
python3 -c "import psycopg; print('psycopg', psycopg.__version__)"
echo "PostgreSQL prêt pour Jarvis Next."
