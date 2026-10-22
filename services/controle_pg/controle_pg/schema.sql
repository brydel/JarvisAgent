-- Jarvis Next — schéma PostgreSQL du moteur de missions, version 1 (mêmes tables et colonnes que lib/jarvis/missions.py).
-- Exécuté par le rôle PROPRIÉTAIRE (administration). Le moteur se connecte avec jarvis_app, qui n'est pas
-- propriétaire : la RLS s'applique donc à chacune de ses requêtes. Le contexte de tenant est
-- current_setting('jarvis.tenant_id') ; sans contexte, aucune ligne n'est visible ni insérable.

CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS organisations (
    id TEXT PRIMARY KEY, nom TEXT NOT NULL, cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS reglages_tenant (
    tenant_id TEXT PRIMARY KEY REFERENCES organisations(id),
    niveaux_auto TEXT NOT NULL, budget_inference_centimes INTEGER NOT NULL DEFAULT 0,
    consomme_centimes INTEGER NOT NULL DEFAULT 0, arret_urgence INTEGER NOT NULL DEFAULT 0,
    board_auto_analyse INTEGER NOT NULL DEFAULT 1);
ALTER TABLE reglages_tenant ADD COLUMN IF NOT EXISTS board_actions_auto INTEGER NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS executants (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES organisations(id), nom TEXT NOT NULL,
    secret_empreinte TEXT NOT NULL, capacites TEXT NOT NULL, fournisseurs TEXT NOT NULL,
    profil TEXT NOT NULL, version TEXT NOT NULL DEFAULT '', systeme TEXT NOT NULL DEFAULT '',
    revoque INTEGER NOT NULL DEFAULT 0, dernier_signe DOUBLE PRECISION, cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS connexions (
    tenant_id TEXT NOT NULL REFERENCES organisations(id), fournisseur TEXT NOT NULL,
    mode_auth TEXT NOT NULL, payant INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
    indisponible_jusqua DOUBLE PRECISION NOT NULL DEFAULT 0, raison TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_id, fournisseur));
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES organisations(id), objectif TEXT NOT NULL,
    source TEXT NOT NULL, demandeur TEXT NOT NULL, statut TEXT NOT NULL, correlation_id TEXT NOT NULL,
    cle_idempotence TEXT, cree DOUBLE PRECISION NOT NULL, maj DOUBLE PRECISION NOT NULL,
    UNIQUE (tenant_id, cle_idempotence));
