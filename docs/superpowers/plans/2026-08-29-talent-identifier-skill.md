# talent-identifier Skill 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 talent-identifier skill——基于 AI4TALENT Open API 识别跨学术/开源/实验室/竞赛/行业的顶尖人才，Agent 互联网补全最新动态，输出 Markdown + HTML + JSONL 三件套洞察报告。

**Architecture:** 混合流水线（设计文档方案 C）：确定性环节（拉取/跨域关联/T-score 评分/渲染）为 Python 脚本，智能环节（互联网探索/定性洞察）由 Agent 按 SKILL.md 指令执行；阶段间以 `output/<run_id>/` 内的 JSONL 文件接力，支持 `--resume` 断点续跑。

**Tech Stack:** Python 3.11+（仅依赖 httpx；测试用 pytest，经 `uv run --with` 免装环境）、AI4TALENT Open API（X-API-Key）、ECharts（HTML 报告，可内联）。

**设计文档:** `docs/superpowers/specs/2026-08-29-talent-identifier-skill-design.md`

**开发位置与部署目标:**
- 开发：`D:\AI\IdentifyAgent\talent-identifier\`（git 仓库内）
- 部署：完成后复制到 `C:\Users\Administrator\.agents\skills\talent-identifier\`
- 运行产物：落在启动时 cwd 的 `output/` 下（git 已忽略则不加 .gitignore 到仓库根——skill 自带 `.gitignore` 只管自身）

**约定（全部任务适用）:**
- 测试命令（在 `D:\AI\IdentifyAgent\talent-identifier` 下执行）：`uv run --with httpx --with pytest python -m pytest scripts/tests -v`；若 uv 不可用且本机 python 已装 httpx/pytest，可用 `python -m pytest scripts/tests -v`
- 单测命令：在上述命令后追加 `scripts/tests/test_xxx.py::test_name`
- 提交信息用 conventional commits（feat/test/docs/chore）
- 所有 Python 文件 UTF-8、无 BOM；JSONL 一行一 JSON 对象

---

## 文件结构总览（分解决策）

```
talent-identifier/
├── SKILL.md                          # Task 13
├── .gitignore                        # Task 1（内容: output/）
├── ai4talent.config.json             # Task 1（配置模板，api_key 留空）
├── references/                       # Task 12
│   ├── openapi-contract.md
│   ├── scoring-model.md
│   ├── identity-linking.md
│   ├── web-exploration.md
│   └── report-templates.md
├── assets/
│   └── echarts.min.js                # Task 13（可选，一次性下载）
└── scripts/
    ├── talent_identifier/            # 共享包（Task 1-6）
    │   ├── __init__.py
    │   ├── config.py                 #   Task 1：配置合并 + 环境变量覆盖
    │   ├── io_utils.py               #   Task 2：run 目录 / JSONL / 断点状态
    │   ├── normalize.py              #   Task 3：姓名/机构/URL 规范化
    │   ├── api_client.py             #   Task 4：Open API 客户端（重试/分页/跨域搜索）
    │   ├── linking.py                #   Task 5：跨域身份关联（DSU + 三档置信度）
    │   └── scoring.py                #   Task 6：T-score 评分模型
    ├── fetch_profiles.py             # Task 7：阶段1 CLI（domain/names 两模式）
    ├── compute_scores.py             # Task 8：阶段2 CLI
    ├── render_report.py              # Task 9-10：阶段4 CLI（md + html + final jsonl）
    ├── check_pipeline.py             # Task 11：产物校验
    └── tests/                        # 各任务配套测试
        ├── conftest.py
        ├── test_config.py
        ├── test_io_utils.py
        ├── test_normalize.py
        ├── test_api_client.py
        ├── test_linking.py
        ├── test_scoring.py
        ├── test_fetch_offline.py
        ├── test_compute_offline.py
        └── test_render_offline.py
```

**数据契约（后续所有任务引用，不得改名）:**

`profiles.jsonl` 每行（阶段1产出）:
```json
{"person_id": "p_ab12cd34", "name": "吴翼", "name_en": "Yi Wu", "org": "清华",
 "homepage": "https://...", "github": "https://github.com/x", "orcid": "", "email": "",
 "tags": ["rl", "llm"], "in_library": true,
 "records": {"academic": {"...原始域字段..."}, "lab": {"..."}},
 "linked_domains": ["academic", "lab"],
 "link_evidence": [{"field": "github", "value": "https://github.com/x", "confidence": "high"}],
 "suspected_same_person": [{"person_id": "p_ff00ee11", "basis": "name+tags"}],
 "contact_info_unavailable": false, "collected_at": "2026-08-29T08:00:00+00:00"}
```

`scores.jsonl` 每行（阶段2产出，按 t_score 降序、null 尾置）:
```json
{"person_id": "p_ab12cd34", "name": "吴翼", "rank": 1, "t_score": 87.5,
 "domain_scores": {"academic": 90.0, "lab": 72.0},
 "score_components": {"academic": {"h_index": 0.82, "cited_by": 0.9, "works": 0.4, "activity": 1.0}},
 "linked_domains": ["academic", "lab"]}
```

`enrichment.jsonl` 每行（阶段3 Agent 追加写入）:
```json
{"person_id": "p_ab12cd34", "kind": "award", "title": "NeurIPS 2026 Best Paper",
 "date": "2026-06", "source_url": "https://...", "evidence_level": "high",
 "summary": "...", "collected_at": "2026-08-29T08:30:00+00:00"}
```
`kind` 枚举：`position_change|paper|project|award|talk|blog|social`；`evidence_level` 枚举：`high|medium|low`。

`_state.json`：`{"run_id": "...", "mode": "domain|names", "stages_done": ["fetch", "score", "explore", "render"]}`

`final/talents_<run_id>.jsonl` 每行（阶段4产出）：画像字段 + 评分字段 + `dynamics[]`（enrichment 行）+ `insight_md`（`enrichment/<person_id>.md` 全文，可省略）。

---

### Task 1: 项目骨架与 config 模块

**Files:**
- Create: `talent-identifier/.gitignore`
- Create: `talent-identifier/ai4talent.config.json`
- Create: `talent-identifier/scripts/talent_identifier/__init__.py`
- Create: `talent-identifier/scripts/talent_identifier/config.py`
- Create: `talent-identifier/scripts/tests/conftest.py`
- Create: `talent-identifier/scripts/tests/test_config.py`

- [ ] **Step 1: 创建目录骨架与基础文件**

```bash
cd /d/AI/IdentifyAgent
mkdir -p talent-identifier/scripts/talent_identifier talent-identifier/scripts/tests talent-identifier/references talent-identifier/assets
printf 'output/\n' > talent-identifier/.gitignore
touch talent-identifier/scripts/talent_identifier/__init__.py
```

`talent-identifier/ai4talent.config.json`:
```json
{
  "base_url": "http://localhost:8003/api/v1",
  "api_key": "",
  "top_n": 20,
  "per_domain_limit": 50,
  "domains": ["academic", "open_source", "lab", "competition", "industry"],
  "exploration": { "max_searches": 6, "max_fetches": 4 }
}
```

`talent-identifier/scripts/tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 2: 写失败测试**

`talent-identifier/scripts/tests/test_config.py`:
```python
import json

from talent_identifier import config


def test_defaults_when_no_files(tmp_path, monkeypatch):
    monkeypatch.delenv("AI4TALENT_API_KEY", raising=False)
    monkeypatch.delenv("AI4TALENT_BASE_URL", raising=False)
    cfg = config.load_config(tmp_path / "skill", tmp_path / "cwd")
    assert cfg["base_url"] == "http://localhost:8003/api/v1"
    assert cfg["top_n"] == 20
    assert cfg["domains"] == ["academic", "open_source", "lab", "competition", "industry"]
    assert cfg["exploration"]["max_searches"] == 6


def test_skill_template_then_cwd_override(tmp_path, monkeypatch):
    monkeypatch.delenv("AI4TALENT_API_KEY", raising=False)
    skill_dir, cwd = tmp_path / "skill", tmp_path / "cwd"
    skill_dir.mkdir(); cwd.mkdir()
    (skill_dir / "ai4talent.config.json").write_text(
        json.dumps({"top_n": 10}), encoding="utf-8")
    (cwd / "ai4talent.config.json").write_text(
        json.dumps({"top_n": 30, "per_domain_limit": 40}), encoding="utf-8")
    cfg = config.load_config(skill_dir, cwd)
    assert cfg["top_n"] == 30          # cwd 覆盖 skill 模板
    assert cfg["per_domain_limit"] == 40
    assert cfg["base_url"] == "http://localhost:8003/api/v1"  # 未覆盖项保留默认


def test_env_overrides(tmp_path, monkeypatch):
    skill_dir, cwd = tmp_path / "skill", tmp_path / "cwd"
    skill_dir.mkdir(); cwd.mkdir()
    monkeypatch.setenv("AI4TALENT_API_KEY", "sk-123")
    monkeypatch.setenv("AI4TALENT_BASE_URL", "http://other:9000/api/v1")
    cfg = config.load_config(skill_dir, cwd)
    assert cfg["api_key"] == "sk-123"
    assert cfg["base_url"] == "http://other:9000/api/v1"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: talent_identifier.config`）

- [ ] **Step 4: 实现 config.py**

`talent-identifier/scripts/talent_identifier/config.py`:
```python
"""配置加载：默认值 < skill 模板 < cwd 配置 < 环境变量。"""
import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "base_url": "http://localhost:8003/api/v1",
    "api_key": "",
    "top_n": 20,
    "per_domain_limit": 50,
    "domains": ["academic", "open_source", "lab", "competition", "industry"],
    "exploration": {"max_searches": 6, "max_fetches": 4},
}


def load_config(skill_dir: Path, cwd: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg["exploration"] = dict(DEFAULT_CONFIG["exploration"])
    for path in (skill_dir / "ai4talent.config.json", cwd / "ai4talent.config.json"):
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            cfg.update(loaded)
            if "exploration" in loaded:
                cfg["exploration"] = {**DEFAULT_CONFIG["exploration"], **loaded["exploration"]}
    if os.environ.get("AI4TALENT_API_KEY"):
        cfg["api_key"] = os.environ["AI4TALENT_API_KEY"]
    if os.environ.get("AI4TALENT_BASE_URL"):
        cfg["base_url"] = os.environ["AI4TALENT_BASE_URL"]
    return cfg
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 项目骨架与 config 模块"
```

---

### Task 2: io_utils（run 目录 / JSONL / 断点状态）

