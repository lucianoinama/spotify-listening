#!/usr/bin/env python3
"""Generates SpotifyListening.Report and SpotifyListening.SemanticModel.

This script owns every generated file under both folders: edit it, not the output, then run
    python build/build_pbip.py
Spec: specs/spotify-listening.md. Rules: copilot-instructions.md.
"""

import json
import os
import re
import shutil
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "SpotifyListening"
REPORT_DIR = os.path.join(ROOT, f"{NAME}.Report")
MODEL_DIR = os.path.join(ROOT, f"{NAME}.SemanticModel")
DEF_DIR = os.path.join(REPORT_DIR, "definition")
PAGES_DIR = os.path.join(DEF_DIR, "pages")
RES_DIR = os.path.join(REPORT_DIR, "StaticResources", "RegisteredResources")
BASE_THEME_DIR = os.path.join(REPORT_DIR, "StaticResources", "SharedResources", "BaseThemes")
MODEL_DEF_DIR = os.path.join(MODEL_DIR, "definition")
TABLES_DIR = os.path.join(MODEL_DEF_DIR, "tables")

PG_SERVER = "localhost:5432"
PG_DATABASE = "spotify"
PG_SCHEMA = "marts"

THEME_NAME = "SpotifyListeningTheme"
SCHEMA_VISUAL = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "visualContainer/2.7.0/schema.json"
)

ACCENT = "#2A78D6"
INK = "#111827"
MUTED = "#6B7280"
LINE = "#E5E7EB"
CANVAS = "#F3F4F6"

NS = uuid.UUID("5c1d1c3e-5b7a-4a34-9a53-0f4a6a7b2e11")


def gid(key):
    return str(uuid.uuid5(NS, key))


