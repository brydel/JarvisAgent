#!/bin/bash
# Prépare le dossier de déploiement passé en argument : releases/, partage/config.env et le lien config.env.
cible=$1
mkdir $cible/releases
mkdir $cible/partage
echo "APP_ENV=production" >> $cible/partage/config.env
echo "APP_PORT=8080" >> $cible/partage/config.env
ln -s $cible/partage/config.env $cible/config.env
echo "prêt"
