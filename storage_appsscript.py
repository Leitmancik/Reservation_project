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
import time
import uuid
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

# Google vydává výsledek na jednorázové adrese, která zhruba ve
# čtvrtině případů odpoví 404, i když skript proběhl v pořádku.
# Měřeno: 9 z 12 požadavků uspěje. Na hlavičkách ani na použité
# knihovně to nezávisí, spolehlivě pomáhá jedině zopakování —
# při pěti pokusech je šance na neúspěch kolem jedné promile.
RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 0.4

# Krátká sdílená cache: když appku otevře víc lidí naráz, sáhne se
# do tabulky jen jednou. Hlavní zrychlení ale dělá paměť stránky
# ve storage.py.
CACHE_TTL_SECONDS = 60


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

    Google navíc občas odmítne vydat výsledek, i když skript proběhl
    v pořádku, proto se požadavek v případě potřeby zopakuje.
    """
    body = {
        "token": st.secrets["appsscript_token"],
        "action": action,
    }
    body.update(payload)

    params = {"payload": json.dumps(body, ensure_ascii=False)}
    last_error = None

    for attempt in range(RETRY_ATTEMPTS):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS * attempt)

        try:
            response = requests.get(
                st.secrets["appsscript_url"],
                params=params,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout:
            last_error = StorageError(
                "Tabulka neodpovídá. Zkus to prosím za chvíli znovu."
            )
            continue
        except requests.exceptions.RequestException as error:
            last_error = StorageError(
                f"Nepodařilo se spojit s tabulkou: {error}"
            )
            continue

        try:
            data = response.json()
        except ValueError:
            # Místo JSON přišlo HTML. Buď je něco špatně nastavené —
            # to poznáme podle obsahu a nemá smysl to zkoušet znovu —
            # nebo Google jen nevydal výsledek a pomůže zopakování.
            text = response.text

            if "doGet" in text:
                raise StorageError(
                    "V tabulce je nasazená stará verze skriptu. "
                    "Nasaď prosím novou verzi s aktuálním kódem."
                )

            if "accounts.google.com" in text:
                raise StorageError(
                    "Skript není veřejný — v nasazení tabulky nastav "
                    "přístup „Kdokoli“."
                )

            last_error = StorageError(
                "Tabulka odpověděla nečekaně, zkus to prosím znovu."
            )
            continue

        if isinstance(data, dict) and data.get("error"):
            raise StorageError(data["error"])

        return data

    raise last_error or StorageError("Tabulka neodpovídá.")


def init_db():
    """Nic nedělá — hlavičku si tabulka doplní sama při prvním zápisu.

    Dřív se tu posílalo ověřovací volání, jenže to při startu aplikace
    přidávalo několik sekund navíc (a při probouzení skriptu i přes
    dvacet). Že spojení funguje, se stejně pozná hned při načtení
    rezervací.
    """


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
    # Identifikátor vyrábíme tady, ne v tabulce. Kdyby se odpověď
    # ztratila a požadavek se zopakoval, dorazí se stejným ID a skript
    # pozná, že řádek už založil — jinak by rezervace přibyla dvakrát.
    reservation_id = uuid.uuid4().hex[:12]

    row = {
        "ID": reservation_id,
        "Jméno": first_name.strip(),
        "Příjmení": last_name.strip(),
        "email": email.strip(),
        "Datum - Start": date_from.isoformat(),
        "Datum - Konec": date_to.isoformat(),
        "Stav": STATUS_TO_SHEET[STATUS_PENDING],
        "Vytvořeno": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        _call("add", row=row)
    except StorageError:
        # Odpověď se nemusela vrátit, i když zápis proběhl. Než chybu
        # ohlásíme uživateli, podíváme se, jestli rezervace v tabulce
        # není — jinak by ji zadal znovu a vznikl by duplikát.
        if not _exists(reservation_id):
            raise

    _invalidate()


def _exists(reservation_id):
    """Je rezervace s tímhle ID v tabulce?"""
    try:
        _invalidate()
        return any(r["id"] == reservation_id for r in load_reservations())
    except StorageError:
        return False


def set_status(reservation_id, status):
    try:
        _call("set_status", id=reservation_id, status=STATUS_TO_SHEET[status])
    except StorageError:
        # Stejně jako u zápisu: změna mohla projít, jen se ztratila
        # odpověď. Ověříme skutečný stav v tabulce.
        _invalidate()

        try:
            current = [
                r for r in load_reservations() if r["id"] == reservation_id
            ]
        except StorageError:
            raise

        if not current or current[0]["status"] != status:
            raise

    _invalidate()


def delete_reservation(reservation_id):
    try:
        _call("delete", id=reservation_id)
    except StorageError:
        # Když řádek v tabulce opravdu není, mazání proběhlo.
        if _exists(reservation_id):
            raise

    _invalidate()
