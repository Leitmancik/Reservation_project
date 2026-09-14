# Rezervace chalupy

Streamlit aplikace pro správu rezervací ubytování.

## Jak to funguje

Aplikace má dvě stránky v horním menu:

- **Kalendář** — dva měsíce vedle sebe, mezi kterými se listuje
  šipkami. Termín se vybírá kliknutím: první klik určí den příjezdu,
  druhý den odjezdu. Když je vybraný jen příjezd, nabídnou se rychlé
  délky pobytu (2, 3, 7 a 14 nocí). Pak se objeví formulář na jméno,
  příjmení a e-mail.
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
| 🟦 modrá | právě vybíraný pobyt |
| ⬜ šedá | den už byl, nejde vybrat |

U vybíraného pobytu se stejně jako u rezervací obarví jen ty poloviny
dnů, které pobyt skutečně zabírá — v den příjezdu odpoledne, v den
odjezdu dopoledne.

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
| `storage_appsscript.py` | ukládání do Sheets přes skript v tabulce |
| `storage_sheets.py` | ukládání do Sheets přes servisní účet |
| `storage_sqlite.py` | ukládání do souboru (lokální vývoj) |
| `ui.py` | drobné UI pomůcky |
| `nastav_sheets.py` | jednorázové nastavení servisního účtu |
| `apps_script/Kod.gs` | skript, který běží uvnitř tabulky |

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

Zápis do Google Sheets vyžaduje přihlášení, a to i u tabulky sdílené
odkazem. Jsou na to dvě cesty a stačí si vybrat jednu.

#### Varianta A — Apps Script (doporučeno)

Nepotřebuje Google Cloud ani stažené klíče, takže ji neblokují
bezpečnostní politiky organizace. Skript běží přímo v tabulce.

1. Otevři tabulku → **Rozšíření → Apps Script**
2. Smaž ukázkový obsah a vlož kód z `apps_script/Kod.gs`
3. V něm nahraď `SEM_VLOZ_TOKEN` vlastním heslem
4. **Nasadit → Nová implementace** → typ **Webová aplikace**,
   spustit jako **Já**, přístup **Kdokoli** → **Nasadit**
   (přístup musí být **Kdokoli**, ne „kdokoli v rámci domény" —
   jinak se k němu aplikace nedostane)
5. Zkopíruj adresu webové aplikace (končí na `/exec`)
6. Do `.streamlit/secrets.toml` vlož:

   ```toml
   appsscript_url = "https://script.google.com/macros/s/..../exec"
   appsscript_token = "stejné heslo jako v Kod.gs"
   ```

Token funguje jako heslo — adresa webové aplikace je veřejná, takže
bez něj by do tabulky mohl psát kdokoli, kdo ji zná.

Data se posílají metodou GET v parametru `payload`. Některé domény
Google Workspace totiž POST na webovou aplikaci neprotlačí a vrátí
chybu 405. Skript umí obojí, aplikace používá GET, protože projde vždy.

### Rychlost

Čtení z tabulky trvá několik sekund, proto si aplikace načtené
rezervace drží v paměti otevřené stránky. Na tabulku sáhne jen při
otevření stránky, po zápisu a po stisku tlačítka ↻. Klikání
v kalendáři a listování měsíci tak nečeká na síť.

Před uložením rezervace se ale vždy načtou čerstvá data, aby se
nestalo, že mezitím někdo jiný stejný termín zabral.

Google vydává výsledek na jednorázové adrese, která zhruba ve čtvrtině
případů odpoví chybou, přestože skript proběhl v pořádku. Aplikace to
řeší dvěma způsoby: požadavek zopakuje (až pětkrát) a identifikátor
rezervace vyrábí sama, takže zopakovaný zápis skript rozpozná a řádek
nezaloží podruhé. Pokud se odpověď ztratí i po všech pokusech, aplikace
se nejdřív podívá do tabulky, jestli změna přece jen neproběhla — a
teprve pak ohlásí chybu.

#### Varianta B — servisní účet

1. V [Google Cloud Console](https://console.cloud.google.com/) založ
   projekt a zapni v něm **Google Sheets API**.
2. V **IAM & Admin → Service Accounts** vytvoř servisní účet a stáhni
   si jeho klíč ve formátu **JSON**.
3. Spusť `python nastav_sheets.py` — skript si stažený JSON najde sám,
   vyrobí z něj `.streamlit/secrets.toml` a vypíše e-mail servisního
   účtu.
4. Otevři tabulku, dej **Sdílet** a nasdílej ji na ten e-mail
   s právem **Editor**.

Pozor: některé organizace zakazují stahování klíčů k servisním účtům
(politika `iam.disableServiceAccountKeyCreation`). Pak použij
variantu A.

Na Streamlit Community Cloud se obsah `secrets.toml` vkládá do
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
