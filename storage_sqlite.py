"""Ukládání rezervací do SQLite souboru vedle kódu.

Používá se pro lokální vývoj a jako záloha, když není nastavené
připojení ke Google Sheets. Na Streamlit Community Cloud je disk
dočasný, takže tam data nepřežijí restart — ostrý provoz patří
do storage_sheets.py.

Rozhraní je stejné jako u storage_sheets.py, přepíná se v storage.py.
"""

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "reservations.db"

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Vytvoří tabulku, pokud ještě neexistuje. Volá se při startu."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name  TEXT NOT NULL,
                email      TEXT NOT NULL,
                date_from  TEXT NOT NULL,
                date_to    TEXT NOT NULL,
                status     TEXT NOT NULL,
                created_at TEXT NOT NULL,
                price      REAL
            )
            """
        )

        # Sloupec přibyl později — u starších databází ho dorovnáme.
        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(reservations)")
        ]

        if "price" not in columns:
            conn.execute("ALTER TABLE reservations ADD COLUMN price REAL")


def load_reservations():
    """Vrátí všechny rezervace jako seznam slovníků, seřazené podle příjezdu."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reservations ORDER BY date_from"
        ).fetchall()

    return [
        {
            "id": str(row["id"]),
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "date_from": date.fromisoformat(row["date_from"]),
            "date_to": date.fromisoformat(row["date_to"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "price": row["price"],
        }
        for row in rows
    ]


def add_reservation(first_name, last_name, email, date_from, date_to, price=None):
    """Přidá novou rezervaci ve stavu 'pending' (čeká na potvrzení)."""
    from datetime import datetime

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO reservations
                (first_name, last_name, email, date_from, date_to,
                 status, created_at, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                first_name.strip(),
                last_name.strip(),
                email.strip(),
                date_from.isoformat(),
                date_to.isoformat(),
                STATUS_PENDING,
                datetime.now().isoformat(timespec="seconds"),
                price,
            ),
        )


def set_status(reservation_id, status):
    """Přepne rezervaci mezi 'pending' a 'confirmed'."""
    with _connect() as conn:
        conn.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )


def delete_reservation(reservation_id):
    with _connect() as conn:
        conn.execute(
            "DELETE FROM reservations WHERE id = ?",
            (reservation_id,),
        )


# ─────────────────────────── ceník ───────────────────────────


def _init_prices():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prices (
                id        TEXT PRIMARY KEY,
                date_from TEXT,
                date_to   TEXT,
                price     REAL NOT NULL,
                label     TEXT
            )
            """
        )


def load_prices():
    """Načte ceník. Řádek bez data je základní cena."""
    _init_prices()

    with _connect() as conn:
        rows = conn.execute("SELECT * FROM prices").fetchall()

    return [
        {
            "id": row["id"],
            "date_from": (
                date.fromisoformat(row["date_from"]) if row["date_from"] else None
            ),
            "date_to": (
                date.fromisoformat(row["date_to"]) if row["date_to"] else None
            ),
            "price": row["price"],
            "label": row["label"] or "",
        }
        for row in rows
    ]


def save_price(price_id, date_from, date_to, price, label):
    import uuid

    _init_prices()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO prices (id, date_from, date_to, price, label)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date_from = excluded.date_from,
                date_to   = excluded.date_to,
                price     = excluded.price,
                label     = excluded.label
            """,
            (
                price_id or uuid.uuid4().hex[:12],
                date_from.isoformat() if date_from else None,
                date_to.isoformat() if date_to else None,
                price,
                label.strip(),
            ),
        )


def delete_price(price_id):
    _init_prices()

    with _connect() as conn:
        conn.execute("DELETE FROM prices WHERE id = ?", (price_id,))
