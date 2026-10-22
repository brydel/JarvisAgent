"""Administration PostgreSQL de Jarvis Next : base, rôle applicatif, schéma, droits, migration depuis SQLite.

Tout ici s'exécute avec TON rôle (propriétaire, connexion locale par socket). Le moteur, lui, n'utilise qu'un
rôle applicatif (non propriétaire, soumis à la RLS), dont le mot de passe est écrit dans un fichier au format pgpass
(600) : le DSN ne contient aucun secret.

Un rôle applicatif PAR BASE : `jarvis_app` pour la base `jarvis`, `jarvis_app_<base>` pour toute autre (tests,
vérifications). Les rôles sont communs à tout le serveur : préparer une base de test ne doit jamais changer le mot
de passe du rôle de ta vraie base.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROLE_APP = "jarvis_app"
ECRITURE = ("organisations", "reglages_tenant", "executants", "connexions", "missions", "taches", "tentatives",
            "approbations", "artefacts", "board_objets", "board_liens", "board_assets", "board_commentaires")
FONCTIONS = ("jarvis_tenant_executant(TEXT)", "jarvis_tenants()", "jarvis_compte_connexion(TEXT)",
             "jarvis_adhesions(TEXT)")
SCHEMA = Path(__file__).with_name("schema.sql")
# ordre d'import (clés étrangères) : parents d'abord ; les comptes n'existent pas en SQLite
ORDRE_IMPORT = ("organisations", "reglages_tenant", "executants", "connexions", "missions", "taches", "tentatives",
                "approbations", "artefacts", "board_objets", "evenements", "board_liens", "board_assets",
                "board_commentaires")


def dossier_config() -> Path:
    d = Path(os.environ.get("JARVIS_CONFIG_DIR") or Path(os.environ.get("XDG_CONFIG_HOME",
                                                                        Path.home() / ".config")) / "jarvis")
    d.mkdir(parents=True, exist_ok=True)
    return d


def fichier_pgpass() -> Path:
    return dossier_config() / "pgpass"


def role_app(base: str) -> str:
    return ROLE_APP if base == "jarvis" else f"{ROLE_APP}_{base}"


def dsn_app(base: str = "jarvis", hote: str = "127.0.0.1", port: int = 5432) -> str:
    return f"host={hote} port={port} dbname={base} user={role_app(base)} passfile={fichier_pgpass()}"


def dsn_admin(base: str = "jarvis") -> str:
    return f"dbname={base}"  # socket local, authentification « peer » : ton utilisateur Linux


def _ecrire_pgpass(role: str, mot_de_passe: str, port: int) -> None:
    p = fichier_pgpass()
    lignes = [l for l in (p.read_text().splitlines() if p.exists() else []) if f":{role}:" not in l]
    lignes.append(f"127.0.0.1:{port}:*:{role}:{mot_de_passe}")
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lignes) + "\n")
    os.chmod(p, 0o600)


def preparer(base: str = "jarvis", *, port: int = 5432, nouveau_mot_de_passe: bool = False) -> str:
    """Crée (si besoin) la base, son rôle applicatif, le schéma, les politiques et les droits. Idempotent."""
    nom_role = role_app(base)
    with psycopg.connect("dbname=postgres", autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (base,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(base)))
        role = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=%s", (nom_role,)).fetchone()
        if role is not None and (role[0] or role[1]):
            raise RuntimeError(f"le rôle {nom_role} existe avec SUPERUSER ou BYPASSRLS : la RLS ne le protégerait pas")
        if role is None or nouveau_mot_de_passe or not fichier_pgpass().exists():
            mdp = secrets.token_urlsafe(32)
            if role is None:
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
                                     "PASSWORD {}").format(sql.Identifier(nom_role), sql.Literal(mdp)))
            else:  # seul un superutilisateur peut même RETIRER SUPERUSER : on ne touche qu'au mot de passe
                conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(nom_role),
                                                                             sql.Literal(mdp)))
            _ecrire_pgpass(nom_role, mdp, port)
        moi = conn.execute("SELECT current_user AS u, rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()
        if moi[1]:
            raise RuntimeError("ton rôle est superutilisateur : refusé (la RLS ne s'appliquerait pas aux tests)")
    with psycopg.connect(dsn_admin(base), autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        ident = sql.Identifier(nom_role)
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(base)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(base), ident))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident))
        conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(ident))
        conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON {} TO {}").format(
            sql.SQL(", ").join(sql.Identifier(t) for t in ECRITURE), ident))
        conn.execute(sql.SQL("GRANT SELECT, INSERT ON evenements TO {}").format(ident))  # journal : ajout seul
        conn.execute(sql.SQL("GRANT SELECT ON meta TO {}").format(ident))
        conn.execute(sql.SQL("GRANT USAGE ON SEQUENCE evenements_seq_seq TO {}").format(ident))
        for f in FONCTIONS:
            conn.execute(sql.SQL("GRANT EXECUTE ON FUNCTION " + f + " TO {}").format(ident))
    return dsn_app(base, port=port)


def supprimer_base(base: str) -> None:
    """Tests seulement : refuse toute base qui ne finit pas par _test."""
    if not base.endswith("_test"):
        raise RuntimeError("suppression refusée : seule une base *_test peut être supprimée")
    with psycopg.connect("dbname=postgres", autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base)))
        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role_app(base))))


def migrer_depuis_sqlite(chemin: Path, base: str = "jarvis") -> dict:
    """Copie missions.db dans PostgreSQL (propriétaire : hors RLS), puis relit et compare chaque ligne.
    La base SQLite n'est pas modifiée ; refusé si la base PostgreSQL contient déjà des missions."""
    src = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    bilan = {}
    try:
        with psycopg.connect(dsn_admin(base), row_factory=dict_row) as conn:  # une seule transaction
            if conn.execute("SELECT COUNT(*) AS n FROM missions").fetchone()["n"]:
                raise RuntimeError("la base PostgreSQL contient déjà des missions : migration refusée")
            for table in ORDRE_IMPORT:
                lignes = [dict(r) for r in src.execute(f"SELECT * FROM {table}")]
                if not lignes:
                    bilan[table] = 0
                    continue
                cols = list(lignes[0])
                requete = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols)),
                    sql.SQL(", ").join(sql.Placeholder() * len(cols)))
                with conn.cursor() as cur:
                    cur.executemany(requete, [tuple(l[c] for c in cols) for l in lignes])
                cle = "seq" if table == "evenements" else ("tenant_id" if table == "reglages_tenant" else
                                                          "id" if "id" in cols else None)
                if cle:  # relecture et comparaison valeur par valeur
                    relu = {r[cle]: r for r in conn.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))}
                    for l in lignes:
                        r = relu.get(l[cle])
                        if r is None or any(_diff(l[c], r[c]) for c in cols):
                            raise RuntimeError(f"vérification échouée : {table} {l[cle]}")
                bilan[table] = len(lignes)
            conn.execute("SELECT setval('evenements_seq_seq', GREATEST((SELECT COALESCE(MAX(seq), 0) FROM evenements), 1))")
    finally:
        src.close()
    return bilan


def _diff(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is None or b is None or abs(float(a) - float(b)) > 1e-6
    return a != b
