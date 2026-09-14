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
| `storage.py` | ukládání dat — jediné místo, které sahá na databázi |
| `ui.py` | drobné UI pomůcky |

## Lokální spuštění

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Databáze

Data se ukládají do SQLite souboru `reservations.db` vedle kódu.
Soubor je v `.gitignore`, takže se do gitu nenahrává.

> **Pozor při nasazení na Streamlit Community Cloud:** tamní disk je
> dočasný. Při každém restartu nebo novém nasazení se `reservations.db`
> smaže i s rezervacemi. Pro ostrý provoz je potřeba data přesunout
> jinam — stačí přepsat `storage.py`, zbytek aplikace zůstane beze změny.

## Nasazení

Nasazeno na Streamlit Community Cloud ze souboru `streamlit_app.py`
na větvi `main`. Každý push do `main` nasadí novou verzi automaticky.
