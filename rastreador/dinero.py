"""Conversión exacta entre pesos y centavos.

Los importes viajan como int (centavos). Decimal solo aparece en la frontera,
al leer texto (JSON/YAML), porque float no representa 0.10 exactamente.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

UN_CENTAVO = Decimal("0.01")


def a_centavos(pesos: int | str | Decimal | float) -> int:
    """Convierte un importe en pesos a centavos enteros (redondeo comercial).

    Un float solo se acepta porque YAML escribe `999.5` como float; se convierte
    por su representación decimal más corta (`str`), que es lo que el humano tecleó.
    """
    if isinstance(pesos, bool):  # bool es subclase de int en Python: True == 1
        raise TypeError("un booleano no es un importe")
    if isinstance(pesos, float):
        pesos = str(pesos)
    if isinstance(pesos, str):
        try:
            pesos = Decimal(pesos.strip())
        except InvalidOperation:
            raise ValueError(f"importe no numérico: {pesos!r}") from None
    if isinstance(pesos, int):
        pesos = Decimal(pesos)
    if not isinstance(pesos, Decimal):
        raise TypeError(f"tipo de importe no soportado: {type(pesos).__name__}")
    if not pesos.is_finite():
        raise ValueError(f"importe no finito: {pesos}")
    if pesos < 0:
        raise ValueError(f"importe negativo: {pesos}")
    return int(pesos.quantize(UN_CENTAVO, rounding=ROUND_HALF_UP) * 100)


def formatear_pesos(centavos: int) -> str:
    """1287908 -> '$12,879.08' (formato de México)."""
    signo = "-" if centavos < 0 else ""
    pesos, cent = divmod(abs(centavos), 100)
    return f"{signo}${pesos:,}.{cent:02d}"
