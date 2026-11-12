"""Read-only access to the marts schema.

The app never connects as the database owner. It uses the `spotify_app` role created by
`bootstrap.py`, which can only SELECT from `marts`. Each connection also sets read-only
transactions, a statement timeout and the search path, so even a query that slipped past the
SQL guard cannot write or run long.
"""

import os
from decimal import Decimal

import pandas as pd
import psycopg

STATEMENT_TIMEOUT_MS = 5000


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ.get("APP_DB_USER", "spotify_app"),
        password=os.environ["APP_DB_PASSWORD"],
        options=(
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
            "-c search_path=marts"
        ),
        autocommit=True,
        connect_timeout=10,
    )


def run_query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Run one query and return a DataFrame. Numeric columns come back as float."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d.name for d in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    for column in df.columns:
        values = df[column].dropna()
        if len(values) and isinstance(values.iloc[0], Decimal):
            df[column] = df[column].astype(float)
    return df


def table_names() -> list[str]:
    df = run_query(
        "select table_name from information_schema.tables "
        "where table_schema = 'marts' order by table_name"
    )
    return df["table_name"].tolist()
