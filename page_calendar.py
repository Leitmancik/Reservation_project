"""Stránka Kalendář — přehled obsazenosti a formulář pro novou rezervaci."""

from datetime import date, timedelta

import streamlit as st

import storage
from calendar_view import render_legend, render_months
from ui import set_flash, show_flash


def _shift_month(year, month, offset):
    total = year * 12 + (month - 1) + offset
    return total // 12, total % 12 + 1


def _month_list(start_year, start_month, count):
    return [_shift_month(start_year, start_month, i) for i in range(count)]


def _reservation_form(reservations):
    st.subheader("Nová rezervace")

    st.caption(
        "Příjezd je možný od 15:00, odjezd nejpozději v 11:00. "
        "Den odjezdu se proto smí krýt se dnem příjezdu dalšího hosta."
    )

    today = date.today()

    with st.form("new_reservation", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            first_name = st.text_input("Jméno")
            date_from = st.date_input(
                "Příjezd (od 15:00)",
                value=today,
                min_value=today,
                format="DD.MM.YYYY",
            )

        with col2:
            last_name = st.text_input("Příjmení")
            date_to = st.date_input(
                "Odjezd (do 11:00)",
                value=today + timedelta(days=1),
                min_value=today,
                format="DD.MM.YYYY",
            )

        email = st.text_input("E-mail")

        submitted = st.form_submit_button("Odeslat rezervaci", type="primary")

    if not submitted:
        return

    errors = []

    if not first_name.strip():
        errors.append("Vyplň jméno.")

    if not last_name.strip():
        errors.append("Vyplň příjmení.")

    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Vyplň platný e-mail.")

    if date_to <= date_from:
        errors.append("Datum odjezdu musí být až po datu příjezdu.")

    if errors:
        for message in errors:
            st.error(message)
        return

    conflict = storage.find_conflict(date_from, date_to, reservations)

    if conflict is not None:
        st.error(
            f"Termín se překrývá s rezervací "
            f"{conflict['first_name']} {conflict['last_name']} "
            f"({conflict['date_from'].strftime('%d.%m.%Y')} – "
            f"{conflict['date_to'].strftime('%d.%m.%Y')}). "
            "Vyber jiný termín."
        )
        return

    storage.add_reservation(first_name, last_name, email, date_from, date_to)

    nights = (date_to - date_from).days
    noci = "noc" if nights == 1 else "noci" if nights < 5 else "nocí"

    set_flash(
        "success",
        f"Rezervace uložena: {first_name.strip()} {last_name.strip()}, "
        f"{date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')} "
        f"({nights} {noci}). Čeká na potvrzení — "
        "potvrdit ji můžeš na stránce Rezervace.",
    )

    st.rerun()


def render():
    st.title("Kalendář obsazenosti")

    show_flash()

    reservations = storage.load_reservations()

    st.html(render_legend())

    if "month_offset" not in st.session_state:
        st.session_state.month_offset = 0

    col_prev, col_next, col_count, col_today = st.columns([1, 1, 2, 1])

    with col_prev:
        if st.button("◀ Zpět", width="stretch"):
            st.session_state.month_offset -= 1
            st.rerun()

    with col_next:
        if st.button("Vpřed ▶", width="stretch"):
            st.session_state.month_offset += 1
            st.rerun()

    with col_count:
        count = st.selectbox(
            "Počet měsíců",
            options=[1, 2, 3, 4, 6],
            index=2,
            label_visibility="collapsed",
        )

    with col_today:
        if st.button("Dnes", width="stretch"):
            st.session_state.month_offset = 0
            st.rerun()

    today = date.today()
    start_year, start_month = _shift_month(
        today.year, today.month, st.session_state.month_offset
    )

    months = _month_list(start_year, start_month, count)

    st.html(render_months(months, reservations, today))

    st.divider()

    _reservation_form(reservations)
