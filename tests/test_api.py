"""API tests with a mocked GosPlan client and a fake predictor (real validation, fake numbers)."""

from __future__ import annotations

from app.services.gosplan import GosplanError
from tests.conftest import make_purchase

PN = "0320300101526000015"


def test_config_includes_bilingual_region_names(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    regions = response.json()["regions"]
    assert regions["25"] == {"name_en": "Primorsky Krai", "name_ru": "Приморский край"}
    assert all(r["name_en"] and r["name_ru"] for r in regions.values())


def upload(client, **body):
    r = client.post("/api/tenders", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_fetches_stores_winner_and_predicts(client):
    rep = upload(client, purchase_numbers=[PN], predict=True)
    assert rep["summary"]["created"] == 1 and rep["summary"]["predicted"] == 1
    item = rep["results"][0]
    assert item["status"] == "created" and item["winner_price"] == 147150.0
    assert item["prediction"]["status"] == "ok"
    d = client.get(f"/api/tenders/{PN}").json()
    assert d["winner"]["price"] == 147150.0 and d["status"] == "winner"
    assert d["prediction"]["available"] and d["prediction"]["predicted_price"] == 901989.0 * 0.8
    assert d["prediction_error"]["abs"] < 0 or d["prediction_error"]["abs"] > 0
    assert d["region_name"] == "Primorsky Krai" and d["approximate_location"] is True
    assert d["extras"]["placing_way"].startswith("Запрос котировок")


def test_batch_reports_per_item_without_failing_whole_batch(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["1111111111111111111"] = make_purchase(ezk_purchase, "1111111111111111111")
    fake_gosplan.errors["2222222222222222222"] = GosplanError("timeout", "GosPlan did not answer in time")
    rep = upload(client, purchase_numbers=[PN, "1111111111111111111", "3333333333333333333", "2222222222222222222", "abc", PN])
    by = {r["purchase_number"]: r for r in rep["results"]}
    assert by[PN]["status"] == "created" and by["1111111111111111111"]["status"] == "created"
    assert by["3333333333333333333"]["status"] == "failed" and "404" in by["3333333333333333333"]["error"]
    assert by["2222222222222222222"]["error_kind"] == "timeout"
    assert by["abc"]["status"] == "failed" and by["abc"]["error_kind"] == "invalid"
    assert rep["summary"]["requested"] == 5  # duplicate PN collapsed
    assert rep["summary"]["failed"] == 3 and rep["summary"]["created"] == 2


def test_unsupported_type_gives_readable_reason(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["4444444444444444444"] = make_purchase(ezk_purchase, "4444444444444444444", purchase_type="epNotificationEOK2020")
    rep = upload(client, purchase_numbers=["4444444444444444444"], predict=True, fetch_winner=False)
    p = rep["results"][0]["prediction"]
    assert p["status"] == "failed" and "not supported" in p["reason"]
    d = client.get("/api/tenders/4444444444444444444").json()
    assert d["prediction"]["available"] is False and "not supported" in d["prediction"]["error"]


def test_missing_max_price_is_stored_but_not_predictable(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["5555555555555555555"] = make_purchase(ezk_purchase, "5555555555555555555", max_price=None)
    rep = upload(client, purchase_numbers=["5555555555555555555"], predict=True, fetch_winner=False)
    assert rep["results"][0]["status"] == "created"
    assert "maximum price" in rep["results"][0]["prediction"]["reason"]


def test_upload_full_record_with_winner_price(client, ezk_purchase):
    rec = make_purchase(ezk_purchase, "6666666666666666666", winner_price=500000)
    rep = upload(client, records=[rec], fetch_winner=False)
    assert rep["results"][0]["winner_price"] == 500000
    assert client.get("/api/tenders/6666666666666666666").json()["winner"]["price"] == 500000


def test_uploaded_winner_price_is_validated(client, ezk_purchase):
    rec = make_purchase(ezk_purchase, "7777777777777777777", winner_price=99999999)
    rep = upload(client, records=[rec], fetch_winner=False)
    assert rep["results"][0]["winner_price"] is None and "exceeds" in rep["results"][0]["winner_note"]
    assert client.get("/api/tenders/7777777777777777777").json()["winner"]["price"] is None


def test_winner_omitted_when_protocols_missing(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["8888888888888888888"] = make_purchase(ezk_purchase, "8888888888888888888")
    upload(client, purchase_numbers=["8888888888888888888"])
    d = client.get("/api/tenders/8888888888888888888").json()
    assert d["winner"]["price"] is None and d["status"] == "pending"


def test_predict_endpoint_and_404(client):
    upload(client, purchase_numbers=[PN])
    r = client.post(f"/api/tenders/{PN}/predict")
    assert r.status_code == 200 and r.json()["prediction"]["available"]
    assert client.post("/api/tenders/9999999999999999999/predict").status_code == 404
    assert client.get("/api/tenders/9999999999999999999").status_code == 404


def test_predict_returns_503_while_model_loads(make_client):
    with make_client(ready=False) as c:
        upload(c, purchase_numbers=[PN])
        r = c.post(f"/api/tenders/{PN}/predict")
        assert r.status_code == 503 and "loading" in r.json()["detail"]
        # upload with predict=true must not crash either
        rep = upload(c, purchase_numbers=[PN], predict=True)
        assert rep["results"][0]["prediction"]["status"] == "failed"


def test_list_filters_search_and_sort(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["1000000000000000001"] = make_purchase(
        ezk_purchase, "1000000000000000001", purchase_type="epNotificationEF2020", max_price=5_000_000.0,
        region=77, object_info="Ноутбук Lenovo", responsible="7701234567", published_at="2026-03-01T10:00:00")
    upload(client, purchase_numbers=[PN, "1000000000000000001"], predict=True)
    allr = client.get("/api/tenders").json()
    assert allr["total"] == 2 and allr["items"][0]["purchase_number"] == "1000000000000000001"  # newest first
    assert client.get("/api/tenders", params={"purchase_type": "epNotificationEF2020"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"region": "25"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"status": "winner"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"status": "not_predicted"}).json()["total"] == 0
    assert client.get("/api/tenders", params={"price_min": 1_000_000}).json()["total"] == 1
    assert client.get("/api/tenders", params={"published_from": "2026-02-01"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"published_to": "2026-01-30"}).json()["total"] == 1
    # Cyrillic, case-insensitive search (SQLite LIKE alone would fail here)
    assert client.get("/api/tenders", params={"q": "ТРУБКА эндотрахеальная"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"q": "lenovo"}).json()["total"] == 1
    assert client.get("/api/tenders", params={"q": "22.21.29.120"}).json()["total"] == 2   # KTRU code
    assert client.get("/api/tenders", params={"q": "03203001015260000"}).json()["items"][0]["purchase_number"] == PN
    assert client.get("/api/tenders", params={"q": "zzzz"}).json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
    assert client.get("/api/tenders", params={"q": "100%"}).json()["total"] == 0   # LIKE wildcards are escaped
    assert client.get("/api/tenders", params={"sort": "price_desc"}).json()["items"][0]["max_price"] == 5_000_000.0
    assert client.get("/api/tenders", params={"limit": 1, "offset": 1}).json()["items"][0]["purchase_number"] == PN


def test_filters_endpoint_is_generated_from_data(client):
    upload(client, purchase_numbers=[PN], predict=True)
    f = client.get("/api/filters").json()
    assert f["total"] == 1
    assert f["purchase_type"][0] == {"value": "epNotificationEZK2020", "label": "EZK", "count": 1}
    assert f["region"][0]["label"] == "Primorsky Krai"
    assert {s["value"]: s["count"] for s in f["status"]} == {"winner": 1, "predicted": 1, "not_predicted": 0}
    resp = client.get("/api/filters/responsibles", params={"q": "вкб"}).json()
    assert resp[0]["value"] == "2536010685" and resp[0]["count"] == 1


def test_map_points_and_summary(client, fake_gosplan, ezk_purchase):
    for i in range(3):
        fake_gosplan.purchases[f"200000000000000000{i}"] = make_purchase(ezk_purchase, f"200000000000000000{i}", max_price=100.0 * (i + 1))
    fake_gosplan.purchases["2999999999999999999"] = make_purchase(ezk_purchase, "2999999999999999999", region=90)  # no location
    upload(client, purchase_numbers=[PN, "2000000000000000000", "2000000000000000001", "2000000000000000002", "2999999999999999999"],
           fetch_winner=False)
    fc = client.get("/api/map/points").json()
    assert len(fc["features"]) == 1                      # all four share the region-25 point
    props = fc["features"][0]["properties"]
    assert props["n"] == 4 and props["precision"] == "region" and "samples" not in props
    # tooltip samples come from the list endpoint: largest first
    top = client.get("/api/tenders", params={"loc_key": props["loc_key"], "sort": "price_desc", "limit": 3}).json()["items"]
    assert [t["max_price"] for t in top] == [901989.0, 300.0, 200.0]
    s = client.get("/api/summary").json()
    assert s["n"] == 5 and s["located"] == 4 and s["unlocated"] == 1
    assert client.get("/api/map/points", params={"price_max": 150}).json()["features"][0]["properties"]["n"] == 1
    # records without a location are still listed
    assert client.get("/api/tenders", params={"has_location": "false"}).json()["total"] == 1


def test_download_proxy_returns_raw_json_attachment(client):
    r = client.get(f"/api/tenders/{PN}/download")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == f'attachment; filename="{PN}.json"'
    assert r.json()["purchase_number"] == PN


def test_download_errors_are_readable(client, fake_gosplan):
    assert client.get("/api/tenders/1234567890123456789/download").status_code == 404
    fake_gosplan.errors["1234567890123456780"] = GosplanError("timeout", "GosPlan did not answer in time")
    r = client.get("/api/tenders/1234567890123456780/download")
    assert r.status_code == 504 and "in time" in r.json()["detail"]
    assert client.get("/api/tenders/not-a-number/download").status_code == 422


def test_delete(client):
    upload(client, purchase_numbers=[PN])
    assert client.delete(f"/api/tenders/{PN}").status_code == 204
    assert client.delete(f"/api/tenders/{PN}").status_code == 404
    assert client.get("/api/tenders").json()["total"] == 0


def test_reupload_keeps_prediction_if_input_unchanged_and_resets_otherwise(client, fake_gosplan):
    upload(client, purchase_numbers=[PN], predict=True)
    upload(client, purchase_numbers=[PN])  # same data
    assert client.get(f"/api/tenders/{PN}").json()["prediction"]["available"] is True
    fake_gosplan.purchases[PN]["max_price"] = 1_000_000.0
    upload(client, purchase_numbers=[PN])  # model input changed -> prediction is stale
    d = client.get(f"/api/tenders/{PN}").json()
    assert d["prediction"]["available"] is False and d["status"] == "winner"


def test_skip_existing(client, fake_gosplan):
    upload(client, purchase_numbers=[PN])
    before = len(fake_gosplan.calls)
    rep = upload(client, purchase_numbers=[PN], skip_existing=True)
    assert rep["results"][0]["status"] == "skipped" and len(fake_gosplan.calls) == before


def test_batch_limit_and_empty_body(client):
    r = client.post("/api/tenders", json={"purchase_numbers": [str(10**18 + i) for i in range(51)]})
    assert r.status_code == 413
    assert client.post("/api/tenders", json={}).status_code == 422


def test_file_upload_csv_txt_json(client, fake_gosplan, ezk_purchase):
    fake_gosplan.purchases["3000000000000000001"] = make_purchase(ezk_purchase, "3000000000000000001")
    csv_body = f"purchase_number,winner_price\n{PN},\n3000000000000000001,12345\n"
    r = client.post("/api/tenders/upload", files={"file": ("x.csv", csv_body, "text/csv")}, data={"predict": "true", "fetch_winner": "false"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["summary"]["created"] == 2 and rep["summary"]["predicted"] == 2
    assert client.get("/api/tenders/3000000000000000001").json()["winner"]["price"] == 12345
    r = client.post("/api/tenders/upload", files={"file": ("n.txt", f"{PN}\n3000000000000000001\n", "text/plain")})
    assert r.json()["summary"]["updated"] == 2
    r = client.post("/api/tenders/upload", files={"file": ("n.json", f'["{PN}"]', "application/json")})
    assert r.json()["summary"]["updated"] == 1
    r = client.post("/api/tenders/upload", files={"file": ("bad.json", "[1,", "application/json")})
    assert r.status_code == 422
    r = client.post("/api/tenders/upload", files={"file": ("empty.txt", "hello", "text/plain")})
    assert r.status_code == 422


def test_health_config_and_index(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["model"]["ready"] is True
    cfg = client.get("/api/config").json()
    assert "tiles" in cfg and cfg["max_batch_size"] == 50
    r = client.get("/")
    assert r.status_code == 200 and "Tender Price Predictor" in r.text
    assert client.get("/static/vendor/maplibre-gl.js").status_code == 200
    assert client.get("/static/data/regions.geojson").status_code == 200
    assert client.get("/openapi.json").status_code == 200
