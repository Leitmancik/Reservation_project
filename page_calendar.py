"""Stránka Kalendář — klikací přehled obsazenosti a formulář rezervace.

Termín se vybírá kliknutím do kalendáře: první klik určí den příjezdu,
druhý den odjezdu. Další klik začne výběr znovu.
"""

from datetime import date, timedelta

import streamlit as st

import pricing
import storage
from calendar_view import (
    MONTH_NAMES,
    half_states,
    month_range,
    render_calendar,
    render_legend,
)
from ui import format_price, nights_label, set_flash, show_flash

# Jak daleko dopředu jde listovat.
MAX_MONTH_OFFSET = 23

# Streamlit renderuje na serveru a o šířce displeje neví nic —
# st.context nabízí hlavičky, ne rozměry okna. Na počet měsíců vedle
# sebe tak zbývá odhad z User-Agenta.
#
# Je to odhad, ne jistota: iPad se v Safari hlásí jako Macintosh a
# dostane dva měsíce, zúžení okna na desktopu se projeví až po
# načtení stránky znovu. Pro telefony, kde na tom záleží nejvíc,
# to ale vychází spolehlivě.
MOBILE_UA_MARKERS = ("iphone", "ipod", "android", "mobile", "windows phone")


def _is_mobile():
    """Odhadne z hlavičky prohlížeče, jestli jde o telefon."""
    try:
        agent = st.context.headers.get("User-Agent", "")
    except Exception:
        # Mimo běžící server hlavičky nejsou — chovej se jako desktop.
        return False

    agent = agent.lower()

    return any(marker in agent for marker in MOBILE_UA_MARKERS)


def _months_visible():
    """Na telefon jeden měsíc, jinak dva vedle sebe."""
    return 1 if _is_mobile() else 2

# Nabízené délky pobytu. Většina hostů jezdí zhruba na týden,
# tak ať to jde vybrat jedním kliknutím.
QUICK_NIGHTS = [2, 3, 7, 14]

# Čtyři délky pobytu by se na úzkém displeji složily pod sebe a
# zabraly by přes 200 px hned pod kalendářem, kde je místa nejmíň.
# Přepsáním minimální šířky na polovinu z nich bude mřížka 2 × 2.
QUICK_CSS = """
<style>
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"]:has([class*="st-key-quick_"])
        > [data-testid="stColumn"] {
        min-width: calc(50% - .5rem) !important;
        flex: 1 1 calc(50% - .5rem) !important;
    }
    [class*="st-key-quick_"] button {
        font-size: .82rem !important;
        padding-left: .25rem !important;
        padding-right: .25rem !important;
    }
}
</style>
"""


def _clear_selection():
    st.session_state.sel_from = None
    st.session_state.sel_to = None


def _handle_click(day, reservations):
    """Zpracuje kliknutí na den v kalendáři."""
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    morning, afternoon = half_states(day, reservations)

    # Den, na který se kleplo, si pamatujeme kvůli detailu pod
    # kalendářem. Na dotyku se k obsazenosti jinak nedá dostat —
    # nápověda tlačítka se ukáže jen pod myší.
    st.session_state.detail_day = day

    # Plně obsazený den se rezervovat nedá, takže výběr necháme být
    # a zůstane jen u detailu.
    if morning is not None and afternoon is not None:
        return

    # Kompletní výběr nebo klik před začátek = začínáme znovu.
    if sel_from is None or sel_to is not None or day <= sel_from:
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    conflict = storage.find_conflict(sel_from, day, reservations)

    if conflict is not None:
        set_flash(
            "error",
            f"V tomhle rozsahu je už rezervace "
            f"{conflict['first_name']} {conflict['last_name']} "
            f"({conflict['date_from'].strftime('%d.%m.%Y')} – "
            f"{conflict['date_to'].strftime('%d.%m.%Y')}). "
            "Vyber kratší pobyt nebo jiný termín.",
        )
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    st.session_state.sel_to = day


