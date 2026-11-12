"""Rebuild the dbt models whenever an ingestion run brings new data.

    python build_loop.py

Every POLL_SECONDS it asks raw.ingest_runs for the latest run that stored something new
(plays, artists or Last.fm tags). If that run is newer than the last one already built, it
runs `dbt build`. It also builds once at start, so a restart always leaves the marts current.

A failed build is retried after RETRY_SECONDS. Postgres not being ready yet is not an error:
the loop just waits.
"""

import logging
import os
import subprocess
import sys
import time

import psycopg2

log = logging.getLogger("dbt_loop")

POLL_SECONDS = int(os.environ.get("DBT_POLL_SECONDS", "60"))
RETRY_SECONDS = int(os.environ.get("DBT_RETRY_SECONDS", "300"))

LATEST_RUN_WITH_NEW_DATA = """
    select coalesce(max(run_id), 0)
    from raw.ingest_runs
    where status = 'ok'
      and (coalesce(plays_inserted, 0) > 0
           or coalesce(artists_fetched, 0) > 0
           or coalesce(tags_fetched, 0) > 0)
"""


def latest_run_with_new_data() -> int:
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute(LATEST_RUN_WITH_NEW_DATA)
            return cur.fetchone()[0]
    finally:
        conn.close()


def build() -> bool:
    log.info("dbt build started")
    started = time.monotonic()
    result = subprocess.run(["dbt", "build"], cwd="/dbt", capture_output=True, text=True)
    elapsed = time.monotonic() - started
    if result.returncode == 0:
        summary = result.stdout.strip().splitlines()[-1:] or [""]
        log.info("dbt build ok in %.0fs: %s", elapsed, summary[0].strip())
        return True
    log.error("dbt build failed in %.0fs\n%s", elapsed, result.stdout[-3000:])
    return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    built_run = None  # None forces a build at start
    while True:
        try:
            latest = latest_run_with_new_data()
        except psycopg2.Error as exc:
            # Fresh database without raw tables yet, or Postgres still starting.
            log.warning("cannot read raw.ingest_runs yet: %s", str(exc).strip().splitlines()[0])
            time.sleep(POLL_SECONDS)
            continue

        if built_run is None or latest > built_run:
            if build():
                # The id read before the build: a run that lands mid-build triggers another one.
                built_run = latest
            else:
                time.sleep(RETRY_SECONDS)
                continue
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
