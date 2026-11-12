"""Readable column names for what the user sees. The database names stay out of the screen."""

import pandas as pd

LABELS = {
    "artist_name": "Artista",
    "artist": "Artista",
    "artista": "Artista",
    "track_name": "Canción",
    "track": "Canción",
    "cancion": "Canción",
    "canción": "Canción",
    "album_name": "Álbum",
    "album": "Álbum",
    "genre": "Género",
    "genero": "Género",
    "género": "Género",
    "reproducciones": "Reproducciones",
    "plays": "Reproducciones",
    "play_count": "Reproducciones",
    "horas": "Horas",
    "hours": "Horas",
    "horas_escuchadas": "Horas",
    "minutos": "Minutos",
    "minutes": "Minutos",
    "play_date": "Fecha",
    "date_day": "Fecha",
    "fecha": "Fecha",
    "date": "Fecha",
    "month_start": "Mes",
    "mes": "Mes",
    "year": "Año",
    "anio": "Año",
    "año": "Año",
    "play_hour": "Hora",
    "hora": "Hora",
    "hour": "Hora",
    "day_name": "Día",
    "dia": "Día",
    "día": "Día",
    "iso_day_of_week": "Día de la semana",
    "skipped": "Saltada",
    "porcentaje": "Porcentaje",
    "pct": "Porcentaje",
    "artistas_distintos": "Artistas distintos",
    "canciones_distintas": "Canciones distintas",
    "albumes_distintos": "Álbumes distintos",
}


def label(column: str) -> str:
    """'artist_name' -> 'Artista'. Unknown names: underscores to spaces, first letter up."""
    key = str(column).strip().lower()
    if key in LABELS:
        return LABELS[key]
    text = key.replace("_", " ")
    return text[:1].upper() + text[1:]


def label_map(columns) -> dict[str, str]:
    """Column -> label, leaving a column as it is when its label would repeat another."""
    mapping = {c: label(c) for c in columns}
    seen: dict[str, int] = {}
    for text in mapping.values():
        seen[text] = seen.get(text, 0) + 1
    return {c: (t if seen[t] == 1 else c) for c, t in mapping.items()}


def friendly(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=label_map(frame.columns))
