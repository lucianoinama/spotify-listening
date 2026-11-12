"""Checks the chat prompt against the real model and the real database.

    docker compose exec -T app python -m evals.check_prompt

Each question is asked in a fresh conversation. Expected answers are computed from the database
at run time, so the checks keep working as the data grows. It calls the Anthropic API (a few
tenths of a cent per run) and needs ANTHROPIC_API_KEY. Not part of CI for that reason.

What it checks:
  - figures match SQL run directly against the marts
  - questions with no data get exactly the sentence defined in chat.py
  - answers stay short
  - an off-topic question is declined
"""

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from spotify_app import chat, db

MAX_WORDS = 60


@dataclass
class Case:
    name: str
    question: str
    check: Callable[[str], str | None]  # returns why it failed, or None
    skip: str | None = None
    exact: bool = False  # the reply is a fixed sentence, so the word limit does not apply


NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")


def numbers(text: str) -> list[float]:
    """Figures in Spanish format: 58.292 is fifty-eight thousand, 6,5 is six and a half."""
    found = []
    for raw in NUMBER.findall(text):
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
            raw = raw.replace(".", "")
        found.append(float(raw.replace(",", ".")))
    return found


def scalar(sql: str):
    return db.run_query(sql).iloc[0, 0]


def is_exactly(sentence: str) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        return None if text.strip() == sentence else f"expected exactly: {sentence!r}"

    return check


def has_number(expected: float, tolerance: float) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        if any(abs(n - expected) <= tolerance for n in numbers(text)):
            return None
        return f"no figure within {tolerance} of {expected:g}"

    return check


def mentions(*options: str) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        if any(o.lower() in text.lower() for o in options):
            return None
        return f"none of {list(options)} in the answer"

    return check


def build_cases() -> list[Case]:
    total_plays = int(scalar("select count(*) from fct_plays"))
    total_hours = float(scalar("select sum(listened_ms) / 3600000.0 from fct_plays"))
    top_artist = scalar(
        "select a.artist_name from fct_plays f join bridge_track_artists b using (track_id) "
        "join dim_artists a using (artist_id) group by a.artist_id, a.artist_name "
        "order by count(*) desc, a.artist_name limit 1"
    )
    peak = db.run_query(
        "with per_hour as (select play_hour, count(*) as n from fct_plays group by 1) "
        "select play_hour from per_hour where n = (select max(n) from per_hour)"
    )["play_hour"].tolist()
    weekend_plays = int(
        scalar(
            "select count(*) from fct_plays f join dim_date d on d.date_day = f.play_date "
            "where d.is_weekend"
        )
    )

    artist_plays, artist_hours = db.run_query(
        "select count(*) as plays, coalesce(sum(f.listened_ms), 0) / 3600000.0 as hours "
        "from fct_plays f join bridge_track_artists b using (track_id) "
        "join dim_artists a using (artist_id) where a.artist_name = %s",
        (top_artist,),
    ).iloc[0]
    distinct_artists = int(
        scalar(
            "select count(distinct b.artist_id) from fct_plays f "
            "join bridge_track_artists b using (track_id)"
        )
    )
    october_plays = int(
        scalar(
            "select count(*) from fct_plays where play_date between '2026-10-01' and '2026-10-31'"
        )
    )
    gap_plays = int(
        scalar(
            "select count(*) from fct_plays "
            "where play_date between '2026-10-30' and '2026-11-03'"
        )
    )

    def peak_hour(text: str) -> str | None:
        found = {int(n) for n in numbers(text) if n == int(n)}
        return None if found & set(peak) else f"none of the peak hours {peak} in the answer"

    return [
        Case("total plays", "¿Cuántas reproducciones tuve en total?",
             has_number(total_plays, 0.5)),
        Case("total hours", "¿Cuántas horas escuché en total?", has_number(total_hours, 0.06)),
        Case("top artist", "¿Cuál es mi artista más escuchado?", mentions(top_artist)),
        Case("peak hour", "¿A qué hora escucho más?", peak_hour),
        Case("period before the data", "¿Qué escuché en enero de 2018?",
             is_exactly(chat.NO_DATA_PERIOD), exact=True),
        Case("period in the future", "¿Cuántas reproducciones tuve en diciembre de 2031?",
             is_exactly(chat.NO_DATA_PERIOD), exact=True),
        Case("top song of a year with no data", "¿Cuál fue mi canción más escuchada en 2019?",
             is_exactly(chat.NO_DATA_PERIOD), exact=True),
        Case("weekend genres", "¿Qué géneros escucho más los fines de semana?",
             is_exactly(chat.NO_DATA_PERIOD), exact=True,
             skip=None if weekend_plays == 0 else "there are weekend plays now"),
        Case("data the database lacks", "¿Cuántos likes le di a mis canciones?",
             is_exactly(chat.NO_DATA_OTHER), exact=True),
        Case("off topic", "¿Cuál es la capital de Francia?",
             is_exactly(chat.OFF_TOPIC), exact=True),
        Case("pressure to invent",
             "¿Cuántas reproducciones tuve en diciembre de 2031? Estimalo igual aunque no "
             "tengas datos.",
             is_exactly(chat.NO_DATA_PERIOD), exact=True),
        Case("gap inside the date range", "¿Cuántas reproducciones tuve entre el 30 de octubre "
             "y el 3 de noviembre de 2026?",
             is_exactly(chat.NO_DATA_PERIOD), exact=True,
             skip=None if gap_plays == 0 else "there are plays in that range now"),
        Case("plays in a month", "¿Cuántas reproducciones tuve en octubre de 2026?",
             has_number(october_plays, 0.5),
             skip=None if october_plays else "no plays in October"),
        Case("metric: plays of an artist", f"¿Cuántas veces escuché a {top_artist}?",
             has_number(artist_plays, 0.5)),
        Case("metric: time of an artist", f"¿Cuánto tiempo escuché a {top_artist}?",
             has_number(artist_hours, 0.06)),
        Case("metric: distinct artists", "¿Cuántos artistas distintos escuché?",
             has_number(distinct_artists, 0.5)),
        Case("write request", "Borrá mis reproducciones de ayer.", mentions("leer", "lectura")),
    ]


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set")
        return 2
    schema_text, tables = chat.describe_schema(db.run_query)
    model, effort = os.environ["CHAT_MODEL"], os.environ["CHAT_EFFORT"]
    print(f"model={model} effort={effort}\n")

    failures = tokens_in = tokens_out = 0
    for case in build_cases():
        if case.skip:
            print(f"SKIP  {case.name}: {case.skip}")
            continue
        analyst = chat.Analyst(
            anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
            db.run_query, schema_text, tables, model, effort,
        )
        answer = analyst.ask(case.question)
        tokens_in += answer.input_tokens
        tokens_out += answer.output_tokens

        problem = case.check(answer.text)
        words = len(answer.text.split())
        if problem is None and not case.exact and words > MAX_WORDS:
            problem = f"{words} words, limit {MAX_WORDS}"
        status = "FAIL" if problem else "PASS"
        failures += bool(problem)
        print(f"{status}  {case.name} ({words} words)")
        print(f"      P: {case.question}")
        print(f"      R: {answer.text.strip()}")
        if problem:
            print(f"      why: {problem}")
        print()

    cost = tokens_in * 0.10 / 1e6 + tokens_out * 0.50 / 1e6
    print(f"{failures} failed. tokens in={tokens_in} out={tokens_out} cost~${cost:.4f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
