import pandas as pd

from spotify_app import labels


def test_known_database_names_become_readable_labels():
    assert labels.label("artist_name") == "Artista"
    assert labels.label("Reproducciones") == "Reproducciones"
    assert labels.label("play_hour") == "Hora"


def test_unknown_names_lose_their_underscores_and_get_a_capital():
    assert labels.label("dias_con_datos") == "Dias con datos"


def test_friendly_renames_columns_but_not_the_values():
    frame = pd.DataFrame({"artist_name": ["A"], "reproducciones": [3]})
    shown = labels.friendly(frame)
    assert list(shown.columns) == ["Artista", "Reproducciones"]
    assert shown.iloc[0, 0] == "A"


def test_two_columns_that_would_get_the_same_label_keep_their_own_names():
    frame = pd.DataFrame({"artist": ["A"], "artist_name": ["A"], "plays": [1]})
    assert list(labels.friendly(frame).columns) == ["artist", "artist_name", "Reproducciones"]
