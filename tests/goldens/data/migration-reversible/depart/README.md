# Carnet de clients

Les migrations vivent dans `migrations/`, un module par étape (`m001_…`, `m002_…`). Chaque module expose
`monter(conn)` et `descendre(conn)` ; `conn` est une connexion `sqlite3`. Une migration valide ses changements
elle-même (`conn.commit()`).