def write_utf8(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def write_json(path, obj):
    write_utf8(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def clean_tree(path):
    """Delete every file under path, and the emptied folders when the OS allows it.

    A running Power BI Desktop keeps folders of the open project locked, which makes
    shutil.rmtree fail halfway and leave the project broken. Files can still be deleted."""
    if not os.path.isdir(path):
        return
    for base, dirs, files in os.walk(path, topdown=False):
        for name in files:
            os.remove(os.path.join(base, name))
        for name in dirs:
            try:
                os.rmdir(os.path.join(base, name))
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Semantic model
# ---------------------------------------------------------------------------

KINDS = {
    "text": ("string", "type text"),
    "int": ("int64", "Int64.Type"),
    "num": ("double", "type number"),
    "date": ("dateTime", "type date"),
    "dt": ("dateTime", "type datetime"),
    "bool": ("boolean", "type logical"),
}


def tmdl_name(name):
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def C(name, src, kind, **kw):
    return dict(name=name, src=src, kind=kind, **kw)


def CALC(name, expr, kind, **kw):
    return dict(name=name, expr=expr, kind=kind, **kw)


def column_tmdl(table, c):
    out = []
    if c.get("desc"):
        out.append(f"\t/// {c['desc']}")
    head = f"\tcolumn {tmdl_name(c['name'])}"
    if c.get("expr"):
        head += f" = {c['expr']}"
    out.append(head)
    out.append(f"\t\tdataType: {KINDS[c['kind']][0]}")
    if c.get("hidden"):
        out.append("\t\tisHidden")
    if c.get("key"):
        out.append("\t\tisKey")
    if c.get("fmt"):
        out.append(f"\t\tformatString: {c['fmt']}")
    if c.get("category"):
        out.append(f"\t\tdataCategory: {c['category']}")
    col_key = "col:" + table + ":" + c["name"]
    out.append(f"\t\tlineageTag: {gid(col_key)}")
    if c.get("sort"):
        out.append(f"\t\tsortByColumn: {tmdl_name(c['sort'])}")
    out.append(f"\t\tsummarizeBy: {c.get('summarize', 'none')}")
    if c.get("src"):
        out.append(f"\t\tsourceColumn: {c['src']}")
    out.append("")
    return out


def m_source(source_table, columns, replacements=()):
    selected = ", ".join(f'"{c["src"]}"' for c in columns)
    typed = ", ".join('{"%s", %s}' % (c["src"], KINDS[c["kind"]][1]) for c in columns)
    lines = [
        "let",
        f'    Source = PostgreSQL.Database("{PG_SERVER}", "{PG_DATABASE}", '
        "[CreateNavigationProperties=false]),",
        f'    Data = Source{{[Schema="{PG_SCHEMA}", Item="{source_table}"]}}[Data],',
        f"    Selected = Table.SelectColumns(Data, {{{selected}}}),",
        f"    Typed = Table.TransformColumnTypes(Selected, {{{typed}}})",
    ]
    last = "Typed"
    for i, (col, old, new) in enumerate(replacements):
        step = f"Replaced{i}"
        lines[-1] += ","
        lines.append(
            f'    {step} = Table.ReplaceValue({last}, "{old}", "{new}", '
            f'Replacer.ReplaceText, {{"{col}"}})'
        )
        last = step
    lines += ["in", f"    {last}"]
    return lines


def imported_table(name, source_table, desc, columns, calc_columns=(), replacements=(), category=None):
    out = []
    out.append(f"/// {desc}")
    out.append(f"table {tmdl_name(name)}")
    if category:
        out.append(f"\tdataCategory: {category}")
    out.append(f"\tlineageTag: {gid('table:' + name)}")
    out.append("")
    for c in columns:
        out += column_tmdl(name, c)
    for c in calc_columns:
        out += column_tmdl(name, c)
    out.append(f"\tpartition {tmdl_name(name)} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    for line in m_source(source_table, columns, replacements):
        out.append("\t\t\t\t" + line)
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def measure_tmdl(name, expr, fmt=None, desc=None, category=None):
    out = []
    if desc:
        out.append(f"\t/// {desc}")
    expr = expr.strip("\n")
    if "\n" in expr:
        out.append(f"\tmeasure {tmdl_name(name)} =")
        for line in expr.split("\n"):
            out.append("\t\t\t" + line)
    else:
        out.append(f"\tmeasure {tmdl_name(name)} = {expr}")
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if category:
        out.append(f"\t\tdataCategory: {category}")
    out.append(f"\t\tlineageTag: {gid('measure:' + name)}")
    out.append("")
    return out


def measures_table(name, desc, measures):
    out = [f"/// {desc}", f"table {tmdl_name(name)}", f"\tlineageTag: {gid('table:' + name)}", ""]
    for m in measures:
        out += measure_tmdl(**m)
    out += [
        "\tcolumn Value",
        "\t\tisHidden",
        "\t\tformatString: 0",
        f"\t\tlineageTag: {gid('col:' + name + ':Value')}",
        "\t\tsummarizeBy: sum",
        "\t\tsourceColumn: [Value]",
        "",
        f"\tpartition {tmdl_name(name)} = calculated",
        "\t\tmode: import",
        "\t\tsource = {BLANK()}",
        "",
        "\tannotation PBI_Id = " + gid("pbiid:" + name),
        "",
    ]
    return "\n".join(out)


DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def switch_names(col, names):
    pairs = ", ".join(f'{i + 1}, "{n}"' for i, n in enumerate(names))
    return f'SWITCH({col}, {pairs}, "Sin dato")'


def build_tables():
    tables = {}

    tables["Reproducciones"] = imported_table(
        "Reproducciones",
        "fct_plays",
        "One row per play, with the local day and hour computed by dbt.",
        [
            C("ID reproducción", "play_id", "text", hidden=True,
              desc="Unique id of the play: a hash of the play time and the track."),
            C("Fecha y hora", "played_at_local", "dt", fmt="dd/mm/yyyy hh:nn",
              desc="When the play happened, in local time."),
            C("Fecha", "play_date", "date", hidden=True, fmt="dd/mm/yyyy",
              desc="Local day of the play. Key to Calendario."),
            C("Hora", "play_hour", "int", fmt="0",
              desc="Hour of the day, 0 to 23, in local time."),
            C("ID canción", "track_id", "text", hidden=True,
              desc="Spotify track id. Key to Canciones."),
            C("Tiempo escuchado en ms", "listened_ms", "int", hidden=True,
              desc="Milliseconds actually played where the extended history has them, else the "
                   "track length as an estimate (plays after the export ends)."),
            C("Origen original", "context_type", "text", hidden=True,
              desc="Where the play started, as Spotify reports it: playlist, album, artist."),
        ],
        calc_columns=[
            CALC("Origen",
                 'IF(ISBLANK(Reproducciones[Origen original]), "Sin dato", '
                 'SWITCH(Reproducciones[Origen original], "playlist", "Playlist", '
                 '"album", "Álbum", "artist", "Artista", "collection", "Biblioteca", '
                 '"show", "Podcast", "Otro"))',
                 "text", desc="Where the play started, in Spanish."),
            CALC("Franja orden",
                 "SWITCH(TRUE(), Reproducciones[Hora] < 6, 1, Reproducciones[Hora] < 12, 2, "
                 "Reproducciones[Hora] < 19, 3, 4)",
                 "int", hidden=True, fmt="0", desc="Sort key for Franja horaria."),
            CALC("Franja horaria",
                 'SWITCH(TRUE(), Reproducciones[Hora] < 6, "Madrugada", '
                 'Reproducciones[Hora] < 12, "Mañana", Reproducciones[Hora] < 19, "Tarde", "Noche")',
                 "text", sort="Franja orden",
                 desc="Time of day: early morning to 5, morning to 11, afternoon to 18, night."),
        ],
    )

    tables["Canciones"] = imported_table(
        "Canciones",
        "dim_tracks",
        "One row per track. Only the main artist is kept.",
        [
            C("ID canción", "track_id", "text", hidden=True, desc="Spotify track id."),
            C("Canción", "track_name", "text", desc="Track title."),
            C("Es explícita", "is_explicit", "bool", hidden=True,
              desc="True when Spotify flags the track as explicit."),
            C("Álbum", "album_name", "text", desc="Album title."),
            C("Portada", "album_image_url", "text", hidden=True, category="ImageUrl",
              desc="URL of the 300 px album cover on Spotify's CDN. Used by the Álbumes page."),
            C("Año de lanzamiento", "release_year", "int", fmt="0",
              desc="Release year of the album."),
            C("Artista principal", "main_artist_name", "text",
              desc="First artist listed for the track."),
        ],
        calc_columns=[
            CALC("Contenido",
                 'IF(Canciones[Es explícita], "Explícita", "Sin marcar")',
                 "text", desc="Explicit flag as a label."),
            CALC("Década orden",
                 "IF(ISBLANK(Canciones[Año de lanzamiento]), 0, "
                 "INT(Canciones[Año de lanzamiento] / 10) * 10)",
                 "int", hidden=True, fmt="0", desc="Sort key for Década."),
            CALC("Década",
                 'IF(Canciones[Década orden] = 0, "Sin dato", '
                 'FORMAT(Canciones[Década orden], "0") & "s")',
                 "text", sort="Década orden", desc="Release decade of the album."),
        ],
    )

    tables["Artistas"] = imported_table(
        "Artistas",
        "dim_artists",
        "One row per artist. Genres come from Last.fm tags, not from Spotify.",
        [
            C("ID artista", "artist_id", "text", hidden=True, desc="Spotify artist id."),
            C("Artista", "artist_name", "text", desc="Artist name."),
            C("Género principal", "primary_genre", "text",
              desc="Most popular Last.fm tag kept as a genre, or Sin género."),
            C("Géneros", "genres", "text", desc="All genres kept for the artist, in order."),
            C("Cantidad de géneros", "genre_count", "int", fmt="0",
              desc="How many genres were kept."),
        ],
        replacements=[("primary_genre", "unknown", "Sin género")],
    )

    tables["Calendario"] = imported_table(
        "Calendario",
        "dim_date",
        "One row per day from the first play to today, including days without plays.",
        [
            C("Fecha", "date_day", "date", key=True, fmt="dd/mm/yyyy", desc="Calendar day."),
            C("Año", "year", "int", fmt="0", desc="Calendar year."),
            C("Mes número", "month", "int", hidden=True, fmt="0", desc="Month number, 1 to 12."),
            C("Inicio de mes", "month_start", "date", hidden=True, fmt="mmm yyyy",
              desc="First day of the month."),
            C("Día número", "iso_day_of_week", "int", hidden=True, fmt="0",
              desc="ISO weekday, 1 is Monday and 7 is Sunday."),
            C("Es fin de semana", "is_weekend", "bool", hidden=True,
              desc="True for Saturday and Sunday."),
        ],
        calc_columns=[
            CALC("Mes", switch_names("Calendario[Mes número]", MONTH_NAMES), "text",
                 sort="Mes número", desc="Month name in Spanish."),
            CALC("Día de la semana", switch_names("Calendario[Día número]", DAY_NAMES), "text",
                 sort="Día número", desc="Weekday name in Spanish, Monday first."),
            CALC("Tipo de día",
                 'IF(Calendario[Es fin de semana], "Fin de semana", "Semana")',
                 "text", desc="Weekend or weekday."),
        ],
        category="Time",
    )

    tables["Ranking Artistas"] = imported_table(
        "Ranking Artistas",
        "mart_top_artists_monthly",
        "Hours and plays per artist and month, ranked by dbt.",
        [
            C("Inicio de mes", "month_start", "date", hidden=True, fmt="mmm yyyy",
              desc="First day of the month. Key to Meses."),
            C("ID artista", "artist_id", "text", hidden=True, desc="Spotify artist id."),
            C("Artista", "artist_name", "text", desc="Artist name."),
            C("Reproducciones del mes", "plays", "int", hidden=True, fmt="#,0",
              desc="Plays of any track by the artist in the month."),
            C("Horas del mes", "hours", "num", hidden=True, fmt="#,0.0",
              desc="Estimated hours of any track by the artist in the month."),
            C("Posición en el mes", "rank_in_month", "int", fmt="0",
              desc="Rank of the artist by hours within the month."),
        ],
    )

    tables["Ranking Géneros"] = imported_table(
        "Ranking Géneros",
        "mart_genre_monthly",
        "Hours and plays per genre and month, ranked by dbt.",
        [
            C("Inicio de mes", "month_start", "date", hidden=True, fmt="mmm yyyy",
              desc="First day of the month. Key to Meses."),
            C("Género", "genre", "text", desc="Genre, a Last.fm tag after filtering."),
            C("Reproducciones del mes", "plays", "int", hidden=True, fmt="#,0",
              desc="Plays of tracks whose artists carry the genre."),
            C("Horas del mes", "hours", "num", hidden=True, fmt="#,0.0",
              desc="Estimated hours of tracks whose artists carry the genre."),
            C("Posición en el mes", "rank_in_month", "int", fmt="0",
              desc="Rank of the genre by hours within the month."),
        ],
    )

    tables["Meses"] = "\n".join([
        "/// One row per month. Lets a single slicer filter both monthly rankings.",
        "table Meses",
        f"\tlineageTag: {gid('table:Meses')}",
        "",
        "\tcolumn Mes",
        "\t\tformatString: mmmm yyyy",
        f"\t\tlineageTag: {gid('col:Meses:Mes')}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Mes]",
        "",
        "\tpartition Meses = calculated",
        "\t\tmode: import",
        "\t\tsource = ```",
        '\t\t\t\tDISTINCT(SELECTCOLUMNS(Calendario, "Mes", Calendario[Inicio de mes]))',
        "\t\t\t\t```",
        "",
        "\tannotation PBI_Id = " + gid("pbiid:Meses"),
        "",
    ])

    tables["_Measures"] = measures_table("_Measures", "Business measures.", MEASURES)
    tables["_SVG_Measures"] = measures_table(
        "_SVG_Measures", "SVG KPI cards, named by page: P1_, P2_.", SVG_MEASURES
    )
    return tables


def top_n(rank_over, measure, n):
    return (
        f"VAR _rank = RANKX(ALLSELECTED({rank_over}), {measure}, , DESC)\n"
        f"RETURN IF(_rank <= {n}, {measure})"
    )


MEASURES = [
    dict(name="Total de reproducciones", expr="COUNTROWS(Reproducciones)", fmt="#,0",
         desc="Number of plays in the current filter."),
    dict(name="Horas escuchadas",
         expr="DIVIDE(SUM(Reproducciones[Tiempo escuchado en ms]), 3600000)", fmt="#,0.0",
         desc="Hours listened: real time played for plays up to the end of the extended history, "
              "an estimate (track length) for later ones."),
    dict(name="Canciones únicas", expr="DISTINCTCOUNT(Reproducciones[ID canción])", fmt="#,0",
         desc="Distinct tracks played."),
    dict(name="Días con actividad", expr="DISTINCTCOUNT(Reproducciones[Fecha])", fmt="#,0",
         desc="Distinct days with at least one play."),
    dict(name="Horas por día activo",
         expr="DIVIDE([Horas escuchadas], [Días con actividad])", fmt="#,0.0",
         desc="Estimated hours divided by days with at least one play."),
    dict(name="Horas por día", expr="[Horas escuchadas] + 0", fmt="#,0.0",
         desc="Estimated hours with zero instead of blank, so days without plays show as zero."),
    dict(name="Hora pico",
         expr=("CONCATENATEX(TOPN(1, VALUES(Reproducciones[Hora]), "
               "[Total de reproducciones], DESC), Reproducciones[Hora], \", \", "
               "Reproducciones[Hora], ASC)"),
         desc="Hour of the day with the most plays. Ties are listed together."),
    dict(name="Día más activo",
         expr=("CONCATENATEX(TOPN(1, VALUES(Calendario[Día de la semana]), "
               "[Horas escuchadas], DESC), Calendario[Día de la semana], \", \")"),
         desc="Weekday with the most estimated hours. Ties are listed together."),
    dict(name="Color mapa de calor",
         expr=("VAR _v = [Horas escuchadas]\n"
               "VAR _max = MAXX(CROSSJOIN(ALLSELECTED(Calendario[Día de la semana]), "
               "ALLSELECTED(Reproducciones[Hora])), [Horas escuchadas])\n"
               "VAR _r = DIVIDE(_v, _max)\n"
               "RETURN IF(ISBLANK(_v), \"#F3F4F6\", SWITCH(TRUE(), _r >= 0.8, \"#1E5FA8\", "
               "_r >= 0.6, \"#2A78D6\", _r >= 0.4, \"#6FA3E3\", _r >= 0.2, \"#A9C8F0\", "
               "\"#D6E6F8\"))"),
         desc="Cell color of the heatmap: five blue steps by share of the busiest cell."),
    dict(name="Color texto mapa de calor",
         expr="IF([Color mapa de calor] IN {\"#1E5FA8\", \"#2A78D6\"}, \"#FFFFFF\", \"#111827\")",
         desc="Text color of the heatmap: white on the two darkest cells, dark otherwise."),
    dict(name="Horas por artista", expr="SUM('Ranking Artistas'[Horas del mes])", fmt="#,0.0",
         desc="Estimated hours per artist from the monthly ranking, for the selected months."),
    dict(name="Horas por artista (Top 10)",
         expr=top_n("'Ranking Artistas'[Artista]", "[Horas por artista]", 10), fmt="#,0.0",
         desc="Hours per artist, blank outside the top 10. Ties can add an artist."),
    dict(name="Horas por género", expr="SUM('Ranking Géneros'[Horas del mes])", fmt="#,0.0",
         desc="Estimated hours per genre from the monthly ranking, for the selected months."),
    dict(name="Horas por género (Top 8)",
         expr=top_n("'Ranking Géneros'[Género]", "[Horas por género]", 8), fmt="#,0.0",
         desc="Hours per genre, blank outside the top 8. Ties can add a genre."),
    dict(name="Cantidad de artistas", expr="DISTINCTCOUNT(Artistas[ID artista])", fmt="#,0",
         desc="Distinct artists in the current filter."),
    dict(name="Artistas por género (Top 8)",
         expr=top_n("Artistas[Género principal]", "[Cantidad de artistas]", 8), fmt="#,0",
         desc="Artists per main genre, blank outside the top 8."),
]


def svg_kpi(value_expr, sub, w, h, fs, y_val, y_sub, fs_sub):
    return (
        f"VAR _Txt = {value_expr}\n"
        "RETURN\n"
        '"data:image/svg+xml;utf8," &\n'
        f"\"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}' "
        "xmlns='http://www.w3.org/2000/svg'>\" &\n"
        f"\"<rect width='{w}' height='{h}' fill='transparent'/>\" &\n"
        f"\"<text x='4' y='{y_val}' font-family='Segoe UI,sans-serif' font-size='{fs}' "
        "font-weight='bold' fill='rgb(17,24,39)'>\" & _Txt & \"</text>\" &\n"
        f"\"<text x='4' y='{y_sub}' font-family='Segoe UI,sans-serif' font-size='{fs_sub}' "
        f"fill='rgb(107,114,128)'>{sub}</text>\" &\n"
        '"</svg>"'
    )


SMALL = dict(w=196, h=58, fs=30, y_val=31, y_sub=51, fs_sub=12)
BIG = dict(w=344, h=108, fs=46, y_val=62, y_sub=94, fs_sub=14)

SVG_MEASURES = [
    dict(name="P1_Horas_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('IF(ISBLANK([Horas escuchadas]), "0,0", '
                      'FORMAT([Horas escuchadas], "#,0.0", "es-AR"))',
                      "horas escuchadas", **SMALL),
         desc="Overview KPI card: hours listened."),
    dict(name="P1_Reproducciones_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('FORMAT([Total de reproducciones], "#,0", "es-AR")', "reproducciones",
                      **SMALL),
         desc="Overview KPI card: number of plays."),
    dict(name="P1_Canciones_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('FORMAT([Canciones únicas], "#,0", "es-AR")', "canciones distintas",
                      **SMALL),
         desc="Overview KPI card: distinct tracks."),
    dict(name="P1_HorasDia_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('IF(ISBLANK([Horas por día activo]), "0,0", '
                      'FORMAT([Horas por día activo], "#,0.0", "es-AR"))',
                      "por día con actividad", **SMALL),
         desc="Overview KPI card: hours per active day."),
    dict(name="P2_HoraPico_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('IF([Hora pico] = "", "-", SUBSTITUTE([Hora pico], ", ", " y ") & " h")',
                      "hora con más reproducciones", **BIG),
         desc="Rhythm KPI card: peak hour of the day."),
    dict(name="P2_DiaActivo_KPI_SVG", category="ImageUrl",
         expr=svg_kpi('IF([Día más activo] = "", "-", SUBSTITUTE([Día más activo], ", ", " y "))',
                      "día con más horas", **BIG),
         desc="Rhythm KPI card: weekday with the most hours."),
]