def _month_label(months):
    """Popisek typu „Září – Říjen 2026“ nad kalendářem."""
    (y1, m1), (y2, m2) = months[0], months[-1]

    # Na telefonu je vidět jediný měsíc — „Říjen – Říjen 2026“ by
    # vypadalo jako chyba.
    if (y1, m1) == (y2, m2):
        return f"{MONTH_NAMES[m1 - 1]} {y1}"

    if y1 == y2:
        return f"{MONTH_NAMES[m1 - 1]} – {MONTH_NAMES[m2 - 1]} {y1}"

    return f"{MONTH_NAMES[m1 - 1]} {y1} – {MONTH_NAMES[m2 - 1]} {y2}"


def _month_navigation(months):
    """Šipky pro listování měsíci. Dozadu se nedá před aktuální měsíc."""
    offset = st.session_state.month_offset

    # Na telefonu je popisek kratší („Říjen 2026“ místo
    # „Září – Říjen 2026“), tak se šipkám uvolní místo — v poměru
    # 1:6:1:1 by na 375px displeji měly sotva 40 px na dotyk.
    is_mobile = _is_mobile()

    if is_mobile:
        # Na telefonu zachováme čtyři jasně oddělené dotykové plochy.
        col_prev, col_label, col_next, col_refresh = st.columns(
            [1, 3, 1, 1], wrap=False
        )
        col_today = None
    else:
        # Na počítači je navíc rychlá cesta zpět na aktuální měsíc.
        col_prev, col_label, col_today, col_next, col_refresh = st.columns(
            [1, 4.5, 1.5, 1, 1], wrap=False
        )

    with col_prev:
        if st.button(
            "◀",
            key="nav_prev",
            width="stretch",
            disabled=offset == 0,
            help="Předchozí měsíc",
        ):
            st.session_state.month_offset = max(0, offset - 1)
            st.rerun()

    with col_label:
        st.markdown(
            f"<div style='text-align:center;font-size:1.05rem;"
            f"font-weight:600;padding-top:.35rem'>{_month_label(months)}</div>",
            unsafe_allow_html=True,
        )

    if col_today is not None:
        with col_today:
            if st.button(
                "Dnes",
                key="nav_today",
                width="stretch",
                disabled=offset == 0,
                help="Přejít na aktuální měsíc",
            ):
                st.session_state.month_offset = 0
                st.rerun()

    with col_next:
        if st.button(
            "▶",
            key="nav_next",
            width="stretch",
            disabled=offset >= MAX_MONTH_OFFSET,
            help="Další měsíc",
        ):
            st.session_state.month_offset = min(MAX_MONTH_OFFSET, offset + 1)
            st.rerun()

    with col_refresh:
        if st.button(
            "↻",
            key="nav_refresh",
            width="stretch",
            help="Načíst rezervace z tabulky znovu",
        ):
            storage.refresh()
            st.rerun()


def _day_detail(reservations):
    """Vypíše, kdo zabírá den, na který uživatel klepl.

    Na desktopu totéž říká nápověda pod myší, jenže ta se na dotykovém
    displeji nezobrazí. Bez tohohle panelu by na telefonu zůstala jen
    barva čtverečku a nedalo by se zjistit, kdo je kde ubytovaný.
    """
    day = st.session_state.get("detail_day")

    if day is None:
        return

    morning, afternoon = half_states(day, reservations)

    # U volného dne by panel nic nepřidal — vybraný termín ukazuje
    # pruh nad kalendářem. Tím se detail sám uklidí, jakmile si
    # uživatel vybere volný den.
    if morning is None and afternoon is None:
        return

    labels = {
        storage.STATUS_PENDING: "čeká na potvrzení",
        storage.STATUS_CONFIRMED: "potvrzeno",
    }

    def half_line(res, when):
        if res is None:
            return f"**{when}** — volno"

        return (
            f"**{when}** — {res['first_name']} {res['last_name']} "
            f"({labels[res['status']]})"
        )

    with st.container(border=True):
        st.markdown(f"**{day.strftime('%d.%m.%Y')}**")
        st.markdown(half_line(morning, "do 11:00"))
        st.markdown(half_line(afternoon, "od 15:00"))

        if morning is not None and afternoon is not None:
            st.caption(
                "Celý den je obsazený, jako termín ho vybrat nejde."
            )


