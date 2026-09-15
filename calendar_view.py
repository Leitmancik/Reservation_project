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
# Jedna sada barev nemůže obsloužit oba motivy. Poloprůhledná vrstva
# totiž světlé pozadí výrazně změní, ale tmavé skoro ne — růžová
# s alfou .26 dá na bílé jasnou růžovou a na tmavé jen sotva znatelný
# nádech. Na tmavém je proto potřeba světlejší základ a vyšší krytí.
#
# Přepíná se přes prefers-color-scheme, ne z Pythonu: Streamlit motiv
# do stránky nedává a ve výchozím nastavení ho přebírá od systému
# (projekt nemá .streamlit/config.toml, který by to přebil). CSS tak
# reaguje okamžitě a nepotřebuje rerun.
#
# Čeká na potvrzení má vlastní jantarovou barvu i v pohledu hosta.
# Původně vypadalo stejně jako Potvrzeno, protože pro hosta je den
# tak jako tak zabraný — jenže pro majitele je to obchodní informace:
# nepotvrzená rezervace znamená zákazníka, kterého je možné urgovat.
PALETTE_CSS = """
.stApp {
    --cal-free: rgba(100, 116, 139, .12);
    --cal-busy: rgba(244, 63, 94, .20);
    --cal-busy-text: #9f1239;
    --cal-pending: rgba(245, 158, 11, .24);
    --cal-pending-text: #92400e;
    --cal-accent: #4f46e5;
    --cal-accent-soft: rgba(79, 70, 229, .20);
    --cal-hover: rgba(79, 70, 229, .16);
}
@media (prefers-color-scheme: dark) {
    .stApp {
        --cal-free: rgba(148, 163, 184, .16);
        --cal-busy: rgba(251, 113, 133, .34);
        --cal-busy-text: #fecdd3;
        --cal-pending: rgba(251, 191, 36, .34);
        --cal-pending-text: #fde68a;
        --cal-accent: #818cf8;
        --cal-accent-soft: rgba(129, 140, 248, .34);
        --cal-hover: rgba(129, 140, 248, .26);
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


def _day_css(today, view=VIEW_GUEST):
    """Vygeneruje CSS pro všechny kombinace barev půlených dnů."""
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
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"]):not(
            :has([data-testid="stHorizontalBlock"])
        ),
        .cal-weekdays {
            max-width: 34rem;
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
        /* Šipky ◀ ▶ ↻ dostanou v poměru 1:6:1:1 na telefonu sotva
           40 px. Výchozí vodorovné odsazení tlačítka je pak širší než
           sloupec a znak se odřízne — proto ho tady rušíme. */
        .st-key-nav_prev button,
        .st-key-nav_next button,
        .st-key-nav_refresh button {
            padding-left: 0 !important;
            padding-right: 0 !important;
            min-width: 0 !important;
            overflow: visible !important;
        }
        .st-key-nav_prev button p,
        .st-key-nav_next button p,
        .st-key-nav_refresh button p {
            overflow: visible !important;
            text-overflow: clip !important;
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
        [data-testid="stHorizontalBlock"]:has([class*="st-key-day-"])
            > [data-testid="stColumn"] {
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
        rules += _admin_rules()
    else:
        rules += _guest_rules()

    rules += _shared_state_rules(today)

    return "<style>" + "".join(rules) + "</style>"


def _admin_rules():
    """Barevný přehled obsazenosti — pohled správce.

    Každý den má sytou výplň, takže je stav vidět na první pohled.
    Číslo je tmavé s bílým podsvitem, což na všech těch barvách
    funguje v obou motivech.
    """
    rules = [
        '[class*="st-key-day-"] button {'
        "color: #111 !important;"
        "text-shadow: 0 0 3px rgba(255,255,255,.95),"
        " 0 0 3px rgba(255,255,255,.95) !important;"
        "}"
    ]

    # Devět kombinací dopoledne × odpoledne.
    for morning in STATES:
        for afternoon in STATES:
            rules.append(
                f'[class*="-{morning}-{afternoon}-"] button {{'
                f"background: linear-gradient(135deg,"
                f" {COLORS[morning]} 0 50%,"
                f" {COLORS[afternoon]} 50% 100%) !important;"
                f"background-clip: content-box !important;"
                f"}}"
            )

    # Minulé dny jsou tlumené, ať je na první pohled vidět,
    # že se na ně nedá kliknout.
    rules.append(
        f'[class*="-{PAST}-{PAST}-"] button {{'
        f"background: {COLORS[PAST]} !important;"
        "background-clip: content-box !important;"
        "opacity: .4 !important;"
        "}"
    )

    return rules


def _guest_rules():
    """Střídmý vzhled pro hosta, ve stylu rezervačních webů.

    Volný den není nijak označený — je to prostě číslo v prostoru,
    bez rámečku a bez výplně. Rámeček kolem každého dne je přesně to,
    co z kalendáře dělá tabulku.

    Rozlišují se tři stavy, každý svou barvou z palety:

        volno            břidlicová, decentní podklad
        čeká na potvrzení jantarová, termín „na dotaz“
        potvrzeno        růžová, k tomu přeškrtnuté číslo

    Přeškrtnutí dostane jen den, který je celý potvrzený. Den, kde
    figuruje nepotvrzená rezervace, zůstane nepřeškrtnutý schválně —
    není to hotová věc a přeškrtnutí by tvrdilo víc, než je pravda.
    """
    fill = {
        FREE: GUEST_FREE,
        STATUS_PENDING: GUEST_PENDING,
        STATUS_CONFIRMED: GUEST_BUSY,
    }

    states = (FREE, STATUS_PENDING, STATUS_CONFIRMED)

    rules = [
        # Volný den: jemný podklad, ať má mřížka strukturu. Úplně
        # průhledné dny se ukázaly jako nečitelné — zbyla z nich
        # drobná čísla plovoucí v prázdnu.
        '[class*="st-key-day-"] button {'
        f"background: {GUEST_FREE} !important;"
        "background-clip: content-box !important;"
        "color: inherit !important;"
        "text-shadow: none !important;"
        "}"
    ]

    # Každá půlka dne dostane barvu svého stavu. U dne, kde jeden host
    # odjíždí a druhý přijíždí, tak vedle sebe stojí dvě barvy.
    for morning in states:
        for afternoon in states:
            if morning == afternoon == FREE:
                continue

            rules.append(
                f'[class*="-{morning}-{afternoon}-"] button {{'
                f"background: linear-gradient(135deg,"
                f" {fill[morning]} 0 50%,"
                f" {fill[afternoon]} 50% 100%) !important;"
                f"background-clip: content-box !important;"
                f"}}"
            )

    # Celý den potvrzený: přeškrtnuté číslo. Tohle je hlavní signál,
    # plocha je jen doplněk.
    rules.append(
        f'[class*="-{STATUS_CONFIRMED}-{STATUS_CONFIRMED}-"] button p {{'
        "text-decoration: line-through !important;"
        "color: var(--cal-busy-text) !important;"
        "opacity: .85 !important;"
        "}"
    )

    # Kdekoli figuruje nepotvrzená rezervace, drží číslo jantarovou
    # barvu a zůstává nepřeškrtnuté — termín visí ve vzduchu.
    for other in states:
        for pair in (
            (STATUS_PENDING, other),
            (other, STATUS_PENDING),
        ):
            rules.append(
                f'[class*="-{pair[0]}-{pair[1]}-"] button p {{'
                "text-decoration: none !important;"
                "color: var(--cal-pending-text) !important;"
                "opacity: .95 !important;"
                "}"
            )

    # Minulé dny se jen ztlumí.
    rules.append(
        f'[class*="-{PAST}-{PAST}-"] button {{'
        "opacity: .25 !important;"
        "}"
    )

    return rules


def _shared_state_rules(today):
    """Pravidla, která platí v obou pohledech.

    Vybraný termín se kreslí jako souvislý pruh přes celé buňky:
    background-clip se přepne na border-box, takže výplň přeteče
    zapuštění a napojí se na souseda. Krajní dny jsou plné a zakulacené
    zvenčí, dny mezi nimi světlejší — stejně jako to dělají rezervační
    weby. Pruh se láme na koncích týdne, což je u kalendáře očekávané.
    """
    accent = ACCENT
    accent_soft = ACCENT_SOFT

    band = (
        "background-clip: border-box !important;"
        "padding: 3px 0 !important;"
    )

    rules = [
        # Dny uvnitř pobytu: světlá výplň bez zaoblení, ať pruh drží.
        f'[class*="-{PICK_INSIDE}"] button {{'
        f"background: {accent_soft} !important;"
        f"{band}"
        "border-radius: 0 !important;"
        "}",
        # Den příjezdu: plný, zakulacený zleva, pruh pokračuje doprava.
        f'[class*="-{PICK_START}"] button {{'
        f"background: {accent} !important;"
        f"{band}"
        "border-radius: 10px 0 0 10px !important;"
        "}",
        # Den odjezdu: plný, zakulacený zprava, pruh končí.
        f'[class*="-{PICK_END}"] button {{'
        f"background: {accent} !important;"
        f"{band}"
        "border-radius: 0 10px 10px 0 !important;"
        "}",
        # Samotný příjezd bez odjezdu: žádný pruh, jen chip.
        f'[class*="-{PICK_ONLY}"] button {{'
        f"background: {accent} !important;"
        "background-clip: content-box !important;"
        "border-radius: 10px !important;"
        "}",
    ]

    # Číslo na sytém podkladu musí být bílé v obou motivech.
    for pick in (PICK_START, PICK_END, PICK_ONLY):
        rules.append(
            f'[class*="-{pick}"] button,'
            f'[class*="-{pick}"] button p {{'
            "color: #fff !important;"
            "text-decoration: none !important;"
            "opacity: 1 !important;"
            "}"
        )

    # Dnešek pozná tečka pod číslem. Rámeček by do mřížky bez rámečků
    # nepatřil a pletl by se s vybraným termínem.
    rules.append(
        f'[class*="st-key-day-{today.isoformat()}-"] button p {{'
        "font-weight: 800 !important;"
        "}"
    )
    rules.append(
        f'[class*="st-key-day-{today.isoformat()}-"] button::after {{'
        'content: "";'
        "position: absolute;"
        "left: 50%;"
        "bottom: 5px;"
        "width: 4px;"
        "height: 4px;"
        "margin-left: -2px;"
        "border-radius: 50%;"
        "background: currentColor;"
        "opacity: .75;"
        "}"
    )

    return rules


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
.cal-month-title {
    font-size: 1rem; font-weight: 600;
    margin: .5rem 0 .35rem 0; text-align: center;
}
.cal-weekdays {
    display: grid; grid-template-columns: repeat(7, 1fr);
    gap: 0; text-align: center;
    font-size: .8rem; font-weight: 600; opacity: .7;
    margin-bottom: .25rem;
}
</style>
"""


