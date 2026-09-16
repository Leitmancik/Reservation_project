# PROJECT_CONTEXT.md

Kontext projektu pro AI agenta, který na něm bude pokračovat.
Čti před první změnou kódu.

---

## Co projekt dělá

Streamlit aplikace pro rezervaci jedné rekreační nemovitosti (chalupy).
Data leží v Google Sheets, aby k nim měl majitel přístup i bez aplikace.

Tři stránky v horním menu:

| Stránka | Obsah |
|---|---|
| **Kalendář** (`/kalendar`) | dva měsíce vedle sebe, výběr termínu klikáním, formulář rezervace |
| **Rezervace** (`/rezervace`) | seznam záznamů, potvrzování, mazání, export CSV/Excel |
| **Cenotvorba** (`/cenotvorba`) | základní cena a období, která ji přebíjejí |

Uživatel je majitel chalupy — netechnický. UI je celé česky.

---

## Architektura

### Vrstvy

```
streamlit_app.py          navigace (st.navigation, position="top")
   ├── page_calendar.py   ─┐
   ├── page_reservations.py│ stránky (UI, žádná doménová logika)
   └── page_pricing.py    ─┘
         │
         ├── calendar_view.py   vykreslení kalendáře (HTML/CSS + st.button)
         ├── pricing.py         výpočet ceny (čisté funkce, bez Streamlitu)
         ├── ui.py              flash hlášky, formátování ceny a nocí
         │
         └── storage.py         FASÁDA — jediný vstup k datům
               ├── storage_sheets.py      Google Sheets přes servisní účet
               ├── storage_appsscript.py  Google Sheets přes skript v tabulce
               └── storage_sqlite.py      lokální soubor
```

### Výběr úložiště

`storage.backend()` vybírá podle Streamlit secrets, v tomto pořadí:

1. `appsscript_url` + `appsscript_token` → `storage_appsscript`
2. `gcp_service_account` → `storage_sheets`
3. jinak → `storage_sqlite`

Všechny tři mají stejné rozhraní. Stránky nikdy neimportují backend přímo,
sahají výhradně přes `storage.py`.

**Aktuálně se lokálně používá `storage_sheets` (servisní účet).**

### Cachování

Načtená data se drží v `st.session_state` (klíče `_reservations_cache`,
`_prices_cache`). Streamlit spouští celý skript znovu po každém kliknutí —
bez cache by každý klik čekal na síť (3–5 s).

- `storage.load_reservations()` / `load_prices()` čtou z cache
- `force=True` obchází cache — **povinné před uložením rezervace**,
  aby se nezabral termín, který mezitím někdo vzal
- zápis cache sám zneplatní (`refresh()`, `refresh_prices()`)
- `init_db()` je obalený `@st.cache_resource`, běží jednou za proces

---

## Důležité soubory

| Soubor | Role |
|---|---|
| `storage.py` | fasáda + `find_conflict()` (překryv rezervací) |
| `storage_sheets.py` | Sheets přes gspread; hlavičky, migrace sloupců, překlad chyb |
| `storage_appsscript.py` | HTTP volání skriptu v tabulce; retry a idempotence |
| `storage_errors.py` | `StorageError` — jediná výjimka, kterou stránky chytají |
| `pricing.py` | `price_for_night()`, `stay_total()`, `overlaps()` — bez Streamlitu, snadno testovatelné |
| `calendar_view.py` | `half_states()` (obsazenost půlek dne), generování CSS, mřížka tlačítek |
| `apps_script/Kod.gs` | kód nasazený v Google tabulce (jen pro Apps Script variantu) |
| `nastav_sheets.py` | jednorázové nastavení servisního účtu z JSON klíče |
| `.streamlit/secrets.toml` | přihlašovací údaje — **v .gitignore, nikdy necommitovat** |

---

## Struktura dat

Google tabulka má dva listy.

**List `Rezervace`** (9 sloupců, pořadí je závazné):

```
Jméno | Příjmení | email | Datum - Start | Datum - Konec | Stav | ID | Vytvořeno | Cena celkem
```

- `Stav`: `Čeká na potvrzení` / `Potvrzeno` (v kódu `pending` / `confirmed`)
- `ID`: generuje aplikace (uuid4 hex, 12 znaků), ne tabulka
- `Cena celkem`: částka platná při vzniku rezervace; starší řádky prázdné

