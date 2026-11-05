"""Ppl: a closed-loop community table for UChicago. Run with: streamlit run app.py"""
from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st

from halalcheck import theme
from halalcheck import ui as foodcheck
from ppl import auth, db, mail
from ppl import ui as community
from ppl.settings import load_settings

try:
    from PIL import Image

    _ICON = Image.open(Path(__file__).parent / "assets" / "icon.png")
except Exception:  # fall back to an emoji if the file is missing
    _ICON = "🍽️"

st.set_page_config(page_title="Ppl", page_icon=_ICON, layout="centered")
st.markdown(theme.CSS, unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets file locally
        value = None
    return str(value or os.getenv(name, default))


@st.cache_resource(show_spinner=False)
def get_engine(url: str | None):
    return db.make_engine(url)


settings = load_settings(secret)
engine = get_engine(settings.database_url)


# ---------------------------------------------------------------- sign in


def _sender(email: str, code: str) -> None:
    if mail.smtp_configured(secret):
        mail.send_code_email(email, code, get=secret)
    elif settings.dev_show_code:
        st.session_state["dev_code"] = code
    else:
        raise auth.AuthError("Sign-in email is not set up yet. Ask the person who runs Ppl.")


def _finish_login(user: dict) -> None:
    user = auth.sync_admin(engine, user, user["email_hash"] in settings.admin_hashes)
    token = auth.create_session(engine, user["id"], pepper=settings.pepper)
    st.query_params["s"] = token
    st.session_state.update(user=user, token=token, stage="email")
    for k in ("pending_email", "pending_hash", "dev_code"):
        st.session_state.pop(k, None)
    st.rerun()


def current_user() -> dict | None:
    user = st.session_state.get("user")
    if user:
        fresh = auth.get_user(engine, user["id"])
        if fresh and not fresh["banned"]:
            st.session_state["user"] = fresh
            return fresh
        st.session_state.pop("user", None)
        st.session_state.pop("token", None)
        return None
    token = st.query_params.get("s")
    found = auth.get_user_for_token(engine, token, pepper=settings.pepper)
    if found:
        st.session_state["user"], st.session_state["token"] = found, token
    return found


def sign_in_card() -> None:
    stage = st.session_state.get("stage", "email")
    domains = " or ".join(settings.domains)
    st.markdown(
        f'<div class="gate"><b>Join your community</b><p class="muted">Sign in with your {theme.esc(domains)} email. '
        "We send a 6-digit code. There is no password.</p></div>",
        unsafe_allow_html=True,
    )
    if stage == "email":
        email = st.text_input("Your university email", key="li_email", placeholder="you@uchicago.edu")
        if st.button("Email me a code", key="li_send"):
            try:
                auth.request_code(engine, email, pepper=settings.pepper, domains=settings.domains, send=_sender)
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                st.session_state.update(stage="code", pending_email=email)
                st.rerun()
    elif stage == "code":
        st.caption(f"Code sent to {st.session_state.get('pending_email', '')}. It works for 10 minutes.")
        if settings.dev_show_code and st.session_state.get("dev_code"):
            st.info(f"Test mode. Your code is {st.session_state['dev_code']}")
        code = st.text_input("6-digit code", key="li_code", max_chars=6)
        if st.button("Sign in", key="li_verify"):
            try:
                h = auth.verify_code(engine, st.session_state.get("pending_email"), code, pepper=settings.pepper)
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                existing = auth.get_user_by_hash(engine, h)
                if existing and not existing["banned"]:
                    _finish_login(existing)
                elif existing:
                    st.error("This email can't sign in.")
                else:
                    st.session_state.update(stage="nickname", pending_hash=h)
                    st.rerun()
        if st.button("Use a different email", key="li_back", type="tertiary"):
            st.session_state.update(stage="email")
            st.rerun()
    else:
        nick = st.text_input("Pick a nickname friends will see", key="li_nick", max_chars=24, placeholder="For example: Sara")
        if st.button("Join", key="li_join"):
            try:
                user = auth.create_user(engine, st.session_state["pending_hash"], nick, admin_hashes=settings.admin_hashes)
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                _finish_login(user)


# ---------------------------------------------------------------- page

now = int(time.time())
user = current_user()

st.markdown(theme.header_html(), unsafe_allow_html=True)
if settings.pepper_is_default and not settings.dev_show_code:
    st.warning("APP_SECRET is not set. Set it before real people sign in.")
community.show_flash()
if not user:
    sign_in_card()

t_plates, t_events, t_check, t_you = st.tabs(["Plates", "Events", "Food check", "You"])

with t_plates:
    if user:
        community.plates_tab(engine, user, now)
    else:
        st.markdown('<div class="empty">Sign in to see plates your friends are sharing.</div>', unsafe_allow_html=True)

with t_events:
    if user:
        community.events_tab(engine, user, now)
    else:
        st.markdown('<div class="empty">Sign in to see what is happening around campus.</div>', unsafe_allow_html=True)

with t_check:
    foodcheck.render(secret("GEMINI_API_KEY"), secret("FEEDBACK_WEBHOOK_URL"))

with t_you:
    if user:
        if community.you_tab(engine, user, settings, st.session_state.get("token")):
            for k in ("user", "token"):
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()
    else:
        st.markdown('<div class="empty">You are not signed in.</div>', unsafe_allow_html=True)

st.markdown(
    f'<p class="foot">{theme.esc(foodcheck.DISCLAIMER)}</p>'
    '<p class="foot">Product data: Open Food Facts (ODbL). Photos are sent to Google Gemini to be read. '
    "This app does not store them, and your location is never saved. Ppl is a student project and is not run by the University of Chicago.</p>",
    unsafe_allow_html=True,
)
