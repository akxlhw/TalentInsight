#!/usr/bin/env python3
"""阶段2：读取 profiles.jsonl，计算 T-score 榜单，产出 scores.jsonl。

用法: python scripts/compute_scores.py --run <output/domain-x-YYYYMMDD>
"""
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