CREATE TABLE IF NOT EXISTS taches (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mission_id TEXT NOT NULL REFERENCES missions(id),
    parent_id TEXT REFERENCES taches(id), profondeur INTEGER NOT NULL DEFAULT 0,
    type TEXT NOT NULL, niveau TEXT NOT NULL, capacites TEXT NOT NULL, fournisseur TEXT NOT NULL,
    travail TEXT NOT NULL, statut TEXT NOT NULL, essais INTEGER NOT NULL DEFAULT 0,
    essais_max INTEGER NOT NULL, delai_s INTEGER NOT NULL, echeance DOUBLE PRECISION,
    bail_executant TEXT, bail_jeton INTEGER NOT NULL DEFAULT 0, bail_expire DOUBLE PRECISION,
    tentative_id TEXT, fournisseur_choisi TEXT, prochaine_tentative DOUBLE PRECISION, raison TEXT NOT NULL DEFAULT '',
    cree DOUBLE PRECISION NOT NULL, maj DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS taches_file ON taches (tenant_id, statut, cree);
CREATE TABLE IF NOT EXISTS tentatives (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, tache_id TEXT NOT NULL REFERENCES taches(id),
    executant_id TEXT NOT NULL, bail_jeton INTEGER NOT NULL, fournisseur TEXT NOT NULL,
    cle_idempotence TEXT NOT NULL UNIQUE, debut DOUBLE PRECISION NOT NULL, fin DOUBLE PRECISION, issue TEXT,
    erreur TEXT);
CREATE TABLE IF NOT EXISTS approbations (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, tache_id TEXT NOT NULL REFERENCES taches(id),
    empreinte TEXT NOT NULL, demandeur TEXT NOT NULL, statut TEXT NOT NULL,
    decide_par TEXT, decide DOUBLE PRECISION, cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS artefacts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, mission_id TEXT NOT NULL, tache_id TEXT NOT NULL,
    tentative_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL, contenu TEXT NOT NULL, empreinte TEXT NOT NULL,
    fournisseur TEXT NOT NULL, factice INTEGER NOT NULL, revue TEXT NOT NULL DEFAULT 'en_cours',
    cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS board_objets (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, espace TEXT NOT NULL, type TEXT NOT NULL,
    contenu TEXT NOT NULL, x DOUBLE PRECISION NOT NULL DEFAULT 0, y DOUBLE PRECISION NOT NULL DEFAULT 0,
    mission_id TEXT, auteur TEXT NOT NULL, cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS evenements (
    seq BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, mission_id TEXT, tache_id TEXT,
    type TEXT NOT NULL, donnees TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS evenements_tenant ON evenements (tenant_id, seq);

-- Comptes : identités globales (une personne peut appartenir à plusieurs organisations).
CREATE TABLE IF NOT EXISTS comptes (
    id TEXT PRIMARY KEY, courriel TEXT NOT NULL UNIQUE, nom TEXT NOT NULL, mdp_empreinte TEXT NOT NULL,
    desactive INTEGER NOT NULL DEFAULT 0, cree DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS adhesions (
    compte_id TEXT NOT NULL REFERENCES comptes(id), tenant_id TEXT NOT NULL REFERENCES organisations(id),
    role TEXT NOT NULL CHECK (role IN ('proprietaire', 'membre', 'lecteur')), cree DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (compte_id, tenant_id));

-- Version 2 : Board V2 (géométrie, priorité, relations, fichiers, commentaires). Ajouts seulement.
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS largeur DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS hauteur DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS z INTEGER NOT NULL DEFAULT 0;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS priorite TEXT NOT NULL DEFAULT '';
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS meta TEXT NOT NULL DEFAULT '{}';
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS asset_id TEXT;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS parent_id TEXT;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS verrouille INTEGER NOT NULL DEFAULT 0;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS supprime INTEGER NOT NULL DEFAULT 0;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE board_objets ADD COLUMN IF NOT EXISTS maj DOUBLE PRECISION NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS board_liens (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, espace TEXT NOT NULL, source_id TEXT NOT NULL,
    cible_id TEXT NOT NULL, libelle TEXT NOT NULL DEFAULT '', style TEXT NOT NULL DEFAULT 'defaut',
    supprime INTEGER NOT NULL DEFAULT 0, cree DOUBLE PRECISION NOT NULL, maj DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS board_assets (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL, taille BIGINT NOT NULL,
    nom TEXT NOT NULL, fichier TEXT NOT NULL, meta TEXT NOT NULL DEFAULT '{}', vignette_id TEXT,
    cree DOUBLE PRECISION NOT NULL, UNIQUE (tenant_id, sha256));
CREATE TABLE IF NOT EXISTS board_commentaires (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, objet_id TEXT NOT NULL, auteur TEXT NOT NULL, texte TEXT NOT NULL,
    cree DOUBLE PRECISION NOT NULL);

ALTER TABLE board_liens ADD COLUMN IF NOT EXISTS auteur TEXT NOT NULL DEFAULT 'humain';

INSERT INTO meta VALUES ('schema_version', '3') ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur;

-- --- RLS : une politique par table, sur le tenant du contexte ---------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['reglages_tenant', 'executants', 'connexions', 'missions', 'taches', 'tentatives',
                           'approbations', 'artefacts', 'board_objets', 'evenements', 'adhesions',
                           'board_liens', 'board_assets', 'board_commentaires'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS par_tenant ON %I', t);
    EXECUTE format('CREATE POLICY par_tenant ON %I USING (tenant_id = current_setting(''jarvis.tenant_id'', true)) '
                   'WITH CHECK (tenant_id = current_setting(''jarvis.tenant_id'', true))', t);
  END LOOP;
END $$;
ALTER TABLE organisations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS par_tenant ON organisations;
CREATE POLICY par_tenant ON organisations USING (id = current_setting('jarvis.tenant_id', true))
  WITH CHECK (id = current_setting('jarvis.tenant_id', true));
ALTER TABLE comptes ENABLE ROW LEVEL SECURITY;  -- aucune politique pour jarvis_app : lecture par fonctions seulement

-- --- Fonctions SECURITY DEFINER : ce qui doit traverser les tenants, et seulement cela --------------------------
-- Le tenant d'un exécutant (pour poser le contexte AVANT de vérifier son secret, sous RLS).
CREATE OR REPLACE FUNCTION jarvis_tenant_executant(p_id TEXT) RETURNS TEXT
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT tenant_id FROM executants WHERE id = p_id $$;
-- La liste des tenants (balayage du démon, un tenant à la fois).
CREATE OR REPLACE FUNCTION jarvis_tenants() RETURNS SETOF TEXT
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT id FROM organisations ORDER BY id $$;
-- Connexion d'un compte : empreinte du mot de passe (vérifiée côté application, jamais le mot de passe).
CREATE OR REPLACE FUNCTION jarvis_compte_connexion(p_courriel TEXT)
  RETURNS TABLE (id TEXT, nom TEXT, mdp_empreinte TEXT, desactive INTEGER)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT id, nom, mdp_empreinte, desactive FROM comptes WHERE courriel = lower(p_courriel) $$;
-- Organisations d'un compte (après une connexion réussie).
CREATE OR REPLACE FUNCTION jarvis_adhesions(p_compte TEXT)
  RETURNS TABLE (tenant_id TEXT, role TEXT, nom TEXT)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
  AS $$ SELECT a.tenant_id, a.role, o.nom FROM adhesions a JOIN organisations o ON o.id = a.tenant_id
        WHERE a.compte_id = p_compte ORDER BY o.nom $$;
REVOKE ALL ON FUNCTION jarvis_tenant_executant(TEXT), jarvis_tenants(), jarvis_compte_connexion(TEXT),
  jarvis_adhesions(TEXT) FROM PUBLIC;