ALBUM_SLOTS = 8


def cover_expr(n):
    return (
        'VAR _t = ADDCOLUMNS(ALLSELECTED(Canciones[Portada]), "Score", [Puntaje de álbum])\n'
        f"VAR _top = TOPN({n}, FILTER(_t, NOT ISBLANK([Score])), [Score], DESC)\n"
        "VAR _min = MINX(_top, [Score])\n"
        f"RETURN IF(COUNTROWS(_top) >= {n}, MAXX(FILTER(_top, [Score] = _min), Canciones[Portada]))"
    )


def svg_safe(expr):
    """Escape text for an SVG inside a utf8 data URI: % and # break the URI, & < > the XML."""
    for old, new in (("%", "%25"), ("#", "%23"), ("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")):
        expr = f'SUBSTITUTE({expr}, "{old}", "{new}")'
    return expr


def caption_svg(cover_measure, plays_measure, prefix):
    line1 = svg_safe(f'"{prefix}" & _short')
    line2 = svg_safe('_artist & " · " & _plays & _unit')
    return (
        f"VAR _u = [{cover_measure}]\n"
        "VAR _name = CALCULATE(MAX(Canciones[Álbum]), Canciones[Portada] = _u)\n"
        "VAR _artist = CALCULATE(MAX(Canciones[Artista principal]), Canciones[Portada] = _u)\n"
        f"VAR _plays = CALCULATE([{plays_measure}], Canciones[Portada] = _u)\n"
        'VAR _short = IF(LEN(_name) > 30, LEFT(_name, 29) & "…", _name)\n'
        f"VAR _line1 = {line1}\n"
        'VAR _unit = IF(_plays = 1, " reproducción", " reproducciones")\n'
        f"VAR _line2 = {line2}\n"
        "RETURN\n"
        "IF(ISBLANK(_u), BLANK(),\n"
        '"data:image/svg+xml;utf8," &\n'
        "\"<svg width='288' height='50' viewBox='0 0 288 50' xmlns='http://www.w3.org/2000/svg'>\" &\n"
        "\"<rect width='288' height='50' fill='transparent'/>\" &\n"
        "\"<text x='144' y='18' text-anchor='middle' font-family='Segoe UI,sans-serif' "
        "font-size='13' font-weight='bold' fill='rgb(17,24,39)'>\" & _line1 & \"</text>\" &\n"
        "\"<text x='144' y='38' text-anchor='middle' font-family='Segoe UI,sans-serif' "
        "font-size='11' fill='rgb(107,114,128)'>\" & _line2 & \"</text>\" &\n"
        '"</svg>")'
    )


