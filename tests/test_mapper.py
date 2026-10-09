from app.ml.pipeline import RAW_COLS
from app.services.mapper import build_raw, build_tender_record, extract_extras
from tests.conftest import make_purchase


def test_raw_mapping_matches_task_table(ezk_purchase):
    raw = build_raw(ezk_purchase)
    assert list(raw) == RAW_COLS
    assert raw == {
        "purchase_number": "0320300101526000015",
        "purchase_type": "epNotificationEZK2020",
        "responsible": "2536010685",
        "published_at_ts": "2026-01-30T00:03:03.391000",
        "collecting_finished_at_ts": "2026-02-06T00:00:00",
        "max_price": 901989.0,
        "contract_guarantee_part": 5.0,
        "ktru_cnt": 1,
        "okpd2_cnt": 0,
        "position_numbers_cnt": 1,
        "object_info": "Трубка эндотрахеальная стандартная, одноразового использования",
        "okpd2": [],
        "ktru": ["22.21.29.120-00000004"],
    }


def test_raw_ignores_docs_and_nested_fields(ezk_purchase):
    # nested notice has another regNum (03203001015) - must NOT be used for `responsible`
    assert build_raw(ezk_purchase)["responsible"] == "2536010685"


def test_missing_object_info_stays_null_not_empty_string(ezk_purchase):
    # deliberate deviation from `or ""` - see mapper docstring (training had NaN, never "")
    r = build_raw({**ezk_purchase, "object_info": None})
    assert r["object_info"] is None
    assert build_raw({**ezk_purchase, "object_info": ""})["object_info"] is None


def test_missing_lists_and_fields_do_not_crash(ezk_purchase):
    r = build_raw({"purchase_number": "1" * 19, "ktru": None, "okpd2": None, "position_numbers": None})
    assert (r["ktru_cnt"], r["okpd2_cnt"], r["position_numbers_cnt"]) == (0, 0, 0)
    assert r["max_price"] is None and r["published_at_ts"] is None and r["responsible"] is None


def test_unparseable_dates_become_none(ezk_purchase):
    r = build_raw({**ezk_purchase, "published_at": "not a date", "collecting_finished_at": ""})
    assert r["published_at_ts"] is None and r["collecting_finished_at_ts"] is None


def test_timezone_aware_dates_are_converted_to_utc(ezk_purchase):
    r = build_raw({**ezk_purchase, "published_at": "2026-01-30T10:03:03+10:00"})
    assert r["published_at_ts"] == "2026-01-30T00:03:03"


def test_extras_from_notice_document(ezk_purchase):
    ex = extract_extras(ezk_purchase)
    assert ex["placing_way"] == "Запрос котировок в электронной форме"
    assert ex["responsible_name"] == 'КГБУЗ "ВКБ № 4"'
    assert ex["delivery_places_text"][0].startswith("Приморский Край")
    assert ex["notice_url"].startswith("https://zakupki.gov.ru/")


def test_record_has_region_location_and_no_docs(ezk_purchase):
    rec = build_tender_record(ezk_purchase)
    assert rec["location"].precision == "region" and rec["location"].region_code == "25"
    assert "docs" not in rec["gp"]
    assert rec["title_source"] == "object_info"


def test_title_falls_back_to_notice_document(ezk_purchase):
    rec = build_tender_record(make_purchase(ezk_purchase, "1" * 19, object_info=None))
    assert rec["title_source"] == "notice_document" and rec["object_info"] is None