**List `Cenotvorba`**:

```
Od | Do | Cena za noc | Popis | ID
```

Řádek s prázdným `Od`/`Do` je **základní cena**.

---

## Technologie

- Python 3.12, virtuální prostředí v `.venv/`
- Streamlit 1.63 (`st.navigation` s `position="top"`, `st.Page`)
- gspread 6.2.1 + google-auth
- pandas 3.0.5, openpyxl (export)
- Hosting: Streamlit Community Cloud, repo `Leitmancik/Reservation_project`

---

## Jak projekt spustit

```bash
cd ~/Desktop/Reservation_project
source .venv/bin/activate
streamlit run streamlit_app.py
```

Bez `secrets.toml` naběhne na SQLite a funguje, jen bez napojení na tabulku.

### Testování

Automatické testy v repozitáři **nejsou**. Ověřuje se přes
`streamlit.testing.v1.AppTest`, který spustí aplikaci bez prohlížeče:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("streamlit_app.py", default_timeout=180)
at.run()
assert not at.exception
days = {b.key: b for b in at.button if b.key and b.key.startswith("day-")}
```

Stav dne se dá ověřit přímo z klíče tlačítka — formát
`day-<ISO datum>-<dopoledne>-<odpoledne>-<stav výběru>`.

Vizuální kontrola: headless Chrome přes CDP (`--remote-debugging-port=9222`)
a knihovnu `websockets`. Chrome je na macOS v
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
Statický `--screenshot` nepoužívat — nepočká na vykreslení Streamlitu.

### Nasazení

Push do `main` nasadí novou verzi automaticky. Secrets se na Streamlit
Cloudu vkládají v **Settings → Secrets**, soubor se tam nenahrává.

---

## Konvence

- **Uživatelské texty, docstringy i komentáře česky.** Názvy proměnných
  a funkcí anglicky.
- **Komentáře vysvětlují proč, ne co.** Kód, který je jasný, komentář nemá.
- Odsazení 4 mezery, řádky do ~79 znaků, prázdný řádek mezi logickými bloky.
- Tlačítka a tabulky: `width="stretch"`. `use_container_width` je
  ve Streamlitu 1.63 zastaralé, nepoužívat.
- Hlášky přežívající `st.rerun()` přes `ui.set_flash()` / `show_flash()` —
  `st.success()` těsně před rerunem by se ztratil.
- Ceny formátovat `ui.format_price()`, počty nocí `ui.nights_label()`
  (skloňování: 1 noc, 3 noci, 5 nocí).
- Commit messages česky bez diakritiky, vysvětlují důvod změny.

---

## Důležitá rozhodnutí

### Půlené dny (jádro domény)

Check-in 15:00, check-out 11:00. Každý den v kalendáři je rozdělený
úhlopříčkou na dvě poloviny, které se obsazují nezávisle:

```python
# calendar_view.half_states()
morning  obsazeno když  res.date_from <  day <= res.date_to
afternoon obsazeno když  res.date_from <= day <  res.date_to
```

Den odjezdu jednoho hosta a příjezdu dalšího je tedy tentýž den se dvěma
barvami. Vizuálně řešeno `linear-gradient(135deg, …)` — levý horní
trojúhelník dopoledne, pravý dolní odpoledne.

### Překryv rezervací

```python
# storage.find_conflict()
konflikt = date_from < res.date_to and res.date_from < date_to
```

Navazující pobyty (odjezd 5. a příjezd 5.) **nejsou** konflikt. Tohle je
přímý důsledek pravidla 11:00/15:00 a nesmí se změnit na `<=`.

### CSS přes klíče widgetů

Streamlit dává widgetu s `key` třídu `st-key-<key>`. Do klíče dne je proto
zakódovaný stav obou půlek a výběru — devět barevných kombinací tak stačí
popsat devíti pravidly místo jednoho pravidla na každý den v roce.

### Ceník

Základní cena + období, která ji přebíjejí. **Při překryvu vyhrává kratší
období** (`pricing.seasons()` řadí podle délky) — svátek uvnitř sezóny tak
funguje bez dělení sezóny na kusy.

Cena se počítá **za noc podle dne příjezdu**: pobyt 4.→7. jsou tři noci
(4., 5., 6.). Období 1. 7. – 31. 8. proto pokrývá i noc z 31. 8. na 1. 9.

### Cena u rezervace

Ukládá se částka platná v okamžiku rezervace, nedopočítává se. Pozdější
změna ceníku nesmí přepsat, na čem se majitel s hostem domluvil.
Souhrn na stránce Rezervace sčítá **jen potvrzené**.

### Nové sloupce jen na konec

`storage_sheets._ensure_header()` dorovnává chybějící sloupce na konec
tabulky. Vkládání doprostřed by posouvalo existující data.

---

## Známé problémy a workaroundy

### Apps Script vrací 404 zhruba u čtvrtiny požadavků

Google vydává výsledek na jednorázové adrese, která často selže, i když
skript proběhl. Naměřeno 9 úspěchů z 12. Nezávisí to na hlavičkách
ani na použité knihovně.

Řešení v `storage_appsscript.py`:
- až 5 pokusů (`RETRY_ATTEMPTS`)
- **ID rezervace generuje aplikace**, ne skript — jinak opakovaný zápis
  založí duplicitní řádek
- mazání nehlásí chybu, když řádek už neexistuje
- když se odpověď ztratí i po všech pokusech, ověří se skutečný stav
  v tabulce a teprve pak se hlásí chyba

### Apps Script komunikuje přes GET

Některé domény Google Workspace neprotlačí POST na webovou aplikaci
(vrátí 405). Data se posílají v query parametru `payload`.

### Apps Script neukládá cenu

`Kod.gs` zapisuje pevný seznam sloupců. Rozšířit by šlo, ale vyžaduje
znovu nasadit webovou aplikaci. Přes servisní účet cena funguje.

### SQLite na Streamlit Cloudu nepřežije restart

Tamní disk je dočasný. Pro ostrý provoz musí být nastavené Sheets.

### Organizační politika blokuje klíče servisních účtů

`iam.disableServiceAccountKeyCreation` (Google „Secure by Default").
Vypíná se v **Zásadách organizace**, ne v projektu, a vyžaduje roli
`roles/orgpolicy.policyAdmin`. Už je vyřešené, ale při obnově klíče
se to vrátí.

### macOS blokuje agentovi přístup do ~/Downloads

Soubor je vidět (`test -f` projde), ale čtení skončí
`Operation not permitted`. Uživatele požádej o přesun na plochu.

### Headless Chrome občas neudrží spojení

Při ladění screenshotů počítej s tím, že proces spadne; testy přes
`AppTest` jsou spolehlivější.

---

## Co se právě řeší

- **Streamlit Cloud pravděpodobně stále běží na Apps Scriptu.** Lokálně
  je nastavený servisní účet; na cloudu je potřeba přepsat Secrets
  obsahem `.streamlit/secrets.toml`. Do té doby tam nefunguje ukládání ceny.
- **Pět starších rezervací nemá vyplněnou cenu** (vznikly před přidáním
  sloupce). Dopsat ručně, nebo jednorázovým skriptem podle aktuálního ceníku.
- V repozitáři je větev `jakub/initial-setup` a konfigurace Dev Containeru
  od dalšího přispěvatele — před pushem ověřit, co je na `origin/main`.

---

## Co rozhodně neměnit bez důvodu

1. **`find_conflict()`** — ostré nerovnosti povolují navazující pobyty.
   Změna na `<=` rozbije jádro domény.
2. **`half_states()`** — asymetrie `<` a `<=` je záměrná, drží pravidlo
   11:00 / 15:00.
3. **Idempotence u Apps Scriptu** — klientské ID a tolerantní mazání
   brání duplicitním rezervacím.
4. **Ověření čerstvých dat před uložením** (`load_reservations(force=True)`)
   — jinak vznikne dvojitá rezervace stejného termínu.
5. **`.streamlit/secrets.toml` v `.gitignore`** — repozitář je veřejný.
   Klíče servisních účtů na GitHubu roboti aktivně vyhledávají.
6. **Nepřidávat ověřovací volání při startu.** Dřív se posílal „ping",
   který při probouzení Apps Scriptu trval i 25 s a nic nepřinášel.
   Spojení se ověří při prvním načtení dat.
7. **Stránky nesmí importovat backend přímo** — jen přes `storage.py`,
   jinak přestane fungovat přepínání úložišť.
