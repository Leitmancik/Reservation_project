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

COLORS = {
    FREE: "#4ade80",
    STATUS_PENDING: "#fb923c",
    STATUS_CONFIRMED: "#ef4444",
    PAST: "#94a3b8",
    SELECTED: "#2563eb",
}

# Stav výběru zakódovaný v klíči tlačítka.
PICK_NONE = "sel0"      # mimo výběr
PICK_START = "sel1"     # den příjezdu — zabírá jen odpoledne
PICK_END = "sel2"       # den odjezdu — zabírá jen dopoledne
PICK_INSIDE = "sel3"    # den uvnitř pobytu — zabírá celý

STATES = [FREE, STATUS_PENDING, STATUS_CONFIRMED, SELECTED]


def _day_css(today):
    """Vygeneruje CSS pro všechny kombinace barev půlených dnů."""
    rules = [
        """
        [class*="st-key-day-"] button {
            width: 100%;
            max-width: 52px;
            margin: 0 auto;
            aspect-ratio: 1 / 1;
            min-height: 0 !important;
            padding: 0 !important;
            border-radius: 8px;
            border: 1px solid rgba(128, 128, 128, .3) !important;
            font-size: .88rem !important;
            font-weight: 600 !important;
            color: #111 !important;
            text-shadow:
                0 0 3px rgba(255, 255, 255, .95),
                0 0 3px rgba(255, 255, 255, .95);
            transition: transform .08s ease, box-shadow .08s ease;
        }
        [class*="st-key-day-"] button:hover:not(:disabled) {
            transform: scale(1.12);
            border-color: #1d4ed8 !important;
            box-shadow: 0 2px 10px rgba(0, 0, 0, .28);
            z-index: 3;
        }
        [class*="st-key-day-"] button:disabled {
            opacity: 1 !important;
            cursor: not-allowed;
        }
        [class*="st-key-day-"] {
            margin-bottom: -.55rem;
        }
        [class*="st-key-empty-"] {
            aspect-ratio: 1 / 1;
        }
        """
    ]

    # Devět kombinací dopoledne × odpoledne.
    for morning in STATES:
        for afternoon in STATES:
            rules.append(
                f'[class*="-{morning}-{afternoon}-"] button {{'
                f"background: linear-gradient(135deg,"
                f" {COLORS[morning]} 0 50%,"
                f" {COLORS[afternoon]} 50% 100%) !important;"
                f"}}"
            )

    # Minulé dny jsou tlumené, ať je na první pohled vidět,
    # že se na ně nedá kliknout.
    rules.append(
        f'[class*="-{PAST}-{PAST}-"] button {{'
        f"background: {COLORS[PAST]} !important;"
        "opacity: .4 !important;"
        "}"
    )

    # Dnešek má čárkovaný rámeček, aby se nepletl s plným
    # rámečkem vybraného termínu.
    rules.append(
        f'[class*="st-key-day-{today.isoformat()}-"] button {{'
        "border: 2px dashed #1e293b !important;"
        "}"
    )

    # Číslo dne, kterého se dotýká výběr, píšeme bíle — na syté
    # modré by tmavé číslo zaniklo.
    rules.append(
        f'[class*="-{SELECTED}-"] button,'
        f'[class*="-{SELECTED}-"] button:disabled {{'
        "color: #fff !important;"
        "text-shadow: 0 1px 3px rgba(0, 0, 0, .55) !important;"
        "}"
    )

    # Krajní dny pobytu dostanou výraznější obrys, ať je poznat,
    # kde pobyt začíná a končí.
    for edge in (PICK_START, PICK_END):
        rules.append(
            f'[class*="-{edge}"] button {{'
            "border: 2px solid #1e40af !important;"
            "}"
        )

    return "<style>" + "".join(rules) + "</style>"


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
    font-size: .7rem; font-weight: 600; opacity: .6;
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
        return PICK_START

    if day == sel_to:
        return PICK_END

    if sel_to is not None and sel_from < day < sel_to:
        return PICK_INSIDE

    return PICK_NONE


def _tooltip(day, morning, afternoon, disabled):
    labels = {
        STATUS_PENDING: "čeká na potvrzení",
        STATUS_CONFIRMED: "potvrzeno",
    }

    parts = [day.strftime("%d.%m.%Y")]

    if morning is not None:
        parts.append(
            f"do 11:00 obsazeno — {morning['first_name']} "
            f"{morning['last_name']} ({labels[morning['status']]})"
        )
    else:
        parts.append("do 11:00 volno")

    if afternoon is not None:
        parts.append(
            f"od 15:00 obsazeno — {afternoon['first_name']} "
            f"{afternoon['last_name']} ({labels[afternoon['status']]})"
        )
    else:
        parts.append("od 15:00 volno")

    if disabled:
        parts.append("nelze vybrat")

    return "\n".join(parts)


def month_range(start, count):
    """Vrátí seznam (rok, měsíc) — `count` měsíců počínaje měsícem `start`."""
    base = start.year * 12 + (start.month - 1)
    return [((base + i) // 12, (base + i) % 12 + 1) for i in range(count)]


def render_month(year, month, reservations, sel_from, sel_to, today):
    """Vykreslí jeden měsíc. Vrátí datum, na které uživatel klikl, jinak None."""
    st.html(f'<div class="cal-month-title">{MONTH_NAMES[month - 1]} {year}</div>')
    st.html(
        '<div class="cal-weekdays">'
        + "".join(f"<div>{name}</div>" for name in WEEKDAY_NAMES)
        + "</div>"
    )

    first_weekday, days_in_month = calendar.monthrange(year, month)

    clicked = None
    day_number = 1

    # Kalendář kreslíme po týdnech, aby dny seděly pod správnými
    # názvy dnů i v měsíci, který nezačíná v pondělí.
    while day_number <= days_in_month:
        cols = st.columns(7, gap="small")

        for weekday in range(7):
            is_lead_gap = day_number == 1 and weekday < first_weekday

            if is_lead_gap or day_number > days_in_month:
                with cols[weekday]:
                    st.html(
                        f'<div class="cal-empty" '
                        f'style="aspect-ratio:1/1"></div>'
                    )
                continue

            day = date(year, month, day_number)
            morning, afternoon = half_states(day, reservations)

            # Plně obsazený den nejde použít jako příjezd ani jako odjezd.
            fully_booked = morning is not None and afternoon is not None
            disabled = fully_booked or day < today

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
                    help=_tooltip(day, morning, afternoon, disabled),
                    disabled=disabled,
                    width="stretch",
                ):
                    clicked = day

            day_number += 1

    return clicked


def render_calendar(months, reservations, sel_from, sel_to, today, columns=2):
    """Vykreslí mřížku měsíců. Vrátí datum, na které uživatel klikl."""
    st.html(_day_css(today))

    clicked = None

    for row_start in range(0, len(months), columns):
        row = months[row_start:row_start + columns]
        cols = st.columns(columns, gap="medium")

        for index, (year, month) in enumerate(row):
            with cols[index]:
                result = render_month(
                    year, month, reservations, sel_from, sel_to, today
                )

                if result is not None:
                    clicked = result

    return clicked


def render_legend():
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
