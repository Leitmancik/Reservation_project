"""Stránka Kalendář — klikací přehled obsazenosti a formulář rezervace.

Termín se vybírá kliknutím do kalendáře: první klik určí den příjezdu,
druhý den odjezdu. Další klik začne výběr znovu.
"""

from datetime import date, timedelta

import streamlit as st

import storage
from calendar_view import (
    MONTH_NAMES,
    month_range,
    render_calendar,
    render_legend,
)
from ui import nights_label, set_flash, show_flash

# Kolik měsíců je vidět naráz a jak daleko dopředu jde listovat.
MONTHS_VISIBLE = 2
MAX_MONTH_OFFSET = 23

# Nabízené délky pobytu. Většina hostů jezdí zhruba na týden,
# tak ať to jde vybrat jedním kliknutím.
QUICK_NIGHTS = [2, 3, 7, 14]


def _clear_selection():
    st.session_state.sel_from = None
    st.session_state.sel_to = None


def _handle_click(day, reservations):
    """Zpracuje kliknutí na den v kalendáři."""
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    # Kompletní výběr nebo klik před začátek = začínáme znovu.
    if sel_from is None or sel_to is not None or day <= sel_from:
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    conflict = storage.find_conflict(sel_from, day, reservations)

    if conflict is not None:
        set_flash(
            "error",
            f"V tomhle rozsahu je už rezervace "
            f"{conflict['first_name']} {conflict['last_name']} "
            f"({conflict['date_from'].strftime('%d.%m.%Y')} – "
            f"{conflict['date_to'].strftime('%d.%m.%Y')}). "
            "Vyber kratší pobyt nebo jiný termín.",
        )
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    st.session_state.sel_to = day


def _month_label(months):
    """Popisek typu „Září – Říjen 2026“ nad kalendářem."""
    (y1, m1), (y2, m2) = months[0], months[-1]

    if y1 == y2:
        return f"{MONTH_NAMES[m1 - 1]} – {MONTH_NAMES[m2 - 1]} {y1}"

    return f"{MONTH_NAMES[m1 - 1]} {y1} – {MONTH_NAMES[m2 - 1]} {y2}"


def _month_navigation(months):
    """Šipky pro listování měsíci. Dozadu se nedá před aktuální měsíc."""
    offset = st.session_state.month_offset

    col_prev, col_label, col_next, col_refresh = st.columns([1, 6, 1, 1])

    with col_prev:
        if st.button(
            "◀",
            width="stretch",
            disabled=offset == 0,
            help="Předchozí měsíc",
        ):
            st.session_state.month_offset = max(0, offset - 1)
            st.rerun()

    with col_label:
        st.markdown(
            f"<div style='text-align:center;font-size:1.05rem;"
            f"font-weight:600;padding-top:.35rem'>{_month_label(months)}</div>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button(
            "▶",
            width="stretch",
            disabled=offset >= MAX_MONTH_OFFSET,
            help="Další měsíc",
        ):
            st.session_state.month_offset = min(MAX_MONTH_OFFSET, offset + 1)
            st.rerun()

    with col_refresh:
        if st.button(
            "↻",
            width="stretch",
            help="Načíst rezervace z tabulky znovu",
        ):
            storage.refresh()
            st.rerun()


def _quick_lengths(reservations):
    """Tlačítka pro rychlý výběr délky pobytu od zvoleného příjezdu."""
    sel_from = st.session_state.sel_from

    st.caption("Nebo rovnou vyber délku pobytu:")

    cols = st.columns(len(QUICK_NIGHTS))

    for col, nights in zip(cols, QUICK_NIGHTS):
        date_to = sel_from + timedelta(days=nights)
        blocked = storage.find_conflict(sel_from, date_to, reservations)

        with col:
            if st.button(
                nights_label(nights),
                key=f"quick_{nights}",
                width="stretch",
                disabled=blocked is not None,
                help=(
                    "V tomhle termínu už je rezervace"
                    if blocked is not None
                    else f"Odjezd {date_to.strftime('%d.%m.%Y')}"
                ),
            ):
                st.session_state.sel_to = date_to
                st.rerun()