**Files:**
- Create: `talent-identifier/scripts/talent_identifier/io_utils.py`
- Test: `talent-identifier/scripts/tests/test_io_utils.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_io_utils.py`:
```python
import json

from talent_identifier import io_utils


def test_slugify():
    assert io_utils.slugify("大模型推理优化") == "大模型推理优化"
    assert io_utils.slugify("LLM Inference & Serving!") == "llm-inference-serving"
    assert len(io_utils.slugify("a" * 100)) == 40


def test_new_run_dir(tmp_path):
    run_id, run_dir = io_utils.new_run_dir(tmp_path, "domain", "LLM 推理")
    assert run_id.startswith("domain-llm-推理-".replace("推理-", "")) or run_id.startswith("domain-")
    assert run_dir.is_dir() and run_dir.parent == tmp_path
    rid2, _ = io_utils.new_run_dir(tmp_path, "names", None)
    assert rid2.startswith("names-")


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "x.jsonl"
    rows = [{"a": 1}, {"b": "中文"}]
    io_utils.write_jsonl(p, rows)
    assert io_utils.read_jsonl(p) == rows


def test_state_stages(tmp_path):
    io_utils.mark_stage(tmp_path, "fetch", run_id="r1", mode="domain")
    st = io_utils.load_state(tmp_path)
    assert st["run_id"] == "r1" and st["mode"] == "domain"
    assert st["stages_done"] == ["fetch"]
    io_utils.mark_stage(tmp_path, "score")
    io_utils.mark_stage(tmp_path, "fetch")  # 重复标记不重复追加
    assert io_utils.load_state(tmp_path)["stages_done"] == ["fetch", "score"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_io_utils.py -v`
Expected: FAIL（`ModuleNotFoundError`/`AttributeError`）

- [ ] **Step 3: 实现 io_utils.py**

`talent-identifier/scripts/talent_identifier/io_utils.py`:
```python
"""run 目录管理、JSONL 读写、断点状态。"""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ALLOWED = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, maxlen: int = 40) -> str:
    s = _ALLOWED.sub("-", (text or "").strip().lower()).strip("-")
    return s[:maxlen].rstrip("-") or uuid.uuid4().hex[:8]


def new_run_dir(output_root: Path, mode: str, topic: str | None) -> tuple[str, Path]:
    today = datetime.now().strftime("%Y%m%d")
    if mode == "domain":
        run_id = f"domain-{slugify(topic or 'untitled')}-{today}"
    else:
        hhmm = datetime.now().strftime("%H%M")
        run_id = f"names-{today}-{hhmm}"
    run_dir = output_root / run_id
    n = 2
    while run_dir.exists():  # 同日同主题多次运行
        run_dir = output_root / f"{run_id}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    return run_dir.name, run_dir


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_state(run_dir: Path) -> dict:
    p = run_dir / "_state.json"
    if not p.exists():
        return {"run_id": run_dir.name, "mode": "domain", "stages_done": []}
    return json.loads(p.read_text(encoding="utf-8"))


def mark_stage(run_dir: Path, stage: str, run_id: str | None = None, mode: str | None = None) -> None:
    st = load_state(run_dir)
    if run_id:
        st["run_id"] = run_id
    if mode:
        st["mode"] = mode
    if stage not in st["stages_done"]:
        st["stages_done"].append(stage)
    (run_dir / "_state.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_io_utils.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): io_utils（run目录/JSONL/断点状态）"
```

---

### Task 3: normalize（姓名/机构/URL 规范化）

**Files:**
- Create: `talent-identifier/scripts/talent_identifier/normalize.py`
- Test: `talent-identifier/scripts/tests/test_normalize.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_normalize.py`:
```python
from talent_identifier import normalize


def test_normalize_name():
    assert normalize.normalize_name("Andrew Y. Ng") == "andrewyng"
    assert normalize.normalize_name("吴翼") == "吴翼"
    assert normalize.normalize_name("  Yi-Wu ") == "yiwu"
    assert normalize.normalize_name(None) == ""


def test_normalize_org():
    assert normalize.normalize_org("DeepMind Inc.") == "deepmind"
    assert normalize.normalize_org("Tsinghua University") == "tsinghua"
    assert normalize.normalize_org("清华大学") == "清华"
    assert normalize.normalize_org("Meta Platforms, Inc.") == "meta platforms"
    assert normalize.normalize_org("") == ""


def test_normalize_url():
    assert normalize.normalize_url("https://www.YiWu.ai/") == "yiwu.ai"
    assert normalize.normalize_url("http://github.com/foo") == "github.com/foo"
    assert normalize.normalize_url("") == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_normalize.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 normalize.py**

`talent-identifier/scripts/talent_identifier/normalize.py`:
```python
"""身份关联用的规范化函数。"""
import re

_PUNCT = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")
_ORG_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "lp", "corp", "corporation",
    "co", "company", "holdings", "university", "univ", "college",
    "大学", "学院", "公司", "研究院",
}


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    return _PUNCT.sub("", s.lower())


def normalize_org(s: str | None) -> str:
    if not s:
        return ""
    tokens = _PUNCT.sub(" ", s.lower()).split()
    while tokens and tokens[-1] in _ORG_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_url(u: str | None) -> str:
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_normalize.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 姓名机构URL规范化"
```

---

### Task 4: api_client（Open API 客户端）

**Files:**
- Create: `talent-identifier/scripts/talent_identifier/api_client.py`
- Test: `talent-identifier/scripts/tests/test_api_client.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_api_client.py`:
```python
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
    import httpx
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_api_client.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 api_client.py**

`talent-identifier/scripts/talent_identifier/api_client.py`:
```python
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
            if isinstance(val, dict) and isinstance(val.get("items"), list):
                items += [dict(it, domain=key) for it in val["items"]]
            elif isinstance(val, list):
                items += [dict(it, domain=key) for it in val]
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
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_api_client.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): Open API 客户端（重试/分页/跨域搜索）"
```

---

### Task 5: linking（跨域身份关联）

**Files:**
- Create: `talent-identifier/scripts/talent_identifier/linking.py`
- Test: `talent-identifier/scripts/tests/test_linking.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_linking.py`:
```python
from talent_identifier import linking


def _rec(domain, **kw):
    base = {"name": kw.get("name", "Yi Wu"), "domain": domain}
    base.update({k: v for k, v in kw.items() if k != "name"})
    return base


def test_high_confidence_merge_on_github():
    records = [
        _rec("open_source", github_login="yiwu", name="Yi Wu"),
        _rec("academic", name="Yi Wu", homepage="https://yiwu.ai", email="a@b.c"),
        _rec("lab", name="Wu Yi", social_links={"github": "https://github.com/yiwu"}),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert set(profiles[0]["linked_domains"]) == {"open_source", "academic", "lab"}
    assert any(e["confidence"] == "high" for e in profiles[0]["link_evidence"])


def test_medium_confidence_merge_on_name_plus_org():
    records = [
        _rec("academic", name="Andrew Ng", education_school="Stanford University"),
        _rec("industry", name="Andrew Ng", current_org="Stanford"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert profiles[0]["link_evidence"][0]["confidence"] == "medium"
    assert "name+org" == profiles[0]["link_evidence"][0]["field"]


def test_no_merge_same_name_different_org():
    records = [
        _rec("academic", name="Wei Li", education_school="Tsinghua University"),
        _rec("open_source", name="Wei Li", company="Alibaba"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    # 名字相同 + 无 org 重叠 → 不产生疑似提示（tags 也无重叠）
    assert all(not p.get("suspected_same_person") for p in profiles)


def test_low_hint_only_when_tags_overlap():
    records = [
        _rec("academic", name="Wei Li", education_school="Tsinghua", topic_tags=["llm", "rl"]),
        _rec("open_source", name="Wei Li", company="Startup", tech_tags="llm, cuda"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    hinted = [p for p in profiles if p.get("suspected_same_person")]
    assert len(hinted) == 2
    assert hinted[0]["suspected_same_person"][0]["basis"] == "name+tags"


def test_same_domain_records_never_merge():
    records = [
        _rec("academic", name="Yi Wu", education_school="A"),
        _rec("academic", name="Yi Wu", education_school="B"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2


def test_person_id_collision_suffix():
    records = [
        _rec("academic", name="Yi Wu", education_school="A"),
        _rec("open_source", name="Yi Wu", company="B"),
    ]
    profiles = linking.link_records(records)
    ids = sorted(p["person_id"] for p in profiles)
    assert ids[0].startswith("p_")
    assert ids[0] != ids[1]  # 冲突时追加序号区分


def test_tags_flatten():
    r = linking._record_identity({"name": "X", "topic_tags": ["LLM", "RL"],
                                  "research_areas": "llm, agents"}, "lab")
    assert "llm" in r["tags"] and "rl" in r["tags"] and "agents" in r["tags"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_linking.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 linking.py**

`talent-identifier/scripts/talent_identifier/linking.py`:
```python
"""跨域身份关联：DSU 合并 + high/medium/low 三档置信度。

规则（设计文档 §7）：
- high   ：homepage / github / orcid / email 任一相同 → 合并
- medium ：规范化名字相同 + 规范化机构相同 → 合并
- low    ：仅名字相同 + 标签重叠(Jaccard>0.2) → 不合并，仅 suspected_same_person 提示
- 同域两条记录永不合并
"""
import hashlib

from .normalize import normalize_name, normalize_org, normalize_url

STRONG_KEYS = ("homepage", "github", "orcid", "email")
DOMAIN_PRIORITY = ("academic", "lab", "open_source", "competition", "industry")


def _first_social_github(social) -> str:
    if isinstance(social, list):
        values = [str(v) for v in social]
    elif isinstance(social, dict):
        values = [str(v) for v in social.values()]
    else:
        return ""
    for v in values:
        if "github.com/" in v:
            login = v.split("github.com/")[1].split("/")[0]
            return f"https://github.com/{login}"
    return ""


def _flatten_tags(item: dict) -> set[str]:
    tags: set[str] = set()
    for key in ("topic_tags", "tech_tags", "research_areas"):
        val = item.get(key)
        if isinstance(val, list):
            tags |= {normalize_name(v) for v in val if normalize_name(v)}
        elif isinstance(val, str):
            tags |= {normalize_name(v) for v in val.replace("，", ",").split(",") if normalize_name(v)}
    return tags


def _record_identity(item: dict, domain: str) -> dict:
    github = item.get("github_login") or item.get("github") or ""
    if not github:
        github = _first_social_github(item.get("social_links"))
    org = (item.get("education_school") or item.get("company_school")
           or item.get("school") or item.get("current_org")
           or item.get("company") or item.get("lab_name") or "")
    return {
        "name": normalize_name(item.get("name_en") or item.get("name") or ""),
        "cn_name": normalize_name(item.get("name") or ""),
        "homepage": normalize_url(item.get("homepage") or ""),
        "github": normalize_url(github),
        "orcid": (item.get("orcid") or "").lower().strip(),
        "email": (item.get("email") or "").lower().strip(),
        "org": normalize_org(str(org)),
        "tags": _flatten_tags(item),
    }


