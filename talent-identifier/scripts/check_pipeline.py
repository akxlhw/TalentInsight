#!/usr/bin/env python3
"""校验 run 目录各阶段产物：JSONL 合法性、必填字段、枚举、榜单有序。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from talent_identifier import io_utils

CONFIDENCE = {"high", "medium", "low"}
EVIDENCE = {"high", "medium", "low"}
KINDS = {"position_change", "paper", "project", "award", "talk", "blog", "social"}


def _read(path: Path) -> tuple[list, int]:
    """返回 (合法行, 非法行数)。行号为物理行号（空行占号但跳过解析）。"""
    rows, bad = [], 0
    if not path.exists():
        return [], 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"FAIL {path.name}:{i} 非法 JSON")
            bad += 1
    return rows, bad


def check_run(run_dir: Path) -> int:
    errors = 0
    profiles, bad = _read(run_dir / "profiles.jsonl")
    errors += bad
    if not profiles and bad == 0:
        print("FAIL profiles.jsonl 缺失/为空")
        errors += 1
    for i, p in enumerate(profiles, 1):
        if not isinstance(p, dict):
            print(f"FAIL profiles.jsonl:{i} 非对象行")
            errors += 1
            continue
        if not p.get("person_id") or not p.get("name"):
            print(f"FAIL profiles.jsonl:{i} 缺 person_id 或 name")
            errors += 1
        for ev in p.get("link_evidence", []):
            if not isinstance(ev, dict) or ev.get("confidence") not in CONFIDENCE:
                print(f"FAIL profiles.jsonl:{i} confidence 非法: "
                      f"{ev.get('confidence') if isinstance(ev, dict) else ev}")
                errors += 1

    scores, bad = _read(run_dir / "scores.jsonl")
    errors += bad
    if not scores and bad == 0:
        print("FAIL scores.jsonl 缺失/为空")
        errors += 1
    ranked = []
    for i, r in enumerate(scores, 1):
        if not isinstance(r, dict):
            print(f"FAIL scores.jsonl:{i} 非对象行")
            errors += 1
            continue
        ts = r.get("t_score")
        if ts is None:
            continue  # 未评分行尾置，不参与榜单校验
        if not isinstance(ts, (int, float)) or isinstance(ts, bool):
            print(f"FAIL scores.jsonl:{i} t_score 非数值: {ts!r}")
            errors += 1
            continue
        ranked.append(r)
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
        enr, bad = _read(enr_path)
        errors += bad
        for i, d in enumerate(enr, 1):
            if not isinstance(d, dict):
                print(f"FAIL enrichment.jsonl:{i} 非对象行")
                errors += 1
                continue
            if d.get("kind") not in KINDS:
                print(f"FAIL enrichment.jsonl:{i} kind 非法: {d.get('kind')}")
                errors += 1
            if not str(d.get("source_url", "")).startswith("http"):
                print(f"FAIL enrichment.jsonl:{i} source_url 缺失或非法（动态必须带来源）")
                errors += 1
            if d.get("evidence_level") not in EVIDENCE:
                print(f"FAIL enrichment.jsonl:{i} evidence_level 非法")
                errors += 1

    if "render" in io_utils.load_state(run_dir).get("stages_done", []):
        if not (run_dir / "report.html").exists():
            print("FAIL render 阶段已完成但 report.html 缺失")
            errors += 1
        if not list((run_dir / "final").glob("talents_*.jsonl")):
            print("FAIL render 阶段已完成但 final/ 下无 talents_*.jsonl")
            errors += 1
        if not (run_dir / "report.md").exists() \
                and not list(run_dir.glob("report_*.md")):
            print("FAIL render 阶段已完成但缺少 report.md / report_*.md")
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
