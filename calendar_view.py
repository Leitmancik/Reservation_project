"""Klikací kalendář obsazenosti.

Každý den je tlačítko rozdělené úhlopříčkou na dvě poloviny:

    levý horní trojúhelník  = dopoledne (do 11:00, kdy se odjíždí)
    pravý dolní trojúhelník = odpoledne (od 15:00, kdy se přijíždí)

Pobyt od soboty do středy obarví jen odpolední půlku soboty, celé
neděle až úterý a jen dopolední půlku středy. Když další host začne
pobyt tou samou středou, obarví se její druhá půlka a ve čtverečku
jsou vidět dvě barvy.

Barvy se tlačítkům přiřazují přes CSS. Streamlit dává každému widgetu
s `key` CSS třídu `st-key-<key>`, takže do klíče zakódujeme stav obou
polovin dne a stav výběru — devět kombinací barev pak stačí popsat
devíti pravidly místo jednoho pravidla pro každý den v roce.
"""

import calendar
from datetime import date

import streamlit as st

from storage import STATUS_CONFIRMED, STATUS_PENDING

MONTH_NAMES = [
    "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
]

WEEKDAY_NAMES = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]

# Každý měsíc se kreslí na pevných šest týdnů, i když poslední zůstane
# prázdný. Bez toho měl únor čtyři řádky a březen šest, takže vedle
# sebe měly měsíce různou výšku — sloupce se vycentrují každý zvlášť
# a nadpisy si přestaly odpovídat. Navíc při listování poskakoval
# zbytek stránky nahoru a dolů.
#
# Šest stačí vždycky: nejhorší případ je 31denní měsíc začínající
# v neděli, tedy 6 prázdných polí + 31 dnů = 37 ze 42 míst.
WEEKS_SHOWN = 6

FREE = "free"
PAST = "past"           # den, který už byl — nejde ho vybrat
SELECTED = "selected"   # půlka dne, kterou zabírá právě vybíraný pobyt

# Paleta pohledu správce. Syté výplně schválně — stav má být čitelný
# na první pohled přes celý měsíc. Odstíny jsou o stupeň světlejší než
# základní, aby na tmavém pozadí neřezaly do očí.
COLORS = {
    FREE: "#4ade80",
    STATUS_PENDING: "#fbbf24",
    STATUS_CONFIRMED: "#f87171",
    PAST: "#94a3b8",
    SELECTED: "#6366f1",
}

# Dva pohledy na tutéž mřížku. Klíč tlačítka nese stav obou půlek dne
# i stav výběru, takže na přepnutí vzhledu stačí jiná sada pravidel —
# kalendář se nikde nekreslí dvakrát.
VIEW_GUEST = "guest"   # střídmý, pro hosta, který hledá volno
VIEW_ADMIN = "admin"   # barevný přehled obsazenosti pro správce

# Paleta pohledu hosta ve dvou variantách.
#
# Všechny dostupné dny jsou světlé v obou motivech — kalendář tak
# funguje jako světlá karta položená na stránce, ať je stránka bílá
# nebo tmavá. Tmavý zůstane jen den, který už proběhl, takže odžitá
# část měsíce viditelně zapadne pod povrch.
#
# Díky tomu je číslo dne vždycky tmavé a nemusí se řídit motivem.
# Předchozí verze používala poloprůhledné vrstvy, jenže ty se chovají
# nesymetricky: světlé pozadí změní výrazně, tmavé skoro ne. Co bylo
# čitelné na bílém, na tmavém splývalo.
#
# Přepíná se přes prefers-color-scheme. Streamlit motiv do stránky
# nedává a ve výchozím nastavení ho přebírá od systému (projekt nemá
# .streamlit/config.toml, který by to přebil), takže to spolu sedí
# a CSS navíc reaguje bez reruns.
#
# Čeká na potvrzení má vlastní jantarovou barvu i v pohledu hosta.
# Původně vypadalo stejně jako Potvrzeno, protože pro hosta je den
# tak jako tak zabraný — jenže pro majitele je to obchodní informace:
# nepotvrzená rezervace znamená zákazníka, kterého je možné urgovat.
PALETTE_CSS = """
.stApp {
    --cal-free: #f1f5f9;
    --cal-pending: #fde68a;
    --cal-busy: #fecdd3;
    --cal-past: #e2e8f0;
    --cal-day-text: #0f172a;
    --cal-past-text: #94a3b8;
    --cal-split: rgba(15, 23, 42, .65);
    --cal-clash: #dc2626;
    --cal-clash-stripe: rgba(127, 29, 29, .55);
    --cal-busy-text: #9f1239;
    --cal-pending-text: #92400e;
    --cal-accent: #4f46e5;
    --cal-accent-soft: #c7d2fe;
    --cal-hover: #cbd5e1;
}
@media (prefers-color-scheme: dark) {
    .stApp {
        --cal-free: #cbd5e1;
        --cal-pending: #fcd34d;
        --cal-busy: #fda4af;
        --cal-past: #1e293b;
        --cal-day-text: #0f172a;
        --cal-past-text: #64748b;
        --cal-split: rgba(15, 23, 42, .65);
        --cal-clash: #f87171;
        --cal-clash-stripe: rgba(127, 29, 29, .6);
        --cal-busy-text: #881337;
        --cal-pending-text: #78350f;
        --cal-accent: #6366f1;
        --cal-accent-soft: #a5b4fc;
        --cal-hover: #f1f5f9;
    }
}
"""

