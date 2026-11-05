import re
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("DEV_SHOW_CODE", "1")
    monkeypatch.setenv("ADMIN_EMAILS", "boss@uchicago.edu")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    import streamlit as st

    st.cache_data.clear()  # product lookups are cached between runs


def new_app():
    return st_testing.AppTest.from_file(APP, default_timeout=30).run()


def texts(at):
    return [m.value for m in at.markdown] + [c.value for c in at.caption]


def sign_in(at, email, nickname):
    at.text_input(key="li_email").set_value(email)
    at.button(key="li_send").click().run()
    assert not at.exception, at.exception
    code = re.search(r"code is (\d{6})", " ".join(i.value for i in at.info)).group(1)
    at.text_input(key="li_code").set_value(code)
    at.button(key="li_verify").click().run()
    if at.text_input(key="li_nick") is not None and any(t.key == "li_nick" for t in at.text_input):
        at.text_input(key="li_nick").set_value(nickname)
        at.button(key="li_join").click().run()
    assert not at.exception, at.exception
    return at


def test_signed_out_screen(env):
    at = new_app()
    assert not at.exception
    assert any("Ppl" in t for t in texts(at))
    assert any("not a religious ruling" in t for t in texts(at))
    assert any("Join your community" in t for t in texts(at))
    assert {"Plates", "Events", "Food check", "You"} <= {t.label for t in at.tabs}


def test_wrong_domain_is_refused(env):
    at = new_app()
    at.text_input(key="li_email").set_value("someone@gmail.com")
    at.button(key="li_send").click().run()
    assert any("only for people with a uchicago.edu" in e.value for e in at.error)


def test_sign_in_share_plate_and_see_it(env):
    at = sign_in(new_app(), "anaya@uchicago.edu", "Anaya")
    assert any("No plates right now" in t for t in texts(at))
    at.text_area(key="pl_body").set_value("Made dal today, one plate left. Want it?")
    at.text_input(key="pl_place").set_value("Harper entrance")
    at.text_area(key="pl_ing").set_value("Lentils, onion, ghee. Contains dairy.")
    at.checkbox(key="pl_safe").check()
    at.button(key="pl_submit").click().run()
    assert not at.exception, at.exception
    assert any("Made dal today" in t and "Anaya" in t for t in texts(at))


def test_plate_needs_ingredients_and_safety_check(env):
    at = sign_in(new_app(), "anaya@uchicago.edu", "Anaya")
    at.text_area(key="pl_body").set_value("Made dal today, one plate left. Want it?")
    at.text_input(key="pl_place").set_value("Harper entrance")
    at.button(key="pl_submit").click().run()
    assert any("packed and stored safely" in e.value for e in at.error)


def test_friend_can_claim_a_plate(env):
    cook = sign_in(new_app(), "anaya@uchicago.edu", "Anaya")
    cook.text_area(key="pl_body").set_value("Made kebabs, 12 in a box. Want to try some?")
    cook.text_input(key="pl_place").set_value("Ida Noyes steps")
    cook.text_area(key="pl_ing").set_value("Beef, onion, spices. No nuts.")
    cook.checkbox(key="pl_safe").check()
    cook.button(key="pl_submit").click().run()

    friend = sign_in(new_app(), "bilal@uchicago.edu", "Bilal")
    assert any("Made kebabs" in t for t in texts(friend))
    claim = [b for b in friend.button if b.key and b.key.startswith("claim_")][0]
    claim.click().run()
    assert not friend.exception, friend.exception
    assert any("You said yes" in s.value for s in friend.success)


def test_food_check_is_open_without_signing_in(env, monkeypatch):
    from halalcheck import off

    payload = {
        "status": 1,
        "product": {"code": "5449000000996", "product_name": "Gummies", "ingredients_text": "sugar, pork gelatin", "countries_tags": []},
    }
    monkeypatch.setattr(off, "_get", lambda url, params, session=None: payload)
    at = new_app()
    at.text_input(key="barcode_text").set_value("5449000000996")
    at.button(key="go_barcode").click().run()
    assert not at.exception
    assert any("Not halal" in m.value and "v-no" in m.value for m in at.markdown)


def test_food_check_network_error_is_shown_not_a_crash(env, monkeypatch):
    from halalcheck import off

    def fake_get(url, params, session=None):
        raise off.OFFError("Could not reach Open Food Facts. Try again in a minute.")

    monkeypatch.setattr(off, "_get", fake_get)
    at = new_app()
    at.text_input(key="barcode_text").set_value("5449000000996")
    at.button(key="go_barcode").click().run()
    assert not at.exception
    assert any("Could not reach" in e.value for e in at.error)


def test_admin_sees_admin_panel(env):
    at = sign_in(new_app(), "boss@uchicago.edu", "Boss")
    assert any("Admin" in t for t in texts(at))
    assert any("No open reports" in t for t in texts(at))
