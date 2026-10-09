from app.services import locations as loc


def test_region_25_is_primorsky_centroid():
    r = loc.resolve({"region": 25})
    assert r.precision == "region" and r.region_name == "Primorsky Krai" and r.key == "region:25"
    assert 40 < r.lat < 50 and 130 < r.lon < 140


def test_region_as_string_and_zero_padding():
    assert loc.resolve({"region": "7"}).region_code == "07"
    assert loc.normalize_region_code("025") == "25"


def test_unknown_region_has_name_but_no_point():
    r = loc.resolve({"region": 90})
    assert not r.has_point and r.region_name == "Region 90" and r.precision is None


def test_missing_region():
    r = loc.resolve({})
    assert r.region_code is None and not r.has_point


def test_exact_coordinates_win_when_present():
    r = loc.resolve({"region": 25, "delivery_places": [{"latitude": "43.1", "longitude": 131.9}]})
    assert r.precision == "exact" and (r.lat, r.lon) == (43.1, 131.9)


def test_invalid_coordinates_are_ignored():
    assert loc.resolve({"region": 25, "latitude": 999, "longitude": 10}).precision == "region"
    assert loc.resolve({"latitude": 0, "longitude": 0}).precision is None


def test_alias_code_shares_location_key():
    assert loc.resolve({"region": 82}).key == loc.resolve({"region": 91}).key
