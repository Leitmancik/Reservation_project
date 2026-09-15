"""Stránka Rezervace — seznam záznamů a jejich potvrzování."""

import io

import pandas as pd
import streamlit as st

import storage
from calendar_view import COLORS
from ui import format_price, nights_label, set_flash, show_flash

STATUS_LABELS = {
    storage.STATUS_PENDING: "Čeká na potvrzení",
    storage.STATUS_CONFIRMED: "Potvrzeno",
}

# Na úzkém displeji Streamlit srovná sloupce pod sebe, takže by čtyři
# metriky zabraly čtyři obrazovky. Přepsáním minimální šířky na polovinu
# se z nich stane mřížka 2 × 2. Na širokém displeji se nic nemění.
METRICS_CSS = """
<style>
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"])
        > [data-testid="stColumn"] {
        min-width: calc(50% - .5rem) !important;
        flex: 1 1 calc(50% - .5rem) !important;
    }
    [data-testid="stMetricValue"] { font-size: 1.4rem; }
    [data-testid="stMetricLabel"] { font-size: .78rem; }
}
</style>
"""


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
                "Cena celkem": res.get("price"),
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

            detail = (
                f"{res['date_from'].strftime('%d.%m.%Y')} od 15:00 → "
                f"{res['date_to'].strftime('%d.%m.%Y')} do 11:00 "
                f"({nights_label(nights)}) &nbsp;·&nbsp; {res['email']}"
            )

            if res.get("price") is not None:
                detail += (
                    f" &nbsp;·&nbsp; **{format_price(res['price'])}**"
                )

            st.caption(detail)

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

    # Tržbu počítáme jen z potvrzených rezervací — nepotvrzené ještě
    # nejsou jisté a sčítat je dohromady by kreslilo lepší obrázek,
    # než jaký je.
    earned = sum(
        r["price"] for r in confirmed if r.get("price") is not None
    )

    st.html(METRICS_CSS)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Celkem", len(reservations))
    col2.metric("Čeká na potvrzení", len(pending))
    col3.metric("Potvrzeno", len(confirmed))
    col4.metric("Za potvrzené", format_price(earned) if earned else "—")

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

    col_note, col_refresh = st.columns([4, 1])

    with col_note:
        st.caption(
            f"Rezervace se ukládají do: **{storage.backend_name()}**"
        )

    with col_refresh:
        if st.button("↻ Načíst znovu", width="stretch"):
            storage.refresh()
            st.rerun()

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
