"""Food check screen: barcode, label photo, name search and dish photo."""
from __future__ import annotations

import os

import streamlit as st

from . import feedback, off, pipeline, rules, theme, vision

VISION_CAP = int(os.getenv("VISION_CALLS_PER_SESSION", "12"))
DISCLAIMER = (
    "Peopl gives information, not a religious ruling. Scholars and certifiers "
    "differ, and recipes change. When it matters, look for a halal logo from a "
    "certifier you trust, or ask the maker."
)


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def cached_product(code: str):
    return off.get_product(code)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def cached_search(query: str, country_tag: str | None):
    return off.search_products(query, country_tag=country_tag, limit=6)


def _spend_vision(gemini_key: str) -> bool:
    used = st.session_state.get("vision_calls", 0)
    if not gemini_key:
        st.info("Photo reading needs a Gemini API key. You can still type a barcode or a product name.")
        return False
    if used >= VISION_CAP:
        st.warning("You have used all the photo checks for this visit. Reload the page later, or type a barcode.")
        return False
    st.session_state["vision_calls"] = used + 1
    return True


def _image_input(key: str, label: str) -> bytes | None:
    uploaded = st.file_uploader(label, type=["jpg", "jpeg", "png", "webp"], key=f"up_{key}")
    with st.expander("Or use the camera"):
        shot = st.camera_input("Take a photo", key=f"cam_{key}")
    chosen = shot or uploaded
    return chosen.getvalue() if chosen else None


def _show_result(result: pipeline.Result, extra: dict | None = None) -> None:
    st.markdown(theme.result_html(result.analysis, result.title, result.warnings), unsafe_allow_html=True)
    st.session_state["last"] = {
        "source": result.source,
        "verdict": result.analysis.verdict,
        "rule_ids": [m.rule_id for m in result.analysis.matches],
        "rulebook_version": rules.load_rulebook().version,
        **(extra or {}),
    }


def _feedback_form(webhook: str) -> None:
    last = st.session_state.get("last")
    if not last:
        return
    with st.expander("Report a wrong or missing result"):
        reason = st.selectbox("What went wrong?", feedback.REASONS, key="fb_reason")
        comment = st.text_area("Details (optional, no personal info)", max_chars=400, key="fb_comment")
        if st.button("Send report", key="fb_send"):
            ok = feedback.log_feedback({**last, "reason": reason, "comment": comment}, webhook=webhook or None)
            st.success("Thank you. Your report was saved." if ok else "Sorry, the report could not be saved.")


def render(gemini_key: str, webhook: str = "") -> None:
    st.markdown(
        '<div class="title">Check what is in your food</div>'
        '<p class="sub">Scan a barcode or an ingredient list. See plain reasons, and what to ask before you eat.</p>',
        unsafe_allow_html=True,
    )
    country_name = st.selectbox(
        "Where will you buy or eat this?",
        list(off.COUNTRIES),
        help="Used only to find the right version of a product. It is not saved.",
    )
    country_tag = off.COUNTRIES[country_name]

    t_barcode, t_label, t_name, t_dish = st.tabs(["Barcode", "Label", "Name", "Dish"])

    with t_barcode:
        st.write("Most exact. A barcode points to one specific product.")
        typed = st.text_input("Type the barcode digits", key="barcode_text", placeholder="e.g. 5449000000996")
        photo = _image_input("barcode", "Or photograph the barcode")
        if st.button("Check barcode", key="go_barcode"):
            try:
                code = off.normalize_barcode(typed)
                if code is None and photo:
                    if _spend_vision(gemini_key):
                        with st.spinner("Reading the barcode..."):
                            code = vision.read_barcode(photo, api_key=gemini_key)
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
                        _show_result(pipeline.check_product(product, country_tag, "barcode"), {"product_code": product.code})
            except (off.OFFError, vision.VisionError) as exc:
                st.error(str(exc))

    with t_label:
        st.write("Reads the ingredient list on the pack in your hand.")
        photo = _image_input("label", "Photograph the ingredient list")
        if st.button("Check ingredient list", key="go_label"):
            if not photo:
                st.warning("Add a photo first.")
            elif _spend_vision(gemini_key):
                try:
                    with st.spinner("Reading the label..."):
                        reading = vision.read_label(photo, api_key=gemini_key)
                    _show_result(pipeline.check_label(reading))
                    if reading.ingredients_text:
                        with st.expander("Text read from your photo"):
                            st.write(reading.ingredients_text)
                except vision.VisionError as exc:
                    st.error(str(exc))

    with t_name:
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
            labels = [
                f"{p.name or p.code} - {p.brands}".strip(" -") + (f" ({p.quantity})" if p.quantity else "")
                for p in matches
            ]
            pick = st.selectbox("Which one is yours?", range(len(matches)), format_func=lambda i: labels[i], key="name_pick")
            chosen = matches[pick]
            if chosen.image_url:
                st.image(chosen.image_url, width=120)
            if st.button("Check this product", key="go_pick"):
                _show_result(pipeline.check_product(chosen, country_tag, "name"), {"product_code": chosen.code})

    with t_dish:
        st.write("For a plated meal. A photo cannot show how food was sourced, so this gives questions to ask, not a verdict.")
        photo = _image_input("dish", "Photograph the dish")
        if st.button("Look at this dish", key="go_dish"):
            if not photo:
                st.warning("Add a photo first.")
            elif _spend_vision(gemini_key):
                try:
                    with st.spinner("Looking at the dish..."):
                        reading = vision.identify_dish(photo, api_key=gemini_key)
                    _show_result(pipeline.check_dish(reading))
                except vision.VisionError as exc:
                    st.error(str(exc))

    _feedback_form(webhook)
