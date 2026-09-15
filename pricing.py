"""Výpočet ceny pobytu.

Ceník má jednu základní cenu a k ní libovolný počet období, která ji
pro své dny přebíjejí. Díky tomu není potřeba vyplňovat celý rok —
stačí zadat výjimky.

Když se dvě období překrývají, platí to kratší. Silvestr uvnitř zimní
sezóny tak funguje sám od sebe a sezónu kvůli němu není nutné dělit.

Cena se počítá za noc a nocí se rozumí den příjezdu: pobyt od 4. do
7. září jsou tři noci (4/5, 5/6, 6/7), takže se sečtou ceny za 4., 5.
a 6. září.
"""

from datetime import timedelta


def is_base(period):
    """Je tohle řádek se základní cenou? Ten nemá vyplněné datum."""
    return period.get("date_from") is None or period.get("date_to") is None


def base_price(periods):
    """Základní cena, nebo None, když žádná není zadaná."""
    for period in periods:
        if is_base(period):
            return period["price"]

    return None


def seasons(periods):
    """Období s vyplněnými daty, seřazená od nejkratšího."""
    dated = [p for p in periods if not is_base(p)]

    return sorted(dated, key=lambda p: (p["date_to"] - p["date_from"]).days)


def price_for_night(day, periods):
    """Cena za noc začínající daným dnem. None, když ceník nic neříká."""
    for period in seasons(periods):
        if period["date_from"] <= day <= period["date_to"]:
            return period["price"]

    return base_price(periods)


def period_for_night(day, periods):
    """Které pravidlo pro danou noc platí — kvůli vysvětlení v aplikaci."""
    for period in seasons(periods):
        if period["date_from"] <= day <= period["date_to"]:
            return period

    for period in periods:
        if is_base(period):
            return period

    return None


def nights(date_from, date_to):
    """Dny, za které se platí: od příjezdu po den před odjezdem."""
    day = date_from

    while day < date_to:
        yield day
        day += timedelta(days=1)


def stay_total(date_from, date_to, periods):
    """Cena celého pobytu a rozpis po nocích.

    Vrací dvojici (celkem, rozpis). Když ceník některou noc nepokrývá,
    je v rozpisu cena None a do součtu se nezapočítá — aplikace na to
    upozorní, ať se neúčtuje nesmysl.
    """
    breakdown = []
    total = 0
    missing = False

    for day in nights(date_from, date_to):
        price = price_for_night(day, periods)

        if price is None:
            missing = True
        else:
            total += price

        breakdown.append({"day": day, "price": price})

    return (None if missing else total), breakdown


def overlaps(period, others):
    """Období, která se s tímhle překrývají — jen pro upozornění."""
    if is_base(period):
        return []

    found = []

    for other in others:
        if is_base(other) or other.get("id") == period.get("id"):
            continue

        if (
            period["date_from"] <= other["date_to"]
            and other["date_from"] <= period["date_to"]
        ):
            found.append(other)

    return found
