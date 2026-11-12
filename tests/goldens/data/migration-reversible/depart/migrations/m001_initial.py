"""Schéma initial."""


def monter(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, nom TEXT NOT NULL, email TEXT)")
    conn.commit()


def descendre(conn):
    conn.execute("DROP TABLE IF EXISTS clients")
    conn.commit()
