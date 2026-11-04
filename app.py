"""Halal Check: Streamlit app. Run with: streamlit run app.py"""
from __future__ import annotations

import os

import streamlit as st

from halalcheck import feedback, off, pipeline, rules, vision

st.set_page_config(page_title="Halal Check", page_icon="🥗", layout="centered")

VISION_CAP = int(os.getenv("VISION_CALLS_PER_SESSION", "12"))
DISCLAIMER = (
    "Halal Check gives information, not a religious ruling. Scholars and certifiers "
    "differ, and recipes change. When it matters, look for a halal logo from a "
    "certifier you trust, or ask the maker."
)


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets file locally
        value = None
    return str(value or os.getenv(name, default))


GEMINI_KEY = secret("GEMINI_API_KEY")
WEBHOOK = secret("FEEDBACK_WEBHOOK_URL")


# ---------------------------------------------------------------- cached lookups


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def cached_product(code: str):
    return off.get_product(code)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def cached_search(query: str, country_tag: str | None):
    return off.search_products(query, country_tag=country_tag, limit=6)


def spend_vision() -> bool:
    used = st.session_state.get("vision_calls", 0)
    if not GEMINI_KEY:
        st.info("Photo reading needs a Gemini API key. You can still type a barcode or a product name.")
        return False
    if used >= VISION_CAP:
        st.warning("You have used all the photo checks for this visit. Reload the page later, or type a barcode.")
        return False
    st.session_state["vision_calls"] = used + 1
    return True


def image_input(key: str, label: str) -> bytes | None:
    uploaded = st.file_uploader(label, type=["jpg", "jpeg", "png", "webp"], key=f"up_{key}")
    with st.expander("Or use the camera"):
        shot = st.camera_input("Take a photo", key=f"cam_{key}")
    chosen = shot or uploaded
    return chosen.getvalue() if chosen else None


# ---------------------------------------------------------------- display


def show_result(result: pipeline.Result, extra: dict | None = None) -> None:
    a = result.analysis
    if result.title:
        st.subheader(result.title)
    box = {
        rules.NOT_HALAL: st.error,
        rules.DOUBTFUL: st.warning,
        rules.LOOKS_HALAL: st.success,
        rules.UNKNOWN: st.info,
    }[a.verdict]
    box(f"**{a.headline}**")

    flagged = [m for m in a.matches if m.status in ("prohibited", "doubtful", "check")]
    if flagged:
        st.markdown("**What the rules found**")
        for m in flagged:
            icon = {"prohibited": "🔴", "doubtful": "🟠", "check": "🟡"}[m.status]
            cleared = " (the label says it is halal, so this is lower risk)" if m.cleared else ""
            line = f"{icon} **{m.text}** ({m.label}): {m.reason}{cleared}"
            if m.note:
                line += f" _{m.note}_"
            st.markdown(line)
    if a.verify:
        st.markdown("**What to check or ask**")
        for item in a.verify:
            st.markdown(f"- {item}")
    for note in list(a.notes) + result.warnings:
        st.caption(note)

    st.session_state["last"] = {
        "source": result.source,
        "verdict": a.verdict,
        "rule_ids": [m.rule_id for m in a.matches],
        "rulebook_version": rules.load_rulebook().version,
        **(extra or {}),
    }


def feedback_form() -> None:
    last = st.session_state.get("last")
    if not last:
        return
    with st.expander("Report a wrong or missing result"):
        reason = st.selectbox("What went wrong?", feedback.REASONS, key="fb_reason")
        comment = st.text_area("Details (optional, no personal info)", max_chars=400, key="fb_comment")
        if st.button("Send report", key="fb_send"):
            ok = feedback.log_feedback({**last, "reason": reason, "comment": comment}, webhook=WEBHOOK or None)
            st.success("Thank you. Your report was saved." if ok else "Sorry, the report could not be saved.")


# ---------------------------------------------------------------- page

st.title("🥗 Halal Check")
st.caption("Scan or search a food. See why it looks halal, doubtful or not halal.")
st.info(DISCLAIMER)

