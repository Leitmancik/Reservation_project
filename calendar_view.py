"""Vykreslení kalendáře jako HTML.

Každý den je čtvereček rozdělený úhlopříčkou na dvě poloviny:

    levý horní trojúhelník  = dopoledne (do 11:00, kdy se odjíždí)
    pravý dolní trojúhelník = odpoledne (od 15:00, kdy se přijíždí)

Rezervace od soboty do středy tak obarví jen odpolední půlku soboty,
celé neděle až úterý, a jen dopolední půlku středy. Pokud někdo další
začne pobyt tou samou středou, obarví se její druhá (odpolední) půlka —
a ve čtverečku jsou vidět dvě různé barvy.
"""

import calendar
from datetime import date

from storage import STATUS_CONFIRMED, STATUS_PENDING

MONTH_NAMES = [
    "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
]

WEEKDAY_NAMES = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]

COLORS = {
    "free": "#4ade80",
    STATUS_PENDING: "#fb923c",
    STATUS_CONFIRMED: "#ef4444",
}

CSS = """
<style>
.cal-wrap {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    margin-bottom: 1.5rem;
}
.cal-title {
    font-size: 1.05rem;
    font-weight: 600;
    text-align: center;
    margin: 0 0 .6rem 0;
}
.cal-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
}
.cal-head {
    text-align: center;
    font-size: .72rem;
    font-weight: 600;
    opacity: .65;
    padding-bottom: 2px;
}
.cal-day {
    position: relative;
    aspect-ratio: 1 / 1;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid rgba(128, 128, 128, .35);
}
.cal-day.empty {
    border: none;
    background: none;
}
.cal-day.today {
    border: 2px solid #2563eb;
}
.cal-half {
    position: absolute;
    inset: 0;
}
.cal-half.morning {
    clip-path: polygon(0 0, 100% 0, 0 100%);
}
.cal-half.afternoon {
    clip-path: polygon(100% 0, 100% 100%, 0 100%);
}
.cal-num {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: .82rem;
    font-weight: 700;
    color: #111;
    text-shadow:
        0 0 3px rgba(255, 255, 255, .95),
        0 0 3px rgba(255, 255, 255, .95);
}
.cal-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
    font-size: .82rem;
    margin-bottom: 1rem;
}
.cal-legend-item {
    display: flex;
    align-items: center;
    gap: .4rem;
}
.cal-swatch {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid rgba(128, 128, 128, .35);
}
.cal-months {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.2rem;
}
</style>
"""


def half_states(day, reservations):
    """Zjistí stav obou polovin jednoho dne.

    Vrací dvojici (dopoledne, odpoledne), kde každá položka je buď None
    (volno), nebo ta rezervace, která danou půlku dne obsazuje.
    """
    morning = None
    afternoon = None

    for res in reservations:
        # Dopoledne je obsazené v každý den pobytu kromě dne příjezdu —
        # ráno dne příjezdu je chalupa ještě volná, host dorazí až v 15:00.
        if res["date_from"] < day <= res["date_to"]:
            morning = res

        # Odpoledne je obsazené v každý den pobytu kromě dne odjezdu —
        # ten den host v 11:00 odjíždí a odpoledne už je volno.
        if res["date_from"] <= day < res["date_to"]:
            afternoon = res

    return morning, afternoon


def _half_html(css_class, res):
    color = COLORS["free"] if res is None else COLORS[res["status"]]
    return f'<div class="cal-half {css_class}" style="background:{color}"></div>'


def _tooltip(day, morning, afternoon):
    labels = {
        STATUS_PENDING: "čeká na potvrzení",
        STATUS_CONFIRMED: "potvrzeno",
    }
    parts = [day.strftime("%d.%m.%Y")]

    if morning is not None:
        parts.append(
            f"do 11:00 — {morning['first_name']} {morning['last_name']}"
            f" ({labels[morning['status']]})"
        )

    if afternoon is not None:
        parts.append(
            f"od 15:00 — {afternoon['first_name']} {afternoon['last_name']}"
            f" ({labels[afternoon['status']]})"
        )

    if morning is None and afternoon is None:
        parts.append("volno")

    return " | ".join(parts)


def render_month(year, month, reservations, today=None):
    """Vrátí HTML jednoho měsíce."""
    if today is None:
        today = date.today()

    first_weekday, days_in_month = calendar.monthrange(year, month)

    cells = []

    for name in WEEKDAY_NAMES:
        cells.append(f'<div class="cal-head">{name}</div>')

    for _ in range(first_weekday):
        cells.append('<div class="cal-day empty"></div>')

    for day_number in range(1, days_in_month + 1):
        day = date(year, month, day_number)
        morning, afternoon = half_states(day, reservations)

        classes = "cal-day today" if day == today else "cal-day"

        cells.append(
            f'<div class="{classes}" title="{_tooltip(day, morning, afternoon)}">'
            f'{_half_html("morning", morning)}'
            f'{_half_html("afternoon", afternoon)}'
            f'<div class="cal-num">{day_number}</div>'
            f"</div>"
        )

    return (
        '<div class="cal-wrap">'
        f'<div class="cal-title">{MONTH_NAMES[month - 1]} {year}</div>'
        f'<div class="cal-grid">{"".join(cells)}</div>'
        "</div>"
    )


def render_months(months, reservations, today=None):
    """Vrátí HTML několika měsíců vedle sebe. `months` je seznam (rok, měsíc)."""
    blocks = [
        render_month(year, month, reservations, today)
        for year, month in months
    ]
    return CSS + f'<div class="cal-months">{"".join(blocks)}</div>'


def render_legend():
    items = [
        (COLORS["free"], "Volno"),
        (COLORS[STATUS_PENDING], "Rezervováno, čeká na potvrzení"),
        (COLORS[STATUS_CONFIRMED], "Potvrzeno"),
    ]

    html = "".join(
        f'<div class="cal-legend-item">'
        f'<div class="cal-swatch" style="background:{color}"></div>'
        f"<span>{label}</span></div>"
        for color, label in items
    )

    return CSS + f'<div class="cal-legend">{html}</div>'
