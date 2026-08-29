import pytest

from talent_identifier import api_client


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise api_client.httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def test_get_retries_on_429_then_ok(monkeypatch):
    calls = []
    seq = [FakeResp(429), FakeResp(200, {"ok": 1})]
    monkeypatch.setattr(api_client.httpx, "get",
                        lambda *a, **k: (calls.append(1), seq[len(calls) - 1])[1])
    monkeypatch.setattr(api_client.time, "sleep", lambda s: None)
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    assert c._get("/health") == {"ok": 1}
    assert len(calls) == 2


def test_get_raises_after_3_failures(monkeypatch):
    monkeypatch.setattr(api_client.httpx, "get",
                        lambda *a, **k: FakeResp(500))
    monkeypatch.setattr(api_client.time, "sleep", lambda s: None)
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    with pytest.raises(api_client.ApiUnreachable):
        c._get("/anything")


def test_list_domain_pagination(monkeypatch):
    page1 = {"items": [{"id": i} for i in range(100)], "total": 150, "page": 1, "page_size": 100}
    page2 = {"items": [{"id": i} for i in range(100, 150)], "total": 150, "page": 2, "page_size": 100}
    monkeypatch.setattr(api_client.httpx, "get", lambda url, **k: FakeResp(200, page1 if k["params"]["page"] == 1 else page2))
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    items = c.list_domain("academic", {"keyword": "rl"}, limit=150)
    assert len(items) == 150


def test_cross_search_flatten_items_envelope():
    c = api_client.OpenApiClient.__new__(api_client.OpenApiClient)
    payload = {"items": [{"domain": "academic", "name": "A"}, {"domain": "lab", "name": "B"}]}
    out = api_client._iter_cross_items(payload)
    assert [r["name"] for r in out] == ["A", "B"]


def test_cross_search_flatten_domain_map_envelope():
    payload = {"academic": {"items": [{"name": "A"}]}, "lab": [{"name": "B"}]}
    out = api_client._iter_cross_items(payload)
    by_dom = {r["domain"]: r["name"] for r in out}
    assert by_dom == {"academic": "A", "lab": "B"}


def test_cross_search_drops_non_dict_in_domain_map():
    payload = {"academic": ["str", {"name": "A"}]}
    out = api_client._iter_cross_items(payload)
    assert [r["name"] for r in out] == ["A"]
    assert out[0]["domain"] == "academic"


def test_no_sleep_after_final_attempt(monkeypatch):
    sleeps = []
    monkeypatch.setattr(api_client.httpx, "get", lambda *a, **k: FakeResp(500))
    monkeypatch.setattr(api_client.time, "sleep", lambda s: sleeps.append(s))
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    with pytest.raises(api_client.ApiUnreachable):
        c._get("/anything")
    assert sleeps == [1, 2]


def test_retries_on_readerror(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise api_client.httpx.ReadError("x")
        return FakeResp(200, {"ok": 1})

    monkeypatch.setattr(api_client.httpx, "get", flaky)
    monkeypatch.setattr(api_client.time, "sleep", lambda s: None)
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    assert c._get("/health") == {"ok": 1}
    assert len(calls) == 2


def test_4xx_raises_immediately_no_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(api_client.httpx, "get",
                        lambda *a, **k: (calls.append(1), FakeResp(404))[1])
    sleeps = []
    monkeypatch.setattr(api_client.time, "sleep", lambda s: sleeps.append(s))
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    with pytest.raises(api_client.httpx.HTTPStatusError):
        c._get("/none")
    assert len(calls) == 1 and sleeps == []


def test_cross_search_accepts_real_name_only():
    # 后端 competition 域人名字段是 real_name（无 name）：不再丢弃，且回填 name 供下游统一读取
    payload = {"competition": [{"real_name": "Gennady Korotkevich", "max_rating": 3900}]}
    out = api_client._iter_cross_items(payload)
    assert len(out) == 1
    assert out[0]["name"] == "Gennady Korotkevich"


def test_health_false_when_unreachable(monkeypatch):
    def boom(*a, **k):
        raise api_client.httpx.ConnectError("no")
    monkeypatch.setattr(api_client.httpx, "get", boom)
    monkeypatch.setattr(api_client.time, "sleep", lambda s: None)
    c = api_client.OpenApiClient("http://x/api/v1", "sk")
    assert c.health() is False
