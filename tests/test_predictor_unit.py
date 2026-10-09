"""Validation + frame building that need no model."""

import pandas as pd

from app.ml import pipeline as pl
from app.ml.predictor import check_raw, raw_to_frame, type_label
from app.services.mapper import build_raw


def test_type_labels():
    assert [type_label(t) for t in pl.SUPPORTED] == ["EF", "EZK", "EZT"]
    assert type_label("epNotificationEOK2020") == "EOK"
    assert type_label(None) is None


def test_check_raw_ok(ezk_purchase):
    assert check_raw(build_raw(ezk_purchase)) is None


def test_check_raw_reasons(ezk_purchase):
    raw = build_raw(ezk_purchase)
    assert "purchase type is missing" in check_raw({**raw, "purchase_type": None})
    assert "not supported" in check_raw({**raw, "purchase_type": "epNotificationEOK2020"})
    assert "maximum price" in check_raw({**raw, "max_price": None})
    assert "greater than 1" in check_raw({**raw, "max_price": 1.0})
    assert "publication date" in check_raw({**raw, "published_at_ts": None})
    assert "publication date" in check_raw({**raw, "published_at_ts": "garbage"})


def test_frame_schema_and_dtypes(ezk_purchase):
    df = raw_to_frame([build_raw(ezk_purchase), build_raw({**ezk_purchase, "object_info": None, "ktru": [], "okpd2": ["26.20.1"]})])
    assert list(df.columns) == pl.RAW_COLS
    assert str(df["published_at_ts"].dtype) == "datetime64[ns]"
    assert df["max_price"].dtype == "float64" and df["ktru_cnt"].dtype == "int64"
    assert pd.isna(df.loc[1, "object_info"]) and df.loc[0, "object_info"].startswith("Трубка")
    assert df.loc[1, "okpd2"] == ["26.20.1"] and df.loc[0, "okpd2"] == []


def test_frame_handles_missing_collecting_date_and_guarantee(ezk_purchase):
    df = raw_to_frame([build_raw({**ezk_purchase, "collecting_finished_at": None, "contract_guarantee_part": None})])
    assert pd.isna(df.loc[0, "collecting_finished_at_ts"]) and pd.isna(df.loc[0, "contract_guarantee_part"])
