"""Nastaví připojení ke Google Sheets ze staženého JSON klíče.

Použití:

    python nastav_sheets.py                      # najde klíč ve Stažených
    python nastav_sheets.py cesta/ke/klici.json  # nebo zadej cestu rovnou

Skript vyrobí soubor .streamlit/secrets.toml, vypíše e-mail servisního
účtu (ten je potřeba nasdílet do tabulky) a nakonec ověří, že zápis
do tabulky opravdu funguje.
"""

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).parent
SECRETS = PROJECT / ".streamlit" / "secrets.toml"
SHEET_ID = "1izUy4AgW32PJFLSL3Cs9xHfLmmPf229FUSz6Z6w0oNM"

REQUIRED = ["client_email", "private_key", "project_id", "token_uri"]


def find_key_file():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser()

    candidates = []

    for folder in (Path.home() / "Downloads", Path.home() / "Stažené soubory", PROJECT):
        if folder.is_dir():
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text())
                except Exception:
                    continue

                if data.get("type") == "service_account":
                    candidates.append((path.stat().st_mtime, path))

    if not candidates:
        return None

    return max(candidates)[1]


def toml_value(text):
    # json.dumps zajistí správné uvozovky i escapování \n v privátním klíči.
    return json.dumps(text, ensure_ascii=False)


def main():
    key_file = find_key_file()

    if key_file is None or not key_file.is_file():
        print("✗ Nenašel jsem JSON klíč servisního účtu.")
        print("  Stáhni ho z Google Cloud Console a spusť skript znovu,")
        print("  případně zadej cestu: python nastav_sheets.py klic.json")
        return 1

    print(f"Používám klíč: {key_file}")

    data = json.loads(key_file.read_text())

    missing = [k for k in REQUIRED if not data.get(k)]

    if missing:
        print(f"✗ V souboru chybí položky: {', '.join(missing)}")
        print("  Nevypadá to na klíč servisního účtu.")
        return 1

    lines = [
        "# Vygeneroval nastav_sheets.py — needituj ručně.",
        f"sheet_id = {toml_value(SHEET_ID)}",
        "",
        "[gcp_service_account]",
    ]

    for key, value in data.items():
        if isinstance(value, str):
            lines.append(f"{key} = {toml_value(value)}")

    SECRETS.parent.mkdir(exist_ok=True)
    SECRETS.write_text("\n".join(lines) + "\n")

    print(f"✓ Zapsáno do {SECRETS.relative_to(PROJECT)}")
    print()
    print("=" * 62)
    print("NASDÍLEJ TABULKU NA TENHLE E-MAIL (právo Editor):")
    print()
    print(f"   {data['client_email']}")
    print()
    print("=" * 62)
    print()

    print("Zkouším se připojit k tabulce…")

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_info(
            data,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ],
        )

        worksheet = gspread.authorize(credentials).open_by_key(SHEET_ID).sheet1
        worksheet.row_values(1)

    except Exception as error:
        message = str(error)

        if "PERMISSION_DENIED" in message or "permission" in message.lower():
            print("✗ Tabulka zatím není nasdílená servisnímu účtu.")
            print("  Otevři ji, klikni na Sdílet a přidej e-mail výše")
            print("  jako Editor. Pak spusť skript znovu.")
        elif "SERVICE_DISABLED" in message or "has not been used" in message:
            print("✗ V projektu není zapnuté Google Sheets API.")
            print("  Zapni ho v Google Cloud Console a spusť skript znovu.")
        else:
            print(f"✗ Nepodařilo se připojit: {message[:300]}")

        return 1

    print("✓ Připojení funguje, tabulka je přístupná.")
    print()
    print("Hotovo. Spusť aplikaci: streamlit run streamlit_app.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
