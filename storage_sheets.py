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

import re
import uuid
from datetime import date, datetime

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

from storage_errors import StorageError

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"

# Do tabulky píšeme stav česky, ať je čitelný i pro člověka.
STATUS_TO_SHEET = {
    STATUS_PENDING: "Čeká na potvrzení",
    STATUS_CONFIRMED: "Potvrzeno",
}
SHEET_TO_STATUS = {v: k for k, v in STATUS_TO_SHEET.items()}

RESERVATIONS_SHEET = "Rezervace"
PRICING_SHEET = "Cenotvorba"

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

PRICING_HEADER = ["Od", "Do", "Cena za noc", "Popis", "ID"]
PRICING_COL_ID = PRICING_HEADER.index("ID") + 1

DEFAULT_SHEET_ID = "1izUy4AgW32PJFLSL3Cs9xHfLmmPf229FUSz6Z6w0oNM"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Jak dlouho držet načtená data, než se sáhne znovu do Sheets.
# Krátká sdílená cache: když appku otevře víc lidí naráz, sáhne se
# do tabulky jen jednou. Hlavní zrychlení ale dělá paměť stránky
# ve storage.py.
CACHE_TTL_SECONDS = 60


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
def _spreadsheet():
    """Otevře dokument. Spojení se drží, nenavazuje se pořád dokola."""
    try:
        credentials = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=SCOPES,
        )

        return gspread.authorize(credentials).open_by_key(_sheet_id())
    except gspread.exceptions.APIError as error:
        raise _readable(error)
    except Exception as error:
        raise StorageError(f"Nepodařilo se připojit k tabulce: {error}")


@st.cache_resource(show_spinner=False)
def _worksheet():
    """List s rezervacemi."""
    document = _spreadsheet()

    try:
        worksheet = document.worksheet(RESERVATIONS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        # Starší tabulky mají list pojmenovaný jinak — vezmeme první.
        worksheet = document.sheet1
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _ensure_header(worksheet)

    return worksheet


@st.cache_resource(show_spinner=False)
def _pricing_worksheet():
    """List s ceníkem. Když ještě není, založí se."""
    document = _spreadsheet()

    try:
        worksheet = document.worksheet(PRICING_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        try:
            worksheet = document.add_worksheet(
                title=PRICING_SHEET, rows=200, cols=len(PRICING_HEADER)
            )
        except gspread.exceptions.APIError as error:
            raise _readable(error)
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    if not worksheet.row_values(1):
        worksheet.update(
            range_name=f"A1:{chr(ord('A') + len(PRICING_HEADER) - 1)}1",
            values=[PRICING_HEADER],
        )
        worksheet.format(
            f"A1:{chr(ord('A') + len(PRICING_HEADER) - 1)}1",
            {"textFormat": {"bold": True}},
        )
        worksheet.freeze(rows=1)

    return worksheet


def _readable(error):
    """Přeloží chybu z Google API na větu, která poradí, co s tím."""
    text = str(error)

    if "PERMISSION_DENIED" in text or "permission" in text.lower():
        return StorageError(
            "Tabulka není nasdílená servisnímu účtu. Otevři ji, dej "
            "Sdílet a přidej e-mail účtu jako Editor."
        )

    if "SERVICE_DISABLED" in text or "has not been used" in text:
        return StorageError(
            "V projektu Google Cloud není zapnuté Google Sheets API."
        )

    if "RESOURCE_EXHAUSTED" in text or "Quota" in text:
        return StorageError(
            "Google dočasně odmítá další požadavky. Zkus to za chvíli."
        )

    if "NOT_FOUND" in text or "not found" in text.lower():
        return StorageError("Tabulka nebyla nalezena — zkontroluj sheet_id.")

    return StorageError(f"Tabulka odpověděla chybou: {text[:200]}")


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
    try:
        return _worksheet().get_all_records(expected_headers=HEADER)
    except gspread.exceptions.APIError as error:
        raise _readable(error)


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
    try:
        _append(first_name, last_name, email, date_from, date_to)
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _invalidate()


def _append(first_name, last_name, email, date_from, date_to):
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
    try:
        row = _find_row(reservation_id)

        if row is None:
            raise StorageError("Rezervace v tabulce není.")

        _worksheet().update_cell(row, COL_STATUS, STATUS_TO_SHEET[status])
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _invalidate()


def delete_reservation(reservation_id):
    try:
        row = _find_row(reservation_id)

        # Když řádek už není, je hotovo — hlásit chybu by bylo matoucí.
        if row is not None:
            _worksheet().delete_rows(row)
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _invalidate()


# ─────────────────────────── ceník ───────────────────────────


def _parse_price(value):
    """Přečte cenu z buňky. Zvládne i '15 000', '15 000 Kč' nebo '15.000'."""
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)
    cleaned = "".join(c for c in text if c.isdigit() or c in ",.")

    # Česky se tisíce oddělují tečkou nebo mezerou a desetinná část
    # čárkou. '15.000' proto znamená patnáct tisíc, ne patnáct korun.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")

    cleaned = cleaned.replace(",", ".")

    if cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "", cleaned.count(".") - 1)

    try:
        return float(cleaned)
    except ValueError:
        return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _load_price_rows():
    try:
        return _pricing_worksheet().get_all_records(
            expected_headers=PRICING_HEADER
        )
    except gspread.exceptions.APIError as error:
        raise _readable(error)


def load_prices():
    """Načte ceník. Řádek bez data je základní cena."""
    prices = []

    for row in _load_price_rows():
        price = _parse_price(row.get("Cena za noc"))

        # Řádek bez ceny je k ničemu, přeskočíme ho.
        if price is None:
            continue

        prices.append(
            {
                "id": str(row.get("ID", "")).strip(),
                "date_from": _parse_date(row.get("Od")),
                "date_to": _parse_date(row.get("Do")),
                "price": price,
                "label": str(row.get("Popis", "")).strip(),
            }
        )

    return prices


def _invalidate_prices():
    _load_price_rows.clear()


def _find_price_row(price_id):
    ids = _pricing_worksheet().col_values(PRICING_COL_ID)

    for index, value in enumerate(ids, start=1):
        if index == 1:
            continue

        if str(value).strip() == str(price_id):
            return index

    return None


def save_price(price_id, date_from, date_to, price, label):
    """Přidá nový řádek ceníku, nebo upraví stávající."""
    values = [
        date_from.isoformat() if date_from else "",
        date_to.isoformat() if date_to else "",
        price,
        label.strip(),
    ]

    try:
        if price_id:
            row = _find_price_row(price_id)

            if row is not None:
                _pricing_worksheet().update(
                    range_name=f"A{row}:D{row}",
                    values=[values],
                    value_input_option="USER_ENTERED",
                )
                _invalidate_prices()
                return

        _pricing_worksheet().append_row(
            values + [uuid.uuid4().hex[:12]],
            value_input_option="USER_ENTERED",
        )
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _invalidate_prices()


def delete_price(price_id):
    try:
        row = _find_price_row(price_id)

        if row is not None:
            _pricing_worksheet().delete_rows(row)
    except gspread.exceptions.APIError as error:
        raise _readable(error)

    _invalidate_prices()
