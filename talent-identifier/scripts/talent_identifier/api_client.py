"""AI4TALENT Open API 客户端：X-API-Key 认证、429/5xx 退避重试、分页、跨域搜索。"""
import time

import httpx

ENVELOPE_DOMAIN_KEYS = ("domain", "source_domain", "source")


class ApiUnreachable(Exception):
    pass


def _iter_cross_items(payload) -> list[dict]:
    """跨域搜索响应防御性解析：兼容 items 列表 / 域名→列表 两种形态。"""
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("items"), list):
        items = payload["items"]
    else:
        items = []
        for key, val in payload.items():
            raw = val.get("items") if isinstance(val, dict) else val
            if not isinstance(raw, list):
                continue
            for it in raw:
                if isinstance(it, dict):
                    items.append(dict(it, domain=key))
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if not any(it.get(k) for k in ENVELOPE_DOMAIN_KEYS):
            it = dict(it, domain="unknown")
        if it.get("name"):
            out.append(it)
    return out


class OpenApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"X-API-Key": api_key} if api_key else {}

    def _get(self, path: str, params: dict | None = None):
        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(3):
            try:
                resp = httpx.get(f"{self.base}{path}", params=params,
                                 headers=self.headers, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = RuntimeError(f"HTTP {resp.status_code}")
                else:
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TransportError as e:
                last_exc = e
            if attempt < 2:
                time.sleep(2 ** attempt)
        raise ApiUnreachable(str(last_exc))

    def health(self) -> bool:
        try:
            self._get("/health")
            return True
        except Exception:
            return False

    def list_domain(self, domain: str, params: dict, limit: int) -> list[dict]:
        items: list[dict] = []
        page, page_size = 1, min(100, max(1, limit))
        while len(items) < limit:
            data = self._get(f"/open-api/{domain}/talents",
                             {**params, "page": page, "page_size": page_size})
            batch = data.get("items") or []
            items += batch
            total = data.get("total", len(items))
            if not batch or len(items) >= total:
                break
            page += 1
        return [it for it in items[:limit] if isinstance(it, dict)]

    def cross_search(self, keyword: str, domains: list[str], per_domain: int = 20) -> list[dict]:
        data = self._get("/open-api/search/talents", {
            "keyword": keyword,
            "domains": ",".join(domains),
            "per_domain": min(20, per_domain),
        })
        return _iter_cross_items(data)