def caption_expr(n):
    return caption_svg(f"Portada #{n}", "Total de reproducciones", f"{n}. ")


def windowed(measure):
    """The measure over the 30 days up to the last play, ignoring the date slicer.

    DAX does not accept a measure inside a boolean CALCULATE filter, so the window edges
    go through variables."""
    return (
        "VAR _end = [Fin de datos]\n"
        "VAR _start = _end - 29\n"
        f"RETURN CALCULATE({measure}, REMOVEFILTERS(Calendario), "
        "Calendario[Fecha] >= _start, Calendario[Fecha] <= _end)"
    )

MEASURES += [
    dict(name="Fin de datos",
         expr="CALCULATE(MAX(Reproducciones[Fecha]), ALL(Reproducciones))", fmt="dd/mm/yyyy",
         desc="Day of the most recent play in the whole model. Ends the 30 day window."),
    dict(name="Reproducciones 30 días",
         expr=windowed("[Total de reproducciones]"), fmt="#,0",
         desc="Plays in the 30 days up to the last recorded play. Ignores the date slicer."),
    dict(name="Puntaje de álbum 30 días",
         expr=windowed("[Puntaje de álbum]"), fmt="0.000000",
         desc="Album score (plays plus a tiny recency term) over the 30 day window."),
    dict(name="Portada álbum top 30 días", category="ImageUrl",
         expr=("VAR _t = ADDCOLUMNS(ALL(Canciones[Portada]), \"Score\", "
               "[Puntaje de álbum 30 días])\n"
               "VAR _top = TOPN(1, FILTER(_t, NOT ISBLANK([Score])), [Score], DESC)\n"
               "RETURN MAXX(_top, Canciones[Portada])"),
         desc="Cover URL of the most played album in the 30 days up to the last recorded play."),
]
SVG_MEASURES.append(dict(
    name="P1_AlbumTop30_Caption_SVG", category="ImageUrl",
    expr=caption_svg("Portada álbum top 30 días", "Reproducciones 30 días", ""),
    desc="Overview caption for the top album of the last 30 days: name, artist and plays."))

