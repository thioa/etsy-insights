"""Perkiraan margin per penjualan dalam sen USD (spec Tahap 4 §8). Semua angka bilangan bulat."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

STATUS_TEXT = {"no_match": "No match", "no_price": "Search to see price",
               "cost_unknown": "Cost unknown", "no_shipping": "No US shipping"}
_USD = re.compile(r"^(?:US)?\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?$")


@dataclass(frozen=True)
class Fees:
    percent: float
    fixed_cents: int


@dataclass(frozen=True)
class Margin:
    status: str  # "ok" | "no_match" | "no_price" | "cost_unknown" | "no_shipping"
    price_cents: int | None = None
    cost_cents: int | None = None
    shipping_cents: int | None = None
    fee_cents: int | None = None
    margin_cents: int | None = None
    margin_percent: float | None = None
    price_needed_cents: int | None = None


NO_MATCH = Margin(status="no_match")


def _half_up(value: Decimal, places: str = "1") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def parse_usd_cents(text: str | None) -> int | None:
    """"US$15.30" / "$1,234.50" → sen. Mata uang lain atau format lain → None."""
    match = _USD.match((text or "").strip())
    if not match:
        return None
    dollars = int(match.group(1).replace(",", ""))
    cents = int((match.group(2) or "0").ljust(2, "0"))
    return dollars * 100 + cents


def paid_price_cents(low: str | None, high: str | None) -> int | None:
    values = [v for v in (parse_usd_cents(low), parse_usd_cents(high)) if v is not None]
    if not values:
        return None
    return int(_half_up(Decimal(sum(values)) / len(values)))


def fee_cents(price_cents: int, fees: Fees) -> int:
    return int(_half_up(Decimal(price_cents) * Decimal(str(fees.percent)) / 100)) + fees.fixed_cents


def price_needed_cents(cost_cents: int, shipping_cents: int, fees: Fees, target_cents: int) -> int:
    """Harga jual terendah (sen) agar margin ≥ target."""
    needed = Decimal(cost_cents + shipping_cents + fees.fixed_cents + target_cents)
    return math.ceil(needed / (1 - Decimal(str(fees.percent)) / 100))


def compute(price_cents: int | None, cost_cents: int | None, shipping_cents: int | None,
            fees: Fees, target_cents: int) -> Margin:
    needed = (price_needed_cents(cost_cents, shipping_cents, fees, target_cents)
              if cost_cents is not None and shipping_cents is not None else None)
    base = dict(price_cents=price_cents, cost_cents=cost_cents, shipping_cents=shipping_cents,
                price_needed_cents=needed)
    if price_cents is None:
        return Margin(status="no_price", **base)
    if cost_cents is None:
        return Margin(status="cost_unknown", **base)
    if shipping_cents is None:
        return Margin(status="no_shipping", **base)
    fee = fee_cents(price_cents, fees)
    margin = price_cents - cost_cents - shipping_cents - fee
    percent = float(_half_up(Decimal(margin) * 100 / price_cents, "0.1")) if price_cents else None
    return Margin(status="ok", fee_cents=fee, margin_cents=margin, margin_percent=percent, **base)


def is_ready(label: str, margin: Margin, minimum_cents: int) -> bool:
    return (label in ("Gold", "Potential") and margin.status == "ok"
            and margin.margin_cents is not None and margin.margin_cents >= minimum_cents)


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}US${cents // 100}.{cents % 100:02d}"
