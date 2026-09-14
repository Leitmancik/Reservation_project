import streamlit as st

st.set_page_config(
    page_title="Reservation Project",
    page_icon="👋",
)

st.title("Hello World 👋")

st.write("Tahle aplikace běží na Streamlit Community Cloud.")

name = st.text_input("Jak se jmenuješ?")

if name:
    st.success(f"Ahoj, {name}!")
