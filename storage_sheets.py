"""Ukládání rezervací do Google Sheets.

Tabulka má tyhle sloupce (pořadí musí sedět, názvy taky):

    Jméno | Příjmení | email | Datum - Start | Datum - Konec | Stav | ID | Vytvořeno

Prvních pět je to, co chce vidět člověk. Poslední tři potřebuje
aplikace: "Stav" drží potvrzení rezervace, "ID" umožňuje najít řádek
při potvrzování a mazání, "Vytvořeno" říká, kdy rezervace přišla.
Do buněk je klidně možné psát i ručně, jen ty tři sloupce nemazat.

Přihlášení běží přes servisní účet Google Cloudu. Jeho JSON klíč patří
do Streamlit secrets pod klíč [gcp_service_account] a tabulka musí být
tomu účtu nasdílená s právem editovat.
"""

import uuid
from datetime import date, datetime

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"

# Do tabulky píšeme stav česky, ať je čitelný i pro člověka.
STATUS_TO_SHEET = {
    STATUS_PENDING: "Čeká na potvrzení",
    STATUS_CONFIRMED: "Potvrzeno",
}
SHEET_TO_STATUS = {v: k for k, v in STATUS_TO_SHEET.items()}

HEADER = [
    "Jméno",
    "Příjmení",
    "email",
    "Datum - Start",
    "Datum - Konec",
    "Stav",
    "ID",
    "Vytvořeno",
]

COL_ID = HEADER.index("ID") + 1
COL_STATUS = HEADER.index("Stav") + 1

DEFAULT_SHEET_ID = "1izUy4AgW32PJFLSL3Cs9xHfLmmPf229FUSz6Z6w0oNM"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Jak dlouho držet načtená data, než se sáhne znovu do Sheets.
# Bez toho by se tabulka volala při každém kliknutí v kalendáři.
CACHE_TTL_SECONDS = 20


def is_configured():
    """Je v secrets servisní účet, přes který se lze přihlásit?"""
    try:
        return "gcp_service_account" in st.secrets
    except Exception:
        # Když soubor se secrets neexistuje, Streamlit umí vyhodit výjimku.
        return False


def _sheet_id():
    try:
        return st.secrets.get("sheet_id", DEFAULT_SHEET_ID)
    except Exception:
        return DEFAULT_SHEET_ID


@st.cache_resource(show_spinner=False)
def _worksheet():
    """Připojí se k tabulce. Spojení se drží, nenavazuje se pořád dokola."""
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(_sheet_id()).sheet1

    _ensure_header(worksheet)

    return worksheet


def _ensure_header(worksheet):
    """Doplní hlavičku, pokud tabulka ještě žádnou nemá."""
    first_row = worksheet.row_values(1)

    if not first_row:
        worksheet.update(
            range_name=f"A1:{chr(ord('A') + len(HEADER) - 1)}1",
            values=[HEADER],
        )
        worksheet.format(
            f"A1:{chr(ord('A') + len(HEADER) - 1)}1",
            {"textFormat": {"bold": True}},
        )


def init_db():
    """Ověří spojení a hlavičku. Volá se při startu aplikace."""
    _worksheet()


def _parse_date(value):
    """Přečte datum z buňky. Google Sheets ho může vrátit v různém tvaru."""
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
    return _worksheet().get_all_records(expected_headers=HEADER)


def load_reservations():
    """Načte rezervace z tabulky, seřazené podle data příjezdu."""
    reservations = []

    for row in _load_rows():
        date_from = _parse_date(row.get("Datum - Start"))
        date_to = _parse_date(row.get("Datum - Konec"))

        # Řádek bez použitelných dat přeskočíme, ať ruční překlep
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
    """Přidá rezervaci jako nový řádek ve stavu 'čeká na potvrzení'."""
    _worksheet().append_row(
        [
            first_name.strip(),
            last_name.strip(),
            email.strip(),
            date_from.isoformat(),
            date_to.isoformat(),
            STATUS_TO_SHEET[STATUS_PENDING],
            uuid.uuid4().hex[:12],
            datetime.now().isoformat(timespec="seconds"),
        ],
        value_input_option="USER_ENTERED",
    )

    _invalidate()


def _find_row(reservation_id):
    """Vrátí číslo řádku s danou rezervací, nebo None."""
    ids = _worksheet().col_values(COL_ID)

    for index, value in enumerate(ids, start=1):
        if index == 1:
            continue  # hlavička

        if str(value).strip() == str(reservation_id):
            return index

    return None


def set_status(reservation_id, status):
    row = _find_row(reservation_id)

    if row is not None:
        _worksheet().update_cell(row, COL_STATUS, STATUS_TO_SHEET[status])
        _invalidate()


def delete_reservation(reservation_id):
    row = _find_row(reservation_id)

    if row is not None:
        _worksheet().delete_rows(row)
        _invalidate()
