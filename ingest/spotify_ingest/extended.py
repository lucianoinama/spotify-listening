"""Load Spotify's "Extended streaming history" export into raw.extended_history.

    python -m spotify_ingest.extended /data/extended

The folder holds the JSON files from the export. Only Streaming_History_Audio_*.json is read,
and only its music tracks: video files, podcast episodes and audiobooks are ignored. Safe to run
again: a row already loaded is skipped.

Rows are stored as the export has them, with two exceptions:
  - ip_addr is dropped. It is not used anywhere and is the most sensitive field in the file.
  - rows that are identical apart from ip_addr count once. They share a row_hash.
Rows that share a timestamp and a track but differ in ms_played are all kept: raw does not
decide which one is right, staging does.
"""

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from . import db

# Only the audio files: video plays are ignored. Within them, only music tracks are kept;
# podcast episodes and audiobooks have no spotify_track_uri.
FILE_PATTERN = re.compile(r"^Streaming_History_(Audio)_[0-9_]+\.json$")
TRACK_URI_PREFIX = "spotify:track:"
DROPPED_FIELDS = ("ip_addr",)
BATCH_SIZE = 1000


class ExportError(ValueError):
    """The file is not what the export looks like."""


def normalize(row: dict, kind: str, source_file: str) -> tuple:
    """(row_hash, ts, kind, track_uri, ms_played, payload, source_file) for one export row."""
    payload = {k: v for k, v in row.items() if k not in DROPPED_FIELDS}
    try:
        ts = datetime.fromisoformat(payload["ts"].replace("Z", "+00:00"))
        ms_played = int(payload["ms_played"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ExportError(f"row without a valid ts or ms_played in {source_file}") from exc
    canonical = json.dumps({"kind": kind, **payload}, sort_keys=True, ensure_ascii=False)
    row_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (
        row_hash,
        ts,
        kind,
        payload.get("spotify_track_uri"),
        ms_played,
        Jsonb(payload),
        source_file,
    )


def read_export(folder: Path, stats: dict | None = None):
    """Yield normalized music rows from every audio file in the folder, oldest file first.

    Rows that are not music tracks (podcast episodes, audiobooks) are counted in
    stats["not_music"] and not yielded.
    """
    files = sorted(p for p in folder.iterdir() if FILE_PATTERN.match(p.name))
    if not files:
        raise ExportError(f"no Streaming_History_Audio_*.json files in {folder}")
    for path in files:
        kind = FILE_PATTERN.match(path.name).group(1).lower()
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ExportError(f"{path.name} is not a list of plays")
        for row in rows:
            if not str(row.get("spotify_track_uri") or "").startswith(TRACK_URI_PREFIX):
                if stats is not None:
                    stats["not_music"] = stats.get("not_music", 0) + 1
                continue
            yield normalize(row, kind, path.name)


def load(folder: Path) -> dict:
    """Load the export. Returns counts: rows read, rows inserted, rows skipped."""
    read = 0
    stats: dict = {}
    with db.connect() as conn:
        db.ensure_schema(conn)
        before = conn.execute("select count(*) from raw.extended_history").fetchone()[0]
        batch = []
        with conn.cursor() as cur:
            for row in read_export(folder, stats):
                batch.append(row)
                read += 1
                if len(batch) >= BATCH_SIZE:
                    _insert(cur, batch)
                    batch = []
            if batch:
                _insert(cur, batch)
        after = conn.execute("select count(*) from raw.extended_history").fetchone()[0]
    return {
        "read": read,
        "inserted": after - before,
        "skipped": read - (after - before),
        "not_music": stats.get("not_music", 0),
    }


def _insert(cur, batch: list[tuple]) -> None:
    cur.executemany(
        """
        insert into raw.extended_history
            (row_hash, ts, kind, track_uri, ms_played, payload, source_file)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (row_hash) do nothing
        """,
        batch,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m spotify_ingest.extended <folder with the JSON files>")
        return 2
    folder = Path(argv[1])
    if not folder.is_dir():
        print(f"{folder} is not a folder")
        return 2
    try:
        counts = load(folder)
    except ExportError as exc:
        print(f"cannot load: {exc}")
        return 1
    print(
        f"rows read={counts['read']} inserted={counts['inserted']} "
        f"skipped (already loaded or duplicate)={counts['skipped']} "
        f"ignored (podcasts, audiobooks)={counts['not_music']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