MEASURES.append(dict(
    name="Puntaje de álbum",
    expr=("[Total de reproducciones] + "
          "DIVIDE(CALCULATE(MAX(Reproducciones[Fecha y hora])), 1000000)"),
    fmt="0.000000",
    desc="Plays plus a tiny term from the last play time, so albums with equal plays rank "
         "by recency and the ranking has no ties."))
for _n in range(1, ALBUM_SLOTS + 1):
    MEASURES.append(dict(
        name=f"Portada #{_n}", expr=cover_expr(_n), category="ImageUrl",
        desc=f"Cover URL of the album ranked {_n} by plays in the current date filter."))
    SVG_MEASURES.append(dict(
        name=f"P5_Album{_n}_Caption_SVG", expr=caption_expr(_n), category="ImageUrl",
        desc=f"Álbumes page caption for the album ranked {_n}: name, artist and plays."))

RELATIONSHIPS = [
    ("Reproducciones.'ID canción'", "Canciones.'ID canción'"),
    ("Reproducciones.Fecha", "Calendario.Fecha"),
    ("'Ranking Artistas'.'Inicio de mes'", "Meses.Mes"),
    ("'Ranking Géneros'.'Inicio de mes'", "Meses.Mes"),
]


def write_model():
    clean_tree(MODEL_DIR)
    tables = build_tables()
    for name, text in tables.items():
        write_utf8(os.path.join(TABLES_DIR, f"{name}.tmdl"), text)

    refs = "\n".join(f"ref table {tmdl_name(n)}" for n in tables)
    write_utf8(
        os.path.join(MODEL_DEF_DIR, "model.tmdl"),
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n\n"
        'annotation PBI_ProTooling = ["DevMode"]\n\n'
        f"{refs}\n\n"
        "ref cultureInfo en-US\n",
    )
    rels = []
    for i, (frm, to) in enumerate(RELATIONSHIPS):
        rels.append(f"relationship {gid('rel:' + str(i))}\n\tfromColumn: {frm}\n\ttoColumn: {to}\n")
    write_utf8(os.path.join(MODEL_DEF_DIR, "relationships.tmdl"), "\n".join(rels))
    write_utf8(os.path.join(MODEL_DEF_DIR, "database.tmdl"), "database\n\tcompatibilityLevel: 1600\n")
    write_utf8(os.path.join(MODEL_DEF_DIR, "cultures", "en-US.tmdl"), "cultureInfo en-US\n")
    write_json(
        os.path.join(MODEL_DIR, "definition.pbism"),
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/"
                       "definitionProperties/1.0.0/schema.json",
            "version": "4.2",
            "settings": {},
        },
    )
    write_json(
        os.path.join(MODEL_DIR, "diagramLayout.json"),
        {
            "version": "1.1.0",
            "diagrams": [{
                "ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": [],
                "name": "All tables", "zoomValue": 100, "pinKeyFieldsToTop": False,
                "showExtraHeaderInfo": False, "hideKeyFieldsWhenCollapsed": False,
                "tablesLocked": False,
            }],
            "selectedDiagram": "All tables",
            "defaultDiagram": "All tables",
        },
    )
    write_json(os.path.join(MODEL_DIR, ".platform"), platform("SemanticModel"))


def platform(item_type):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                   "platformProperties/2.0.0/schema.json",
        "metadata": {"type": item_type, "displayName": NAME},
        "config": {"version": "2.0", "logicalId": gid("platform:" + item_type)},
    }


# ---------------------------------------------------------------------------
# Report: fields and visual builders
# ---------------------------------------------------------------------------


def lit(value):
    return {"expr": {"Literal": {"Value": value}}}


