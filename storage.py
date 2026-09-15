"""Přístup k rezervacím — jediné místo, přes které aplikace sahá na data.

Máme tři úložiště se stejným rozhraním:

    storage_appsscript.py — Google Sheets přes skript v tabulce
    storage_sheets.py     — Google Sheets přes servisní účet
    storage_sqlite.py     — soubor na disku, lokální vývoj

Vybere se to první, které je nastavené ve Streamlit secrets. Když není
nastavené nic, použije se SQLite, aby šla aplikace spustit i bez
připojení ke Googlu.

Načtené rezervace se drží v paměti otevřené stránky. Čtení z Google
Sheets trvá několik sekund a kalendář se překresluje při každém
kliknutí — bez toho by se na tabulku sahalo pořád dokola a appka by
byla nepoužitelně pomalá. Znovu se načítá jen při otevření stránky,
po zápisu a na vyžádání tlačítkem.
"""

import streamlit as st

import storage_appsscript
import storage_sheets
import storage_sqlite
from storage_errors import StorageError  # noqa: F401  (pro stránky)

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"


def backend():
    """Vrátí modul, který se právě používá k ukládání."""
    if storage_appsscript.is_configured():
        return storage_appsscript

    if storage_sheets.is_configured():
        return storage_sheets

    return storage_sqlite


def backend_name():
    """Krátký popis úložiště pro zobrazení v aplikaci."""
    current = backend()

    if current is storage_appsscript:
        return "Google Sheets (přes skript v tabulce)"

    if current is storage_sheets:
        return "Google Sheets (přes servisní účet)"

    return "místní soubor (data nepřežijí restart na Streamlit Cloud)"


# Klíč, pod kterým si stránka drží načtené rezervace.
_CACHE_KEY = "_reservations_cache"


@st.cache_resource(show_spinner=False)
def _init_backend_once(name):
    """Ověří spojení s úložištěm. Jen jednou, ne při každém překreslení.

    Streamlit spouští celý skript znovu po každém kliknutí — bez tohohle
    by se při každém kliknutí do kalendáře zbytečně volala tabulka.
    """
    backend().init_db()
    return True


def init_db():
    _init_backend_once(backend().__name__)


def load_reservations(force=False):
    """Vrátí rezervace, pokud možno z paměti stránky.

    S `force=True` se vždy sáhne do tabulky — to je potřeba tam, kde
    musíme mít jistotu, že data nejsou zastaralá, typicky při kontrole
    volného termínu těsně před uložením rezervace.
    """
    if not force:
        cached = st.session_state.get(_CACHE_KEY)

        if cached is not None:
            return cached

    reservations = backend().load_reservations()
    st.session_state[_CACHE_KEY] = reservations

    return reservations


def refresh():
    """Zahodí uložená data, takže se příště načtou z tabulky."""
    st.session_state.pop(_CACHE_KEY, None)
    st.session_state.pop("_prices_cache", None)


def add_reservation(first_name, last_name, email, date_from, date_to):
    backend().add_reservation(first_name, last_name, email, date_from, date_to)
    refresh()


def set_status(reservation_id, status):
    backend().set_status(reservation_id, status)
    refresh()


def delete_reservation(reservation_id):
    backend().delete_reservation(reservation_id)
    refresh()


# ─────────────────────────── ceník ───────────────────────────

_PRICES_KEY = "_prices_cache"


def supports_pricing():
    """Umí současné úložiště ceník?

    Apps Script v tabulce obsluhuje jen rezervace — ceník by znamenal
    rozšířit a znovu nasadit skript. Přes servisní účet i v místním
    souboru ceník funguje.
    """
    return hasattr(backend(), "load_prices")


def load_prices(force=False):
    """Ceník, pokud možno z paměti stránky."""
    if not supports_pricing():
        return []

    if not force:
        cached = st.session_state.get(_PRICES_KEY)

        if cached is not None:
            return cached

    prices = backend().load_prices()
    st.session_state[_PRICES_KEY] = prices

    return prices


def refresh_prices():
    st.session_state.pop(_PRICES_KEY, None)


def save_price(price_id, date_from, date_to, price, label):
    backend().save_price(price_id, date_from, date_to, price, label)
    refresh_prices()


def delete_price(price_id):
    backend().delete_price(price_id)
    refresh_prices()


def find_conflict(date_from, date_to, reservations=None):
    """Najde rezervaci, která se s daným termínem překrývá.

    Protože se odjíždí v 11:00 a přijíždí až v 15:00, smí na sebe dva
    pobyty navazovat ve stejný den — odjezd 5. a příjezd 5. je v pořádku.
    Konflikt je až tehdy, když se termíny skutečně přesahují.
    """
    if reservations is None:
        reservations = load_reservations()

    for res in reservations:
        if date_from < res["date_to"] and res["date_from"] < date_to:
            return res

    return None
