# Rezervace chalupy

Streamlit aplikace pro správu rezervací ubytování.

## Jak to funguje

Aplikace má dvě stránky v horním menu:

- **Kalendář** — barevný přehled obsazenosti na 12 měsíců dopředu.
  Termín se vybírá kliknutím: první klik určí den příjezdu, druhý den
  odjezdu. Pak se objeví formulář na jméno, příjmení a e-mail.
- **Rezervace** — seznam záznamů, potvrzování a mazání, export do CSV/Excelu

### Půlené dny

Příjezd je od 15:00, odjezd do 11:00. Každý den v kalendáři je proto
rozdělený úhlopříčkou na dvě poloviny:

- **levý horní trojúhelník** = dopoledne (do 11:00, kdy se odjíždí)
- **pravý dolní trojúhelník** = odpoledne (od 15:00, kdy se přijíždí)

Pobyt od soboty do středy tak obarví jen odpolední půlku soboty, celé
neděle až úterý a jen dopolední půlku středy. Když další host začne
pobyt tou samou středou, obarví se její druhá půlka — ve čtverečku
jsou vidět dvě barvy.

Díky tomu smí na sebe pobyty navazovat ve stejný den. Blokují se jen
termíny, které se skutečně přesahují.

### Barvy

| Barva | Význam |
|---|---|
| 🟩 zelená | volno |
| 🟧 oranžová | rezervováno, čeká na potvrzení |
| 🟥 červená | potvrzeno |
| ⬜ šedá | den už byl, nejde vybrat |

Plně obsazené dny nejdou kliknout. Dny, kde je volná jen jedna půlka,
kliknout jdou — takový den totiž může posloužit jako odjezd jednoho
hosta a zároveň příjezd dalšího.

## Struktura souborů

| Soubor | K čemu je |
|---|---|
| `streamlit_app.py` | vstupní bod, horní menu |
| `page_calendar.py` | stránka Kalendář |
| `page_reservations.py` | stránka Rezervace |
| `calendar_view.py` | vykreslení kalendáře (HTML/CSS, půlené dny) |
| `storage.py` | přepíná úložiště, jediné místo sahající na data |
| `storage_sheets.py` | ukládání do Google Sheets (ostrý provoz) |
| `storage_sqlite.py` | ukládání do souboru (lokální vývoj) |
| `ui.py` | drobné UI pomůcky |

## Lokální spuštění

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Databáze

Rezervace se ukládají do Google Sheets. Tabulka má tyhle sloupce:

| Sloupec | Obsah |
|---|---|
| Jméno | křestní jméno hosta |
| Příjmení | příjmení hosta |
| email | kontaktní e-mail |
| Datum - Start | den příjezdu (od 15:00) |
| Datum - Konec | den odjezdu (do 11:00) |
| Stav | `Čeká na potvrzení` nebo `Potvrzeno` |
| ID | interní identifikátor řádku |
| Vytvořeno | kdy rezervace přišla |

Prvních pět sloupců je pro člověka, poslední tři potřebuje aplikace:
podle `ID` najde řádek při potvrzování a mazání, `Stav` drží potvrzení.
Do tabulky jde psát i ručně — jen ty tři sloupce nemazat.

### Nastavení přístupu

Zápis do Google Sheets vyžaduje přihlášení přes servisní účet, a to
i u tabulky sdílené odkazem. Postup:

1. V [Google Cloud Console](https://console.cloud.google.com/) založ
   projekt a zapni v něm **Google Sheets API**.
2. V **IAM & Admin → Service Accounts** vytvoř servisní účet a stáhni
   si jeho klíč ve formátu **JSON**.
3. Zkopíruj `.streamlit/secrets.toml.example` na
   `.streamlit/secrets.toml` a vyplň hodnoty z toho JSON souboru.
4. Otevři tabulku v prohlížeči, dej **Sdílet** a nasdílej ji na
   `client_email` ze servisního účtu s právem **Editor**.
5. Na Streamlit Community Cloud vlož stejný obsah do
   **Settings → Secrets** (soubor se tam nenahrává).

Dokud přihlašovací údaje chybí, aplikace ukládá do SQLite souboru
`reservations.db` vedle kódu, aby šla spustit i bez připojení ke
Googlu. Na stránce Rezervace je vždy vidět, které úložiště je právě
aktivní.

> **Pozor:** SQLite na Streamlit Community Cloud nepřežije restart,
> tamní disk je dočasný. Pro ostrý provoz musí být nastavené Sheets.

## Nasazení

Nasazeno na Streamlit Community Cloud ze souboru `streamlit_app.py`
na větvi `main`. Každý push do `main` nasadí novou verzi automaticky.
