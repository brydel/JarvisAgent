"""Backend PostgreSQL du moteur de missions (lib/jarvis/missions.py).

Le moteur écrit son SQL avec des « ? » et lit les colonnes par nom : ce module traduit les marqueurs, renvoie des
lignes sous forme de dictionnaires, et pose le contexte de tenant (`jarvis.tenant_id`) que les politiques RLS
utilisent. La connexion se fait avec le rôle jarvis_app, qui n'est pas propriétaire des tables : la RLS lui est
toujours imposée. Le DSN vient de JARVIS_MISSIONS_PG (voir `python3 -m controle_pg dsn`).
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

TABLES = ("board_commentaires", "board_assets", "board_liens", "evenements", "board_objets", "artefacts", "approbations", "tentatives", "taches", "missions",
          "connexions", "executants", "reglages_tenant", "adhesions", "comptes", "organisations")


class _Connexion:
    """Interface minimale attendue par le moteur : execute(sql, params) → curseur ; close()."""

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("?", "%s"), tuple(params))

    def close(self) -> None:
        self._conn.close()


class BackendPostgres:
    nom = "postgres"
    verrou_file = " FOR UPDATE SKIP LOCKED"  # deux réclamations concurrentes ne voient pas la même tâche

    def __init__(self, dsn: str, *, dsn_admin: str | None = None):
        self.dsn, self.dsn_admin = dsn, dsn_admin

    def connecter(self, tenant_id: str | None):
        try:
            conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row, connect_timeout=10)
        except psycopg.OperationalError as exc:
            from jarvis.missions import MissionError  # noqa: PLC0415 — le moteur est déjà chargé quand il appelle ceci
            detail = str(exc).strip().splitlines()[-1][:200]
            raise MissionError("base", "connexion à PostgreSQL impossible (" + detail + "). Vérifie que le serveur "
                               "tourne (pg_isready) ; si le mot de passe a changé : cd services/controle_pg && "
                               "python3 -m controle_pg preparer --nouveau-mot-de-passe") from None
        return _Connexion(conn)

    def debut(self, c) -> None:
        c.execute("BEGIN")

    def definir_tenant(self, c, tenant_id: str) -> None:
        # niveau session (false) : vaut pour la transaction en cours et pour une connexion de lecture sans transaction
        c.execute("SELECT set_config('jarvis.tenant_id', ?, false)", (tenant_id,))

    def tenant_de_executant(self, c, executant_id: str) -> str | None:
        r = c.execute("SELECT jarvis_tenant_executant(?) AS t", (executant_id,)).fetchone()
        return r["t"] if r else None

    def tenants(self) -> list[str]:
        c = self.connecter(None)
        try:
            return [r["t"] for r in c.execute("SELECT jarvis_tenants() AS t")]
        finally:
            c.close()

    def existe(self) -> bool:
        return True

    def reinitialiser(self) -> None:
        """Tests seulement : vide toutes les tables (rôle propriétaire requis, jamais jarvis_app)."""
        if not self.dsn_admin:
            raise RuntimeError("réinitialisation refusée : pas de connexion d'administration (tests seulement)")
        with psycopg.connect(self.dsn_admin, autocommit=True) as conn:
            conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
