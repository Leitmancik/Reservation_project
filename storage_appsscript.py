"""Ukládání rezervací do Google Sheets přes Apps Script.

Na rozdíl od storage_sheets.py nepotřebuje Google Cloud ani servisní
účet. V tabulce běží skript nasazený jako webová aplikace a tenhle
modul mu posílá požadavky na jeho adresu.

Do Streamlit secrets patří dvě hodnoty:

    appsscript_url   = "https://script.google.com/macros/s/..../exec"
    appsscript_token = "stejný token jako v Kod.gs"

Tabulka má sloupce:

    Jméno | Příjmení | email | Datum - Start | Datum - Konec | Stav | ID | Vytvořeno
"""

import json
from datetime import date, datetime

import requests
import streamlit as st

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"

STATUS_TO_SHEET = {
    STATUS_PENDING: "Čeká na potvrzení",
    STATUS_CONFIRMED: "Potvrzeno",
}
SHEET_TO_STATUS = {v: k for k, v in STATUS_TO_SHEET.items()}

TIMEOUT_SECONDS = 25

# Bez cache by se skript volal při každém kliknutí v kalendáři.
CACHE_TTL_SECONDS = 20


class StorageError(RuntimeError):
    """Skript v tabulce odpověděl chybou."""


def is_configured():
    try:
        return bool(st.secrets.get("appsscript_url")) and bool(
            st.secrets.get("appsscript_token")
        )
    except Exception:
        # Když soubor se secrets neexistuje, Streamlit vyhodí výjimku.
        return False


def _call(action, **payload):
    """Pošle požadavek skriptu v tabulce a vrátí jeho odpověď.

    Data posíláme metodou GET v parametru "payload". Některé domény
    Google Workspace totiž POST na webovou aplikaci neprotlačí a vrátí
    chybu 405 — GET projde vždy. Požadavky jsou krátké, do délky
    adresy se pohodlně vejdou.
    """
    body = {
        "token": st.secrets["appsscript_token"],
        "action": action,
    }
    body.update(payload)

    try:
        response = requests.get(
            st.secrets["appsscript_url"],
            params={"payload": json.dumps(body, ensure_ascii=False)},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        raise StorageError(
            "Tabulka neodpovídá. Zkus to prosím za chvíli znovu."
        )
    except requests.exceptions.RequestException as error:
        raise StorageError(f"Nepodařilo se spojit s tabulkou: {error}")
    except ValueError:
        # Místo JSON přišlo HTML. Typicky přihlašovací stránka, když
        # skript není nasazený s přístupem pro kohokoli, nebo hláška
        # o chybějící funkci, když je nasazená stará verze kódu.
        detail = ""

        if "doGet" in response.text:
            detail = (
                " Vypadá to na starou verzi skriptu — nasaď prosím "
                "novou implementaci s aktuálním kódem."
            )
        elif "accounts.google.com" in response.text:
            detail = (
                " Skript není veřejný — v nasazení nastav přístup "
                "„Kdokoli“."
            )

        raise StorageError(
            "Tabulka odpověděla nečekaně." + detail
        )

    if isinstance(data, dict) and data.get("error"):
        raise StorageError(data["error"])

    return data


def init_db():
    """Ověří, že se skript ozývá. Volá se při startu aplikace."""
    _call("ping")


def _parse_date(value):
    """Přečte datum z buňky. Tabulka ho může vrátit v různém tvaru."""
    if isinstance(value, date):
        return value

    text = str(value).strip()

    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d. %m. %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _load_rows():
    return _call("list").get("rows", [])


def load_reservations():
    """Načte rezervace z tabulky, seřazené podle data příjezdu."""
    reservations = []

    for row in _load_rows():
        date_from = _parse_date(row.get("Datum - Start"))
        date_to = _parse_date(row.get("Datum - Konec"))

        # Řádek s nečitelným datem přeskočíme, ať ruční překlep
        # v tabulce neshodí celou aplikaci.
        if date_from is None or date_to is None:
            continue

        reservations.append(
            {
                "id": str(row.get("ID", "")).strip(),
                "first_name": str(row.get("Jméno", "")).strip(),
                "last_name": str(row.get("Příjmení", "")).strip(),
                "email": str(row.get("email", "")).strip(),
                "date_from": date_from,
                "date_to": date_to,
                "status": SHEET_TO_STATUS.get(
                    str(row.get("Stav", "")).strip(), STATUS_PENDING
                ),
                "created_at": str(row.get("Vytvořeno", "")).strip(),
            }
        )

    return sorted(reservations, key=lambda r: r["date_from"])


def _invalidate():
    _load_rows.clear()


def add_reservation(first_name, last_name, email, date_from, date_to):
    _call(
        "add",
        row={
            "Jméno": first_name.strip(),
            "Příjmení": last_name.strip(),
            "email": email.strip(),
            "Datum - Start": date_from.isoformat(),
            "Datum - Konec": date_to.isoformat(),
            "Stav": STATUS_TO_SHEET[STATUS_PENDING],
            "Vytvořeno": datetime.now().isoformat(timespec="seconds"),
        },
    )

    _invalidate()


def set_status(reservation_id, status):
    _call("set_status", id=reservation_id, status=STATUS_TO_SHEET[status])
    _invalidate()


def delete_reservation(reservation_id):
    _call("delete", id=reservation_id)
    _invalidate()
