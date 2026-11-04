from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_starts_with_disclaimer_and_tabs():
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("not a religious ruling" in i.value for i in at.info)
    assert len(at.tabs) == 4


def test_typed_barcode_without_network_shows_error_not_crash(monkeypatch):
    from halalcheck import off

    def fake_get(url, params, session=None):
        raise off.OFFError("Could not reach Open Food Facts. Try again in a minute.")

    monkeypatch.setattr(off, "_get", fake_get)
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="barcode_text").set_value("5449000000996")
    at.button(key="go_barcode").click().run()
    assert not at.exception
    assert any("Could not reach" in e.value for e in at.error)


def test_typed_barcode_shows_verdict(monkeypatch):
    from halalcheck import off

    payload = {
        "status": 1,
        "product": {"code": "5449000000996", "product_name": "Gummies", "ingredients_text": "sugar, pork gelatin", "countries_tags": []},
    }
    monkeypatch.setattr(off, "_get", lambda url, params, session=None: payload)
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="barcode_text").set_value("5449000000996")
    at.button(key="go_barcode").click().run()
    assert not at.exception
    assert any("Not halal" in e.value for e in at.error)