country_name = st.selectbox(
    "Where will you buy or eat this?",
    list(off.COUNTRIES),
    help="Used only to find the right version of a product. It is not saved.",
)
country_tag = off.COUNTRIES[country_name]

tab_barcode, tab_label, tab_name, tab_dish = st.tabs(
    ["Barcode", "Ingredient label", "Product name", "Dish photo"]
)

with tab_barcode:
    st.write("Most exact. A barcode points to one specific product.")
    typed = st.text_input("Type the barcode digits", key="barcode_text", placeholder="e.g. 5449000000996")
    photo = image_input("barcode", "Or photograph the barcode")
    if st.button("Check barcode", key="go_barcode"):
        try:
            code = off.normalize_barcode(typed)
            if code is None and photo:
                if spend_vision():
                    with st.spinner("Reading the barcode..."):
                        code = vision.read_barcode(photo, api_key=GEMINI_KEY)
                    if code is None:
                        st.warning("Could not read the barcode digits. Type them in, or photograph the ingredient list.")
            elif code is None:
                st.warning("Type the barcode digits or add a photo.")
            if code:
                with st.spinner("Looking up the product..."):
                    product = cached_product(code)
                if product is None:
                    st.warning("This barcode is not in Open Food Facts yet. Photograph the ingredient list instead.")
                else:
                    show_result(pipeline.check_product(product, country_tag, "barcode"), {"product_code": product.code})
        except (off.OFFError, vision.VisionError) as exc:
            st.error(str(exc))

with tab_label:
    st.write("Reads the ingredient list on the pack in your hand.")
    photo = image_input("label", "Photograph the ingredient list")
    if st.button("Check ingredient list", key="go_label"):
        if not photo:
            st.warning("Add a photo first.")
        elif spend_vision():
            try:
                with st.spinner("Reading the label..."):
                    reading = vision.read_label(photo, api_key=GEMINI_KEY)
                show_result(pipeline.check_label(reading))
                if reading.ingredients_text:
                    with st.expander("Text read from your photo"):
                        st.write(reading.ingredients_text)
            except vision.VisionError as exc:
                st.error(str(exc))

with tab_name:
    st.write("Search by name. Good for a quick look, but the exact recipe may differ.")
    query = st.text_input("Product name", key="name_query", placeholder="e.g. Doritos Nacho Cheese")
    if st.button("Search", key="go_search"):
        try:
            with st.spinner("Searching..."):
                st.session_state["matches"] = cached_search(query.strip(), country_tag)
            if not st.session_state["matches"]:
                st.warning("No matches. Try fewer words, or scan the barcode.")
        except off.OFFError as exc:
            st.error(str(exc))
    matches = st.session_state.get("matches") or []
    if matches:
        labels = [f"{p.name or p.code} - {p.brands}".strip(" -") + (f" ({p.quantity})" if p.quantity else "") for p in matches]
        pick = st.selectbox("Which one is yours?", range(len(matches)), format_func=lambda i: labels[i], key="name_pick")
        chosen = matches[pick]
        if chosen.image_url:
            st.image(chosen.image_url, width=120)
        if st.button("Check this product", key="go_pick"):
            show_result(pipeline.check_product(chosen, country_tag, "name"), {"product_code": chosen.code})

with tab_dish:
    st.write("For a plated meal. A photo cannot show how food was sourced, so this gives questions to ask, not a verdict.")
    photo = image_input("dish", "Photograph the dish")
    if st.button("Look at this dish", key="go_dish"):
        if not photo:
            st.warning("Add a photo first.")
        elif spend_vision():
            try:
                with st.spinner("Looking at the dish..."):
                    reading = vision.identify_dish(photo, api_key=GEMINI_KEY)
                show_result(pipeline.check_dish(reading))
            except vision.VisionError as exc:
                st.error(str(exc))

feedback_form()
st.divider()
st.caption(DISCLAIMER)
st.caption("Product data: Open Food Facts (ODbL). Photos are sent to Google Gemini to be read, are not stored by this app, and location is never saved.")