def _quick_lengths(reservations, prices):
    """Tlačítka pro rychlý výběr délky pobytu od zvoleného příjezdu."""
    sel_from = st.session_state.sel_from

    st.caption("Nebo rovnou vyber délku pobytu:")

    st.html(QUICK_CSS)

    cols = st.columns(len(QUICK_NIGHTS))

    for col, nights in zip(cols, QUICK_NIGHTS):
        date_to = sel_from + timedelta(days=nights)
        blocked = storage.find_conflict(sel_from, date_to, reservations)

        total, _ = pricing.stay_total(sel_from, date_to, prices)

        # Cena patří na tlačítko — ať je vidět rozdíl mezi délkami
        # bez klikání.
        label = nights_label(nights)

        if total is not None and blocked is None:
            label = f"{label} · {format_price(total)}"

        with col:
            if st.button(
                label,
                key=f"quick_{nights}",
                width="stretch",
                disabled=blocked is not None,
                help=(
                    "V tomhle termínu už je rezervace"
                    if blocked is not None
                    else f"Odjezd {date_to.strftime('%d.%m.%Y')}"
                ),
            ):
                st.session_state.sel_to = date_to
                st.rerun()


def _selection_bar(prices):
    """Pruh nad kalendářem s aktuálně vybraným termínem."""
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    col_text, col_clear = st.columns([4, 1])

    with col_text:
        if sel_from is None:
            st.info(
                "**1. Vyber příjezd** · potom klikni na den odjezdu. "
                "Příjezd od 15:00, odjezd do 11:00.",
                icon="👉",
            )
        elif sel_to is None:
            st.warning(
                f"**Příjezd: {sel_from.strftime('%d.%m.%Y')} od 15:00** "
                "· **2. Vyber odjezd**",
                icon="📅",
            )
        else:
            nights = (sel_to - sel_from).days
            total, _ = pricing.stay_total(sel_from, sel_to, prices)

            text = (
                f"**{sel_from.strftime('%d.%m.%Y')}** od 15:00 → "
                f"**{sel_to.strftime('%d.%m.%Y')}** do 11:00 "
                f"· {nights_label(nights)}"
            )

            if total is not None:
                text += f" · **{format_price(total)}**"

            st.success(text, icon="✅")

    with col_clear:
        if sel_from is not None:
            if st.button("Zrušit výběr", width="stretch"):
                _clear_selection()
                st.rerun()


def _price_summary(sel_from, sel_to, prices):
    """Cena pobytu i s rozpisem, ať je vidět, jak se k ní došlo."""
    total, breakdown = pricing.stay_total(sel_from, sel_to, prices)

    if not prices:
        st.caption(
            "Ceník zatím není nastavený — doplň ho na stránce Cenotvorba."
        )
        return

    if total is None:
        st.warning(
            "Některé noci nemají cenu. Nastav základní cenu na stránce "
            "Cenotvorba.",
            icon="⚠️",
        )
        return

    nights = len(breakdown)

    col_total, col_detail = st.columns([1, 2])

    with col_total:
        st.metric(f"Cena za {nights_label(nights)}", format_price(total))

    with col_detail:
        # Rozpis dává smysl jen tehdy, když nejsou všechny noci stejné.
        unique = {item["price"] for item in breakdown}

        if len(unique) == 1:
            label = pricing.period_for_night(breakdown[0]["day"], prices)
            st.caption(
                f"{format_price(breakdown[0]['price'])} za noc"
                + (f" — {label['label']}" if label and label.get("label") else "")
            )
        else:
            st.caption("Cena se v průběhu pobytu mění:")

            lines = []

            for item in breakdown:
                rule = pricing.period_for_night(item["day"], prices)
                lines.append(
                    f"{item['day'].strftime('%d.%m.')} — "
                    f"{format_price(item['price'])}"
                    + (f" ({rule['label']})" if rule and rule.get("label") else "")
                )

            st.markdown(
                "<div style='font-size:.85rem;opacity:.85'>"
                + "<br>".join(lines)
                + "</div>",
                unsafe_allow_html=True,
            )


