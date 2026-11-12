import pytest
from streamlit.testing.v1 import AppTest

from spotify_app.ui import has_cover


@pytest.mark.parametrize("value", [None, float("nan"), "", "   "])
def test_a_missing_cover_is_not_a_cover(value):
    assert not has_cover(value)


def test_a_url_is_a_cover():
    assert has_cover("https://i.scdn.co/image/abc")


@pytest.mark.parametrize("value", [None, float("nan"), ""])
def test_an_album_without_cover_shows_the_placeholder_instead_of_failing(value):
    def page(cover):
        from spotify_app.ui import show_cover

        show_cover(cover)

    app = AppTest.from_function(page, args=(value,)).run()
    assert not app.exception
    assert "Sin portada" in app.markdown[0].value