GUEST_FREE = "var(--cal-free)"
GUEST_BUSY = "var(--cal-busy)"
GUEST_PENDING = "var(--cal-pending)"
ACCENT = "var(--cal-accent)"
ACCENT_SOFT = "var(--cal-accent-soft)"

# Stav výběru zakódovaný v klíči tlačítka.
PICK_NONE = "sel0"      # mimo výběr
PICK_START = "sel1"     # den příjezdu — zabírá jen odpoledne
PICK_END = "sel2"       # den odjezdu — zabírá jen dopoledne
PICK_INSIDE = "sel3"    # den uvnitř pobytu — zabírá celý
PICK_ONLY = "sel4"      # vybraný příjezd, odjezd se teprve hledá

STATES = [FREE, STATUS_PENDING, STATUS_CONFIRMED, SELECTED]


def _day_css(today, view, states):
    """CSS pro konkrétní dny, které jsou právě vidět.

    Stav dne se dřív kódoval do klíče tlačítka a barvily ho obecné
    kombinační selektory. Fungovalo to, jenže klíč se měnil při každé
    změně výběru — a Streamlit tlačítko se změněným klíčem zahodí
    a vytvoří znovu. Otevřená nápověda se pak neměla čeho pustit
    a zůstávala viset přes stránku.

    Klíč je proto stálý (jen datum) a stav nese pravidlo napsané
    přímo pro ten den. Pravidel je víc, ale jsou krátká a hlavně se
    tlačítka při klikání nepřetvářejí.
    """
    rules = [
        PALETTE_CSS,
        """
        /* Tlačítko vyplní celou buňku. Bez toho by mezi dny zůstaly
           mezery a vybraný termín by nešel nakreslit jako souvislý
           pruh — rozpadl by se na řadu oddělených čtverečků.
           Vizuální odstup dělá padding spolu s background-clip:
           výplň se ořízne na obsah, takže je uvnitř buňky zapuštěná.
           Pruh výběru si pak stačí přepnout na border-box a roztáhne
           se přes celou buňku až k sousedovi. */
        [class*="st-key-day-"] button {
            width: 100%;
            margin: 0;
            aspect-ratio: 1 / 1;
            min-height: 0 !important;
            padding: 4px !important;
            background-clip: content-box !important;
            border: 0 !important;
            border-radius: 12px;
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            position: relative;
            transition: background .12s ease;
        }
        /* Strop šířky patří jen řádku týdne, ne všemu, co dny obsahuje.
           :has() totiž matchuje i nadřazené bloky — dva měsíce vedle
           sebe jsou taky stHorizontalBlock a taky v sobě mají dny,
           takže by strop dostal celý pár a na měsíc by zbyla půlka.
           :not(:has(stHorizontalBlock)) vybere jen ty nejvnitřnější,
           tedy skutečné týdny. */
        /* Nadpis měsíce a záhlaví dnů. Patří sem, ne k legendě —
           kalendář je kreslí vždycky, kdežto legenda se vykreslit
           nemusí. Dokud byla tahle pravidla v legendě, stačilo, aby
           se nevykreslila, a záhlaví dnů se rozpadlo pod sebe. */
        .cal-month-title {
            font-size: 1rem;
            font-weight: 600;
            margin: .5rem 0 .35rem 0;
            text-align: center;
        }
        .cal-weekdays {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 0;
            text-align: center;
            font-size: .8rem;
            font-weight: 600;
            opacity: .7;
            margin-bottom: .25rem;
        }
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"]):not(
            :has([data-testid="stHorizontalBlock"])
        ),
        .cal-weekdays {
            max-width: 34rem;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        /* Blok obou měsíců a řádek se šipkami drží stejnou šířku a
           stojí uprostřed. Bez toho by byly šipky roztažené přes celé
           okno, tedy kus od mřížky, a měsíce by se rozutekly každý do
           své poloviny stránky. */
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"]):has(
            [data-testid="stHorizontalBlock"]
        ),
        [data-testid="stHorizontalBlock"]:has(.st-key-nav_prev) {
            max-width: 80rem;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        /* Zvětšení jen tam, kde se opravdu dá najet myší. Na dotyku
           by hover po klepnutí zůstal viset a den by zůstal nafouklý. */
        @media (hover: hover) and (pointer: fine) {
            [class*="st-key-day-"] button:hover:not(:disabled) {
                background-color: var(--cal-hover) !important;
            }
        }
        /* Na dotyku dáme zpětnou vazbu stiskem místo hoveru. */
        [class*="st-key-day-"] button:active:not(:disabled) {
            background-color: var(--cal-accent-soft) !important;
        }
        [class*="st-key-day-"] button:disabled {
            opacity: 1 !important;
            cursor: not-allowed;
        }
        [class*="st-key-day-"] {
            margin-bottom: -.35rem;
        }
        /* wrap=False udělá z řádku rolovatelný pás a tah prstem pak
           posouvá řádek místo stránky. Prst přitom na kalendáři začne
           skoro vždycky, protože zabírá většinu displeje.

           Obě osy musí být visible najednou. Zakázat jen vodorovnou
           nestačí: podle CSS se druhá osa z visible sama přepne na
           auto, takže z řádku vznikne svislý rolovací kontejner —
           a protože dny mají záporný spodní okraj, je v něm co
           rolovat. Řádek se pak posouval nahoru a dolů sám v sobě.

           touch-action: pan-y navíc pustí gesto na stránku i kdyby
           přetečení někdy přece jen vzniklo. */
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"]),
        [data-testid="stHorizontalBlock"]:has(.st-key-nav_prev),
        [data-testid="stHorizontalBlock"]:has([class*="st-key-quick_"]) {
            overflow: visible !important;
            touch-action: pan-y !important;
        }
        /* Totéž na samotných dnech: bez toho by tah, který začne
           přesně na tlačítku, mohl skončit jako nechtěné klepnutí
           místo odrolování. */
        [class*="st-key-day-"] button {
            touch-action: pan-y !important;
        }
        /* Prázdné pole drží místo a rozměr, ale nesmí být vidět.
           visibility (ne display) proto, aby si ponechalo velikost. */
        [class*="st-key-day-empty-"] button {
            visibility: hidden !important;
        }
        /* Šipky stojí v úzkém sloupci, takže výchozí vodorovné
           odsazení tlačítka bývá širší než sloupec a znak se odřízne.
           Proto ho rušíme a znak zvětšujeme ručně.

           margin-top je dorovnání na střed mřížky. vertical_alignment
           u sloupců vycentruje šipku na celý sloupec — jenže ten
           obsahuje i nadpis měsíce a záhlaví dnů, takže jeho střed
           leží nad středem mřížky. Přesné to být nemůže, výška se
           mění podle toho, jestli má měsíc pět nebo šest týdnů. */
        .st-key-nav_prev button,
        .st-key-nav_next button {
            padding: 0 !important;
            min-width: 0 !important;
            overflow: visible !important;
            height: 3rem !important;
            min-height: 3rem !important;
            font-size: 1.5rem !important;
            line-height: 1 !important;
            border-radius: 999px !important;
            margin-top: 2.8rem !important;
        }
        .st-key-nav_prev button p,
        .st-key-nav_next button p {
            overflow: visible !important;
            text-overflow: clip !important;
            font-size: 1.5rem !important;
            line-height: 1 !important;
        }
        /* wrap=False u st.columns zastaví skládání sloupců pod sebe,
           ale zároveň jim dá min-width: 8rem (128 px). Sedm dnů by pak
           chtělo 896 px a přeteklo by i na desktopu. Tady to minimum
           rušíme, ať se týden roztáhne přesně na dostupnou šířku. */
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"])
            > [data-testid="stColumn"],
        [data-testid="stHorizontalBlock"]:has(.st-key-nav_prev)
            > [data-testid="stColumn"] {
            min-width: 0 !important;
        }
        /* Stejný podíl šířky patří jen dnům v týdnu. Řádek s měsíci
           obsahuje dny taky, ale tam jsou krajní sloupce úzké šipky —
           kdyby dostaly stejný podíl, roztáhly by se na šířku měsíce. */
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"]):not(
            :has([data-testid="stHorizontalBlock"])
        ) > [data-testid="stColumn"] {
            flex: 1 1 0 !important;
        }
        @media (max-width: 640px) {
            [class*="st-key-day-"] button {
                border-radius: 10px;
                font-size: .95rem !important;
                /* Šedý záblesk, kterým Safari kvituje dotyk, přes
                   barevné půlky dne jen ruší. */
                -webkit-tap-highlight-color: transparent;
            }
            [class*="st-key-day-"] {
                margin-bottom: -.75rem;
            }
        }
        """
    ]

    if view == VIEW_ADMIN:
        rules.append(_admin_base())
    else:
        rules.append(_guest_base())

    for den, stav in sorted(states.items()):
        rules += _day_rules(den, stav, today, view)

    return "<style>" + "".join(rules) + "</style>"


