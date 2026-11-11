from etsy_insights.margin import (NO_MATCH, STATUS_TEXT, Fees, compute, fee_cents, is_ready, money,
                                  paid_price_cents, parse_usd_cents)

FEES = Fees(percent=9.5, fixed_cents=45)


def test_spec_example():
    m = compute(3000, 1241, 475, FEES, 500)
    assert (m.status, m.fee_cents, m.margin_cents, m.margin_percent, m.price_needed_cents) == ("ok", 330, 954, 31.8, 2499)
    assert money(954) == "US$9.54" and money(-332) == "-US$3.32" and money(2499) == "US$24.99"


def test_parse_usd():
    assert parse_usd_cents("US$15.30") == 1530
    assert parse_usd_cents("$1,234.50") == 123450
    assert parse_usd_cents("US$18") == 1800
    for text in (None, "", "Rp 712,738", "€15,30", "CA$15.30", "15.30"):
        assert parse_usd_cents(text) is None


def test_paid_price_midpoint():
    assert paid_price_cents("US$15.30", "US$18.70") == 1700
    assert paid_price_cents("US$15.30", "US$18.71") == 1701  # 1700.5 dibulatkan ke atas
    assert paid_price_cents(None, "US$18.70") == 1870
    assert paid_price_cents("Rp 1", None) is None


def test_fee_rounding_half_up():
    assert fee_cents(1010, FEES) == 96 + 45  # 95.95
    assert fee_cents(1700, FEES) == 162 + 45  # 161.5
    assert fee_cents(1, Fees(50, 0)) == 1


def test_statuses_in_order():
    assert compute(None, None, None, FEES, 500).status == "no_price"
    assert compute(3000, None, 475, FEES, 500).status == "cost_unknown"
    assert compute(3000, 1241, None, FEES, 500).status == "no_shipping"
    assert compute(None, 1241, 475, FEES, 500).price_needed_cents == 2499
    assert NO_MATCH.status == "no_match" and NO_MATCH.margin_cents is None
    assert STATUS_TEXT == {"no_match": "No match", "no_price": "Search to see price",
                           "cost_unknown": "Cost unknown", "no_shipping": "No US shipping"}


def test_negative_margin_and_ready():
    loss = compute(1700, 1350, 475, FEES, 500)
    assert (loss.margin_cents, loss.margin_percent, loss.price_needed_cents) == (-332, -19.5, 2619)
    ok = compute(3000, 1241, 475, FEES, 500)
    assert is_ready("Gold", ok, 500) and is_ready("Potential", ok, 954) and not is_ready("Potential", ok, 955)
    assert not is_ready("Skip", ok, 500) and not is_ready("Gold", loss, 0)
    assert not is_ready("Gold", compute(None, 1241, 475, FEES, 500), 0)


def test_zero_or_numeric_price_never_crashes():
    assert parse_usd_cents(15.3) is None and paid_price_cents(15.3, None) is None
    assert compute(0, 1241, 475, FEES, 500).status == "no_price"