def half_states(day, reservations):
    """Vrátí dvojici (dopoledne, odpoledne) — rezervace, nebo None když volno."""
    morning = None
    afternoon = None

    for res in reservations:
        # Ráno dne příjezdu je ještě volno, host dorazí až v 15:00.
        if res["date_from"] < day <= res["date_to"]:
            morning = res

        # Odpoledne dne odjezdu je už volno, host odjel v 11:00.
        if res["date_from"] <= day < res["date_to"]:
            afternoon = res

    return morning, afternoon


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


def _tooltip(day, morning, afternoon, disabled, view=VIEW_GUEST):
    parts = [day.strftime("%d.%m.%Y")]

    parts.append(f"do 11:00 {half_text(morning, view)}")
    parts.append(f"od 15:00 {half_text(afternoon, view)}")

    if disabled:
        parts.append("nelze vybrat")

    return "\n".join(parts)


def month_range(start, count):
    """Vrátí seznam (rok, měsíc) — `count` měsíců počínaje měsícem `start`."""
    base = start.year * 12 + (start.month - 1)
    return [((base + i) // 12, (base + i) % 12 + 1) for i in range(count)]


def render_month(
    year, month, reservations, sel_from, sel_to, today, show_title=True,
    view=VIEW_GUEST,
):
    """Vykreslí jeden měsíc. Vrátí datum, na které uživatel klikl, jinak None.

    `show_title` vypne nadpis nad mřížkou. Když je vidět jediný měsíc,
    říká totéž popisek mezi šipkami a na telefonu je každý ušetřený
    řádek znát.
    """
    if show_title:
        st.html(
            f'<div class="cal-month-title">'
            f"{MONTH_NAMES[month - 1]} {year}</div>"
        )
    st.html(
        '<div class="cal-weekdays">'
        + "".join(f"<div>{name}</div>" for name in WEEKDAY_NAMES)
        + "</div>"
    )

    first_weekday, days_in_month = calendar.monthrange(year, month)

    clicked = None
    day_number = 1
    week_index = 0

    # Kalendář kreslíme po týdnech, aby dny seděly pod správnými
    # názvy dnů i v měsíci, který nezačíná v pondělí.
    while day_number <= days_in_month:
        # wrap=False: bez toho Streamlit pod ~640 px přeskládá
        # každý sloupec pod sebe a ze sedmi dnů týdne udělá sloupec.
        # gap=0: dny se musí dotýkat, jinak se pruh vybraného
        # termínu rozpadne na oddělené čtverečky.
        cols = st.columns(7, gap=0, wrap=False)

        for weekday in range(7):
            is_lead_gap = day_number == 1 and weekday < first_weekday

            if is_lead_gap or day_number > days_in_month:
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

            day = date(year, month, day_number)
            morning, afternoon = half_states(day, reservations)

            # Plně obsazený den nejde použít jako příjezd ani jako odjezd,
            # ale klepnout na něj musí jít — na dotyku se jinak není jak
            # dozvědět, kdo ho zabírá. Stránka na takový klik jen ukáže
            # detail a výběr nechá být. Zamčené jsou tak už jen minulé dny.
            fully_booked = morning is not None and afternoon is not None
            disabled = day < today

            # Minulý den bez rezervace vykreslíme šedě. Minulý den
            # s rezervací si barvy nechá, ať je vidět historie pobytů.
            if day < today and morning is None and afternoon is None:
                morning_name = afternoon_name = PAST
            else:
                morning_name = _state_name(morning)
                afternoon_name = _state_name(afternoon)

            # Vybíraný pobyt obarvíme modře, ale u krajních dnů jen tu
            # polovinu, kterou skutečně zabírá: v den příjezdu se
            # přijíždí až v 15:00, v den odjezdu se odjíždí v 11:00.
            pick = _pick_state(day, sel_from, sel_to)

            if pick == PICK_START:
                afternoon_name = SELECTED
            elif pick == PICK_END:
                morning_name = SELECTED
            elif pick == PICK_INSIDE:
                morning_name = afternoon_name = SELECTED

            key = (
                f"day-{day.isoformat()}"
                f"-{morning_name}-{afternoon_name}-{pick}"
            )

            with cols[weekday]:
                if st.button(
                    str(day_number),
                    key=key,
                    help=_tooltip(
                        day, morning, afternoon,
                        disabled or fully_booked, view,
                    ),
                    disabled=disabled,
                    width="stretch",
                ):
                    clicked = day

            day_number += 1

        week_index += 1

    return clicked


def render_calendar(
    months, reservations, sel_from, sel_to, today, columns=2,
    view=VIEW_GUEST,
):
    """Vykreslí mřížku měsíců. Vrátí datum, na které uživatel klikl."""
    st.html(_day_css(today, view))

    clicked = None

    for row_start in range(0, len(months), columns):
        row = months[row_start:row_start + columns]
        cols = st.columns(columns, gap="medium")

        for index, (year, month) in enumerate(row):
            with cols[index]:
                result = render_month(
                    year, month, reservations, sel_from, sel_to, today,
                    show_title=columns > 1,
                    view=view,
                )

                if result is not None:
                    clicked = result

    return clicked


def render_legend(view=VIEW_GUEST):
    """Vysvětlivky k barvám. Každý pohled potřebuje jiné.

    Hostovi nemá smysl vysvětlovat, že prázdný den je volný — to je
    samo sebou. Zajímá ho opak: co znamená ta šedá.
    """
    # „Na dotaz“ je nepotvrzená rezervace. Hostovi to říká, že termín
    # ještě není definitivní, a majiteli, že je koho urgovat.
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