def _selection_bar():
    """Pruh nad kalendářem s aktuálně vybraným termínem."""
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    col_text, col_clear = st.columns([4, 1])

    with col_text:
        if sel_from is None:
            st.info(
                "Klikni v kalendáři na den **příjezdu**. "
                "Druhým kliknutím vybereš den **odjezdu**.",
                icon="👉",
            )
        elif sel_to is None:
            st.warning(
                f"Příjezd **{sel_from.strftime('%d.%m.%Y')}** od 15:00. "
                "Teď klikni na den odjezdu.",
                icon="📅",
            )
        else:
            nights = (sel_to - sel_from).days
            st.success(
                f"**{sel_from.strftime('%d.%m.%Y')}** od 15:00 → "
                f"**{sel_to.strftime('%d.%m.%Y')}** do 11:00 "
                f"· {nights_label(nights)}",
                icon="✅",
            )

    with col_clear:
        if sel_from is not None:
            if st.button("Zrušit výběr", width="stretch"):
                _clear_selection()
                st.rerun()


def _reservation_form(reservations):
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    st.subheader("Dokončení rezervace")

    if sel_from is None or sel_to is None:
        st.caption(
            "Nejdřív vyber termín kliknutím do kalendáře — "
            "pak se tu objeví formulář."
        )
        return

    nights = (sel_to - sel_from).days

    st.caption(
        f"Termín: {sel_from.strftime('%d.%m.%Y')} od 15:00 → "
        f"{sel_to.strftime('%d.%m.%Y')} do 11:00 ({nights_label(nights)})"
    )

    with st.form("new_reservation", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            first_name = st.text_input("Jméno")

        with col2:
            last_name = st.text_input("Příjmení")

        with col3:
            email = st.text_input("E-mail")

        submitted = st.form_submit_button(
            "Odeslat rezervaci", type="primary"
        )

    if not submitted:
        return

    errors = []

    if not first_name.strip():
        errors.append("Vyplň jméno.")

    if not last_name.strip():
        errors.append("Vyplň příjmení.")

    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Vyplň platný e-mail.")

    if errors:
        for message in errors:
            st.error(message)
        return

    with st.spinner("Ukládám rezervaci…"):
        try:
            # Mezi výběrem a odesláním mohl někdo termín zabrat, proto
            # se tady ptáme přímo tabulky, ne uložených dat.
            conflict = storage.find_conflict(
                sel_from, sel_to, storage.load_reservations(force=True)
            )

            if conflict is not None:
                st.error(
                    f"Termín mezitím obsadila rezervace "
                    f"{conflict['first_name']} {conflict['last_name']}. "
                    "Vyber prosím jiný."
                )
                return

            storage.add_reservation(
                first_name, last_name, email, sel_from, sel_to
            )
        except storage.StorageError as error:
            st.error(f"Rezervaci se nepodařilo uložit. {error}")
            return

    set_flash(
        "success",
        f"Rezervace uložena: {first_name.strip()} {last_name.strip()}, "
        f"{sel_from.strftime('%d.%m.%Y')} – {sel_to.strftime('%d.%m.%Y')} "
        f"({nights_label(nights)}). Čeká na potvrzení — "
        "potvrdit ji můžeš na stránce Rezervace.",
    )

    _clear_selection()
    st.rerun()


def render():
    st.title("Rezervace chalupy")

    st.session_state.setdefault("sel_from", None)
    st.session_state.setdefault("sel_to", None)
    st.session_state.setdefault("month_offset", 0)

    show_flash()

    try:
        reservations = storage.load_reservations()
    except storage.StorageError as error:
        st.error(f"Nepodařilo se načíst rezervace. {error}")
        st.caption(
            "Kalendář teď nejde zobrazit, protože není jisté, "
            "které termíny jsou volné. Zkus stránku načíst znovu."
        )
        return

    today = date.today()

    _selection_bar()

    start = date(today.year, today.month, 1)
    months = month_range(
        _shift_start(start, st.session_state.month_offset),
        MONTHS_VISIBLE,
    )

    _month_navigation(months)

    clicked = render_calendar(
        months,
        reservations,
        st.session_state.sel_from,
        st.session_state.sel_to,
        today,
    )

    if clicked is not None:
        _handle_click(clicked, reservations)
        st.rerun()

    # Rychlé délky pobytu dávají smysl jen ve chvíli, kdy je vybraný
    # příjezd a chybí odjezd.
    if (
        st.session_state.sel_from is not None
        and st.session_state.sel_to is None
    ):
        _quick_lengths(reservations)

    st.html(render_legend())

    st.divider()

    _reservation_form(reservations)


def _shift_start(start, offset):
    total = start.year * 12 + (start.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)