def _admin_base():
    """Společné pro všechny dny v přehledu.

    Číslo je tmavé s bílým podsvitem — na sytých barvách stavů to
    funguje ve světlém i tmavém motivu.
    """
    return (
        '[class*="st-key-day-"] button {'
        "color: #111 !important;"
        "text-shadow: 0 0 3px rgba(255,255,255,.95),"
        " 0 0 3px rgba(255,255,255,.95) !important;"
        "}"
    )


def _guest_base():
    """Společné pro všechny dny v zákaznickém kalendáři."""
    return (
        '[class*="st-key-day-"] button {'
        "color: var(--cal-day-text) !important;"
        "text-shadow: none !important;"
        "}"
    )


# Výplně podle stavu. Správce vidí syté barvy, host tlumené z palety.
GUEST_FILL = {
    FREE: GUEST_FREE,
    STATUS_PENDING: GUEST_PENDING,
    STATUS_CONFIRMED: GUEST_BUSY,
    SELECTED: ACCENT,
    PAST: "var(--cal-past)",
}

# Zářez v rohu u dne, kdy se střídají dva hosté.
_ZAREZ = (
    "content: '';"
    "position: absolute;"
    "width: 38%;"
    "height: 38%;"
    "pointer-events: none;"
    "background: linear-gradient(135deg,"
    " transparent calc(50% - 1px),"
    " var(--cal-split) calc(50% - 1px),"
    " var(--cal-split) calc(50% + 1px),"
    " transparent calc(50% + 1px));"
)


