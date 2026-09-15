"""Rezervační systém chalupy — vstupní bod aplikace.

Spuštění lokálně:  streamlit run streamlit_app.py
"""

import streamlit as st

import page_calendar
import page_pricing
import page_reservations
import storage

st.set_page_config(
    page_title="Rezervace chalupy",
    page_icon="🏡",
    layout="wide",
)

# Streamlit nechává nad obsahem široký pruh. Na stránce, kde hlavní
# roli hraje kalendář, je to jen nevyužité místo — obsah se tím
# posune výš a mřížka se vejde na obrazovku bez rolování.
#
# Dolů to ale jde jen po určitou mez: horní navigace je připnutá přes
# obsah, ne nad ním, takže jí tohle odsazení musí nechat místo. Pod
# zhruba 3 rem začne lišta překrývat nadpis.
st.html(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        padding-top: 4.5rem !important;
    }
    [data-testid="stMainBlockContainer"] h1 {
        margin-top: 0 !important;
        padding-top: 0 !important;
        margin-bottom: .4rem !important;
    }
    </style>
    """
)

try:
    storage.init_db()
except Exception as error:
    st.error(f"Nepodařilo se spojit s úložištěm rezervací. {error}")
    st.stop()

# url_path je potřeba zadat ručně — obě stránky mají funkci render(),
# takže by si Streamlit odvodil stejnou adresu a spadl.
pages = [
    st.Page(
        page_calendar.render,
        title="Kalendář",
        icon="📅",
        url_path="kalendar",
        default=True,
    ),
    st.Page(
        page_reservations.render,
        title="Rezervace",
        icon="📋",
        url_path="rezervace",
    ),
    st.Page(
        page_pricing.render,
        title="Cenotvorba",
        icon="💰",
        url_path="cenotvorba",
    ),
]

st.navigation(pages, position="top").run()
