from app.config import Settings


def test_empty_tile_url_disables_tiles(monkeypatch):
    monkeypatch.setenv("MAP_TILE_URL", "")
    assert Settings.from_env().map_tile_url == ""


def test_unset_tile_url_uses_default(monkeypatch):
    monkeypatch.delenv("MAP_TILE_URL", raising=False)
    assert Settings.from_env().map_tile_url.startswith("https://tile.openstreetmap.org")


def test_defaults(monkeypatch):
    for k in ("GOSPLAN_BASE_URL", "GOSPLAN_CONCURRENCY", "MAX_BATCH_SIZE"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.gosplan_base_url == "https://v2test.gosplan.info" and s.gosplan_concurrency == 8 and s.max_batch_size == 1000


def test_trailing_slash_is_stripped(monkeypatch):
    monkeypatch.setenv("GOSPLAN_BASE_URL", "https://example.test/")
    assert Settings.from_env().gosplan_base_url == "https://example.test"
