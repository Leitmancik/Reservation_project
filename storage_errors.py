"""Společný typ chyby pro všechna úložiště.

Stránky chytají jen tuhle výjimku, takže je jedno, jestli rezervace
leží v Google Sheets nebo v souboru na disku — výpadek úložiště
skončí srozumitelnou hláškou, ne pádem celé stránky.
"""


class StorageError(RuntimeError):
    """Úložiště rezervací neodpovědělo, nebo odpovědělo chybou."""
