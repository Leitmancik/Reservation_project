"""Stránka Cenotvorba — základní cena a období, která ji přebíjejí.

Ceník se ukládá do listu Cenotvorba ve stejné tabulce jako rezervace.
Řádek bez vyplněných dat je základní cena; ostatní řádky jsou období.
Když se dvě období překrývají, platí to kratší.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import pricing
import storage
from ui import format_price, nights_label, set_flash, show_flash


def _base_form(prices):
    """Základní cena, která platí všude, kde nic jiného neplatí."""
    current = pricing.base_price(prices)

    st.subheader("Základní cena")

    if current is None:
        st.warning(
            "Základní cena zatím není nastavená. Bez ní se nedá spočítat "
            "pobyt mimo zadaná období.",
            icon="⚠️",
        )
    else:
        st.caption(
            f"Platí ve všech termínech, na které se nevztahuje žádné "
            f"období níže. Teď: **{format_price(current)}** za noc."
        )

    base_row = next((p for p in prices if pricing.is_base(p)), None)

    with st.form("base_price", clear_on_submit=False):
        col_price, col_button = st.columns([3, 1])

        with col_price:
            value = st.number_input(
                "Cena za noc (Kč)",
                min_value=0,
                step=500,
                value=int(current) if current is not None else 10000,
            )

        with col_button:
            st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Uložit", width="stretch")

    if submitted:
        with st.spinner("Ukládám…"):
            try:
                storage.save_price(
                    base_row["id"] if base_row else None,
                    None,
                    None,
                    value,
                    "Základní cena",
                )
            except storage.StorageError as error:
                st.error(f"Nepodařilo se uložit. {error}")
                return

        set_flash("success", f"Základní cena nastavena na {format_price(value)}.")
        st.rerun()


def _period_form(prices):
    """Formulář pro nové období s odlišnou cenou."""
    st.subheader("Přidat období")

    st.caption(
        "Období přebíjí základní cenu. Když se dvě období překrývají, "
        "platí to kratší — Silvestr uvnitř zimní sezóny tak funguje sám "
        "od sebe."
    )

    today = date.today()

    with st.form("new_period", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 3])

        with col1:
            date_from = st.date_input(
                "Od", value=today, format="DD.MM.YYYY"
            )

        with col2:
            date_to = st.date_input(
                "Do", value=today + timedelta(days=6), format="DD.MM.YYYY"
            )

        with col3:
            price = st.number_input(
                "Cena za noc (Kč)", min_value=0, step=500, value=15000
            )

        with col4:
            label = st.text_input("Popis", placeholder="Letní sezóna")

        submitted = st.form_submit_button("Přidat období", type="primary")

    if not submitted:
        return

    if date_to < date_from:
        st.error("Datum „Do“ musí být stejné nebo pozdější než „Od“.")
        return

    if not label.strip():
        st.error("Vyplň popis, ať v ceníku poznáš, o co jde.")
        return

    with st.spinner("Ukládám…"):
        try:
            storage.save_price(None, date_from, date_to, price, label)
        except storage.StorageError as error:
            st.error(f"Nepodařilo se uložit. {error}")
            return

    set_flash(
        "success",
        f"Období „{label.strip()}“ ({date_from.strftime('%d.%m.%Y')} – "
        f"{date_to.strftime('%d.%m.%Y')}) za {format_price(price)} za noc "
        "bylo přidáno.",
    )
    st.rerun()


def _period_list(prices):
    """Seznam zadaných období."""
    periods = [p for p in prices if not pricing.is_base(p)]

    if not periods:
        st.info(
            "Zatím tu nejsou žádná období — všude platí základní cena.",
            icon="ℹ️",
        )
        return

    st.subheader("Zadaná období")

    # Řadíme podle data, ne podle priority — takhle se v tom lépe čte.
    for period in sorted(periods, key=lambda p: p["date_from"]):
        with st.container(border=True):
            col_info, col_price, col_delete = st.columns([4, 2, 1])

            days = (period["date_to"] - period["date_from"]).days + 1

            with col_info:
                st.markdown(f"**{period['label'] or 'Bez popisu'}**")
                st.caption(
                    f"{period['date_from'].strftime('%d.%m.%Y')} – "
                    f"{period['date_to'].strftime('%d.%m.%Y')} · {days} dní"
                )

                collisions = pricing.overlaps(period, prices)

                if collisions:
                    shorter = [
                        c["label"]
                        for c in collisions
                        if (c["date_to"] - c["date_from"]).days
                        < (period["date_to"] - period["date_from"]).days
                    ]

                    if shorter:
                        st.caption(
                            "⚠️ Uvnitř tohohle období platí jinde: "
                            + ", ".join(shorter)
                        )

            with col_price:
                st.markdown(
                    f"<div style='text-align:right;font-size:1.1rem;"
                    f"font-weight:600;padding-top:.4rem'>"
                    f"{format_price(period['price'])}</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "<div style='text-align:right'>za noc</div>",
                    unsafe_allow_html=True,
                )

            with col_delete:
                with st.popover("Smazat", width="stretch"):
                    st.write("Opravdu smazat tohle období?")

                    if st.button(
                        "Ano, smazat",
                        key=f"del_price_{period['id']}",
                        type="primary",
                        width="stretch",
                    ):
                        with st.spinner("Mažu…"):
                            try:
                                storage.delete_price(period["id"])
                            except storage.StorageError as error:
                                st.error(f"Nepodařilo se smazat. {error}")
                                st.stop()

                        set_flash(
                            "warning",
                            f"Období „{period['label']}“ bylo smazáno.",
                        )
                        st.rerun()


def _calculator(prices):
    """Kontrola, kolik bude stát konkrétní termín."""
    st.subheader("Kolik bude stát pobyt")

    today = date.today()

    col1, col2 = st.columns(2)

    with col1:
        date_from = st.date_input(
            "Příjezd",
            value=today,
            format="DD.MM.YYYY",
            key="calc_from",
        )

    with col2:
        date_to = st.date_input(
            "Odjezd",
            value=today + timedelta(days=7),
            format="DD.MM.YYYY",
            key="calc_to",
        )

    if date_to <= date_from:
        st.caption("Odjezd musí být až po příjezdu.")
        return

    total, breakdown = pricing.stay_total(date_from, date_to, prices)
    count = len(breakdown)

    if total is None:
        st.error(
            "Některé noci nemají cenu — nastav základní cenu výše.",
            icon="⚠️",
        )
    else:
        st.metric(
            f"Celkem za {nights_label(count)}",
            format_price(total),
        )

    rows = []

    for item in breakdown:
        period = pricing.period_for_night(item["day"], prices)

        rows.append(
            {
                "Noc z": item["day"].strftime("%d.%m.%Y"),
                "na": (item["day"] + timedelta(days=1)).strftime("%d.%m.%Y"),
                "Cena": format_price(item["price"]),
                "Podle pravidla": (period or {}).get("label", "—"),
            }
        )

    with st.expander(f"Rozpis po nocích ({count})"):
        st.dataframe(
            pd.DataFrame(rows), width="stretch", hide_index=True
        )


def render():
    st.title("Cenotvorba")

    show_flash()

    if not storage.supports_pricing():
        st.warning(
            "Současné úložiště ceník neumí. Ceník funguje přes servisní "
            "účet Google nebo v místním souboru.",
            icon="⚠️",
        )
        return

    try:
        prices = storage.load_prices()
    except storage.StorageError as error:
        st.error(f"Nepodařilo se načíst ceník. {error}")
        return

    col_note, col_refresh = st.columns([4, 1])

    with col_note:
        st.caption("Ceník se ukládá do listu **Cenotvorba** ve stejné tabulce.")

    with col_refresh:
        if st.button("↻ Načíst znovu", width="stretch"):
            storage.refresh_prices()
            st.rerun()

    _base_form(prices)

    st.divider()

    _period_form(prices)

    _period_list(prices)

    st.divider()

    _calculator(prices)