def _pozadi(stav, view):
    """Deklarace pozadí jednoho dne."""
    pick = stav["pick"]

    # Vybraný termín se kreslí jako souvislý pruh přes celé buňky:
    # background-clip border-box přeteče zapuštění a napojí se na
    # souseda. Krajní dny jsou plné a zakulacené zvenčí.
    if pick == PICK_INSIDE:
        return [
            f"background: {ACCENT_SOFT} !important",
            "background-clip: border-box !important",
            "padding: 3px 0 !important",
            "border-radius: 0 !important",
        ]

    if pick in (PICK_START, PICK_END):
        radius = (
            "10px 0 0 10px" if pick == PICK_START else "0 10px 10px 0"
        )
        return [
            f"background: {ACCENT} !important",
            "background-clip: border-box !important",
            "padding: 3px 0 !important",
            f"border-radius: {radius} !important",
        ]

    # Vybraný příjezd bez odjezdu: není z čeho kreslit pruh.
    if pick == PICK_ONLY:
        return [
            f"background: {ACCENT} !important",
            "background-clip: content-box !important",
            "border-radius: 10px !important",
        ]

    if view == VIEW_GUEST and stav["past"]:
        # Minulost jde v zákaznickém kalendáři celá do pozadí.
        return [
            "background: var(--cal-past) !important",
            "background-clip: content-box !important",
        ]

    fill = COLORS if view == VIEW_ADMIN else GUEST_FILL

    return [
        f"background: linear-gradient(135deg,"
        f" {fill[stav['morning_name']]} 0 50%,"
        f" {fill[stav['afternoon_name']]} 50% 100%) !important",
        "background-clip: content-box !important",
    ]


