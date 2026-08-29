import json

import httpx

import fetch_profiles


class FakeClient:
    def __init__(self, domain_items=None, cross=None, healthy=True):
        self.domain_items = domain_items or {}
        self.cross = cross or {}
        self.healthy = healthy

    def health(self):
        return self.healthy

    def list_domain(self, domain, params, limit):
        return self.domain_items.get(domain, [])[:limit]

    def cross_search(self, keyword, domains, per_domain=20):
        return self.cross.get(keyword, [])


def test_domain_mode_writes_profiles(tmp_path):
    client = FakeClient(domain_items={
        "academic": [{"name": "Yi Wu", "education_school": "Tsinghua University",
                      "h_index": 30}],
        "open_source": [{"github_login": "yiwu", "name": "Yi Wu",
                         "company": "Tsinghua", "total_stars_received": 9000}],
        "competition": [],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "rl", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(profiles) == 1                      # name+org 相同 → medium 合并
    assert set(profiles[0]["linked_domains"]) == {"academic", "open_source"}
    assert profiles_state_ok(run_dir)


def profiles_state_ok(run_dir):
    state = json.loads((run_dir / "_state.json").read_text(encoding="utf-8"))
    return state["stages_done"] == ["fetch"] and state["mode"] == "domain"


def test_domain_mode_keyword_fallback_filter(tmp_path):
    class PickyClient(FakeClient):
        def list_domain(self, domain, params, limit):
            if params.get("keyword") == "rl":
                raise fetch_profiles.api_client.ApiUnreachable("400 simulated")
            return self.domain_items.get(domain, [])[:limit]
    client = PickyClient(domain_items={
        "academic": [{"name": "A", "education_school": "X", "topic_tags": ["rl"]},
                     {"name": "B", "education_school": "X", "topic_tags": ["cv"]}],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "rl", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    names = {p["name"] for p in profiles}
    assert "A" in names and "B" not in names


def test_names_mode_in_library_false(tmp_path):
    client = FakeClient(cross={"Nobody": []})
    rc = fetch_profiles.main(
        ["--mode", "names", "--names", "Nobody", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert profiles[0]["in_library"] is False
    assert profiles[0]["name"] == "Nobody"
    assert profiles[0]["person_id"].startswith("p_")


def test_names_mode_filters_foreign_names(tmp_path):
    client = FakeClient(cross={
        "Yi Wu": [
            {"domain": "academic", "name": "Yi Wu", "education_school": "T"},
            {"domain": "open_source", "name": "Completely Different", "github_login": "x"},
        ]})
    rc = fetch_profiles.main(
        ["--mode", "names", "--names", "Yi Wu", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(profiles) == 1
    assert "academic" in profiles[0]["records"]


def test_unhealthy_backend_exit_2(tmp_path):
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "x", "--out", str(tmp_path)],
        client=FakeClient(healthy=False))
    assert rc == 2
    assert not [d for d in tmp_path.iterdir() if d.is_dir()]  # 不遗留空 run 目录


def _http_status_error():
    req = httpx.Request("GET", "http://testserver/open-api/x/talents")
    resp = httpx.Response(400, request=req)
    return httpx.HTTPStatusError("400 Bad Request", request=req, response=resp)


def test_domain_gap_recorded(tmp_path):
    class GapClient(FakeClient):
        def list_domain(self, domain, params, limit):
            if domain == "academic":
                raise RuntimeError("boom")
            return self.domain_items.get(domain, [])[:limit]
    client = GapClient(domain_items={
        "open_source": [{"github_login": "dev1", "name": "Dev One",
                         "company": "Acme", "total_stars_received": 100}],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "x", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    gaps = (run_dir / "gaps.txt").read_text(encoding="utf-8").split()
    assert "academic" in gaps and "open_source" not in gaps
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {p["name"] for p in profiles} == {"Dev One"}  # 其余域画像照常


def test_fallback_triggered_by_http_status_error(tmp_path):
    class FourHundredClient(FakeClient):
        def list_domain(self, domain, params, limit):
            if params.get("keyword"):
                raise _http_status_error()  # 真实客户端 4xx → HTTPStatusError
            return self.domain_items.get(domain, [])[:limit]
    client = FourHundredClient(domain_items={
        "academic": [{"name": "A", "education_school": "X", "topic_tags": ["rl"]},
                     {"name": "B", "education_school": "X", "topic_tags": ["cv"]}],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "rl", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    names = {p["name"] for p in profiles}
    assert "A" in names and "B" not in names  # 4xx 触发兜底 → 本地过滤生效


def test_fallback_failure_recorded_as_gap(tmp_path):
    class FlakyFallbackClient(FakeClient):
        def list_domain(self, domain, params, limit):
            if domain == "academic":
                if params.get("keyword"):
                    raise fetch_profiles.api_client.ApiUnreachable("503 simulated")
                raise RuntimeError("still down")  # 兜底调用也失败
            return self.domain_items.get(domain, [])[:limit]
    client = FlakyFallbackClient(domain_items={
        "open_source": [{"github_login": "dev1", "name": "Dev One", "company": "Acme"}],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "x", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    gaps = (run_dir / "gaps.txt").read_text(encoding="utf-8").split()
    assert "academic" in gaps and "open_source" not in gaps
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {p["name"] for p in profiles} == {"Dev One"}


def test_contact_on_non_lead_record(tmp_path):
    client = FakeClient(domain_items={
        "academic": [{"name": "Yi Wu", "education_school": "Tsinghua University"}],
        "open_source": [{"github_login": "yiwu", "name": "Yi Wu",
                         "company": "Tsinghua", "total_stars_received": 9000}],
    })
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "rl", "--out", str(tmp_path)], client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(profiles) == 1  # name+org medium 合并
    # github_login 在 open_source 成员记录上（主记录 academic 无联系字段）
    assert profiles[0]["contact_info_unavailable"] is False


def test_resume_skips_completed_fetch(tmp_path):
    client = FakeClient(cross={"Nobody": []})
    argv = ["--mode", "names", "--names", "Nobody", "--out", str(tmp_path)]
    assert fetch_profiles.main(argv, client=client) == 0
    assert fetch_profiles.main(argv + ["--resume"], client=client) == 0
    assert len([d for d in tmp_path.iterdir() if d.is_dir()]) == 1  # 不新建目录


def test_names_dedup(tmp_path):
    client = FakeClient(cross={
        "Yi Wu": [{"domain": "academic", "name": "Yi Wu", "education_school": "T"}]})
    rc = fetch_profiles.main(
        ["--mode", "names", "--names", "Yi Wu,Yi Wu", "--out", str(tmp_path)],
        client=client)
    assert rc == 0
    run_dir = next(d for d in tmp_path.iterdir() if d.is_dir())
    profiles = [json.loads(l) for l in
                (run_dir / "profiles.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(profiles) == 1  # 重复名不产生双画像
    ids = [p["person_id"] for p in profiles]
    assert len(set(ids)) == len(ids)


def test_names_file_missing_exit_1(tmp_path, capsys):
    rc = fetch_profiles.main(
        ["--mode", "names", "--names-file", str(tmp_path / "nope.txt"),
         "--out", str(tmp_path)])
    assert rc == 1
    assert "不存在" in capsys.readouterr().err