def col_field(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def meas_field(entity, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(field, entity, prop, active=False):
    p = {"field": field, "queryRef": f"{entity}.{prop}"}
    if active:
        p["active"] = True
    return p


def C_(entity, prop):
    return col_field(entity, prop), entity, prop


def M_(prop, entity="_Measures"):
    return meas_field(entity, prop), entity, prop


def chrome():
    off = {"properties": {"show": lit("false")}}
    return {"background": [off], "border": [off], "dropShadow": [off], "title": [off]}


def container(name, box, tab, visual):
    x, y, w, h = box
    return {
        "$schema": SCHEMA_VISUAL,
        "name": name,
        "position": {"x": x, "y": y, "z": tab, "height": h, "width": w, "tabOrder": tab * 1000},
        "visual": visual,
    }


def axes_and_labels(precision, horizontal_value_axis_hidden=True):
    return {
        "categoryAxis": [{"properties": {"showAxisTitle": lit("false"), "show": lit("true")}}],
        "valueAxis": [{"properties": {"showAxisTitle": lit("false"), "show": lit("false")}}],
        "labels": [{"properties": {
            "show": lit("true"),
            "labelPrecision": lit(f"{precision}L"),
            "enableValueDataLabel": lit("true"),
            "labelDisplayUnits": lit("1D"),
        }}],
    }


def sort_by_measure(measure):
    field, _, _ = measure
    return {"sortDefinition": {"sort": [{"field": field, "direction": "Descending"}]}}


def chart(vtype, cat, measure, precision=0, sort_desc=False, line=False, categorical=False):
    cf, ce, cp = cat
    mf, me, mp = measure
    query = {"queryState": {
        "Category": {"projections": [proj(cf, ce, cp, active=True)]},
        "Y": {"projections": [proj(mf, me, mp)]},
    }}
    if sort_desc:
        query.update(sort_by_measure(measure))
    objects = axes_and_labels(precision)
    if categorical:
        objects["categoryAxis"][0]["properties"]["axisType"] = lit("'Categorical'")
    if line:
        objects["lineStyles"] = [{"properties": {
            "strokeWidth": lit("2D"), "areaShow": lit("true"),
            "showMarker": lit("true"), "markerSize": lit("3D"),
        }}]
    return {"visualType": vtype, "query": query, "objects": objects,
            "visualContainerObjects": chrome()}


def donut(cat, measure):
    cf, ce, cp = cat
    mf, me, mp = measure
    return {
        "visualType": "donutChart",
        "query": {"queryState": {
            "Category": {"projections": [proj(cf, ce, cp, active=True)]},
            "Y": {"projections": [proj(mf, me, mp)]},
        }},
        "objects": {
            "labels": [{"properties": {
                "show": lit("true"), "labelStyle": lit("'Data value'"),
                "labelPrecision": lit("0L"),
            }}],
            "legend": [{"properties": {
                "show": lit("true"), "position": lit("'Bottom'"), "showTitle": lit("false"),
            }}],
        },
        "visualContainerObjects": chrome(),
    }


def table(columns, sort_field=None, descending=True, compact=False):
    query = {"queryState": {"Values": {"projections": [proj(f, e, p) for f, e, p in columns]}}}
    if sort_field is not None:
        f, _, _ = sort_field
        query["sortDefinition"] = {"sort": [{
            "field": f, "direction": "Descending" if descending else "Ascending"}]}
    objects = {}
    if compact:
        objects["columnHeaders"] = [{"properties": {"fontSize": lit("9D")}}]
        objects["values"] = [{"properties": {"fontSize": lit("9D")}}]
        objects["total"] = [{"properties": {"totals": lit("false")}}]
    return {"visualType": "tableEx", "query": query, "objects": objects,
            "visualContainerObjects": chrome()}


def matrix(rows, columns, value, back, font):
    rf, re_, rp = rows
    cf, ce, cp = columns
    vf, ve, vp = value
    return {
        "visualType": "pivotTable",
        "query": {"queryState": {
            "Rows": {"projections": [proj(rf, re_, rp, active=True)]},
            "Columns": {"projections": [proj(cf, ce, cp, active=True)]},
            "Values": {"projections": [proj(vf, ve, vp)]},
        }},
        "objects": {"values": [
            {"properties": {"fontSize": lit("10D")}},
            {
                "properties": {
                    "backColor": {"solid": {"color": {"expr": back[0]}}},
                    "fontColor": {"solid": {"color": {"expr": font[0]}}},
                },
                "selector": {
                    "data": [{"dataViewWildcard": {"matchingOption": 1}}],
                    "metadata": f"{ve}.{vp}",
                },
            },
        ]},
        "visualContainerObjects": chrome(),
    }


def slicer(field, mode):
    f, e, p = field
    return {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj(f, e, p, active=True)]}}},
        "objects": {
            "data": [{"properties": {"mode": lit(f"'{mode}'")}}],
            "header": [{"properties": {"show": lit("false")}}],
        },
        "visualContainerObjects": chrome(),
    }


def image_kpi(measure_name, entity="_SVG_Measures"):
    return {
        "visualType": "image",
        "objects": {"image": [{"properties": {
            "sourceType": lit("'imageData'"),
            "sourceField": {"expr": meas_field(entity, measure_name)},
        }}]},
        "visualContainerObjects": chrome(),
    }


# ---------------------------------------------------------------------------
# Report: SVG backgrounds, theme and pages
# ---------------------------------------------------------------------------


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_text(x, y, text, size, fill, weight="normal", anchor="start"):
    return (
        f"<text x='{x}' y='{y}' font-family='Segoe UI,sans-serif' font-size='{size}' "
        f"font-weight='{weight}' fill='{fill}' text-anchor='{anchor}'>{esc(text)}</text>"
    )


def svg_card(x, y, w, h, title):
    card = (
        f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='12' fill='#FFFFFF' "
        f"stroke='{LINE}' stroke-width='1'/>"
    )
    return card + svg_text(x + 16, y + 24, title, 13, INK, "bold") if title else card


def background_svg(title, strip, cards, footer):
    parts = [
        "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>",
        f"<rect width='1280' height='720' fill='{CANVAS}'/>",
        f"<rect width='1280' height='56' fill='{INK}'/>",
        f"<rect y='52' width='1280' height='4' fill='{ACCENT}'/>",
        svg_text(32, 36, title, 20, "#FFFFFF", "bold"),
        svg_text(1248, 34, "Datos: Spotify · Géneros: Last.fm", 12, "#9CA3AF", anchor="end"),
        f"<rect x='24' y='64' width='1232' height='56' rx='12' fill='#FFFFFF' "
        f"stroke='{LINE}' stroke-width='1'/>",
    ]
    for x, text in strip:
        parts.append(svg_text(x, 98, text, 12, MUTED, "bold"))
    for x, y, w, h, t in cards:
        parts.append(svg_card(x, y, w, h, t))
    parts.append(svg_text(24, 716, footer, 11, MUTED))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def inner(card, dy=32, dh=38):
    x, y, w, h, _ = card
    return (x + 12, y + dy, w - 24, h - dh)


def theme():
    return {
        "name": THEME_NAME,
        "dataColors": [ACCENT, "#9AA3AE", "#EB6834", "#1BAF7A", "#EDA100", "#6250D6",
                       "#E87BA4", "#E34948"],
        "background": "#FFFFFF",
        "foreground": INK,
        "tableAccent": ACCENT,
        "maximum": ACCENT,
        "minimum": "#D6E6F8",
        "null": "#9AA3AE",
        "textClasses": {
            "label": {"color": MUTED, "fontSize": 10, "fontFace": "Segoe UI"},
            "callout": {"color": INK, "fontSize": 28, "fontFace": "Segoe UI", "fontWeight": "bold"},
            "title": {"color": INK, "fontSize": 13, "fontFace": "Segoe UI", "fontWeight": "bold"},
            "header": {"color": INK, "fontSize": 11, "fontFace": "Segoe UI",
                       "fontWeight": "semibold"},
            "largeTitle": {"color": INK, "fontSize": 16, "fontFace": "Segoe UI",
                           "fontWeight": "bold"},
        },
        "visualStyles": {"*": {"*": {"fontFamily": [{"value": "Segoe UI"}]}}},
    }