def _barva_cisla(stav, view):
    """Deklarace pro číslo dne."""
    if stav["pick"] in (PICK_START, PICK_END, PICK_ONLY):
        return ["color: #fff !important", "opacity: 1 !important"]

    if view == VIEW_ADMIN:
        return []

    if stav["past"]:
        return ["color: var(--cal-past-text) !important"]

    pulky = (stav["morning_name"], stav["afternoon_name"])

    # Nepotvrzená rezervace kdekoli ve dni drží jantarovou barvu —
    # termín ještě není hotová věc.
    if STATUS_PENDING in pulky:
        return ["color: var(--cal-pending-text) !important"]

    if pulky == (STATUS_CONFIRMED, STATUS_CONFIRMED):
        return [
            "color: var(--cal-busy-text) !important",
            "opacity: .95 !important",
        ]

    return []


def _day_rules(den, stav, today, view):
    """Pravidla pro jeden konkrétní den."""
    sel = f".st-key-day-{den.isoformat()}"

    tlacitko = _pozadi(stav, view)

    if view == VIEW_ADMIN and stav["past"]:
        # Minulost si tady barvu nechá, jen ztlumenou — z historie
        # pobytů je pro majitele vidět, kdo kdy byl.
        tlacitko.append("opacity: .65 !important")

    if stav["clash"]:
        tlacitko += [
            "outline: 3px solid var(--cal-clash) !important",
            "outline-offset: -3px !important",
        ]

    if den == today:
        tlacitko.append(
            "box-shadow: inset 0 0 0 2px var(--cal-accent) !important"
        )

    out = [f"{sel} button {{" + ";".join(tlacitko) + ";}"]

    cislo = _barva_cisla(stav, view)

    if den == today:
        cislo.append("font-weight: 800 !important")

    if cislo:
        out.append(f"{sel} button p {{" + ";".join(cislo) + ";}")

    if view != VIEW_ADMIN:
        return out

    # Šrafy kolize a zářez střídání sdílejí ::after. Když nastane
    # obojí, vyhrávají šrafy — kolize je naléhavější informace.
    if stav["clash"]:
        out.append(f"{sel} button::before {{display: none !important;}}")
        out.append(
            f"{sel} button::after {{"
            "content: '';"
            "position: absolute;"
            "top: 4px; right: 4px; bottom: 4px; left: 4px;"
            "width: auto; height: auto;"
            "border-radius: inherit;"
            "pointer-events: none;"
            "background: repeating-linear-gradient(45deg,"
            " var(--cal-clash-stripe) 0 5px,"
            " transparent 5px 13px);"
            "}"
        )
    elif stav["swap"]:
        out.append(
            f"{sel} button::before {{" + _ZAREZ + "top: 4px; right: 4px;}"
        )
        out.append(
            f"{sel} button::after {{" + _ZAREZ + "bottom: 4px; left: 4px;}"
        )

    return out


def half_reservations(day, reservations):
    """Vrátí dva seznamy rezervací — pro dopoledne a pro odpoledne.

    Seznamy proto, že od chvíle, kdy nepotvrzené rezervace termín
    neblokují, může na jednu půlku dne připadat víc poptávek. Dřív
    tahle funkce vracela jednu rezervaci na půlku a v cyklu ji
    přepisovala, takže při překryvu poslední vyhrála a ta druhá byla
    v kalendáři neviditelná.
    """
    morning = []
    afternoon = []

    for res in reservations:
        # Ráno dne příjezdu je ještě volno, host dorazí až v 15:00.
        if res["date_from"] < day <= res["date_to"]:
            morning.append(res)

        # Odpoledne dne odjezdu je už volno, host odjel v 11:00.
        if res["date_from"] <= day < res["date_to"]:
            afternoon.append(res)

    return morning, afternoon


def _representative(rezervace):
    """Která rezervace půlku dne obarví, když se jich sejde víc.

    Potvrzená má přednost — je to hotová věc, zatímco poptávky se
    teprve řeší. Že jich je víc, hlásí kalendář zvlášť.
    """
    if not rezervace:
        return None

    for res in rezervace:
        if res["status"] == STATUS_CONFIRMED:
            return res

    return rezervace[0]


