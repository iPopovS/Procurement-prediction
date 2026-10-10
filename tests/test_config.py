from app.config import Settings


def test_empty_tile_url_disables_tiles(monkeypatch):
    monkeypatch.setenv("MAP_TILE_URL", "")
    assert Settings.from_env().map_tile_url == ""


def test_unset_tile_url_uses_default(monkeypatch):
    monkeypatch.delenv("MAP_TILE_URL", raising=False)
    assert Settings.from_env().map_tile_url.startswith("https://tile.openstreetmap.org")


def test_defaults(monkeypatch):
    for k in ("GOSPLAN_BASE_URL", "GOSPLAN_API_KEY", "GOSPLAN_CONCURRENCY", "MAX_BATCH_SIZE"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.gosplan_base_url == "https://v2test.gosplan.info" and s.gosplan_concurrency == 8 and s.max_batch_size == 1000


def test_trailing_slash_is_stripped(monkeypatch):
    monkeypatch.setenv("GOSPLAN_BASE_URL", "https://example.test/")
    assert Settings.from_env().gosplan_base_url == "https://example.test"


def test_api_key_switches_default_to_production(monkeypatch):
    monkeypatch.delenv("GOSPLAN_BASE_URL", raising=False)
    monkeypatch.setenv("GOSPLAN_API_KEY", " secret ")
    s = Settings.from_env()
    assert s.gosplan_api_key == "secret" and s.gosplan_base_url == "https://v2.gosplan.info"


def test_explicit_base_url_wins_over_key(monkeypatch):
    monkeypatch.setenv("GOSPLAN_API_KEY", "secret")
    monkeypatch.setenv("GOSPLAN_BASE_URL", "https://v2test.gosplan.info")
    assert Settings.from_env().gosplan_base_url == "https://v2test.gosplan.info"
