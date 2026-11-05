"""Community screens: plates, events and the You tab."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import streamlit as st

from halalcheck import theme

from . import auth, copy, posts
from .timefmt import TZ, local, to_epoch


def _flash(message: str) -> None:
    st.session_state["flash"] = message


def show_flash() -> None:
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def _run(action, *args, ok: str = "", **kwargs) -> bool:
    """Run a posts.* action. Show a friendly error, or a message on success."""
    try:
        action(*args, **kwargs)
    except (posts.PostError, auth.AuthError) as exc:
        st.error(str(exc))
        return False
    if ok:
        _flash(ok)
    return True


# ---------------------------------------------------------------- plates


def _plate_actions(engine, user, p: dict, claimed: dict | None, now: int) -> None:
    pid = p["id"]
    mine = p["user_id"] == user["id"]

    if mine:
        claimers = posts.list_claimers(engine, pid)
        if claimers:
            st.markdown("**Who said yes**")
            for c in claimers:
                said = copy.RATINGS.get(c["rating"], "")
                line = f"{c['nickname']}" + (f": {said}" if said else "")
                if c["note"]:
                    line += f". \"{c['note']}\""
                st.markdown(f"- {line}")
        if p["state"] == "open" and st.button("All shared", key=f"close_{pid}", type="tertiary"):
            if _run(posts.close_post, engine, user, pid, ok=copy.ALL_SHARED):
                st.rerun()
    elif claimed:
        st.success(f"You said yes. Pick it up at {p['place']}.")
        if claimed["rating"] is None:
            with st.expander("How was it?"):
                rating = st.radio(
                    "Tell the cook what you thought",
                    list(copy.RATINGS),
                    format_func=copy.RATINGS.get,
                    key=f"rate_{pid}",
                    horizontal=False,
                )
                note = st.text_input("Say a few words (optional)", key=f"note_{pid}", max_chars=200)
                if st.button("Send", key=f"send_rate_{pid}"):
                    if _run(posts.rate_claim, engine, user, pid, rating, note, ok="Thank you. The cook will love that."):
                        st.rerun()
        else:
            st.caption(f"You told the cook: {copy.RATINGS.get(claimed['rating'], '')}")
        if p["state"] == "open" and claimed["rating"] is None:
            if st.button(copy.UNCLAIM, key=f"unclaim_{pid}", type="tertiary"):
                posts.unclaim(engine, user, pid)
                st.rerun()
    elif p["state"] == "open":
        if st.button(copy.CLAIM, key=f"claim_{pid}"):
            if _run(posts.claim, engine, user, pid, ok="Lovely. Check the pickup spot below."):
                st.rerun()

    replies = posts.list_replies(engine, pid)
    with st.expander(f"Say hi ({len(replies)})" if replies else "Say hi"):
        for r in replies:
            st.markdown(
                f'<div class="reply"><b>{theme.esc(r["nickname"])}</b> {theme.esc(r["body"])}</div>',
                unsafe_allow_html=True,
            )
        text = st.text_input("Write a message", key=f"reply_{pid}", max_chars=300)
        if st.button("Send message", key=f"send_reply_{pid}"):
            if _run(posts.add_reply, engine, user, pid, text):
                st.rerun()
        if not mine:
            reason = st.text_input("Something wrong with this post? Tell us", key=f"why_{pid}", max_chars=200)
            if st.button("Report this post", key=f"report_{pid}", type="tertiary"):
                if _run(posts.report_post, engine, user, pid, reason, ok="Thank you. An admin will take a look."):
                    st.rerun()


def plates_tab(engine, user: dict, now: int) -> None:
    with st.expander("Share a plate"):
        with st.form("plate_form", clear_on_submit=True):
            body = st.text_area(
                copy.PLATE_HINT,
                placeholder=copy.PLATE_PLACEHOLDER,
                max_chars=400,
                key="pl_body",
            )
            c1, c2 = st.columns(2)
            portions = c1.number_input("How many plates?", min_value=1, max_value=50, value=1, key="pl_portions")
            window = c2.selectbox("Available for", list(copy.WINDOWS), key="pl_window")
            place = st.text_input("Where can they pick it up?", placeholder=copy.PLACE_PLACEHOLDER, max_chars=80, key="pl_place")
            ingredients = st.text_area(
                "Ingredients and allergens",
                placeholder=copy.INGREDIENTS_PLACEHOLDER,
                max_chars=300,
                key="pl_ing",
                height=80,
            )
            tag = st.selectbox("Where is it from?", list(copy.TAGS), format_func=copy.TAGS.get, key="pl_tag")
            safe = st.checkbox(copy.SAFE_LABEL, key="pl_safe")
            go = st.form_submit_button("Share", key="pl_submit")
        if go:
            try:
                posts.create_plate(
                    engine,
                    user,
                    body=body,
                    portions=portions,
                    place=place,
                    minutes=copy.WINDOWS[window],
                    ingredients=ingredients,
                    tag=tag,
                    safe_ok=safe,
                )
            except posts.PostError as exc:
                st.error(str(exc))
            else:
                _flash("Shared. Thank you for sharing.")
                st.rerun()

    items = posts.list_plates(engine, now=now)
    if not items:
        st.markdown(
            '<div class="empty">No plates right now.<br>Cooked too much? Tap "Share a plate" and tell your friends.</div>',
            unsafe_allow_html=True,
        )
        return
    mine = posts.my_claims(engine, user["id"])
    for p in items:
        st.markdown(theme.plate_card_html(p, now), unsafe_allow_html=True)
        _plate_actions(engine, user, p, mine.get(p["id"]), now)


# ---------------------------------------------------------------- events


def events_tab(engine, user: dict, now: int) -> None:
    if user["is_organizer"] or user["is_admin"]:
        with st.expander("Post an event"):
            with st.form("event_form", clear_on_submit=True):
                title = st.text_input("Event name", max_chars=100, key="ev_title")
                body = st.text_area("Details", max_chars=400, key="ev_body", height=90)
                tomorrow = local(now).date() + timedelta(days=1)
                c1, c2 = st.columns(2)
                day = c1.date_input("Day", value=tomorrow, key="ev_day")
                clock = c2.time_input("Starts at", value=datetime(2000, 1, 1, 18, 0).time(), key="ev_time", step=900)
                place = st.text_input("Where", max_chars=80, key="ev_place")
                go = st.form_submit_button("Post event", key="ev_submit")
            if go:
                try:
                    posts.create_event(engine, user, title=title, body=body, starts_at=to_epoch(day, clock), place=place)
                except posts.PostError as exc:
                    st.error(str(exc))
                else:
                    _flash("Event posted.")
                    st.rerun()
    items = posts.list_events(engine, now=now)
    if not items:
        st.markdown('<div class="empty">No events yet.<br>Organizers will post them here.</div>', unsafe_allow_html=True)
    for e in items:
        st.markdown(theme.event_card_html(e, now), unsafe_allow_html=True)
        reason = ""
        if e["user_id"] != user["id"]:
            with st.expander("Report this post"):
                reason = st.text_input("What is wrong?", key=f"ev_why_{e['id']}", max_chars=200)
                if st.button("Send report", key=f"ev_report_{e['id']}"):
                    if _run(posts.report_post, engine, user, e["id"], reason, ok="Thank you. An admin will take a look."):
                        st.rerun()
    if not (user["is_organizer"] or user["is_admin"]):
        st.caption("Want to post an event for your group? Ask an admin to make you an organizer.")


# ---------------------------------------------------------------- you


def you_tab(engine, user: dict, settings, token: str | None) -> bool:
    """Returns True when the person signed out or deleted the account."""
    st.markdown(f'<div class="title">{theme.esc(user["nickname"])}</div>', unsafe_allow_html=True)
    st.caption(
        "Peopl does not save your email address. It keeps a scrambled version so it can recognise you."
    )
    if st.button("Sign out", key="signout"):
        auth.sign_out(engine, token, pepper=settings.pepper)
        return True
    with st.expander("Delete my account"):
        st.write("This removes your account, your plates, your events and your messages. It can't be undone.")
        sure = st.checkbox("Yes, delete everything", key="del_sure")
        if st.button("Delete my account", key="del_go", disabled=not sure):
            auth.delete_account(engine, user["id"])
            return True

    if user["is_admin"]:
        st.markdown('<div class="title" style="margin-top:1.4rem">Admin</div>', unsafe_allow_html=True)
        reports = posts.list_reports(engine, user)
        if not reports:
            st.caption("No open reports.")
        for r in reports:
            st.markdown(
                f'<div class="post"><div class="muted">Reported: {theme.esc(r["reason"])}</div>'
                f'<div class="bubble" style="margin-top:.5rem">{theme.esc(r["body"])}</div>'
                f'<div class="muted" style="margin-top:.5rem">By {theme.esc(r["author"])}</div></div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3 = st.columns(3)
            if c1.button("Hide post", key=f"hide_{r['report_id']}"):
                posts.hide_post(engine, user, r["post_id"])
                st.rerun()
            if c2.button("Dismiss", key=f"dismiss_{r['report_id']}"):
                posts.dismiss_report(engine, user, r["report_id"])
                st.rerun()
            if c3.button("Ban", key=f"ban_{r['report_id']}"):
                if _run(posts.ban_user, engine, user, r["author_id"]):
                    st.rerun()
        with st.form("organizer_form", clear_on_submit=True):
            nick = st.text_input("Make someone an organizer (their nickname)", key="org_nick")
            make = st.form_submit_button("Make organizer", key="org_go")
        if make:
            if _run(posts.set_organizer, engine, user, nick, True, ok=f"{nick} can now post events."):
                st.rerun()
    return False
