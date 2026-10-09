"""Winner-price extraction. EZK is verified on real data; EF/EZT fixtures follow the task spec."""

from app.services.winner import extract_winner_price, validate_price


def app(price_key, price, rating=None, path=None):
    node = {"commonInfo": {"appNumber": "1"}}
    cur = node
    keys = path or [price_key]
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = price
    if rating is not None:
        node["admittedInfo"] = {"appAdmittedInfo": {"admitted": "true", "appRating": rating}}
    return node


def proto(doc_type, apps, published="2026-02-06T01:51:11"):
    return {"doc_type": doc_type, "published_at": published,
            "source": {"protocolInfo": {"applicationsInfo": {"applicationInfo": apps}}}}


def test_ezk_real_example_lowest_rating_wins(ezk_protocols):
    r = extract_winner_price(ezk_protocols, 901989.0)
    assert r.price == 147150.00
    assert r.source == "epProtocolEZK2020Final"


def test_rating_decides_not_list_order_or_price():
    apps = [app("finalPrice", "500.00", "2"), app("finalPrice", "900.00", "1"), app("finalPrice", "100.00", "3")]
    assert extract_winner_price([proto("epProtocolEZK2020Final", apps)], 1000).price == 900.0


def test_single_application_dict_not_list():
    p = proto("epProtocolEZK2020Final", app("finalPrice", "10.5", "1"))
    assert extract_winner_price([p], 100).price == 10.5


def test_ef_final_uses_final_price_then_last_price_offer():
    a = proto("epProtocolEF2020Final", [app("finalPrice", "80.00", "1")])
    assert extract_winner_price([a], 100).price == 80.0
    b = proto("epProtocolEF2020Final", [app(None, "70.00", "1", path=["lastPriceOffer", "price"])])
    assert extract_winner_price([b], 100).price == 70.0


def test_ef_submit_offers_is_last_resort_and_flagged():
    sub = proto("epProtocolEF2020SubmitOffers", [app(None, "60.00", "1", path=["priceOffer", "price"])])
    r = extract_winner_price([sub], 100)
    assert r.price == 60.0 and "preliminary" in r.note
    fin = proto("epProtocolEF2020Final", [app("finalPrice", "55.00", "1")])
    assert extract_winner_price([sub, fin], 100).price == 55.0


def test_ezt_final_price():  # path unverified on real data
    p = proto("epProtocolEZT2020Final", [app("finalPrice", "42.00", "1")])
    assert extract_winner_price([p], 100).price == 42.0


def test_validation_rules():
    assert validate_price(10.0, 100.0) == (10.0, None)
    assert validate_price(100.0, 100.0)[0] == 100.0          # equal to max is fine
    assert validate_price(100.01, 100.0)[0] is None            # above max -> missing
    assert validate_price(0.0, 100.0)[0] is None
    assert validate_price(-5.0, 100.0)[0] is None
    assert validate_price(5.0, None)[0] is None


def test_price_above_max_is_treated_as_missing():
    p = proto("epProtocolEZK2020Final", [app("finalPrice", "2000.00", "1")])
    r = extract_winner_price([p], 1000)
    assert r.price is None and "exceeds" in r.note


def test_newest_valid_protocol_version_wins():
    old = proto("epProtocolEZK2020Final", [app("finalPrice", "90.00", "1")], "2026-02-01T00:00:00")
    new = proto("epProtocolEZK2020Final", [app("finalPrice", "80.00", "1")], "2026-02-05T00:00:00")
    assert extract_winner_price([old, new], 100).price == 80.0


def test_no_ratings_cases():
    one = proto("epProtocolEZK2020Final", [app("finalPrice", "7.00")])
    assert extract_winner_price([one], 100).price == 7.0
    many = proto("epProtocolEZK2020Final", [app("finalPrice", "9.00"), app("finalPrice", "7.00")])
    r = extract_winner_price([many], 100)
    assert r.price == 7.0 and "lowest price" in r.note


def test_decimal_comma_and_spaces():
    p = proto("epProtocolEZK2020Final", [app("finalPrice", "1 234,50", "1")])
    assert extract_winner_price([p], 2000).price == 1234.5


def test_empty_and_irrelevant_protocols():
    assert extract_winner_price([], 100).price is None
    assert extract_winner_price(None, 100).price is None
    r = extract_winner_price([{"doc_type": "epProtocolEvasion", "source": {}}], 100)
    assert r.price is None and r.note
