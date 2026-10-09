import httpx
import pytest

from app.services.gosplan import GosplanClient, GosplanError


def make(handler, retries=3):
    transport = httpx.MockTransport(handler)
    return GosplanClient("https://example.test", retries=retries, backoff=0.0, concurrency=2,
                         client=httpx.AsyncClient(transport=transport))


async def test_retries_503_then_succeeds():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"purchase_number": "1"})

    c = make(handler)
    assert (await c.get_purchase("1"))["purchase_number"] == "1"
    assert len(calls) == 3


async def test_404_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(GosplanError) as e:
        await make(handler).get_purchase("1")
    assert e.value.kind == "not_found" and len(calls) == 1


async def test_timeout_after_retries():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(GosplanError) as e:
        await make(handler, retries=2).get_purchase("1")
    assert e.value.kind == "timeout"


async def test_persistent_5xx_reports_unavailable():
    with pytest.raises(GosplanError) as e:
        await make(lambda r: httpx.Response(502), retries=1).get_protocols("1")
    assert e.value.kind == "unavailable" and "502" in e.value.message


async def test_invalid_json_and_wrong_shape():
    with pytest.raises(GosplanError) as e:
        await make(lambda r: httpx.Response(200, text="<html>")).get_purchase("1")
    assert e.value.kind == "bad_response"
    with pytest.raises(GosplanError):
        await make(lambda r: httpx.Response(200, json={"x": 1})).get_purchase("1")
    with pytest.raises(GosplanError):
        await make(lambda r: httpx.Response(200, json={"x": 1})).get_protocols("1")


async def test_download_returns_untouched_bytes_and_sends_accept_header():
    seen = {}

    def handler(req):
        seen["accept"] = req.headers["accept"]
        seen["path"] = req.url.path
        return httpx.Response(200, content=b'{"purchase_number":"1","k":"\xd1\x82"}')

    body = await make(handler).download_purchase("123")
    assert body == b'{"purchase_number":"1","k":"\xd1\x82"}'
    assert seen == {"accept": "application/json", "path": "/fz44/purchases/123"}


async def test_path_injection_is_quoted():
    seen = {}

    def handler(req):
        seen["raw"] = req.url.raw_path.decode()
        return httpx.Response(200, json={"purchase_number": "x"})

    await make(handler).get_purchase("../../etc")
    assert "/../" not in seen["raw"]
