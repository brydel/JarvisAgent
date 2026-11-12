"""Colonne clients.email_normalise (email sans espaces de bord, en minuscules) et son index."""
import sqlite3

INDEX = "ix_clients_email_normalise"


def _colonnes(conn):
    return [ligne[1] for ligne in conn.execute("PRAGMA table_info(clients)")]


def monter(conn):
    if "email_normalise" not in _colonnes(conn):
        conn.execute("ALTER TABLE clients ADD COLUMN email_normalise TEXT")
    conn.execute("UPDATE clients SET email_normalise = lower(trim(email))")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON clients(email_normalise)")
    conn.commit()


def descendre(conn):
    conn.execute(f"DROP INDEX IF EXISTS {INDEX}")
    if "email_normalise" in _colonnes(conn):
        if sqlite3.sqlite_version_info >= (3, 35):
            conn.execute("ALTER TABLE clients DROP COLUMN email_normalise")
        else:  # SQLite ancien : reconstruire la table sans la colonne
            conn.execute("ALTER TABLE clients RENAME TO clients_ancienne")
            conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, nom TEXT NOT NULL, email TEXT)")
            conn.execute("INSERT INTO clients (id, nom, email) SELECT id, nom, email FROM clients_ancienne")
            conn.execute("DROP TABLE clients_ancienne")
    conn.commit()
