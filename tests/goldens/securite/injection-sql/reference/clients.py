def chercher_client(conn, nom):
    return conn.execute("SELECT id, nom FROM clients WHERE nom = ?", (nom,)).fetchall()