def build_pages():
    pages = []

    # Page 1: Resumen
    c_kpi = [(24 + i * 232, 132, 220, 96, t) for i, t in enumerate(
        ["Horas escuchadas", "Reproducciones", "Canciones únicas", "Horas por día activo"])]
    c_day = (24, 240, 916, 150, "Horas por día")
    c_alb = (956, 132, 300, 258, "Álbum más escuchado · últimos 30 días")
    c_art = (24, 402, 608, 302, "Top 10 artistas por horas")
    c_gen = (648, 402, 608, 302, "Top 8 géneros por horas")
    v = []
    v.append(("slicer-fecha", (170, 70, 420, 44), slicer(C_("Calendario", "Fecha"), "Between")))
    v.append(("slicer-mes", (920, 76, 280, 34), slicer(C_("Meses", "Mes"), "Dropdown")))
    for i, name in enumerate(["P1_Horas_KPI_SVG", "P1_Reproducciones_KPI_SVG",
                              "P1_Canciones_KPI_SVG", "P1_HorasDia_KPI_SVG"]):
        x, y, w, h = inner(c_kpi[i], 30, 38)
        v.append((f"kpi{i + 1}", (x, y, w, h), image_kpi(name)))
    v.append(("portada30", (c_alb[0] + 75, c_alb[1] + 36, 150, 150),
              image_kpi("Portada álbum top 30 días", entity="_Measures")))
    v.append(("titulo30", (c_alb[0] + 6, c_alb[1] + 192, 288, 50),
              image_kpi("P1_AlbumTop30_Caption_SVG")))
    v.append(("dia", inner(c_day), chart("lineChart", C_("Calendario", "Fecha"),
                                         M_("Horas por día"), precision=1, line=True)))
    v.append(("artistas", inner(c_art), chart("barChart", C_("Ranking Artistas", "Artista"),
                                              M_("Horas por artista (Top 10)"), precision=1,
                                              sort_desc=True)))
    v.append(("generos", inner(c_gen), chart("barChart", C_("Ranking Géneros", "Género"),
                                             M_("Horas por género (Top 8)"), precision=1,
                                             sort_desc=True)))
    pages.append(dict(
        key="resumen", display="Resumen", bg="bg_resumen.svg", title="Mi escucha en Spotify",
        strip=[(40, "Rango de fechas"), (672, "Mes (rankings de artistas y géneros)")],
        cards=c_kpi + [c_alb, c_day, c_art, c_gen],
        footer="Las horas se estiman con la duración de cada canción. Artistas y géneros "
               "suman más que el total: una canción cuenta completa para cada uno. El álbum "
               "del cuadro usa los últimos 30 días hasta la última reproducción.",
        visuals=v))

    # Page 2: Cuándo escucho
    c_heat = (24, 132, 848, 316, "Horas por día de la semana y hora")
    c_peak = (888, 132, 368, 148, "Hora pico")
    c_top = (888, 300, 368, 148, "Día más activo")
    c_hour = (24, 464, 560, 240, "Reproducciones por hora del día")
    c_band = (600, 464, 320, 240, "Horas por franja horaria")
    c_week = (936, 464, 320, 240, "Semana y fin de semana")
    v = [("slicer-fecha", (170, 70, 420, 44), slicer(C_("Calendario", "Fecha"), "Between"))]
    v.append(("mapa", inner(c_heat), matrix(
        C_("Calendario", "Día de la semana"), C_("Reproducciones", "Hora"),
        M_("Horas escuchadas"), M_("Color mapa de calor"), M_("Color texto mapa de calor"))))
    x, y, w, h = inner(c_peak, 32, 40)
    v.append(("pico", (x, y, w, 108), image_kpi("P2_HoraPico_KPI_SVG")))
    x, y, w, h = inner(c_top, 32, 40)
    v.append(("activo", (x, y, w, 108), image_kpi("P2_DiaActivo_KPI_SVG")))
    v.append(("hora", inner(c_hour), chart("clusteredColumnChart", C_("Reproducciones", "Hora"),
                                           M_("Total de reproducciones"), categorical=True)))
    v.append(("franja", inner(c_band), chart("clusteredColumnChart",
                                             C_("Reproducciones", "Franja horaria"),
                                             M_("Horas escuchadas"), precision=1)))
    v.append(("semana", inner(c_week), chart("clusteredColumnChart", C_("Calendario", "Tipo de día"),
                                             M_("Horas escuchadas"), precision=1)))
    pages.append(dict(
        key="ritmo", display="Cuándo escucho", bg="bg_ritmo.svg", title="Cuándo escucho",
        strip=[(40, "Rango de fechas")],
        cards=[c_heat, c_peak, c_top, c_hour, c_band, c_week],
        footer="Horas en tiempo local. El mapa de calor oscurece las celdas con más horas.",
        visuals=v))

    # Page 3: Artistas y géneros
    c_art = (24, 132, 608, 300, "Top 10 artistas del mes")
    c_gen = (648, 132, 608, 300, "Top 8 géneros del mes")
    c_cnt = (24, 448, 608, 256, "Artistas por género principal")
    c_tab = (648, 448, 608, 256, "Detalle de artistas")
    v = [("slicer-mes", (170, 76, 300, 34), slicer(C_("Meses", "Mes"), "Dropdown"))]
    v.append(("artistas", inner(c_art), chart("barChart", C_("Ranking Artistas", "Artista"),
                                              M_("Horas por artista (Top 10)"), precision=1,
                                              sort_desc=True)))
    v.append(("generos", inner(c_gen), chart("barChart", C_("Ranking Géneros", "Género"),
                                             M_("Horas por género (Top 8)"), precision=1,
                                             sort_desc=True)))
    v.append(("porgenero", inner(c_cnt), chart("barChart", C_("Artistas", "Género principal"),
                                               M_("Artistas por género (Top 8)"), sort_desc=True)))
    v.append(("detalle", inner(c_tab), table(
        [C_("Artistas", "Artista"), C_("Artistas", "Género principal"), C_("Artistas", "Géneros")],
        sort_field=C_("Artistas", "Artista"), descending=False)))
    pages.append(dict(
        key="artistas", display="Artistas y géneros", bg="bg_artistas.svg",
        title="Artistas y géneros", strip=[(40, "Mes")],
        cards=[c_art, c_gen, c_cnt, c_tab],
        footer="El filtro de mes afecta los dos rankings. Géneros: etiquetas de Last.fm "
               "filtradas; pueden ser imprecisas.",
        visuals=v))

    # Page 4: Canciones
    c_top = (24, 132, 700, 572, "Canciones más escuchadas")
    c_dec = (740, 132, 516, 250, "Reproducciones por década de lanzamiento")
    c_org = (740, 398, 250, 306, "Origen de la reproducción")
    c_exp = (1006, 398, 250, 306, "Contenido explícito")
    v = [("slicer-fecha", (170, 70, 420, 44), slicer(C_("Calendario", "Fecha"), "Between"))]
    v.append(("canciones", inner(c_top), table(
        [C_("Canciones", "Canción"), C_("Canciones", "Artista principal"),
         M_("Total de reproducciones")],
        sort_field=M_("Total de reproducciones"), compact=True)))
    v.append(("decada", inner(c_dec), chart("clusteredColumnChart", C_("Canciones", "Década"),
                                            M_("Total de reproducciones"))))
    v.append(("origen", inner(c_org), donut(C_("Reproducciones", "Origen"),
                                            M_("Total de reproducciones"))))
    v.append(("explicito", inner(c_exp), donut(C_("Canciones", "Contenido"),
                                               M_("Total de reproducciones"))))
    pages.append(dict(
        key="canciones", display="Canciones", bg="bg_canciones.svg", title="Canciones",
        strip=[(40, "Rango de fechas")], cards=[c_top, c_dec, c_org, c_exp],
        footer="Cada canción se cuenta por reproducción. Con pocos datos casi todas aparecen una vez.",
        visuals=v))

    # Page 5: Álbumes, a gallery of the top covers
    cards = []
    v = [("slicer-fecha", (170, 70, 420, 44), slicer(C_("Calendario", "Fecha"), "Between"))]
    for i in range(ALBUM_SLOTS):
        x, y = 24 + (i % 4) * 312, 132 + (i // 4) * 288
        cards.append((x, y, 296, 272, None))
        v.append((f"portada{i + 1}", (x + 48, y + 14, 200, 200),
                  image_kpi(f"Portada #{i + 1}", entity="_Measures")))
        v.append((f"titulo{i + 1}", (x + 4, y + 218, 288, 50),
                  image_kpi(f"P5_Album{i + 1}_Caption_SVG")))
    pages.append(dict(
        key="albumes", display="Álbumes", bg="bg_albumes.svg", title="Álbumes",
        strip=[(40, "Rango de fechas")], cards=cards,
        footer="Portadas de Spotify. Orden por reproducciones; en un empate gana el álbum "
               "escuchado más recientemente.",
        visuals=v))
    return pages


def write_report():
    clean_tree(REPORT_DIR)
    pages = build_pages()
    page_ids = {p["key"]: gid("page:" + p["key"]).replace("-", "")[:20] for p in pages}

    resource_items = [{"name": p["bg"], "path": p["bg"], "type": "Image"} for p in pages]
    resource_items.append(
        {"name": THEME_NAME, "path": f"{THEME_NAME}.json", "type": "CustomTheme"})
    versions = {"visual": "2.6.0", "report": "3.1.0", "page": "2.3.0"}
    write_json(os.path.join(DEF_DIR, "report.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                   "report/3.2.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY26SU02", "reportVersionAtImport": versions,
                          "type": "SharedResources"},
            "customTheme": {"name": THEME_NAME, "reportVersionAtImport": versions,
                            "type": "RegisteredResources"},
        },
        "objects": {"section": [{"properties": {"verticalAlignment": lit("'Top'")}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY26SU02", "path": "BaseThemes/CY26SU02.json",
                        "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": resource_items},
        ],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
        },
    })
    write_json(os.path.join(DEF_DIR, "version.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                   "versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    write_json(os.path.join(PAGES_DIR, "pages.json"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                   "pagesMetadata/1.0.0/schema.json",
        "pageOrder": [page_ids[p["key"]] for p in pages],
        "activePageName": page_ids[pages[0]["key"]],
    })
    write_json(os.path.join(REPORT_DIR, "definition.pbir"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                   "definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })
    write_json(os.path.join(REPORT_DIR, ".platform"), platform("Report"))

    os.makedirs(BASE_THEME_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "build", "assets", "CY26SU02.json"),
                    os.path.join(BASE_THEME_DIR, "CY26SU02.json"))
    write_json(os.path.join(RES_DIR, f"{THEME_NAME}.json"), theme())

    for p in pages:
        write_utf8(os.path.join(RES_DIR, p["bg"]),
                   background_svg(p["title"], p["strip"], p["cards"], p["footer"]))
        pid = page_ids[p["key"]]
        write_json(os.path.join(PAGES_DIR, pid, "page.json"), {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                       "definition/page/2.1.0/schema.json",
            "name": pid,
            "displayName": p["display"],
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
            "objects": {
                "outspace": [{"properties": {"color": {"solid": {"color": lit(f"'{CANVAS}'")}}}}],
                "background": [{"properties": {
                    "transparency": lit("0D"),
                    "image": {"image": {
                        "name": lit(f"'{p['bg']}'"),
                        "url": {"expr": {"ResourcePackageItem": {
                            "PackageName": "RegisteredResources", "PackageType": 1,
                            "ItemName": p["bg"]}}},
                        "scaling": lit("'Fill'"),
                    }},
                }}],
            },
        })
        for i, (vname, box, visual) in enumerate(p["visuals"], start=1):
            name = f"{p['key'][:3]}{i:03d}"
            write_json(os.path.join(PAGES_DIR, pid, "visuals", name, "visual.json"),
                       container(name, box, i, visual))


def write_project_file():
    write_json(os.path.join(ROOT, f"{NAME}.pbip"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/"
                   "1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })


def check_no_bom():
    bad = []
    for base, _, files in os.walk(ROOT):
        if os.sep + ".claude" in base or os.sep + "build" in base:
            continue
        for f in files:
            if f.endswith((".tmdl", ".json", ".svg", ".pbip", ".pbir", ".pbism")):
                with open(os.path.join(base, f), "rb") as fh:
                    if fh.read(3) == b"\xef\xbb\xbf":
                        bad.append(os.path.join(base, f))
    if bad:
        raise SystemExit("BOM found in: " + ", ".join(bad))


if __name__ == "__main__":
    write_model()
    write_report()
    write_project_file()
    check_no_bom()
    print("Built", NAME, "- tables:", len(build_tables()), "- pages:", len(build_pages()))
