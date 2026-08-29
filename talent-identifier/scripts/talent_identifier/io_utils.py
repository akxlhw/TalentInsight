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
    st = json.loads(p.read_text(encoding="utf-8"))
    st.setdefault("stages_done", [])  # 兜底手工编辑过的旧格式 state
    return st


def mark_stage(run_dir: Path, stage: str, run_id: str | None = None, mode: str | None = None) -> None:
    st = load_state(run_dir)
    if run_id:
        st["run_id"] = run_id
    if mode:
        st["mode"] = mode
    if stage not in st["stages_done"]:
        st["stages_done"].append(stage)
    tmp = run_dir / "_state.json.tmp"  # 原子写，防写一半崩溃损坏断点状态
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(run_dir / "_state.json")
