"""Drobné UI pomůcky sdílené mezi stránkami."""

import streamlit as st

_KEY = "_flash_messages"


def set_flash(kind, text):
    """Uloží hlášku, která se zobrazí až po překreslení stránky.

    Bez tohohle by se st.success() ztratil, protože hned po uložení
    voláme st.rerun() a stránka se vykreslí znovu od začátku.
    """
    st.session_state.setdefault(_KEY, []).append((kind, text))


def show_flash():
    """Vypíše a zahodí hlášky uložené při minulém běhu."""
    for kind, text in st.session_state.pop(_KEY, []):
        getattr(st, kind)(text)


def nights_label(nights):
    """Správně vyskloňovaný počet nocí: 1 noc, 3 noci, 5 nocí."""
    if nights == 1:
        return "1 noc"

    if nights < 5:
        return f"{nights} noci"

    return f"{nights} nocí"
