import json

import pytest

from spotify_ingest import extended

ROW = {
    "ts": "2026-10-31T21:14:44Z",
    "platform": "android",
    "ms_played": 237028,
    "conn_country": "AR",
    "ip_addr": "203.0.113.7",
    "master_metadata_track_name": "Song",
    "master_metadata_album_artist_name": "Artist",
    "master_metadata_album_album_name": "Album",
    "spotify_track_uri": "spotify:track:abc123",
    "skipped": False,
}


def test_ip_address_is_dropped_from_the_stored_payload():
    _, _, _, _, _, payload, _ = extended.normalize(ROW, "audio", "f.json")
    assert "ip_addr" not in payload.obj
    assert payload.obj["master_metadata_track_name"] == "Song"


def test_fields_are_extracted():
    row_hash, ts, kind, uri, ms, _, source = extended.normalize(ROW, "audio", "f.json")
    assert ts.isoformat() == "2026-10-31T21:14:44+00:00"
    assert (kind, uri, ms, source) == ("audio", "spotify:track:abc123", 237028, "f.json")
    assert len(row_hash) == 64


def test_rows_differing_only_in_ip_share_a_hash():
    other = {**ROW, "ip_addr": "198.51.100.9"}
    first = extended.normalize(ROW, "audio", "a.json")
    second = extended.normalize(other, "audio", "b.json")
    assert first[0] == second[0]


def test_rows_differing_in_ms_played_or_kind_do_not():
    shorter = {**ROW, "ms_played": 1000}
    base = extended.normalize(ROW, "audio", "f.json")[0]
    assert base != extended.normalize(shorter, "audio", "f.json")[0]
    assert base != extended.normalize(ROW, "video", "f.json")[0]


@pytest.mark.parametrize("bad", [{}, {**ROW, "ts": None}, {**ROW, "ms_played": "x"}])
def test_rows_without_valid_ts_or_ms_played_are_rejected(bad):
    with pytest.raises(extended.ExportError):
        extended.normalize(bad, "audio", "f.json")


def test_read_export_reads_audio_files_only(tmp_path):
    (tmp_path / "Streaming_History_Audio_2026.json").write_text(json.dumps([ROW]))
    (tmp_path / "Streaming_History_Video_2026.json").write_text(json.dumps([ROW]))
    (tmp_path / "notes.txt").write_text("ignored")
    rows = list(extended.read_export(tmp_path))
    assert [r[2] for r in rows] == ["audio"]


def test_podcast_episodes_and_rows_without_a_track_are_ignored_and_counted(tmp_path):
    episode = {**ROW, "spotify_track_uri": None, "spotify_episode_uri": "spotify:episode:xyz"}
    no_uri = {k: v for k, v in ROW.items() if k != "spotify_track_uri"}
    (tmp_path / "Streaming_History_Audio_2026.json").write_text(json.dumps([ROW, episode, no_uri]))
    stats: dict = {}
    rows = list(extended.read_export(tmp_path, stats))
    assert len(rows) == 1
    assert stats["not_music"] == 2


def test_read_export_fails_on_an_empty_folder(tmp_path):
    with pytest.raises(extended.ExportError):
        list(extended.read_export(tmp_path))
