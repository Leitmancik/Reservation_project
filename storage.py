"""Přístup k rezervacím — jediné místo, přes které aplikace sahá na data.

Máme dvě úložiště se stejným rozhraním:

    storage_sheets.py  — Google Sheets, ostrý provoz
    storage_sqlite.py  — soubor na disku, lokální vývoj

Použije se Sheets, jakmile jsou ve Streamlit secrets přihlašovací údaje
servisního účtu. Jinak appka spadne zpátky na SQLite, aby šla spustit
i bez připojení ke Googlu.
"""

import storage_sheets
import storage_sqlite

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"


def backend():
    """Vrátí modul, který se právě používá k ukládání."""
    if storage_sheets.is_configured():
        return storage_sheets

    return storage_sqlite


def backend_name():
    """Krátký popis úložiště pro zobrazení v aplikaci."""
    if backend() is storage_sheets:
        return "Google Sheets"

    return "místní soubor (data nepřežijí restart na Streamlit Cloud)"


def init_db():
    backend().init_db()


def load_reservations():
    return backend().load_reservations()


def add_reservation(first_name, last_name, email, date_from, date_to):
    backend().add_reservation(first_name, last_name, email, date_from, date_to)


def set_status(reservation_id, status):
    backend().set_status(reservation_id, status)


def delete_reservation(reservation_id):
    backend().delete_reservation(reservation_id)


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
