import pytest

from spotify_app import sqlguard

TABLES = {"fct_plays", "dim_tracks", "dim_artists", "mart_daily_listening"}


def ok(sql: str) -> str:
    return sqlguard.check(sql, TABLES)


def rejected(sql: str) -> str:
    with pytest.raises(sqlguard.UnsafeQuery) as excinfo:
        sqlguard.check(sql, TABLES)
    return str(excinfo.value)


def test_plain_select_passes_and_is_regenerated():
    sql = ok("select play_date, count(*) from fct_plays group by 1 order by 1")
    assert sql.lower().startswith("select")


def test_cte_union_and_schema_prefix_pass():
    ok("with t as (select track_id from fct_plays) select count(*) from t")
    ok("select 1 from fct_plays union all select 2 from marts.fct_plays")
    ok("select generate_series(1, 3)")


def test_like_pattern_with_percent_passes():
    ok("select track_name from dim_tracks where track_name ilike '%love%'")


@pytest.mark.parametrize(
    "sql",
    [
        "drop table fct_plays",
        "delete from fct_plays",
        "update fct_plays set duration_ms = 0",
        "insert into fct_plays select * from fct_plays",
        "create table x as select 1",
        "select * into newtable from fct_plays",
        "select * from fct_plays for update",
        "set role postgres",
        "copy fct_plays to '/tmp/x'",
        "alter table fct_plays add column x int",
    ],
)
def test_writes_and_session_commands_are_rejected(sql):
    rejected(sql)


def test_multiple_statements_are_rejected():
    assert "exactly one" in rejected("select 1; select 2")
    rejected("select 1; drop table fct_plays")


def test_catalog_and_other_schemas_are_rejected():
    rejected("select * from pg_catalog.pg_tables")
    rejected("select * from information_schema.tables")
    rejected("select * from raw.recently_played")
    rejected("select * from pg_tables")
    rejected("select * from public.something")


def test_unknown_table_lists_the_available_ones():
    message = rejected("select * from users")
    assert "fct_plays" in message


@pytest.mark.parametrize(
    "sql",
    [
        "select pg_sleep(10)",
        "select pg_read_file('/etc/passwd')",
        "select set_config('role', 'postgres', false)",
        "select current_setting('password_encryption')",
        "select lo_import('/etc/passwd')",
    ],
)
def test_dangerous_functions_are_rejected(sql):
    rejected(sql)


def test_empty_garbage_and_oversized_queries_are_rejected():
    rejected("")
    rejected("   ")
    rejected("this is not sql at all")
    rejected("select " + "1," * 3000 + "1")
