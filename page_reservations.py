"""Stránka Rezervace — seznam záznamů a jejich potvrzování."""

import io

import pandas as pd
import streamlit as st

import storage
from calendar_view import COLORS
from ui import nights_label, set_flash, show_flash

STATUS_LABELS = {
    storage.STATUS_PENDING: "Čeká na potvrzení",
    storage.STATUS_CONFIRMED: "Potvrzeno",
}


def _to_dataframe(reservations):
    return pd.DataFrame(
        [
            {
                "Jméno": res["first_name"],
                "Příjmení": res["last_name"],
                "E-mail": res["email"],
                "Příjezd": res["date_from"].strftime("%d.%m.%Y"),
                "Odjezd": res["date_to"].strftime("%d.%m.%Y"),
                "Nocí": (res["date_to"] - res["date_from"]).days,
                "Stav": STATUS_LABELS[res["status"]],
                "Vytvořeno": res["created_at"],
            }
            for res in reservations
        ]
    )


def _status_badge(status):
    return (
        f'<span style="background:{COLORS[status]};color:#111;'
        f"padding:2px 10px;border-radius:999px;font-size:.78rem;"
        f'font-weight:600;">{STATUS_LABELS[status]}</span>'
    )


def _render_row(res):
    with st.container(border=True):
        col_info, col_actions = st.columns([3, 1])

        with col_info:
            st.markdown(
                f"**{res['first_name']} {res['last_name']}** &nbsp; "
                f"{_status_badge(res['status'])}",
                unsafe_allow_html=True,
            )

            nights = (res["date_to"] - res["date_from"]).days

            st.caption(
                f"{res['date_from'].strftime('%d.%m.%Y')} od 15:00 → "
                f"{res['date_to'].strftime('%d.%m.%Y')} do 11:00 "
                f"({nights_label(nights)}) &nbsp;·&nbsp; {res['email']}"
            )

        with col_actions:
            if res["status"] == storage.STATUS_PENDING:
                if st.button(
                    "Potvrdit",
                    key=f"confirm_{res['id']}",
                    type="primary",
                    width="stretch",
                ):
                    with st.spinner("Potvrzuji…"):
                        try:
                            storage.set_status(
                                res["id"], storage.STATUS_CONFIRMED
                            )
                        except storage.StorageError as error:
                            st.error(f"Nepodařilo se potvrdit. {error}")
                            st.stop()

                    set_flash(
                        "success",
                        f"Rezervace {res['first_name']} {res['last_name']} "
                        "byla potvrzena.",
                    )
                    st.rerun()
            else:
                if st.button(
                    "Vrátit zpět",
                    key=f"revert_{res['id']}",
                    width="stretch",
                ):
                    with st.spinner("Vracím zpět…"):
                        try:
                            storage.set_status(
                                res["id"], storage.STATUS_PENDING
                            )
                        except storage.StorageError as error:
                            st.error(f"Nepodařilo se vrátit zpět. {error}")
                            st.stop()

                    set_flash(
                        "info",
                        f"Potvrzení rezervace {res['first_name']} "
                        f"{res['last_name']} bylo zrušeno.",
                    )
                    st.rerun()

            with st.popover("Smazat", width="stretch"):
                st.write("Opravdu smazat tuhle rezervaci? Nejde to vrátit.")

                if st.button(
                    "Ano, smazat",
                    key=f"delete_{res['id']}",
                    type="primary",
                    width="stretch",
                ):
                    with st.spinner("Mažu…"):
                        try:
                            storage.delete_reservation(res["id"])
                        except storage.StorageError as error:
                            st.error(f"Nepodařilo se smazat. {error}")
                            st.stop()

                    set_flash(
                        "warning",
                        f"Rezervace {res['first_name']} {res['last_name']} "
                        "byla smazána.",
                    )
                    st.rerun()


def render():
    st.title("Rezervace")

    show_flash()

    try:
        reservations = storage.load_reservations()
    except storage.StorageError as error:
        st.error(f"Nepodařilo se načíst rezervace. {error}")
        return

    if not reservations:
        st.info(
            "Zatím tu nejsou žádné rezervace. "
            "Vytvoř první na stránce Kalendář."
        )
        return

    pending = [r for r in reservations if r["status"] == storage.STATUS_PENDING]
    confirmed = [
        r for r in reservations if r["status"] == storage.STATUS_CONFIRMED
    ]

    col1, col2, col3 = st.columns(3)
    col1.metric("Celkem", len(reservations))
    col2.metric("Čeká na potvrzení", len(pending))
    col3.metric("Potvrzeno", len(confirmed))

    st.divider()

    if pending:
        st.subheader("Čeká na potvrzení")
        for res in pending:
            _render_row(res)

    if confirmed:
        st.subheader("Potvrzené")
        for res in confirmed:
            _render_row(res)

    st.divider()

    st.caption(f"Rezervace se ukládají do: **{storage.backend_name()}**")

    with st.expander("Přehled v tabulce a export"):
        df = _to_dataframe(reservations)
        st.dataframe(df, width="stretch", hide_index=True)

        col_csv, col_xlsx = st.columns(2)

        with col_csv:
            st.download_button(
                "Stáhnout CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name="rezervace.csv",
                mime="text/csv",
                width="stretch",
            )

        with col_xlsx:
            buffer = io.BytesIO()

            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Rezervace")

            buffer.seek(0)

            st.download_button(
                "Stáhnout Excel",
                data=buffer,
                file_name="rezervace.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                width="stretch",
            )
