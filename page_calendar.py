"""Stránka Kalendář — klikací přehled obsazenosti a formulář rezervace.

Termín se vybírá kliknutím do kalendáře: první klik určí den příjezdu,
druhý den odjezdu. Další klik začne výběr znovu.
"""

from datetime import date, timedelta

import streamlit as st
from streamlit.components.v1 import html as _html_component

import pricing
import storage
from calendar_view import (
    MONTH_NAMES,
    VIEW_ADMIN,
    VIEW_GUEST,
    half_reservations,
    half_states,
    half_text,
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


def _both_halves_confirmed(morning, afternoon):
    """Drží obě půlky dne potvrzená rezervace?"""
    return all(
        res is not None and res["status"] == storage.STATUS_CONFIRMED
        for res in (morning, afternoon)
    )


def _handle_click(day, reservations, view=VIEW_GUEST):
    """Zpracuje kliknutí na den v kalendáři."""
    sel_from = st.session_state.sel_from
    sel_to = st.session_state.sel_to

    morning, afternoon = half_states(day, reservations)

    # Den, na který se kleplo, si pamatujeme kvůli detailu pod
    # kalendářem. Na dotyku se k obsazenosti jinak nedá dostat —
    # nápověda tlačítka se ukáže jen pod myší.
    st.session_state.detail_day = day

    # Detail je pod kalendářem, takže na velkém displeji leží mimo
    # obrazovku. Příznak si vyzvedne _day_detail a sjede k němu.
    st.session_state["_scroll_to_detail"] = True

    # V přehledu se nerezervuje, takže klik jen otevře detail.
    if view == VIEW_ADMIN:
        return

    # Blokuje jen den, jehož obě půlky drží potvrzená rezervace.
    # Nepotvrzená je zatím poptávka, ne překážka — jinak by „na dotaz“
    # nedávalo smysl, protože by se nedalo zeptat.
    if _both_halves_confirmed(morning, afternoon):
        return

    # Kompletní výběr nebo klik před začátek = začínáme znovu.
    if sel_from is None or sel_to is not None or day <= sel_from:
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    conflict = storage.find_conflict(sel_from, day, reservations)

    if conflict is not None:
        # Jméno hosta patří jen do pohledu správce — v zákaznickém
        # kalendáři by to byl únik osobního údaje. Termín sám o sobě
        # osobní údaj není a host ho potřebuje vidět, aby věděl,
        # kudy si pobyt zkrátit.
        kdo = ""

        if view == VIEW_ADMIN:
            kdo = (
                f" {conflict['first_name']} {conflict['last_name']}"
            )

        set_flash(
            "error",
            f"V tomhle rozsahu je už rezervace{kdo} "
            f"({conflict['date_from'].strftime('%d.%m.%Y')} – "
            f"{conflict['date_to'].strftime('%d.%m.%Y')}). "
            "Vyber kratší pobyt nebo jiný termín.",
        )
        st.session_state.sel_from = day
        st.session_state.sel_to = None
        return

    st.session_state.sel_to = day


def _view_switch():
    """Přepínač mezi pohledem hosta a přehledem správce.

    Není to oprávnění, jen volba zobrazení — přepnout si může kdokoli.
    Aplikace nikoho nepřihlašuje, takže skrytí jmen za tenhle přepínač
    by byla iluze bezpečí, ne bezpečí.
    """
    labels = {
        VIEW_GUEST: "Rezervovat",
        VIEW_ADMIN: "Přehled obsazenosti",
    }

    col_view, col_refresh = st.columns([4, 1])

    with col_view:
        view = st.segmented_control(
            "Zobrazení",
            options=[VIEW_GUEST, VIEW_ADMIN],
            format_func=lambda value: labels[value],
            default=VIEW_GUEST,
            required=True,
            key="cal_view",
            label_visibility="collapsed",
        )

    # Načtení znovu zahodí rezervace uložené v paměti stránky. Host ho
    # nepotřebuje — před uložením rezervace se čerstvá data načtou tak
    # jako tak, takže mu zastaralá mezipaměť uškodit nemůže.
    if view == VIEW_ADMIN:
        with col_refresh:
            if st.button(
                "↻ Načíst znovu",
                key="nav_refresh",
                width="stretch",
            ):
                storage.refresh()
                st.rerun()

    return view


def _nav_arrows():
    """Vrátí dvojici funkcí, které vykreslí šipky pro listování.

    Kalendář je zavolá do krajních sloupců řádku s měsíci, takže šipky
    stojí přímo u mřížky. Posun měsíců zůstává tady, protože stránka
    drží stav a ví, kam až se smí listovat.
    """
    offset = st.session_state.month_offset

    def dozadu():
        if st.button(
            "◀",
            key="nav_prev",
            width="stretch",
            disabled=offset == 0,
            help="Předchozí měsíc",
        ):
            st.session_state.month_offset = max(0, offset - 1)
            st.rerun()

    def dopredu():
        if st.button(
            "▶",
            key="nav_next",
            width="stretch",
            disabled=offset >= MAX_MONTH_OFFSET,
            help="Další měsíc",
        ):
            st.session_state.month_offset = min(MAX_MONTH_OFFSET, offset + 1)
            st.rerun()

    return dozadu, dopredu


STATUS_LABELS = {
    storage.STATUS_PENDING: "Čeká na potvrzení",
    storage.STATUS_CONFIRMED: "Potvrzeno",
}


# Jméno v konfliktu je tlačítko, ale má vypadat jako nadpis. Výchozí
# tlačítko je drobné a nese kolem sebe odsazení, kvůli kterému mezi
# jménem a údaji pod ním zůstávala díra.
LINK_CSS = """
<style>
[class*="st-key-jdi_"] button {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    padding: 0 !important;
    min-height: 0 !important;
    height: auto !important;
}
[class*="st-key-jdi_"] button p {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
}
[class*="st-key-jdi_"] {
    margin-bottom: -.85rem !important;
}
</style>
"""


def _open_in_reservations(res):
    """Přepne na stránku Rezervace a otevře tam danou rezervaci."""
    st.session_state["focus_reservation"] = str(res["id"])

    stranky = st.session_state.get("_pages")

    if stranky:
        st.switch_page(stranky["rezervace"])


def _reservation_card(res, odkaz_key=None):
    """Vypíše jednu rezervaci se vším, co majitel potřebuje.

    Používá to detail dne i rozbalený konflikt, ať se údaje o téže
    rezervaci nezobrazují na dvou místech jinak.

    S `odkaz_key` je jméno tlačítko, které přepne na stránku Rezervace
    a tuhle rezervaci tam otevře. Řešení konfliktu obvykle končí tím,
    že se jedna z nich potvrdí nebo smaže, a to jde jen tam.
    """
    noci = (res["date_to"] - res["date_from"]).days

    jmeno = f"{res['first_name']} {res['last_name']}"

    # Stav patří do stejného bloku jako zbytek údajů. Jako samostatný
    # prvek by kolem sebe dostal rozestup, který Streamlit dává mezi
    # prvky, a mezi jménem a daty by zela mezera.
    radky = [
        STATUS_LABELS[res["status"]],
        f"{res['date_from'].strftime('%d.%m.%Y')} od 15:00 → "
        f"{res['date_to'].strftime('%d.%m.%Y')} do 11:00 "
        f"({nights_label(noci)})",
        f"{res['email']}",
    ]

    if res.get("price") is not None:
        radky.append(f"Cena pobytu: **{format_price(res['price'])}**")

    if odkaz_key is None:
        radky.insert(0, f"**{jmeno}**")
    else:
        if st.button(
            f"{jmeno}  ›",
            key=odkaz_key,
            type="tertiary",
            help="Otevřít na stránce Rezervace",
        ):
            _open_in_reservations(res)

    st.markdown("  \n".join(radky))


def _admin_detail(day, reservations):
    """Vypíše celé rezervace, které se daného dne týkají.

    Majitel od přehledu chce vědět, kdo tam je a jak ho zastihnout,
    ne jen že je obsazeno. Vypíšou se všechny — i ty, které se
    navzájem překrývají, protože právě ty je potřeba rozhodnout.
    Tatáž rezervace přes obě půlky dne se vypíše jen jednou.
    """
    morning, afternoon = half_reservations(day, reservations)

    videno = []

    for res in morning + afternoon:
        if not any(str(res["id"]) == str(v["id"]) for v in videno):
            videno.append(res)

    st.html(LINK_CSS)

    for res in videno:
        # Klíč musí začínat na "jdi_", aby platil styl odkazu, a být
        # jiný než v upozornění na konflikty — tatáž rezervace může
        # být na stránce dvakrát.
        _reservation_card(res, odkaz_key=f"jdi_detail_{res['id']}")

        if res is not videno[-1]:
            st.divider()


def _jump_to(day):
    """Přelistuje kalendář na měsíc daného dne a otevře jeho detail.

    Rolování je tu podstatné: když konflikt padne do měsíce, který je
    zrovna vidět, `month_offset` se nezmění a bez posunu na detail by
    to vypadalo, že tlačítko nedělá vůbec nic.
    """
    today = date.today()

    offset = (day.year * 12 + day.month - 1) - (
        today.year * 12 + today.month - 1
    )

    st.session_state.month_offset = max(0, min(MAX_MONTH_OFFSET, offset))
    st.session_state.detail_day = day
    st.session_state["_scroll_to_detail"] = True


def _clash_banner(reservations):
    """Upozorní majitele na termíny, o které se hlásí víc lidí.

    Od chvíle, kdy nepotvrzená rezervace termín neblokuje, může jich
    na stejný termín přijít víc. Je to záměr — jenže pak to někdo musí
    rozhodnout, a bez upozornění by se na to přišlo až ve chvíli, kdy
    potvrzení druhé rezervace skončí chybou.

    Každý konflikt jde rozbalit a jsou pod ním rovnou kontakty na oba
    zájemce. Řešení konfliktu totiž znamená někomu zavolat nebo napsat
    a bez toho by se majitel musel proklikávat jinam.
    """
    pary = []

    for index, prvni in enumerate(reservations):
        for druha in reservations[index + 1:]:
            if (
                prvni["date_from"] < druha["date_to"]
                and druha["date_from"] < prvni["date_to"]
            ):
                pary.append((prvni, druha))

    if not pary:
        return

    pocet = len(pary)
    slovo = "termín" if pocet == 1 else ("termíny" if pocet < 5 else "termínů")

    st.html(LINK_CSS)

    with st.container(border=True):
        st.markdown(
            f"⚠️ **{pocet} {slovo} se překrývá** — potvrdit lze jen jednu "
            "rezervaci z každé dvojice."
        )

        for prvni, druha in pary:
            # Den, kterým se překryv začíná. Na ten se kalendář
            # přelistuje, protože právě tam je konflikt vidět.
            od = max(prvni["date_from"], druha["date_from"])
            do = min(prvni["date_to"], druha["date_to"])

            popis = (
                f"{prvni['first_name']} {prvni['last_name']}"
                f" × {druha['first_name']} {druha['last_name']}"
                f"  ·  {od.strftime('%d.%m.')} – {do.strftime('%d.%m.%Y')}"
            )

            with st.expander(popis):
                _reservation_card(prvni, odkaz_key=f"jdi_{prvni['id']}_{druha['id']}_a")
                st.divider()
                _reservation_card(druha, odkaz_key=f"jdi_{prvni['id']}_{druha['id']}_b")

                if st.button(
                    "Ukázat v kalendáři",
                    # Klíč nesmí obsahovat "clash" ani "swap" — CSS
                    # hledá tahle slova ve třídách dnů v kalendáři
                    # a Streamlit z klíče dělá třídu st-key-<klíč>.
                    key=f"konflikt_{prvni['id']}_{druha['id']}",
                ):
                    _jump_to(od)
                    st.rerun()


def _scroll_to_detail():
    """Sjede na detail dne, pokud se o to někdo řekl kliknutím.

    Streamlit na rolování žádné API nemá, takže to obstará krátký
    skript ve vložené komponentě. Ta běží ve vlastním rámu, ale ten má
    povolené allow-scripts i allow-same-origin, takže se k rodičovské
    stránce dostane.

    Příznak se spotřebuje, aby se nerolovalo při každém překreslení —
    jinak by stránka ujížděla pokaždé, když se cokoli změní.
    """
    if not st.session_state.pop("_scroll_to_detail", False):
        return

    _html_component(
        """
        <script>
            const cil = window.parent.document.querySelector(
                ".st-key-detail_dne"
            );

            if (cil) {
                cil.scrollIntoView({behavior: "smooth", block: "center"});
            }
        </script>
        """,
        height=0,
    )


def _day_detail(reservations, view=VIEW_GUEST):
    """Vypíše, co se s daným dnem děje.

    Hostovi stačí, že je den zabraný. Majitel v přehledu potřebuje
    celou rezervaci — jméno, kontakt, termín i cenu.

    Na desktopu říká totéž nápověda pod myší, jenže ta se na dotykovém
    displeji nezobrazí. Bez tohohle panelu by na telefonu zůstala jen
    barva čtverečku.
    """
    day = st.session_state.get("detail_day")

    if day is None:
        return

    morning, afternoon = half_states(day, reservations)

    # U volného dne by panel nic nepřidal.
    if morning is None and afternoon is None:
        return

    # key dá kontejneru třídu st-key-detail_dne, na kterou se dá
    # zacílit z rolovacího skriptu. Spolehlivější než id ve vlastním
    # HTML — st.html obsah sanitizuje.
    with st.container(border=True, key="detail_dne"):
        st.markdown(f"**{day.strftime('%d.%m.%Y')}**")

        if view == VIEW_ADMIN:
            _admin_detail(day, reservations)
            return

        st.markdown(f"**do 11:00** — {half_text(morning, view)}")
        st.markdown(f"**od 15:00** — {half_text(afternoon, view)}")

        if _both_halves_confirmed(morning, afternoon):
            st.caption(
                "Celý den je potvrzený, jako termín ho vybrat nejde."
            )
        elif morning is not None and afternoon is not None:
            st.caption(
                "Rezervace na tenhle den zatím není potvrzená — "
                "termín si můžeš vyžádat a ozveme se ti."
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
                "Klikni v kalendáři na den **příjezdu**. "
                "Druhým kliknutím vybereš den **odjezdu**.",
                icon="👉",
            )
        elif sel_to is None:
            st.warning(
                f"Příjezd **{sel_from.strftime('%d.%m.%Y')}** od 15:00. "
                "Teď klikni na den odjezdu.",
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
                    "Termín mezitím někdo obsadil. Vyber prosím jiný."
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

    view = _view_switch()

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

    if view == VIEW_GUEST:
        _selection_bar(prices)
    else:
        _clash_banner(reservations)

    visible = _months_visible()

    start = date(today.year, today.month, 1)
    months = month_range(
        _shift_start(start, st.session_state.month_offset),
        visible,
    )

    dozadu, dopredu = _nav_arrows()

    clicked = render_calendar(
        months,
        reservations,
        st.session_state.sel_from,
        st.session_state.sel_to,
        today,
        columns=visible,
        view=view,
        nav_prev=dozadu,
        nav_next=dopredu,
    )

    if clicked is not None:
        _handle_click(clicked, reservations, view)
        st.rerun()

    _day_detail(reservations, view)

    _scroll_to_detail()

    # Přehled obsazenosti je jen ke koukání — rezervovat se v něm
    # nedá, od toho je pohled hosta. Rychlé délky pobytu i formulář
    # by tu jen zabíraly místo a mátly.
    if view == VIEW_GUEST:
        # Rychlé délky pobytu dávají smysl jen ve chvíli, kdy je
        # vybraný příjezd a chybí odjezd.
        if (
            st.session_state.sel_from is not None
            and st.session_state.sel_to is None
        ):
            _quick_lengths(reservations, prices)

    st.html(render_legend(view))

    if view == VIEW_GUEST:
        st.divider()

        _reservation_form(reservations, prices)


def _shift_start(start, offset):
    total = start.year * 12 + (start.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)
