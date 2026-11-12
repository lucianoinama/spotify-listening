"""One-shot setup: create the read-only database role the app uses.

    python -m spotify_app.bootstrap

Runs as the database owner (the `app-init` service in docker-compose), safe to repeat.
`alter default privileges` matters: dbt recreates the marts tables on every build, and
without it each rebuild would drop the role's access to the new tables.
"""

import os
import sys

import psycopg
from psycopg import sql


def main() -> int:
    app_user = os.environ.get("APP_DB_USER", "spotify_app")
    app_password = os.environ.get("APP_DB_PASSWORD")
    if not app_password:
        print("APP_DB_PASSWORD is not set: add it to .env (any long random string)")
        return 1

    owner = os.environ["POSTGRES_USER"]
    database = os.environ["POSTGRES_DB"]
    role = sql.Identifier(app_user)

    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=database,
        user=owner,
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as conn:
        exists = conn.execute("select 1 from pg_roles where rolname = %s", (app_user,)).fetchone()
        verb = sql.SQL("alter" if exists else "create")
        conn.execute(
            sql.SQL("{} role {} login password {}").format(
                verb, role, sql.Literal(app_password)
            )
        )
        statements = [
            sql.SQL("alter role {} set default_transaction_read_only = on").format(role),
            sql.SQL("create schema if not exists marts"),
            sql.SQL("grant connect on database {} to {}").format(sql.Identifier(database), role),
            sql.SQL("grant usage on schema marts to {}").format(role),
            sql.SQL("grant select on all tables in schema marts to {}").format(role),
            sql.SQL(
                "alter default privileges for role {} in schema marts grant select on tables to {}"
            ).format(sql.Identifier(owner), role),
        ]
        for statement in statements:
            conn.execute(statement)

    print(f"role {app_user} ready: read-only on schema marts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