def _reservation_form(reservations, prices):
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    st.subheader("Dokončení rezervace")

    if sel_from is None or sel_to is None:
        st.caption(
            "Nejdřív vyber termín kliknutím do kalendáře — "
            "pak se tu objeví formulář."
        )
        return

    nights = (sel_to - sel_from).days

    st.caption(
        f"Termín: {sel_from.strftime('%d.%m.%Y')} od 15:00 → "
        f"{sel_to.strftime('%d.%m.%Y')} do 11:00 ({nights_label(nights)})"
    )

    _price_summary(sel_from, sel_to, prices)

    with st.form("new_reservation", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            first_name = st.text_input("Jméno")

        with col2:
            last_name = st.text_input("Příjmení")

        with col3:
            email = st.text_input("E-mail")

        submitted = st.form_submit_button(
            "Odeslat rezervaci", type="primary"
        )

    if not submitted:
        return

    errors = []

    if not first_name.strip():
        errors.append("Vyplň jméno.")

    if not last_name.strip():
        errors.append("Vyplň příjmení.")

    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Vyplň platný e-mail.")

    if errors:
        for message in errors:
            st.error(message)
        return

    with st.spinner("Ukládám rezervaci…"):
        try:
            # Mezi výběrem a odesláním mohl někdo termín zabrat, proto
            # se tady ptáme přímo tabulky, ne uložených dat.
            conflict = storage.find_conflict(
                sel_from, sel_to, storage.load_reservations(force=True)
            )

            if conflict is not None:
                st.error(
                    f"Termín mezitím obsadila rezervace "
                    f"{conflict['first_name']} {conflict['last_name']}. "
                    "Vyber prosím jiný."
                )
                return

            # Cenu ukládáme takovou, jaká platí teď — aby pozdější
            # změna ceníku nepřepsala, na čem jsme se s hostem domluvili.
            total, _ = pricing.stay_total(sel_from, sel_to, prices)

            storage.add_reservation(
                first_name, last_name, email, sel_from, sel_to, total
            )
        except storage.StorageError as error:
            st.error(f"Rezervaci se nepodařilo uložit. {error}")
            return

    message = (
        f"Rezervace uložena: {first_name.strip()} {last_name.strip()}, "
        f"{sel_from.strftime('%d.%m.%Y')} – {sel_to.strftime('%d.%m.%Y')} "
        f"({nights_label(nights)})"
    )

    if total is not None:
        message += f" za {format_price(total)}"

    set_flash(
        "success",
        message + ". Čeká na potvrzení — potvrdit ji můžeš na stránce "
        "Rezervace.",
    )

    _clear_selection()
    st.rerun()


def render():
    st.title("Rezervace chalupy")

    st.session_state.setdefault("sel_from", None)
    st.session_state.setdefault("sel_to", None)
    st.session_state.setdefault("month_offset", 0)

    show_flash()

    try:
        reservations = storage.load_reservations()
    except storage.StorageError as error:
        st.error(f"Nepodařilo se načíst rezervace. {error}")
        st.caption(
            "Kalendář teď nejde zobrazit, protože není jisté, "
            "které termíny jsou volné. Zkus stránku načíst znovu."
        )
        return

    # Ceník se drží v paměti stránky stejně jako rezervace, takže
    # klikání v kalendáři kvůli němu nečeká na tabulku.
    try:
        prices = storage.load_prices()
    except storage.StorageError:
        # Bez ceníku se dá rezervovat dál, jen se neukáže cena.
        prices = []

    today = date.today()

    _selection_bar(prices)

    visible = _months_visible()

    start = date(today.year, today.month, 1)
    months = month_range(
        _shift_start(start, st.session_state.month_offset),
        visible,
    )

    _month_navigation(months)

    clicked = render_calendar(
        months,
        reservations,
        st.session_state.sel_from,
        st.session_state.sel_to,
        today,
        columns=visible,
    )

    if clicked is not None:
        _handle_click(clicked, reservations)
        st.rerun()

    _day_detail(reservations)

    # Rychlé délky pobytu dávají smysl jen ve chvíli, kdy je vybraný
    # příjezd a chybí odjezd.
    if (
        st.session_state.sel_from is not None
        and st.session_state.sel_to is None
    ):
        _quick_lengths(reservations, prices)

    st.html(render_legend())

    st.divider()

    _reservation_form(reservations, prices)


def _shift_start(start, offset):
    total = start.year * 12 + (start.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)
