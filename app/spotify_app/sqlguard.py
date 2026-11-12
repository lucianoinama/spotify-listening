"""Checks the SQL the chat model writes before it reaches the database.

This is the first of two layers. The second is the database itself: the `spotify_app` role
has SELECT on `marts` only, in read-only transactions with a statement timeout. The guard
exists to give the model a clear error and to keep catalog tables (pg_*, information_schema)
out of reach, which the role alone does not prevent.

It parses the query with sqlglot and returns the SQL regenerated from the parse tree, so what
is checked is exactly what runs.
"""

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError

SCHEMA = "marts"
MAX_QUERY_CHARS = 4000

_FORBIDDEN_NAMES = [
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "Command", "Set",
    "Copy", "TruncateTable", "Into", "Lock", "Grant", "Revoke", "Use", "Transaction",
    "Commit", "Rollback", "Pragma", "Analyze", "Describe", "Show",
]  # fmt: skip
FORBIDDEN_NODES = tuple(
    node for name in _FORBIDDEN_NAMES if (node := getattr(exp, name, None)) is not None
)
_SET_OPERATION = getattr(exp, "SetOperation", exp.Union)
ALLOWED_ROOTS = (exp.Select, exp.Union, _SET_OPERATION)

FORBIDDEN_FUNCTIONS = {"dblink", "set_config", "current_setting", "version"}
FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink_")


class UnsafeQuery(ValueError):
    """The query is not a plain read of the marts tables."""


def check(sql: str, allowed_tables: set[str]) -> str:
    """Return the validated query as SQL text, or raise UnsafeQuery with the reason."""
    if not sql or not sql.strip():
        raise UnsafeQuery("The query is empty.")
    if len(sql) > MAX_QUERY_CHARS:
        raise UnsafeQuery(f"The query is longer than {MAX_QUERY_CHARS} characters.")

    try:
        statements = [s for s in parse(sql, read="postgres") if s is not None]
    except SqlglotError as exc:
        raise UnsafeQuery(f"The query does not parse as PostgreSQL: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeQuery("Send exactly one SELECT statement.")

    tree = statements[0]
    if not isinstance(tree, ALLOWED_ROOTS):
        raise UnsafeQuery("Only SELECT queries are allowed.")
    if tree.find(*FORBIDDEN_NODES):
        raise UnsafeQuery("Only a plain SELECT is allowed: no writes, locks or session commands.")

    for function in tree.find_all(exp.Func):
        name = (function.name or function.sql_name()).lower()
        if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
            raise UnsafeQuery(f"The function {name} is not allowed.")

    allowed = {t.lower() for t in allowed_tables}
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:  # a table function such as generate_series
            continue
        if table.catalog or (table.db and table.db.lower() != SCHEMA):
            raise UnsafeQuery(f"Only the {SCHEMA} schema can be queried.")
        if table.db and name not in allowed:
            raise UnsafeQuery(f"{SCHEMA}.{name} does not exist.")
        if not table.db and name not in cte_names and name not in allowed:
            raise UnsafeQuery(
                f"The table {name} does not exist. Available: {', '.join(sorted(allowed))}."
            )

    return tree.sql(dialect="postgres")