class _DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def link_records(records: list[dict]) -> list[dict]:
    """records: [{domain, item}] → 统一画像列表。"""
    n = len(records)
    ids = [_record_identity(r["item"], r["domain"]) for r in records]
    dsu = _DSU(n)
    evidence: dict[tuple[int, int], dict] = {}
    low_pairs: list[tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            if records[i]["domain"] == records[j]["domain"]:
                continue
            a, b = ids[i], ids[j]
            strong = next((k for k in STRONG_KEYS
                           if a[k] and a[k] == b[k]), None)
            if strong:
                dsu.union(i, j)
                evidence[(i, j)] = {"field": strong, "value": a[strong], "confidence": "high"}
                continue
            names_equal = (a["name"] and a["name"] == b["name"]) or \
                          (a["cn_name"] and a["cn_name"] == b["cn_name"])
            if names_equal and a["org"] and a["org"] == b["org"]:
                dsu.union(i, j)
                evidence[(i, j)] = {"field": "name+org",
                                    "value": f'{a["name"] or a["cn_name"]}@{a["org"]}',
                                    "confidence": "medium"}
                continue
            if names_equal and a["tags"] and b["tags"]:
                jac = len(a["tags"] & b["tags"]) / len(a["tags"] | b["tags"])
                if jac > 0.2:
                    low_pairs.append((i, j))

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(dsu.find(idx), []).append(idx)

    profiles = []
    for members in groups.values():
        members.sort(key=lambda i: DOMAIN_PRIORITY.index(records[i]["domain"])
                     if records[i]["domain"] in DOMAIN_PRIORITY else 99)
        lead = members[0]
        lead_item = records[lead]["item"]
        profile = {
            "name": lead_item.get("name") or lead_item.get("name_en") or "",
            "name_en": lead_item.get("name_en") or "",
            "records": {records[m]["domain"]: records[m]["item"] for m in members},
            "linked_domains": [records[m]["domain"] for m in members],
            "link_evidence": [evidence[(min(i, j), max(i, j))]
                              for i in members for j in members
                              if (min(i, j), max(i, j)) in evidence],
            "suspected_same_person": [],
        }
        ident = ids[lead]
        profile["org"] = next((ids[m]["org"] for m in members if ids[m]["org"]), "")
        profile["homepage"] = ident["homepage"]
        profile["github"] = ident["github"]
        profile["orcid"] = ident["orcid"]
        profile["email"] = ident["email"]
        profile["tags"] = sorted({t for m in members for t in ids[m]["tags"]})
        profiles.append(profile)

    # person_id：规范化姓名哈希；冲突追加序号
    seen: dict[str, int] = {}
    for p in profiles:
        key = normalize_name(p["name_en"] or p["name"])
        base = "p_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
        seen[base] = seen.get(base, 0) + 1
        p["person_id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"

    by_member = {}
    for gi, members in enumerate(groups.values()):
        for m in members:
            by_member[m] = profiles[gi]
    for i, j in low_pairs:
        if dsu.find(i) != dsu.find(j):
            by_member[i].setdefault("suspected_same_person", []).append(
                {"person_id": by_member[j]["person_id"], "basis": "name+tags"})
            by_member[j].setdefault("suspected_same_person", []).append(
                {"person_id": by_member[i]["person_id"], "basis": "name+tags"})

    return profiles
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_linking.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 跨域身份关联（DSU+三档置信度）"
```

---

### Task 6: scoring（T-score 评分模型）

**Files:**
- Create: `talent-identifier/scripts/talent_identifier/scoring.py`
- Test: `talent-identifier/scripts/tests/test_scoring.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_scoring.py`:
```python
from talent_identifier import scoring


def _prof(pid, name, **domains):
    return {"person_id": pid, "name": name,
            "records": domains, "linked_domains": list(domains)}


def test_lognorm_bounds_and_flat():
    assert scoring._lognorm([0, 0]) == [0.5, 0.5]
    out = scoring._lognorm([0, 10, 100])
    assert out[0] == 0.0 and out[2] == 1.0 and 0 < out[1] < 1


def test_academic_weights_sum_to_one():
    comps = scoring.ACADEMIC_WEIGHTS
    assert abs(sum(comps.values()) - 1.0) < 1e-9


def test_single_domain_tscore_equals_subscore():
    profs = [_prof("p1", "A", academic={"h_index": 50, "cited_by_count": 10000,
                                        "works_count": 100, "latest_active_year": 2026}),
             _prof("p2", "B", academic={"h_index": 5, "cited_by_count": 100,
                                        "works_count": 10, "latest_active_year": 2020})]
    rows = scoring.compute_scores(profs)
    assert rows[0]["t_score"] == rows[0]["domain_scores"]["academic"]
    assert rows[0]["rank"] == 1 and rows[0]["person_id"] == "p1"


def test_cross_domain_bonus_and_cap():
    profs = [_prof("p1", "A",
                   academic={"h_index": 50, "cited_by_count": 9999, "works_count": 50,
                             "latest_active_year": 2026},
                   open_source={"total_stars_received": 50000, "followers_count": 5000,
                                "primary_languages": ["Python", "C++", "Rust", "Go"]}),
             _prof("p2", "B", academic={"h_index": 10, "cited_by_count": 100,
                                        "works_count": 5, "latest_active_year": 2026})]
    rows = scoring.compute_scores(profs)
    p1 = rows[0]
    expected = min(100.0, 0.7 * max(p1["domain_scores"].values())
                   + 0.3 * (sum(p1["domain_scores"].values()) - max(p1["domain_scores"].values()))
                   + 5)
    assert p1["t_score"] == round(expected, 1)


def test_no_metrics_null_and_ranked_last():
    profs = [_prof("p1", "A", academic={"h_index": 10, "cited_by_count": 100,
                                        "works_count": 5, "latest_active_year": 2026}),
             _prof("p2", "B", industry={"current_org": "Acme", "current_title": "Engineer"})]
    rows = scoring.compute_scores(profs)
    null_row = next(r for r in rows if r["person_id"] == "p2")
    assert null_row["t_score"] is None
    assert rows[-1]["person_id"] == "p2"


def test_lab_role_and_prestige():
    assert scoring._role_weight("Faculty", "") == 1.0
    assert scoring._role_weight("PhD Students", "") == 0.3
    assert scoring._lab_prestige("OpenAI") == 1.0
    assert scoring._lab_prestige("北京智源人工智能研究院") == 0.85
    assert scoring._lab_prestige("Somewhere Lab") == 0.7


def test_rank_title_scores():
    assert scoring._rank_title_score("Legendary Grandmaster") == 1.0
    assert scoring._rank_title_score("master") == 0.7
    assert scoring._rank_title_score("newbie") == 0.2
    assert scoring._rank_title_score(None) == 0.3  # 缺失保守值


def test_industry_renormalize_without_match_score():
    w = scoring._industry_weights(has_match=False)
    assert abs(sum(w.values()) - 1.0) < 1e-9
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 scoring.py**

`talent-identifier/scripts/talent_identifier/scoring.py`:
```python
"""T-score 评分模型（设计文档 §6）：候选集内归一化，各域子分 0-100。"""
import math
from datetime import datetime

ACADEMIC_WEIGHTS = {"h_index": 0.35, "cited_by": 0.35, "works": 0.15, "activity": 0.15}
OS_WEIGHTS = {"stars": 0.45, "followers": 0.35, "breadth": 0.20}
COMP_WEIGHTS = {"rating": 0.60, "rank_title": 0.25, "medals": 0.15}

ROLE_RULES = [("faculty", 1.0), ("professor", 1.0), ("research scientist", 0.8),
              ("researcher", 0.8), ("postdoc", 0.6), ("alumni", 0.5),
              ("phd", 0.3), ("student", 0.3)]
LAB_PRESTIGE = [("stanford ai lab", 1.0), ("mit csail", 1.0), ("csail", 1.0),
                ("deepmind", 1.0), ("fair", 1.0), ("meta ai", 1.0), ("openai", 1.0),
                ("anthropic", 1.0), ("microsoft research", 1.0), ("msr", 1.0), ("bair", 1.0),
                ("智源", 0.85), ("tsinghua", 0.85), ("清华", 0.85)]
RANK_TITLE_SCORES = [("legendary", 1.0), ("international grandmaster", 0.95),
                     ("grandmaster", 0.9), ("international master", 0.8),
                     ("candidate master", 0.6), ("master", 0.7), ("expert", 0.5),
                     ("specialist", 0.4), ("pupil", 0.3), ("newbie", 0.2)]
TITLE_RULES = [("distinguished", 1.0), ("fellow", 1.0), ("chief", 0.9),
               ("principal", 0.95), ("staff", 0.85), ("lead", 0.75),
               ("senior", 0.7), ("junior", 0.3)]
ORG_PRESTIGE = [("openai", 1.0), ("anthropic", 1.0), ("deepmind", 1.0), ("google", 1.0),
                ("meta", 1.0), ("microsoft", 1.0), ("nvidia", 1.0), ("bytedance", 0.95),
                ("字节", 0.95), ("alibaba", 0.9), ("阿里", 0.9), ("tencent", 0.9),
                ("腾讯", 0.9), ("huawei", 0.9), ("华为", 0.9), ("baidu", 0.85), ("百度", 0.85)]


def _lognorm(values: list[float]) -> list[float]:
    vals = [math.log(v + 1) for v in values]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


def _first_match(rules, text, default):
    s = (text or "").lower()
    for key, w in rules:
        if key in s:
            return w
    return default


def _role_weight(role_section, role_type):
    return _first_match(ROLE_RULES, f"{role_section} {role_type}", 0.6)


def _lab_prestige(lab_name):
    return _first_match(LAB_PRESTIGE, str(lab_name or ""), 0.7)


def _rank_title_score(rank_title):
    return _first_match(RANK_TITLE_SCORES, rank_title, 0.3)


def _title_weight(title):
    return _first_match(TITLE_RULES, str(title or ""), 0.5)


def _org_prestige(org):
    return _first_match(ORG_PRESTIGE, str(org or ""), 0.6)


def _activity(year):
    if not year:
        return 0.3
    lag = max(0, datetime.now().year - int(year))
    return max(0.0, 1.0 - lag / 5.0)


def _industry_weights(has_match: bool):
    if has_match:
        return {"org": 0.5, "title": 0.3, "match": 0.2}
    return {"org": 0.625, "title": 0.375, "match": 0.0}


def score_academic(profiles):
    rows = [p for p in profiles if "academic" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["academic"] for p in rows]
    h = _lognorm([it.get("h_index") or 0 for it in items])
    c = _lognorm([it.get("cited_by_count") or 0 for it in items])
    w = _lognorm([it.get("works_count") or 0 for it in items])
    out = {}
    for i, p in enumerate(rows):
        comps = {"h_index": h[i], "cited_by": c[i], "works": w[i],
                 "activity": _activity(items[i].get("latest_active_year"))}
        out[p["person_id"]] = {"sub": 100 * sum(
            ACADEMIC_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_open_source(profiles):
    rows = [p for p in profiles if "open_source" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["open_source"] for p in rows]
    stars = _lognorm([it.get("total_stars_received") or 0 for it in items])
    foll = _lognorm([it.get("followers_count") or 0 for it in items])
    langs = [it.get("primary_languages") or [] for it in items]
    breadth = _lognorm([len(l) for l in langs])
    out = {}
    for i, p in enumerate(rows):
        comps = {"stars": stars[i], "followers": foll[i], "breadth": breadth[i]}
        out[p["person_id"]] = {"sub": 100 * sum(
            OS_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_lab(profiles):
    out = {}
    for p in profiles:
        it = p["records"].get("lab")
        if not it:
            continue
        rw = _role_weight(it.get("role_section"), it.get("role_type"))
        pr = _lab_prestige(it.get("lab_name") or it.get("parent_lab"))
        comps = {"role_weight": rw, "lab_prestige": pr}
        out[p["person_id"]] = {"sub": 100 * rw * pr, "components": comps}
    return out


def score_competition(profiles):
    rows = [p for p in profiles if "competition" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["competition"] for p in rows]
    rating = _lognorm([it.get("max_rating") or it.get("current_rating") or 0 for it in items])
    medals = _lognorm([(it.get("medals_gold") or 0) * 3 + (it.get("medals_silver") or 0) * 2
                       + (it.get("medals_bronze") or 0) for it in items])
    out = {}
    for i, p in enumerate(rows):
        rt = _rank_title_score(items[i].get("rank_title"))
        comps = {"rating": rating[i], "rank_title": rt, "medals": medals[i]}
        out[p["person_id"]] = {"sub": 100 * sum(
            COMP_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_industry(profiles):
    rows = [p for p in profiles if "industry" in p["records"]]
    if not rows:
        return {}
    out = {}
    for p in rows:
        it = p["records"]["industry"]
        has_match = it.get("match_score") is not None
        wts = _industry_weights(has_match)
        comps = {"org": _org_prestige(it.get("current_org")),
                 "title": _title_weight(it.get("current_title")),
                 "match": (it.get("match_score") or 0) / 100.0 if has_match else 0.0}
        out[p["person_id"]] = {"sub": 100 * sum(wts[k] * comps[k] for k in comps),
                               "components": comps}
    return out


def compute_scores(profiles: list[dict]) -> list[dict]:
    """profiles → 按序榜单行（t_score 降序、null 尾置、rank 1..n）。"""
    per_domain = {"academic": score_academic(profiles),
                  "open_source": score_open_source(profiles),
                  "lab": score_lab(profiles),
                  "competition": score_competition(profiles),
                  "industry": score_industry(profiles)}
    rows = []
    for p in profiles:
        domain_scores, components = {}, {}
        for dom, table in per_domain.items():
            if p["person_id"] in table:
                domain_scores[dom] = round(table[p["person_id"]]["sub"], 1)
                components[dom] = {k: round(v, 3) for k, v
                                   in table[p["person_id"]]["components"].items()}
        if domain_scores:
            subs = list(domain_scores.values())
            if len(subs) == 1:
                t = subs[0]
            else:
                top = max(subs)
                rest_mean = (sum(subs) - top) / (len(subs) - 1)
                t = min(100.0, 0.7 * top + 0.3 * rest_mean + min(10, 5 * (len(subs) - 1)))
            t_score = round(t, 1)
        else:
            t_score = None
        rows.append({"person_id": p["person_id"], "name": p.get("name") or "",
                     "t_score": t_score, "domain_scores": domain_scores,
                     "score_components": components,
                     "linked_domains": p.get("linked_domains", [])})
    rows.sort(key=lambda r: (r["t_score"] is None, -(r["t_score"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_scoring.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): T-score 评分模型（五域+融合）"
```

---

### Task 7: fetch_profiles.py（阶段1 CLI，两模式）

**Files:**
- Create: `talent-identifier/scripts/fetch_profiles.py`
- Test: `talent-identifier/scripts/tests/test_fetch_offline.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_fetch_offline.py`（用例中两条 Yi Wu 记录机构相同，验证 medium 合并）：
```python
import json

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
    client = FakeClient(domain_items={
        "academic": [{"name": "A", "education_school": "X", "topic_tags": ["rl"]},
                     {"name": "B", "education_school": "X", "topic_tags": ["cv"]}],
    })
    # keyword 参数会被传入；FakeClient 不做服务端过滤，fetch 侧兜底过滤应剔除 B
    class PickyClient(FakeClient):
        def list_domain(self, domain, params, limit):
            if params.get("keyword") == "rl":
                raise fetch_profiles.api_client.ApiUnreachable("400 simulated")
            return self.domain_items.get(domain, [])[:limit]
    rc = fetch_profiles.main(
        ["--mode", "domain", "--keyword", "rl", "--out", str(tmp_path)], client=PickyClient())
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_fetch_offline.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'fetch_profiles'`——conftest 只加了 scripts/ 的父目录到 path，还需把 scripts/ 本身加进去）

- [ ] **Step 3: 更新 conftest.py 让入口脚本可导入**

`talent-identifier/scripts/tests/conftest.py` 改为：
```python
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))              # 导入 fetch_profiles 等入口脚本
sys.path.insert(0, str(SCRIPTS.parent / "scripts"))  # 兜底
```
说明：`parents[1]` 即 `scripts/`，第一行已够；第二行幂等无害。

- [ ] **Step 4: 实现 fetch_profiles.py**

`talent-identifier/scripts/fetch_profiles.py`:
```python
#!/usr/bin/env python3
"""阶段1：从 AI4TALENT Open API 拉取候选人才并做跨域关联，产出 profiles.jsonl。

用法:
  python scripts/fetch_profiles.py --mode domain --keyword "大模型推理优化" [--domains academic,lab]
  python scripts/fetch_profiles.py --mode names --names "张三,李四" | --names-file names.txt
选项: --out <dir>(默认 ./output)  --resume(跳过已完成阶段)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from talent_identifier import api_client, config, io_utils, linking
from talent_identifier.normalize import normalize_name


def _make_person_id(name: str) -> str:
    return "p_" + hashlib.sha256(normalize_name(name).encode("utf-8")).hexdigest()[:8]


def _client_side_filter(items: list[dict], keyword: str) -> list[dict]:
    kw = keyword.lower()
    return [it for it in items
            if kw in json.dumps(it, ensure_ascii=False).lower()]


def _fetch_domain(client, domain: str, keyword: str, limit: int):
    """带兜底：keyword 参数被拒(4xx 转(ApiUnreachable))时，拉全量后本地过滤。"""
    try:
        return client.list_domain(domain, {"keyword": keyword}, limit), None
    except api_client.ApiUnreachable:
        items = client.list_domain(domain, {}, limit)
        return _client_side_filter(items, keyword), None
    except Exception as e:  # 单域失败不阻塞
        return [], str(e)


def _name_matches(query_norm: str, item: dict) -> bool:
    for key in ("name", "name_en"):
        n = normalize_name(item.get(key))
        if n and (n == query_norm or n in query_norm or query_norm in n):
            return True
    return False


def _finalize(profiles: list[dict], run_dir: Path, mode: str) -> None:
    for p in profiles:
        p["in_library"] = bool(p.get("records"))
        p["contact_info_unavailable"] = not (
            p.get("homepage") or p.get("github") or p.get("email")
            or (p.get("records", {}).get("lab", {}) or {}).get("social_links"))
        p["collected_at"] = io_utils.utc_now()
        if not p.get("suspected_same_person"):
            p.pop("suspected_same_person", None)
    io_utils.write_jsonl(run_dir / "profiles.jsonl", profiles)
    io_utils.mark_stage(run_dir, "fetch", run_id=run_dir.name, mode=mode)


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["domain", "names"], required=True)
    ap.add_argument("--keyword")
    ap.add_argument("--domains", help="逗号分隔，默认全部五域")
    ap.add_argument("--names")
    ap.add_argument("--names-file")
    ap.add_argument("--out", default="output")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)

    skill_dir = Path(__file__).resolve().parent.parent
    cfg = config.load_config(skill_dir, Path.cwd())
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else cfg["domains"]

    if args.mode == "domain" and not args.keyword:
        print("ERROR: --mode domain 需要 --keyword", file=sys.stderr)
        return 1
    names = []
    if args.mode == "names":
        if args.names_file:
            names = [l.strip() for l in
                     Path(args.names_file).read_text(encoding="utf-8").splitlines() if l.strip()]
        elif args.names:
            names = [n.strip() for n in args.names.split(",") if n.strip()]
        if not names:
            print("ERROR: --mode names 需要 --names 或 --names-file", file=sys.stderr)
            return 1

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    if args.resume:
        candidates = sorted([d for d in out_root.iterdir() if d.is_dir()], reverse=True)
        run_dir = next((d for d in candidates
                        if "fetch" in io_utils.load_state(d)["stages_done"]), None)
        if run_dir:
            print(f"[resume] 跳过 fetch：{run_dir}")
            return 0
    run_id, run_dir = io_utils.new_run_dir(out_root, args.mode,
                                           args.keyword if args.mode == "domain" else None)

    if client is None:
        client = api_client.OpenApiClient(cfg["base_url"], cfg["api_key"])
    if not client.health():
        print(f"ERROR: AI4TALENT 后端不可达（{cfg['base_url']}）。"
              f"请先启动后端，或用 AI4TALENT_BASE_URL 指定地址。", file=sys.stderr)
        return 2

    gaps: list[str] = []
    records: list[dict] = []
    if args.mode == "domain":
        for domain in domains:
            items, err = _fetch_domain(client, domain, args.keyword, cfg["per_domain_limit"])
            if err:
                gaps.append(domain)
                print(f"[gap] {domain}: {err}", file=sys.stderr)
            records += [{"domain": domain, "item": it} for it in items]
        profiles = linking.link_records(records)
    else:
        profiles = []
        for name in names:
            try:
                found = [it for it in client.cross_search(name, domains)
                         if _name_matches(normalize_name(name), it)]
            except Exception as e:
                print(f"[gap] 跨域搜索失败: {name}: {e}", file=sys.stderr)
                found = []
            if found:
                profiles += linking.link_records(
                    [{"domain": it.get("domain", "unknown"), "item": it} for it in found])
            else:
                profiles.append({"person_id": _make_person_id(name), "name": name,
                                 "name_en": "", "records": {}, "linked_domains": [],
                                 "link_evidence": [], "org": "", "homepage": "",
                                 "github": "", "orcid": "", "email": "", "tags": []})

    if gaps:
        (run_dir / "gaps.txt").write_text("\n".join(gaps) + "\n", encoding="utf-8")
    _finalize(profiles, run_dir, args.mode)
    linked = sum(1 for p in profiles if len(p.get("linked_domains", [])) > 1)
    print(f"[fetch] run={run_id} 人数={len(profiles)} 跨域合并={linked} 缺口域={gaps or '无'}")
    print(f"[fetch] 产物: {run_dir / 'profiles.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_fetch_offline.py -v`
Expected: 5 passed

- [ ] **Step 6: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 阶段1 fetch_profiles CLI（两模式+兜底过滤+缺口记录）"
```

---

### Task 8: compute_scores.py（阶段2 CLI）

**Files:**
- Create: `talent-identifier/scripts/compute_scores.py`
- Test: `talent-identifier/scripts/tests/test_compute_offline.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_compute_offline.py`:
```python
import json

import compute_scores


def test_compute_writes_sorted_scores(tmp_path):
    run_dir = tmp_path / "domain-x-20260829"
    run_dir.mkdir()
    (run_dir / "profiles.jsonl").write_text(
        '{"person_id":"p1","name":"A","records":{"academic":{"h_index":50,'
        '"cited_by_count":9000,"works_count":60,"latest_active_year":2026}},'
        '"linked_domains":["academic"]}\n'
        '{"person_id":"p2","name":"B","records":{"academic":{"h_index":3,'
        '"cited_by_count":30,"works_count":4,"latest_active_year":2024}},'
        '"linked_domains":["academic"]}\n', encoding="utf-8")
    rc = compute_scores.main(["--run", str(run_dir)])
    assert rc == 0
    rows = [json.loads(l) for l in
            (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["person_id"] == "p1"
    state = json.loads((run_dir / "_state.json").read_text(encoding="utf-8"))
    assert "score" in state["stages_done"]


def test_missing_profiles_error(tmp_path, capsys):
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    rc = compute_scores.main(["--run", str(run_dir)])
    assert rc == 1
    assert "profiles.jsonl" in capsys.readouterr().err
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_compute_offline.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 compute_scores.py**

`talent-identifier/scripts/compute_scores.py`:
```python
#!/usr/bin/env python3
"""阶段2：读取 profiles.jsonl，计算 T-score 榜单，产出 scores.jsonl。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from talent_identifier import io_utils, scoring


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="run 目录路径")
    args = ap.parse_args(argv)

    run_dir = Path(args.run)
    profiles = io_utils.read_jsonl(run_dir / "profiles.jsonl")
    if not profiles:
        print(f"ERROR: {run_dir / 'profiles.jsonl'} 不存在或为空，先跑 fetch_profiles",
              file=sys.stderr)
        return 1

    rows = scoring.compute_scores(profiles)
    io_utils.write_jsonl(run_dir / "scores.jsonl", rows)
    io_utils.mark_stage(run_dir, "score")

    print(f"[score] 榜单 {len(rows)} 人")
    for r in rows[:10]:
        t = r["t_score"] if r["t_score"] is not None else "N/A"
        print(f"  #{r['rank']:>3} {t:>5}  {r['name']}  [{','.join(r['linked_domains'])}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_compute_offline.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 阶段2 compute_scores CLI"
```

---

### Task 9: render_report.py — Markdown 报告

**Files:**
- Create: `talent-identifier/scripts/render_report.py`（本 Task 实现 md 部分 + main 骨架）
- Test: `talent-identifier/scripts/tests/test_render_offline.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_render_offline.py`:
```python
import json

import render_report


def _make_run(tmp_path):
    run_dir = tmp_path / "domain-agent-20260829"
    run_dir.mkdir()
    (run_dir / "profiles.jsonl").write_text(
        '{"person_id":"p1","name":"Alice","name_en":"Alice A","org":"MIT",'
        '"records":{"academic":{"h_index":40,"cited_by_count":5000}},'
        '"linked_domains":["academic"],"link_evidence":[],"tags":["rl"],'
        '"in_library":true,"collected_at":"2026-08-29T00:00:00+00:00"}\n', encoding="utf-8")
    (run_dir / "scores.jsonl").write_text(
        '{"person_id":"p1","name":"Alice","rank":1,"t_score":82.3,'
        '"domain_scores":{"academic":82.3},"score_components":{},'
        '"linked_domains":["academic"]}\n', encoding="utf-8")
    (run_dir / "enrichment.jsonl").write_text(
        '{"person_id":"p1","kind":"award","title":"Best Paper","date":"2026-06",'
        '"source_url":"https://x.example/a","evidence_level":"high",'
        '"summary":"获奖","collected_at":"2026-08-29T00:00:00+00:00"}\n', encoding="utf-8")
    enr = run_dir / "enrichment"
    enr.mkdir()
    (enr / "p1.md").write_text("### 定性洞察\n上升趋势。", encoding="utf-8")
    return run_dir


def test_render_domain_markdown(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "执行摘要" in md and "榜单总表" in md
    assert "#1" in md or "1." in md
    assert "Alice" in md and "82.3" in md
    assert "https://x.example/a" in md          # 动态必须带来源
    assert "上升趋势" in md                     # insight md 内容并入
    assert "方法论" in md


def test_render_final_jsonl(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    finals = list((run_dir / "final").glob("talents_*.jsonl"))
    assert len(finals) == 1
    row = json.loads(finals[0].read_text(encoding="utf-8").splitlines()[0])
    assert row["person_id"] == "p1"
    assert row["dynamics"][0]["kind"] == "award"
    assert "insight_md" in row


def test_render_names_mode_per_person(tmp_path):
    run_dir = _make_run(tmp_path)
    st = json.loads((run_dir / "_state.json").read_text(encoding="utf-8"))
    st["mode"] = "names"
    (run_dir / "_state.json").write_text(json.dumps(st), encoding="utf-8")
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    reports = list(run_dir.glob("report_*.md"))
    assert len(reports) == 1 and "Alice" in reports[0].read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_render_offline.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 render_report.py（本 Task：数据装配 + Markdown；HTML 下一 Task 补）**

`talent-identifier/scripts/render_report.py`:
```python
#!/usr/bin/env python3
"""阶段4：装配画像/评分/动态，渲染 Markdown 报告 + HTML + final JSONL。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from talent_identifier import io_utils

KIND_CN = {"position_change": "职位变动", "paper": "论文", "project": "项目",
           "award": "获奖", "talk": "演讲", "blog": "博客", "social": "社媒"}
DOMAIN_CN = {"academic": "学术", "open_source": "开源", "lab": "实验室",
             "competition": "竞赛", "industry": "行业"}


def load_run(run_dir: Path) -> dict:
    profiles = {p["person_id"]: p for p in io_utils.read_jsonl(run_dir / "profiles.jsonl")}
    scores = io_utils.read_jsonl(run_dir / "scores.jsonl")
    dynamics: dict[str, list] = {}
    for d in io_utils.read_jsonl(run_dir / "enrichment.jsonl"):
        dynamics.setdefault(d["person_id"], []).append(d)
    insights = {}
    enr_dir = run_dir / "enrichment"
    if enr_dir.is_dir():
        for f in enr_dir.glob("*.md"):
            insights[f.stem] = f.read_text(encoding="utf-8")
    return {"profiles": profiles, "scores": scores,
            "dynamics": dynamics, "insights": insights}


def _key_metrics(rec: dict) -> str:
    bits = []
    if "h_index" in rec:
        bits.append(f"h-index {rec['h_index']}")
    if "cited_by_count" in rec:
        bits.append(f"引用 {rec['cited_by_count']}")
    if "total_stars_received" in rec:
        bits.append(f"stars {rec['total_stars_received']}")
    if "max_rating" in rec:
        bits.append(f"rating {rec['max_rating']}")
    if "current_title" in rec:
        bits.append(f"{rec.get('current_org', '')} {rec['current_title']}")
    return "；".join(bits)


def _person_section(row, data, top_label=True) -> str:
    p = data["profiles"].get(row["person_id"], {})
    lines = []
    head = f"### #{row['rank']} {row['name']}" if top_label else f"## {row['name']}"
    t = row["t_score"] if row["t_score"] is not None else "N/A"
    lines.append(f"{head}（T-score {t}）")
    doms = "、".join(DOMAIN_CN.get(d, d) for d in row["linked_domains"]) or "库外"
    lines.append(f"- 域：{doms}" + (f" ｜ 机构：{p['org']}" if p.get("org") else ""))
    for d, rec in p.get("records", {}).items():
        m = _key_metrics(rec)
        if m:
            lines.append(f"- {DOMAIN_CN.get(d, d)}：{m}")
    for ev in p.get("link_evidence", []):
        lines.append(f"- 跨域关联（{ev['confidence']}）：{ev['field']} = {ev['value']}")
    for s in p.get("suspected_same_person", []):
        lines.append(f"- ⚠️ 疑似与 {s['person_id']} 为同一人（{s['basis']}），未合并")
    dyn = data["dynamics"].get(row["person_id"], [])
    if dyn:
        lines.append("")
        lines.append("#### 最新动态（互联网补全）")
        for d in sorted(dyn, key=lambda x: x.get("date") or "", reverse=True):
            lines.append(f"- [{d.get('date', '?')}]（{KIND_CN.get(d['kind'], d['kind'])}）"
                         f"{d['title']} — {d.get('summary', '')}"
                         f"（证据 {d['evidence_level']}）[来源]({d['source_url']})")
    ins = data["insights"].get(row["person_id"])
    lines.append("")
    lines.append("#### 定性洞察")
    lines.append(ins if ins else "（本次未生成洞察）")
    return "\n".join(lines)


def render_markdown(run_dir: Path, data: dict, mode: str, keyword: str | None) -> list[Path]:
    scores = data["scores"]
    cross = [r for r in scores if len(r["linked_domains"]) > 1]
    n_dyn = sum(len(v) for v in data["dynamics"].values())
    gaps = ""
    if (run_dir / "gaps.txt").exists():
        gaps = (run_dir / "gaps.txt").read_text(encoding="utf-8").strip().replace("\n", "、")

    if mode == "names":
        outs = []
        for row in scores:
            md = [f"# 人才深度洞察：{row['name']}", "",
                  _person_section(row, data, top_label=False), "",
                  "---", "## 方法论", "- 数据：AI4TALENT Open API（采集时间见各画像 collected_at）"
                  "- 评分：T-score 候选集内归一化，口径见 skill references/scoring-model.md"
                  "- 关联：规则自动关联，置信度见正文；低置信仅提示不合并"]
            if gaps:
                md.append(f"- 数据缺口域：{gaps}")
            out = run_dir / f"report_{row['person_id']}.md"
            out.write_text("\n".join(md) + "\n", encoding="utf-8")
            outs.append(out)
        return outs

    md = [f"# 领域人才洞察报告：{keyword or ''}", "",
          "## 执行摘要",
          f"- 本次识别候选 {len(scores)} 人，其中跨域关联成功 {len(cross)} 人；"
          f"互联网补全动态 {n_dyn} 条。",
          "- 关键发现："]
    top3 = [r for r in scores if r["t_score"] is not None][:3]
    for r in top3:
        md.append(f"  - {r['name']} 以 T-score {r['t_score']} 居首"
                  f"（{('、'.join(DOMAIN_CN.get(d, d) for d in r['linked_domains']))}）")
    if n_dyn:
        md.append(f"  - 互联网补全捕捉到 {n_dyn} 条最新动态（含来源链接）")
    md += ["", "## 榜单总表", "",
           "| 排名 | 姓名 | T-score | 域 | 机构 |", "|---|---|---|---|---|"]
    for r in scores:
        doms = "、".join(DOMAIN_CN.get(d, d) for d in r["linked_domains"]) or "库外"
        org = data["profiles"].get(r["person_id"], {}).get("org", "")
        md.append(f"| {r['rank']} | {r['name']} | {r['t_score'] if r['t_score'] is not None else 'N/A'}"
                  f" | {doms} | {org} |")
    md += ["", f"## Top 榜单小传", ""]
    for row in scores[:20]:
        md.append(_person_section(row, data))
        md.append("")
    if cross:
        md += ["## 跨域人才专题", ""]
        for r in cross:
            evs = data["profiles"].get(r["person_id"], {}).get("link_evidence", [])
            md.append(f"- {r['name']}：{len(r['linked_domains'])} 域（"
                      + "；".join(f"{e['field']}({e['confidence']})" for e in evs) + "）")
        md.append("")
    md += ["---", "## 方法论附录",
           "- 数据来源：AI4TALENT Open API 五域人才库（采集时间见各画像 collected_at）",
           "- 评分口径：T-score 为本次候选集内归一化（log+min-max），仅本次榜单内可比；"
           "单域=域子分，跨域=0.7×最高+0.3×其余均值+广度加分(+5/域，上限+10)",
           "- 关联口径：high=标识字段相同；medium=名字+机构相同；low=仅提示不合并",
           "- 互联网动态均带来源链接与证据分级（high/medium/low）"]
    if gaps:
        md.append(f"- 数据缺口域：{gaps}（当次采集失败，已跳过）")
    out = run_dir / "report.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    return [out]


def render_final_jsonl(run_dir: Path, data: dict) -> Path:
    rows = []
    generated_at = io_utils.utc_now()
    for r in data["scores"]:
        p = data["profiles"].get(r["person_id"], {})
        row = {"person_id": r["person_id"], "name": r["name"],
               "name_en": p.get("name_en"), "org": p.get("org"),
               "in_library": p.get("in_library"),
               "linked_domains": r["linked_domains"], "t_score": r["t_score"],
               "rank": r["rank"], "domain_scores": r["domain_scores"],
               "score_components": r["score_components"],
               "link_evidence": p.get("link_evidence"),
               "dynamics": data["dynamics"].get(r["person_id"]),
               "insight_md": data["insights"].get(r["person_id"]),
               "run_id": run_dir.name, "generated_at": generated_at}
        rows.append({k: v for k, v in row.items()
                     if v not in (None, "", [], {})})
    out = run_dir / "final" / f"talents_{run_dir.name}.jsonl"
    io_utils.write_jsonl(out, rows)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args(argv)
    run_dir = Path(args.run)
    if not (run_dir / "scores.jsonl").exists():
        print(f"ERROR: {run_dir / 'scores.jsonl'} 不存在，先跑 compute_scores", file=sys.stderr)
        return 1
    data = load_run(run_dir)
    mode = io_utils.load_state(run_dir).get("mode", "domain")
    keyword = None
    if mode == "domain" and run_dir.name.startswith("domain-"):
        keyword = run_dir.name[len("domain-"):].rsplit("-", 1)[0]
    render_markdown(run_dir, data, mode, keyword)
    render_final_jsonl(run_dir, data)
    render_html(run_dir, data)  # Task 10 实现；本 Task 先占位 pass
    io_utils.mark_stage(run_dir, "render")
    print(f"[render] 报告已生成: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**本 Task 先提交占位的 render_html**（在文件末尾、main 之前加）：
```python
def render_html(run_dir: Path, data: dict) -> Path | None:
    return None  # Task 10 实现
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_render_offline.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 阶段4 Markdown 报告与 final JSONL"
```

---

### Task 10: render_report.py — HTML 可视化

**Files:**
- Modify: `talent-identifier/scripts/render_report.py`（实现 `render_html`）
- Test: `talent-identifier/scripts/tests/test_render_offline.py`（追加用例）

- [ ] **Step 1: 追加失败测试**

在 `talent-identifier/scripts/tests/test_render_offline.py` 末尾追加：
```python
def test_render_html(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "echarts" in html.lower()          # 内联或 CDN 二选一
    assert "Alice" in html
    assert '"scores"' in html or "DATA" in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_render_offline.py::test_render_html -v`
Expected: FAIL（report.html 不存在）

- [ ] **Step 3: 实现 render_html**

替换 `talent-identifier/scripts/render_report.py` 中的占位函数为：
```python
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{run_id} · 人才洞察</title>
{echarts_tag}
<style>
body{{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:24px;background:#f7f8fa;color:#1f2937}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card{{background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
th,td{{border:1px solid #e5e7eb;padding:6px 10px;text-align:left}}
th{{background:#f3f4f6}}
</style></head><body>
<h1>{run_id} · 人才洞察</h1>
<p>候选 {total} 人 ｜ 跨域 {cross} 人 ｜ 互联网动态 {dynamics} 条（生成于 {generated_at}）</p>
<div class="grid">
<div class="card" id="hist" style="height:320px"></div>
<div class="card" id="pie" style="height:320px"></div>
<div class="card" id="bar" style="height:460px;grid-column:1/3"></div>
<div class="card" id="radars" style="grid-column:1/3;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px"></div>
</div>
<h2>Top 榜单</h2>
<table><thead><tr><th>排名</th><th>姓名</th><th>T-score</th><th>域</th><th>机构</th></tr></thead>
<tbody>{rows}</tbody></table>
<script>
const DATA = {data_json};
function mk(id, opt) {{ const el = document.getElementById(id);
  if (!el || typeof echarts === 'undefined') return;
  const c = echarts.init(el); c.setOption(opt); }}
mk('hist', {{tooltip:{{}}, xAxis:{{type:'category',data:DATA.hist.labels}},
  yAxis:{{type:'value'}}, series:[{{type:'bar',data:DATA.hist.counts,
  itemStyle:{{color:'#6366f1'}}}}]}});
mk('pie', {{tooltip:{{}}, series:[{{type:'pie',radius:'65%',data:DATA.pie}}]}});
mk('bar', {{tooltip:{{}}, grid:{{left:120}},
  xAxis:{{type:'value',max:100}},
  yAxis:{{type:'category',data:DATA.bar.names.reverse()}},
  series:[{{type:'bar',data:DATA.bar.scores.reverse(),
  itemStyle:{{color:'#22c55e'}},label:{{show:true,position:'right'}}}}]}});
DATA.radars.forEach(function(r, i) {{
  const div = document.createElement('div');
  div.style.height = '300px'; div.id = 'radar' + i;
  document.getElementById('radars').appendChild(div);
  mk(div.id, {{title:{{text:r.name,left:'center',textStyle:{{fontSize:13}}}},
    tooltip:{{}}, radar:{{indicator:r.indicator,radius:'65%'}},
    series:[{{type:'radar',data:[{{value:r.values,name:r.name}}]}}]}});
}});
</script></body></html>"""


def render_html(run_dir: Path, data: dict) -> Path | None:
    scores = [r for r in data["scores"]]
    ts = [r["t_score"] for r in scores if r["t_score"] is not None]
    hist_labels, hist_counts = [], []
    if ts:
        lo, hi = 0, 100
        step = 10
        for b in range(lo, hi, step):
            hist_labels.append(f"{b}-{b + step}")
            hist_counts.append(sum(1 for t in ts if b <= t < b + step))
    pie_map: dict[str, int] = {}
    for r in scores:
        for d in r["linked_domains"]:
            pie_map[DOMAIN_CN.get(d, d)] = pie_map.get(DOMAIN_CN.get(d, d), 0) + 1
    top = [r for r in scores if r["t_score"] is not None][:15]
    radars = []
    for r in [x for x in scores if len(x["domain_scores"]) >= 3][:5]:
        radars.append({
            "name": r["name"],
            "indicator": [{"name": DOMAIN_CN.get(d, d), "max": 100}
                          for d in r["domain_scores"]],
            "values": list(r["domain_scores"].values())})
    rows_html = "".join(
        f"<tr><td>{r['rank']}</td><td>{r['name']}</td>"
        f"<td>{r['t_score'] if r['t_score'] is not None else 'N/A'}</td>"
        f"<td>{'、'.join(DOMAIN_CN.get(d, d) for d in r['linked_domains'])}</td>"
        f"<td>{data['profiles'].get(r['person_id'], {}).get('org', '')}</td></tr>"
        for r in scores)

    assets = Path(__file__).resolve().parent.parent / "assets" / "echarts.min.js"
    if assets.exists():
        echarts_tag = "<script>" + assets.read_text(encoding="utf-8") + "</script>"
    else:
        echarts_tag = ('<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/'
                       'echarts.min.js"></script>')

    payload = {"hist": {"labels": hist_labels, "counts": hist_counts},
               "pie": [{"name": k, "value": v} for k, v in pie_map.items()],
               "bar": {"names": [r["name"] for r in top],
                       "scores": [r["t_score"] for r in top]},
               "radars": radars}
    html = _HTML_TEMPLATE.format(
        run_id=run_dir.name, echarts_tag=echarts_tag,
        total=len(scores),
        cross=sum(1 for r in scores if len(r["linked_domains"]) > 1),
        dynamics=sum(len(v) for v in data["dynamics"].values()),
        generated_at=io_utils.utc_now(), rows=rows_html,
        data_json=json.dumps(payload, ensure_ascii=False))
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out
```

注意：模板中 CSS 花括号已用 `{{` `}}` 转义，`format` 只替换命名占位符。

- [ ] **Step 4: 运行全部 render 测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_render_offline.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): HTML 可视化报告（直方图/饼图/条形/雷达）"
```

---

### Task 11: check_pipeline.py（产物校验）

**Files:**
- Create: `talent-identifier/scripts/check_pipeline.py`
- Test: `talent-identifier/scripts/tests/test_check_pipeline.py`

- [ ] **Step 1: 写失败测试**

`talent-identifier/scripts/tests/test_check_pipeline.py`:
```python
import json

import check_pipeline


def _write(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_valid_run_passes(tmp_path, capsys):
    run = tmp_path / "r1"
    _write(run / "profiles.jsonl",
           [{"person_id": "p1", "name": "A", "linked_domains": ["academic"],
             "link_evidence": [{"field": "x", "value": "y", "confidence": "high"}]}])
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": 80.0,
             "domain_scores": {"academic": 80.0}, "linked_domains": ["academic"]}])
    _write(run / "enrichment.jsonl",
           [{"person_id": "p1", "kind": "award", "title": "T", "source_url":
             "https://a", "evidence_level": "high"}])
    assert check_pipeline.main(["--run", str(run)]) == 0


def test_invalid_confidence_fails(tmp_path, capsys):
    run = tmp_path / "r2"
    _write(run / "profiles.jsonl",
           [{"person_id": "p1", "name": "A", "linked_domains": [],
             "link_evidence": [{"field": "x", "value": "y", "confidence": "maybe"}]}])
    _write(run / "scores.jsonl", [])
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "confidence" in capsys.readouterr().out


def test_unsorted_scores_fail(tmp_path, capsys):
    run = tmp_path / "r3"
    _write(run / "profiles.jsonl", [{"person_id": "p1", "name": "A"}])
    _write(run / "scores.jsonl",
           [{"person_id": "p2", "name": "B", "rank": 1, "t_score": 50.0},
            {"person_id": "p1", "name": "A", "rank": 2, "t_score": 90.0}])
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "降序" in capsys.readouterr().out


def test_enrichment_missing_source_fails(tmp_path, capsys):
    run = tmp_path / "r4"
    _write(run / "profiles.jsonl", [{"person_id": "p1", "name": "A"}])
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": 90.0}])
    _write(run / "enrichment.jsonl",
           [{"person_id": "p1", "kind": "paper", "title": "T",
             "source_url": "no-url", "evidence_level": "low"}])
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "source_url" in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_check_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 check_pipeline.py**

`talent-identifier/scripts/check_pipeline.py`:
```python
#!/usr/bin/env python3
"""校验 run 目录各阶段产物：JSONL 合法性、必填字段、枚举、榜单有序。"""
import argparse
import json
import sys
from pathlib import Path

CONFIDENCE = {"high", "medium", "low"}
EVIDENCE = {"high", "medium", "low"}
KINDS = {"position_change", "paper", "project", "award", "talk", "blog", "social"}


def _read(path: Path) -> list[dict]:
    rows, bad = [], 0
    for i, line in enumerate((path.read_text(encoding="utf-8").splitlines()
                              if path.exists() else []), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"FAIL {path.name}:{i} 非法 JSON")
            bad += 1
    return rows if bad == 0 else []


def check_run(run_dir: Path) -> int:
    errors = 0
    profiles = _read(run_dir / "profiles.jsonl")
    if not profiles:
        print("FAIL profiles.jsonl 缺失/为空/含非法行")
        errors += 1
    for i, p in enumerate(profiles, 1):
        if not p.get("person_id") or not p.get("name"):
            print(f"FAIL profiles.jsonl:{i} 缺 person_id 或 name")
            errors += 1
        for ev in p.get("link_evidence", []):
            if ev.get("confidence") not in CONFIDENCE:
                print(f"FAIL profiles.jsonl:{i} confidence 非法: {ev.get('confidence')}")
                errors += 1

    scores = _read(run_dir / "scores.jsonl")
    if not scores:
        print("FAIL scores.jsonl 缺失/为空/含非法行")
        errors += 1
    ranked = [r for r in scores if r.get("t_score") is not None]
    vals = [r["t_score"] for r in ranked]
    if vals != sorted(vals, reverse=True):
        print("FAIL scores.jsonl 榜单未按 t_score 降序")
        errors += 1
    for i, r in enumerate(ranked, 1):
        if r.get("rank") != i:
            print(f"FAIL scores.jsonl rank 应为 {i}，实际 {r.get('rank')}")
            errors += 1
        if not (0 <= r["t_score"] <= 100):
            print(f"FAIL scores.jsonl:{i} t_score 越界: {r['t_score']}")
            errors += 1

    enr_path = run_dir / "enrichment.jsonl"
    if enr_path.exists():
        for i, d in enumerate(_read(enr_path), 1):
            if d.get("kind") not in KINDS:
                print(f"FAIL enrichment.jsonl:{i} kind 非法: {d.get('kind')}")
                errors += 1
            if not str(d.get("source_url", "")).startswith("http"):
                print(f"FAIL enrichment.jsonl:{i} source_url 缺失或非法（动态必须带来源）")
                errors += 1
            if d.get("evidence_level") not in EVIDENCE:
                print(f"FAIL enrichment.jsonl:{i} evidence_level 非法")
                errors += 1

    if errors == 0:
        print(f"PASS {run_dir}")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args(argv)
    return 1 if check_run(Path(args.run)) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests/test_check_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): 产物完整性校验 check_pipeline"
```

---

### Task 12: references/ 五份契约与手册文档

**Files:**
- Create: `talent-identifier/references/openapi-contract.md`
- Create: `talent-identifier/references/scoring-model.md`
- Create: `talent-identifier/references/identity-linking.md`
- Create: `talent-identifier/references/web-exploration.md`
- Create: `talent-identifier/references/report-templates.md`

本 Task 无代码测试，验收标准为文件存在且包含规定小节。逐份创建：

- [ ] **Step 1: openapi-contract.md**

内容必须包含：
- 认证：`X-API-Key` 请求头；key 由 AI4TALENT super_admin 在「系统配置 → API Key 管理」生成，scope 需含 `academic:read` 等各域读权限
- Base：`{base_url}`（默认 `http://localhost:8003/api/v1`），Swagger 在 `http://localhost:8003/docs`，权威文档 `D:\AI\AI4TALENT\docs\open-api\01-agent-guide.md`
- 端点表：`GET /open-api/search/talents`（keyword/domains/per_domain≤20）、`GET /open-api/{academic|open-source|lab|competition|industry}/talents`（page/page_size 1-100 默认 20，envelope `{items,total,page,page_size}`）、`GET /open-api/{domain}/talents/{id}`、`GET /open-api/{domain}/stats`
- 各域关键字段表（从模型摘录）：academic=name/name_en/orcid/current_title/role_type/topic_tags/works_count/cited_by_count/h_index/latest_active_year；open_source=github_login/bio/company/followers_count/total_stars_received/primary_languages/tech_tags；lab=name/role_section/role_type/homepage/email/social_links/research_areas/lab_name/parent_lab/advisor；competition=handle/school/current_rating/max_rating/rank_title/medals_gold|silver|bronze；industry=name/current_org/current_title/degree/years_of_exp
- **PII 说明**：当前白名单模式会脱敏 email/social_links/orcid；平台侧将按 key 提供 PII。skill 行为：`contact_info_unavailable=true` 时 Agent 探索改用「名字+机构+方向」搜索词
- 错误处理：429/5xx 指数退避重试 3 次；单域失败记入 `gaps.txt`；`/health` 探活
- **运行时核对指令**：调用前先 `curl -H "X-API-Key: $KEY" {base_url}/open-api/academic/talents?page_size=1` 核对字段名与脱敏情况，若与本文档不符以实际响应为准并回填本文档

- [ ] **Step 2: scoring-model.md**

内容必须包含：设计文档 §6 全表（五域指标+权重、log+min-max 归一化、活跃度衰减公式、融合公式 0.7/0.3/+5/域上限+10、截断 100）、`_role_weight`/`_lab_prestige`/`_rank_title_score`/`_title_weight`/`_org_prestige` 的映射表（与 scoring.py 常量一致）、"候选集内归一化→榜单仅本次可比"的告示语、缺失指标默认值（activity 缺失 0.3、rank_title 缺失 0.3、未知角色 0.6、未知机构 0.6/0.7）

- [ ] **Step 3: identity-linking.md**

内容必须包含：三档证据表（high=homepage/github/orcid/email 相同；medium=规范化名字+机构相同；low=名字+标签 Jaccard>0.2 仅提示）、同域不合并规则、名字/机构/URL 规范化定义（与 normalize.py 一致）、person_id 生成规则（sha256 前 8 位+冲突序号）、`suspected_same_person` 字段语义、Agent 判读指引（low 提示需人工确认，报告不得当作同一人陈述）

- [ ] **Step 4: web-exploration.md**

内容必须包含（Agent 阶段3 的操作手册）：
- 目标信息七类与 `kind` 枚举映射
- 信源优先级：个人主页 > Google Scholar > GitHub > X/Twitter > LinkedIn > 权威媒体 > 学术数据库
- 证据分级：high=官方页面 / medium=权威媒体或本人社媒 / low=二手转述；**无 source_url 不写入**
- 搜索词构造：`"<name>" <org> <topic> 2026`、`"<name>" <org> (joined OR appointed OR award OR paper)`；PII 降级时用机构+方向替代主页类搜索
- 预算：每人 ≤`exploration.max_searches` 次搜索、≤`exploration.max_fetches` 次抓取（默认 6/4）；超预算立即收束
- 时效优先：近 12 个月；`date` 字段尽量精确到月（YYYY-MM），确实未知则省略
- 写入规范：每发现一条动态立即 `append` 到 `enrichment.jsonl`（一行一 JSON，字段见数据契约）；每人探索结束后把定性洞察写入 `enrichment/<person_id>.md`（结构：亮点/风险/趋势三小节，每节 2-4 句，观点须有动态或库内指标支撑）
- 中断与失败：单人失败在 enrichment.jsonl 追加 `{"person_id":..., "kind":"social", "title":"EXPLORATION_FAILED", ...}` 不合法——改为：失败者不写动态，仅在最终汇报中说明；**部分成功优于完全失败**

- [ ] **Step 5: report-templates.md**

内容必须包含：领域榜单报告五段结构模板（执行摘要/榜单总表/Top 小传/跨域专题/方法论附录）、个人报告四段结构模板、小传的定性洞察写作规范（亮点/风险/趋势，禁无依据推断，禁臆造联系方式）、Markdown 表格样式示例、HTML 报告图表清单（直方图/饼图/条形/雷达）与数据来源字段说明

- [ ] **Step 6: 验收文件存在**

Run: `ls /d/AI/IdentifyAgent/talent-identifier/references/`
Expected: 列出 5 个 .md 文件

- [ ] **Step 7: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "docs(talent-identifier): 五份契约与手册（API/评分/关联/探索/报告）"
```

---

### Task 13: SKILL.md 与部署

**Files:**
- Create: `talent-identifier/SKILL.md`
- Create: `talent-identifier/assets/`（下载 echarts）

- [ ] **Step 1: 撰写 SKILL.md**

`talent-identifier/SKILL.md`（frontmatter 与生态一致：仅 name + description，末尾触发场景）：

````markdown
---
name: talent-identifier
description: |
  跨域顶尖人才识别与洞察。基于 AI4TALENT 人才库 Open API（学术/开源/实验室/竞赛/行业五域），
  按技术方向识别顶尖人才榜单（硬指标 T-score 定量 + LLM 定性洞察），或对给定名单逐人深挖；
  Agent 在互联网上探索补全人才最新动态（职位/论文/项目/获奖，均带来源），最终产出
  Markdown 深度洞察报告 + HTML 可视化 + JSONL 结构化数据三件套。
  触发场景："识别XX领域顶尖人才" / "人才识别" / "跨域人才榜单" / "深挖这些人" /
  "给我一份XX方向人才洞察报告" / "talent identification"。
---

# talent-identifier：跨域顶尖人才识别

读 AI4TALENT 五域人才库 → 跨域关联 + T-score 榜单 → 互联网补全最新动态 → 三件套洞察报告。
**纯消费型 skill：只读 Open API，绝不写回平台。**

## 前置检查（执行前必做）

1. 配置：cwd 或 skill 目录的 `ai4talent.config.json`，`api_key` 可用环境变量
   `AI4TALENT_API_KEY` 覆盖；base_url 可用 `AI4TALENT_BASE_URL` 覆盖。
2. 探活：`curl -s -m 5 <base_url>/health`，不通则提示用户先启动 AI4TALENT 后端再停止。
3. 运行时：Python 3.11+；脚本依赖仅 httpx。执行命令统一用
   `uv run --with httpx python scripts/xxx.py ...`（uv 缺失且本机 python 有 httpx 时可直跑）。

## 模式 A：领域识别（输入=技术方向）

```bash
cd <项目目录>   # 产物落在 cwd 的 output/
# 阶段1+2（确定性）
uv run --with httpx python <skill>/scripts/fetch_profiles.py --mode domain --keyword "<方向>"
uv run --with httpx python <skill>/scripts/compute_scores.py --run output/<run_id>
```

## 模式 B：名单深挖（输入=人名列表）

```bash
uv run --with httpx python <skill>/scripts/fetch_profiles.py --mode names --names "名字1,名字2"
uv run --with httpx python <skill>/scripts/compute_scores.py --run output/<run_id>
```

## 阶段3：互联网探索（Agent 执行，逐人）

对 `scores.jsonl` 的 Top N（config `top_n`，默认 20；名单模式为全部库内人员 + 所有库外人员）：
1. 读 `references/web-exploration.md`，按信源优先级与搜索词构造逐人搜索（WebSearch/WebFetch）。
2. 每条动态**立即**追加一行到 `output/<run_id>/enrichment.jsonl`（schema 见该文件头部约定，
   无 source_url 的信息一律丢弃）。
3. 每人探索完写 `output/<run_id>/enrichment/<person_id>.md` 定性洞察（亮点/风险/趋势）。
4. 严守预算（默认每人 6 搜 4 抓）；`contact_info_unavailable=true` 者走降级搜索词。
5. 单人失败跳过并记录，不阻塞他人——部分成功优于完全失败。

## 阶段4：渲染与验收

```bash
uv run --with httpx python <skill>/scripts/render_report.py --run output/<run_id>
uv run --with httpx python <skill>/scripts/check_pipeline.py --run output/<run_id>
```

## 硬性约束

- 只读 Open API，不写回 AI4TALENT；不触碰任何需要登录的站点，不绕验证码/风控。
- 评分与关联全部由脚本完成，Agent 不得手改 scores.jsonl；定性观点必须有动态或指标支撑。
- 断点续跑：中断后同命令加 `--resume`（fetch 阶段）/直接重跑后续阶段（幂等覆盖产物）。
- 中英名字、同名不同人歧义时，宁可少合并不多合并（低置信只提示）。

## 完成标准

- 榜单非空（或名单模式每人有报告）；check_pipeline 返回 PASS。
- 报告三件套齐全：report.md（或逐人 report_*.md）、report.html、final/*.jsonl。
- 每条动态带来源；报告含方法论附录。

## 参考文件

- references/openapi-contract.md — Open API 契约与字段/PII 降级
- references/scoring-model.md — T-score 口径与映射表
- references/identity-linking.md — 跨域关联与置信度
- references/web-exploration.md — 互联网探索手册（阶段3 必读）
- references/report-templates.md — 报告结构与写作规范
````

- [ ] **Step 2: 下载 echarts 资产（可选但推荐）**

Run: `mkdir -p /d/AI/IdentifyAgent/talent-identifier/assets && curl -L -o /d/AI/IdentifyAgent/talent-identifier/assets/echarts.min.js https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js && ls -la /d/AI/IdentifyAgent/talent-identifier/assets/`
Expected: echarts.min.js 约 1MB。失败（无网络）不阻塞——渲染会自动退回 CDN 引用。

- [ ] **Step 3: 部署到 skill 目录**

```bash
rm -rf "/c/Users/Administrator/.agents/skills/talent-identifier"
cp -r /d/AI/IdentifyAgent/talent-identifier "/c/Users/Administrator/.agents/skills/talent-identifier"
find "/c/Users/Administrator/.agents/skills/talent-identifier" -name "__pycache__" -type d -exec rm -rf {} +
find "/c/Users/Administrator/.agents/skills/talent-identifier" -name ".pytest_cache" -type d -exec rm -rf {} +
```

注意：部署排除测试目录可选；保留 tests 无害（体积小），保留以便现场诊断。

- [ ] **Step 4: 提交**

```bash
cd /d/AI/IdentifyAgent && git add talent-identifier && git commit -m "feat(talent-identifier): SKILL.md 主文档与部署"
```

---

### Task 14: 端到端验收

**Files:**
- 无新文件；产出验证记录于提交信息

- [ ] **Step 1: 全量单测**

Run: `cd /d/AI/IdentifyAgent/talent-identifier && uv run --with httpx --with pytest python -m pytest scripts/tests -v`
Expected: 全部通过（约 30+ 用例）

- [ ] **Step 2: 离线端到端（构造 fixture 数据全链路）**

```bash
cd /d/AI/IdentifyAgent/talent-identifier
mkdir -p /tmp/ti-e2e && cp scripts/tests/conftest.py /tmp/ti-e2e/ 2>/dev/null || true
uv run --with httpx python - <<'PY'
import sys, json, pathlib
sys.path.insert(0, "scripts")
import fetch_profiles

class FakeClient:
    def health(self): return True
    def list_domain(self, domain, params, limit):
        data = {
            "academic": [{"name": "Yi Wu", "name_en": "Yi Wu", "education_school": "Tsinghua University", "h_index": 35, "cited_by_count": 8000, "works_count": 80, "latest_active_year": 2026, "topic_tags": ["rl"]}],
            "open_source": [{"name": "Yi Wu", "github_login": "yiwu", "company": "Tsinghua", "total_stars_received": 12000, "followers_count": 3000, "primary_languages": ["Python", "C++"]}],
            "lab": [{"name": "Wu Yi", "role_section": "Faculty", "lab_name": "Tsinghua AIR", "research_areas": "llm, agents"}],
        }
        return data.get(domain, [])[:limit]
    def cross_search(self, keyword, domains, per_domain=20): return []

rc = fetch_profiles.main(["--mode", "domain", "--keyword", "llm", "--out", "/tmp/ti-e2e/output"], client=FakeClient)
print("fetch rc =", rc); sys.exit(rc)
PY
uv run --with httpx python scripts/compute_scores.py --run /tmp/ti-e2e/output/domain-llm-*
# 手工模拟阶段3：追加一条动态
RUN=$(ls -d /tmp/ti-e2e/output/domain-llm-* | head -1)
mkdir -p "$RUN/enrichment"
printf '%s\n' '{"person_id":"PLACEHOLDER","kind":"award","title":"Test Award","date":"2026-05","source_url":"https://example.com/a","evidence_level":"high","summary":"e2e","collected_at":"2026-08-29T00:00:00+00:00"}' >> "$RUN/enrichment.jsonl"
# 用真实 person_id 修正该行（演示环境直接重写第一行）
PID=$(head -1 "$RUN/profiles.jsonl" | python -c "import sys,json;print(json.load(sys.stdin)['person_id'])")
python - "$RUN" "$PID" <<'PY'
import json, sys, pathlib
run, pid = pathlib.Path(sys.argv[1]), sys.argv[2]
rows = [json.loads(l) for l in (run/"enrichment.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for r in rows: r["person_id"] = pid
with (run/"enrichment.jsonl").open("w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False)+"\n")
PY
uv run --with httpx python scripts/render_report.py --run "$RUN"
uv run --with httpx python scripts/check_pipeline.py --run "$RUN"
```
Expected: fetch rc=0；score 打印榜单；render 生成三件套；check_pipeline 输出 PASS

- [ ] **Step 3: 在线冒烟（后端在跑且已有 API key 时执行；否则跳过并记录）**

```bash
export AI4TALENT_API_KEY=<用户提供>
curl -s -m 5 http://localhost:8003/api/v1/health
cd /d/AI/IdentifyAgent
uv run --with httpx python talent-identifier/scripts/fetch_profiles.py --mode domain --keyword "agent" --out smoke_output
RUN=$(ls -d smoke_output/domain-agent-* | head -1)
uv run --with httpx python talent-identifier/scripts/compute_scores.py --run "$RUN"
# Agent 按 SKILL.md 阶段3 探索 top 3（人工/主 Agent 执行）后：
uv run --with httpx python talent-identifier/scripts/render_report.py --run "$RUN"
uv run --with httpx python talent-identifier/scripts/check_pipeline.py --run "$RUN"
```
Expected: 同 Step 2；另外人工打开 report.html 确认图表渲染

- [ ] **Step 4: 最终提交**

```bash
cd /d/AI/IdentifyAgent
printf 'smoke_output/\n' >> .gitignore
git add .gitignore talent-identifier
git commit -m "chore(talent-identifier): 端到端验收通过，skill v0.1.0 就绪"
```

---

## Self-Review 记录（计划完成后自查）

1. **Spec 覆盖**：§4 结构→Task 1/12/13；§5 两模式→Task 7；§6 评分→Task 6/8；§7 关联→Task 5；§8 探索→Task 12(web-exploration)+Task 13(阶段3 指令)+Task 11(动态校验)；§9 报告→Task 9/10；§10 配置容错→Task 1(config/env)、Task 4(重试)、Task 7(health/缺口/兜底/resume)、Task 2(state)；§11 测试验收→各任务 TDD + Task 14。§12 依赖（PII 优化属平台侧）在 openapi-contract.md 有运行时核对与降级说明。无缺口。
2. **占位符扫描**：无 TBD/TODO；Task 9 的 `render_html` 占位在 Task 10 落地，属计划内接力，非遗留占位。
3. **类型一致性**：`person_id/domain_scores/t_score/link_evidence/suspected_same_person/contact_info_unavailable` 等字段名在数据契约、Task 5/6/7/9/10/11 间已逐一核对一致；`_record_identity`/`link_records`/`compute_scores`/`load_run`/`render_html` 等签名前后一致；测试中引用的常量（`ACADEMIC_WEIGHTS`、`api_client.httpx`、`api_client.time`）在实现中均存在。
