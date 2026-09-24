"""Streamlit presentation layer for the FastAPI car assistant."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

from client.api import ApiClient, ApiError

st.set_page_config(
    page_title="dubizzle cars | Assistant",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

_STYLES = (Path(__file__).resolve().parent / ".streamlit" / "styles.css").read_text(
    encoding="utf-8"
)
st.markdown(f"<style>{_STYLES}</style>", unsafe_allow_html=True)


def _state() -> None:
    for key, default in (
        ("active_user_id", None),
        ("active_display_name", None),
        ("session_id", None),
        ("messages", []),
    ):
        if key not in st.session_state:
            st.session_state[key] = default


def _photo_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    return (
        value.strip() if parsed.scheme in {"http", "https"} and parsed.netloc else None
    )


def _number(value: object, suffix: str = "") -> str:
    return (
        f"{value:,}{suffix}"
        if isinstance(value, int) and not isinstance(value, bool)
        else "Not specified"
    )


def _display_car(car: dict) -> dict:
    """Keep only card fields in UI state; PostgreSQL owns the full record."""
    fields = (
        "listing_id",
        "year",
        "make",
        "model",
        "trim",
        "photo_url",
        "price_aed",
        "mileage_km",
    )
    result = {field: car.get(field) for field in fields}
    description = car.get("description_clean") or car.get("description")
    result["description_clean"] = (
        description[:240] if isinstance(description, str) else None
    )
    return result


def _vehicle_card(car: dict, position: int) -> None:
    with st.container(border=True):
        photo, details = st.columns([1, 2.1], vertical_alignment="top")
        with photo:
            image_url = _photo_url(car.get("photo_url"))
            if image_url:
                try:
                    st.image(image_url, width="stretch")
                except Exception:  # noqa: BLE001 - seller image may disappear.
                    st.caption("Image not available")
            else:
                st.caption("Image not available")
        with details:
            listing_id = car.get("listing_id") or "Listing ID not specified"
            st.caption(f"{position:02d}  ·  {listing_id}")
            title = " ".join(
                str(value).strip()
                for value in (
                    car.get("year"),
                    car.get("make"),
                    car.get("model"),
                    car.get("trim"),
                )
                if value is not None and str(value).strip()
            )
            st.subheader(title or "Vehicle details not specified")
            price, mileage = st.columns(2)
            with price:
                st.caption("Cash price")
                amount = _number(car.get("price_aed"))
                st.write(f"AED {amount}" if amount != "Not specified" else amount)
            with mileage:
                st.caption("Mileage")
                st.write(_number(car.get("mileage_km"), " km"))
            description = car.get("description_clean") or car.get("description")
            if isinstance(description, str) and description.strip():
                description = description.strip()
                st.caption("Seller description")
                st.write(description[:220] + ("…" if len(description) > 220 else ""))
                if len(description) > 220:
                    with st.expander("Read full description"):
                        st.write(description)


def _show_message(item: dict) -> None:
    with st.chat_message(item["role"]):
        if item.get("error"):
            st.error(item["content"])
        else:
            st.write(item["content"])
            for position, car in enumerate(item.get("cars") or [], 1):
                _vehicle_card(car, position)


def main() -> None:
    _state()
    try:
        api = ApiClient()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.markdown(
            '<div class="brand"><span class="brand-mark">✦</span>'
            '<div class="brand-name">dubizzle <span>cars</span></div></div>',
            unsafe_allow_html=True,
        )
        new_session = st.button(
            "New Session",
            type="primary",
            width="stretch",
            disabled=not st.session_state.active_user_id,
        )
        if new_session:
            try:
                session_id = api.create_session(
                    st.session_state.active_user_id,
                    st.session_state.active_display_name,
                )
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.session_state.session_id = session_id
                st.session_state.messages = []

        st.markdown(
            '<div class="side-label">YOUR PROFILE</div>', unsafe_allow_html=True
        )
        with st.form("identity_form"):
            display_name = st.text_input(
                "Your name", key="identity_name", placeholder="e.g. Amina"
            )
            start = st.form_submit_button("Start / switch user", width="stretch")
        if start:
            name = display_name.strip()
            if not name:
                st.error("Enter your name to start.")
            else:
                try:
                    if (
                        st.session_state.active_user_id
                        and name.casefold()
                        == st.session_state.active_display_name.casefold()
                    ):
                        user_id = st.session_state.active_user_id
                        session_id = api.create_session(user_id, name)
                    else:
                        user_id, session_id = api.start_user(name)
                except ApiError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.active_user_id = user_id
                    st.session_state.active_display_name = name
                    st.session_state.session_id = session_id
                    st.session_state.messages = []

        if st.session_state.session_id:
            st.markdown(
                '<div class="profile-pill">'
                f'<div class="profile-name">'
                f"{escape(st.session_state.active_display_name)}</div>"
                '<div class="profile-note">Your preferences stay with '
                "this profile</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Current session · {st.session_state.session_id[:8]}")
        else:
            st.markdown(
                '<div class="side-note">Enter your name to begin.</div>',
                unsafe_allow_html=True,
            )
        recent = [
            item["content"]
            for item in st.session_state.messages
            if item["role"] == "user"
        ][-4:]
        if recent:
            st.markdown(
                '<div class="side-label">THIS SESSION</div>', unsafe_allow_html=True
            )
            for message in reversed(recent):
                st.caption("↳ " + message[:38] + ("…" if len(message) > 38 else ""))
        st.divider()
        st.markdown(
            '<div class="side-note">A new session keeps your saved preferences '
            "and liked cars. "
            "For a viewing, give a date and time in Dubai time.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="topline"><span class="top-pill">'
        '<span class="dot"></span> Cars assistant</span>'
        '<span class="top-meta">Inventory-backed · Dubai time</span></div>',
        unsafe_allow_html=True,
    )

    suggested_prompt = None
    if st.session_state.messages:
        st.markdown("### Your conversation")
        for item in st.session_state.messages:
            _show_message(item)
        st.markdown(
            '<div class="composer-label">ASK A FOLLOW-UP</div>', unsafe_allow_html=True
        )
        with st.container(key="composer"):
            prompt = st.chat_input(
                "Ask about a car or request a viewing…",
                key="chat_prompt",
                disabled=not st.session_state.session_id,
                max_chars=4000,
            )
    else:
        name = escape(st.session_state.active_display_name or "there")
        st.markdown(
            '<div class="hero"><div class="orb-wrap"><div class="orb"></div></div>'
            f'<div class="hello">Hello, {name}</div>'
            '<div class="hero-title">How can I help you find a car?</div>'
            '<div class="hero-sub">Search the inventory, ask about a '
            "listing, or plan a viewing.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="composer-label">START WITH A QUESTION</div>',
            unsafe_allow_html=True,
        )
        with st.container(key="composer"):
            prompt = st.chat_input(
                "Ask about any car in the inventory…",
                key="chat_prompt",
                disabled=not st.session_state.session_id,
                max_chars=4000,
            )
        st.markdown(
            '<div class="suggestions-label">SOME IDEAS TO START</div>',
            unsafe_allow_html=True,
        )
        suggestions = (
            (
                "◈",
                "Family SUVs",
                "Comfort and room for everyday drives",
                "Show me comfortable family SUVs",
            ),
            (
                "◇",
                "Sporty cars",
                "Find something with a little edge",
                "Show me something sporty and comfortable",
            ),
            (
                "⌕",
                "Toyota options",
                "Explore the available Toyota cars",
                "Show me Toyota cars",
            ),
        )
        for column, (icon, title, subtitle, query) in zip(
            st.columns(3, gap="small"), suggestions, strict=True
        ):
            with column, st.container(key=f"suggestion_{title.split()[0].lower()}"):
                st.markdown(
                    f'<div style="color:#a787d8;font-size:1.3rem">{icon}</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    title,
                    key=f"prompt_{title}",
                    disabled=not st.session_state.session_id,
                ):
                    suggested_prompt = query
                st.caption(subtitle)

    submitted = prompt or suggested_prompt
    if submitted:
        user_item = {"role": "user", "content": submitted}
        st.session_state.messages.append(user_item)
        _show_message(user_item)
        try:
            with st.spinner("Checking the car inventory…"):
                answer = api.chat(
                    st.session_state.active_user_id,
                    st.session_state.session_id,
                    submitted,
                )
            assistant_item = {
                "role": "assistant",
                "content": answer["message"],
                "cars": [_display_car(car) for car in answer["cars"]],
            }
        except ApiError as exc:
            assistant_item = {"role": "assistant", "content": str(exc), "error": True}
        st.session_state.messages.append(assistant_item)
        st.session_state.messages = st.session_state.messages[-40:]
        st.rerun()


if __name__ == "__main__":
    main()
