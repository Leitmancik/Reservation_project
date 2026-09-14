"""Rezervační systém chalupy — vstupní bod aplikace.

Spuštění lokálně:  streamlit run streamlit_app.py
"""

import streamlit as st

import page_calendar
import page_reservations
import storage

st.set_page_config(
    page_title="Rezervace chalupy",
    page_icon="🏡",
    layout="wide",
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
]

st.navigation(pages, position="top").run()