def half_states(day, reservations):
    """Vrátí dvojici (dopoledne, odpoledne) — rezervace, nebo None když volno."""
    morning, afternoon = half_reservations(day, reservations)

    return _representative(morning), _representative(afternoon)


def has_clash(day, reservations):
    """Připadá na některou půlku dne víc než jedna rezervace?"""
    morning, afternoon = half_reservations(day, reservations)

    return len(morning) > 1 or len(afternoon) > 1


def _state_name(res):
    return FREE if res is None else res["status"]


def _pick_state(day, sel_from, sel_to):
    """Jak se dne dotýká právě vybíraný pobyt."""
    if sel_from is None:
        return PICK_NONE

    if day == sel_from:
        # Dokud není vybraný odjezd, není z čeho kreslit pruh — den
        # zůstane samostatný. Jinak by z něj vybíhal pruh doprava
        # do dnů, které do pobytu vůbec nepatří.
        return PICK_START if sel_to is not None else PICK_ONLY

    if day == sel_to:
        return PICK_END

    if sel_to is not None and sel_from < day < sel_to:
        return PICK_INSIDE

    return PICK_NONE


# Jak se o obsazené půlce dne mluví, když se nesmí jmenovat host.
HALF_LABELS = {
    STATUS_PENDING: "na dotaz",
    STATUS_CONFIRMED: "obsazeno",
}


def half_text(res, view):
    """Popíše stav půlky dne. Jméno hosta jen v pohledu správce.

    Kdo si termín zabral, je osobní údaj. V zákaznickém kalendáři
    proto zůstane jen informace, že je den zabraný — to je všechno,
    co host pro rozhodnutí potřebuje.
    """
    if res is None:
        return "volno"

    if view == VIEW_ADMIN:
        return (
            f"{res['first_name']} {res['last_name']}"
            f" ({HALF_LABELS[res['status']]})"
        )

    return HALF_LABELS[res["status"]]


def occupancy_text(morning, afternoon, view=VIEW_GUEST):
    """Shrne obsazenost dne do jedné věty.

    Většinu dnů jde popsat jedním slovem — celý je volný, nebo celý
    zabraný. Na půlky se den dělí jen tam, kde pobyt začíná nebo končí,
    a teprve tam má smysl psát „volno od 15:00“. Rozepisovat obě půlky
    u každého dne zaplavilo nápovědu textem, ve kterém se ztratilo to
    podstatné.
    """
    if view == VIEW_ADMIN:
        return " · ".join(
            f"{kdy} {half_text(res, view)}"
            for kdy, res in (("do 11:00", morning), ("od 15:00", afternoon))
        )

    if morning is None and afternoon is None:
        return "volno"

    # Den, kdy někdo odjíždí — dopoledne ještě obsazeno, pak volno.
    if afternoon is None:
        return "volno od 15:00"

    # Den, kdy někdo přijíždí — do 11:00 ještě volno.
    if morning is None:
        return "volno do 11:00"

    if morning["status"] == afternoon["status"]:
        return HALF_LABELS[morning["status"]]

    # Obě půlky zabrané, ale každá jinak — typicky odjezd potvrzeného
    # hosta a příjezd toho, kdo se teprve ptá.
    return (
        f"do 11:00 {HALF_LABELS[morning['status']]}"
        f" · od 15:00 {HALF_LABELS[afternoon['status']]}"
    )


def day_state(day, reservations, sel_from, sel_to, today, view):
    """Spočítá všechno, co o dni potřebuje vykreslení i CSS.

    Je to jediné místo, kde se stav dne odvozuje. Dřív se počítal
    uvnitř vykreslování a do klíče tlačítka, takže se CSS a mřížka
    mohly rozejít.
    """
    morning, afternoon = half_states(day, reservations)

    # Nevybrat se dá jen den, jehož obě půlky drží potvrzená
    # rezervace. Nepotvrzená termín neblokuje.
    fully_booked = all(
        res is not None and res["status"] == STATUS_CONFIRMED
        for res in (morning, afternoon)
    )

    # Minulý den bez rezervace je šedý. Minulý den s rezervací si
    # barvu nechá, ať je v přehledu vidět historie pobytů.
    if day < today and morning is None and afternoon is None:
        morning_name = afternoon_name = PAST
    else:
        morning_name = _state_name(morning)
        afternoon_name = _state_name(afternoon)

    # Vybíraný pobyt obarvíme, ale u krajních dnů jen tu polovinu,
    # kterou skutečně zabírá: příjezd je od 15:00, odjezd do 11:00.
    pick = _pick_state(day, sel_from, sel_to)

    if pick == PICK_START:
        afternoon_name = SELECTED
    elif pick == PICK_END:
        morning_name = SELECTED
    elif pick == PICK_INSIDE:
        morning_name = afternoon_name = SELECTED

    return {
        "morning": morning,
        "afternoon": afternoon,
        "morning_name": morning_name,
        "afternoon_name": afternoon_name,
        "pick": pick,
        "past": day < today,
        "disabled": day < today,
        "fully_booked": fully_booked,
        # Den, kdy jeden host odjíždí a druhý přijíždí.
        "swap": (
            morning is not None
            and afternoon is not None
            and str(morning["id"]) != str(afternoon["id"])
        ),
        # Na jednu půlku dne připadá víc poptávek.
        "clash": view == VIEW_ADMIN and has_clash(day, reservations),
    }


def month_days(year, month):
    """Dny měsíce tak, jak se kreslí — včetně prázdných polí."""
    first_weekday, days_in_month = calendar.monthrange(year, month)

    policka = []
    day_number = 1

    for week_index in range(WEEKS_SHOWN):
        for weekday in range(7):
            if (day_number == 1 and weekday < first_weekday) or (
                day_number > days_in_month
            ):
                policka.append((week_index, weekday, None))
                continue

            policka.append((week_index, weekday, date(year, month, day_number)))
            day_number += 1

    return policka


def _tooltip(day, morning, afternoon, disabled, view=VIEW_GUEST):
    parts = [
        day.strftime("%d.%m.%Y"),
        occupancy_text(morning, afternoon, view),
    ]

    if disabled:
        parts.append("nelze vybrat")

    return "\n".join(parts)


def month_range(start, count):
    """Vrátí seznam (rok, měsíc) — `count` měsíců počínaje měsícem `start`."""
    base = start.year * 12 + (start.month - 1)
    return [((base + i) // 12, (base + i) % 12 + 1) for i in range(count)]


def render_month(year, month, states, view=VIEW_GUEST):
    """Vykreslí jeden měsíc. Vrátí datum, na které uživatel klikl, jinak None.

    Stavy dnů dostane hotové — spočítaly se jednou v render_calendar,
    protože je z nich zároveň postavené CSS.
    """
    st.html(
        f'<div class="cal-month-title">'
        f"{MONTH_NAMES[month - 1]} {year}</div>"
    )
    st.html(
        '<div class="cal-weekdays">'
        + "".join(f"<div>{name}</div>" for name in WEEKDAY_NAMES)
        + "</div>"
    )

    clicked = None
    policka = month_days(year, month)

    # Kalendář kreslíme po týdnech, aby dny seděly pod správnými
    # názvy dnů i v měsíci, který nezačíná v pondělí.
    for week_index in range(WEEKS_SHOWN):
        # wrap=False: bez toho Streamlit pod ~640 px přeskládá
        # každý sloupec pod sebe a ze sedmi dnů týdne udělá sloupec.
        # gap=0: dny se musí dotýkat, jinak se pruh vybraného
        # termínu rozpadne na oddělené čtverečky.
        cols = st.columns(7, gap=0, wrap=False)

        tyden = [p for p in policka if p[0] == week_index]

        for _, weekday, day in tyden:
            if day is None:
                with cols[weekday]:
                    # Prázdné pole musí mít úplně stejnou stavbu jako
                    # den, jinak se řádek, ve kterém je, chová jinak
                    # vysoko než ostatní: záporný spodní okraj, kterým
                    # se řádky přitahují k sobě, sedí na obalu widgetu,
                    # a holý <div> ho nedostal. Proto je to taky
                    # tlačítko, jen schované přes CSS.
                    st.button(
                        "\u00a0",
                        key=(
                            f"day-empty-{year}-{month:02d}"
                            f"-{week_index}-{weekday}"
                        ),
                        disabled=True,
                        width="stretch",
                    )
                continue

            stav = states[day]

            with cols[weekday]:
                # Klíč je jen datum. Kdyby v něm byl stav, měnil by se
                # při každém výběru a Streamlit by tlačítko pokaždé
                # zahodil a vytvořil znovu — otevřená nápověda by pak
                # zůstala viset přes stránku.
                if st.button(
                    str(day.day),
                    key=f"day-{day.isoformat()}",
                    help=_tooltip(
                        day,
                        stav["morning"],
                        stav["afternoon"],
                        stav["disabled"] or stav["fully_booked"],
                        view,
                    ),
                    disabled=stav["disabled"],
                    width="stretch",
                ):
                    clicked = day

    return clicked


def render_calendar(
    months, reservations, sel_from, sel_to, today, columns=2,
    view=VIEW_GUEST, nav_prev=None, nav_next=None,
):
    """Vykreslí mřížku měsíců. Vrátí datum, na které uživatel klikl.

    `nav_prev` a `nav_next` jsou funkce, které vykreslí šipky pro
    listování. Nekreslí se nad kalendářem, ale do krajních sloupců
    téhož řádku, takže stojí přímo u mřížky a svisle uprostřed.

    Šipky si aplikace předává jako funkce, protože posun měsíců patří
    stránce — ta drží stav a ví, kam až se smí listovat. Kalendář jim
    jen dá místo.
    """
    # Stavy všech viditelných dnů spočítáme jednou. Staví se z nich
    # CSS i mřížka, takže se nemůžou rozejít.
    states = {
        day: day_state(day, reservations, sel_from, sel_to, today, view)
        for year, month in months
        for _, _, day in month_days(year, month)
        if day is not None
    }

    st.html(_day_css(today, view, states))

    clicked = None

    for row_start in range(0, len(months), columns):
        row = months[row_start:row_start + columns]

        # ◀ | měsíc | mezera | měsíc | ▶
        #
        # Mezeru dělá prázdný sloupec, ne gap. Gap je jedna ze tří
        # předvolených velikostí a „medium“ byla na oddělení dvou
        # měsíců málo — splývaly v jednu mřížku čtrnácti sloupců.
        spec = [2]
        mesice = []

        for index in range(len(row)):
            if index:
                spec.append(3)

            mesice.append(len(spec))
            spec.append(14)

        spec.append(2)

        cols = st.columns(
            spec,
            gap="medium",
            vertical_alignment="center",
            wrap=False,
        )

        with cols[0]:
            if nav_prev is not None:
                nav_prev()

        for index, (year, month) in enumerate(row):
            with cols[mesice[index]]:
                result = render_month(year, month, states, view)

                if result is not None:
                    clicked = result

        with cols[-1]:
            if nav_next is not None:
                nav_next()

    return clicked


LEGEND_CSS = """
<style>
.cal-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 1.1rem;
    align-items: center;
    font-size: .84rem;
    margin: .2rem 0 .8rem 0;
}
.cal-legend-item { display: flex; align-items: center; gap: .4rem; }
.cal-swatch {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid rgba(128, 128, 128, .35);
}
</style>
"""


def render_legend(view=VIEW_GUEST):
    """Vysvětlivky k barvám. Každý pohled potřebuje jiné.

    Hostovi nemá smysl vysvětlovat, že prázdný den je volný — to je
    samo sebou. Zajímá ho opak: co znamená ta šedá.
    """
    # „Na dotaz“ je nepotvrzená rezervace. Hostovi to říká, že termín
    # ještě není definitivní, a majiteli, že je koho urgovat.
    #
    # Minulé dny ve vysvětlivkách nejsou schválně: že termín už
    # proběhl, je z kalendáře zřejmé a hosta to nezajímá — vybírá si
    # z toho, co teprve bude.
    if view == VIEW_GUEST:
        items = [
            (GUEST_PENDING, "Na dotaz"),
            (GUEST_BUSY, "Obsazeno"),
            (ACCENT, "Váš termín"),
        ]
    else:
        items = [
            (COLORS[FREE], "Volno"),
            (COLORS[STATUS_PENDING], "Čeká na potvrzení"),
            (COLORS[STATUS_CONFIRMED], "Potvrzeno"),
        ]

    html = "".join(
        f'<div class="cal-legend-item">'
        f'<div class="cal-swatch" style="background:{color}"></div>'
        f"<span>{label}</span></div>"
        for color, label in items
    )

    html += (
        '<div class="cal-legend-item" style="opacity:.7">'
        "<span>◤ dopoledne do 11:00 &nbsp;·&nbsp; ◢ odpoledne od 15:00</span>"
        "</div>"
    )

    return LEGEND_CSS + f'<div class="cal-legend">{html}</div>'
