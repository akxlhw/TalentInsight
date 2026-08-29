#!/usr/bin/env python3
"""阶段4：装配画像/评分/动态，渲染 Markdown 报告 + HTML + final JSONL。

用法: python scripts/render_report.py --run <output/domain-x-YYYYMMDD>
"""
import argparse
import re
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
        bits.append(f"{(rec.get('current_org') or '')} {rec['current_title']}")
    return "；".join(bits)


def _cell(s) -> str:
    return str(s).replace("|", "\\|")


def _person_section(row, data, top_label=True) -> str:
    p = data["profiles"].get(row["person_id"], {})
    lines = []
    t = row["t_score"] if row["t_score"] is not None else "N/A"
    if top_label:
        head = f"### #{row['rank']} {row['name']}（T-score {t}）"
    else:  # names 模式：H1 已含人名，H2 用综合画像避免重复
        head = f"## 综合画像（T-score {t}）"
    lines.append(head)
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
            lines.append(f"- [{d.get('date') or '?'}]（{KIND_CN.get(d['kind'], d['kind'])}）"
                         f"{d['title']} — {d.get('summary', '')}"
                         f"（证据 {d['evidence_level']}）[来源]({d['source_url']})")
    ins = data["insights"].get(row["person_id"])
    if ins and ins.startswith("#"):  # 剥掉 insight 文件自带标题，避免与本节 H4 冗余
        ins = "\n".join(ins.splitlines()[1:]).lstrip()
    lines.append("")
    lines.append("#### 定性洞察")
    lines.append(ins if ins else "（本次未生成洞察）")
    return "\n".join(lines)


def render_markdown(run_dir: Path, data: dict, mode: str, keyword: str | None) -> list[Path]:
    scores = data["scores"]
    cross = [r for r in scores if len(r["linked_domains"]) > 1]
    n_dyn = sum(len(v) for pid, v in data["dynamics"].items() if pid in data["profiles"])
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
        md.append(f"  - #{r['rank']} {r['name']} T-score {r['t_score']}"
                  f"（{('、'.join(DOMAIN_CN.get(d, d) for d in r['linked_domains']))}）")
    if n_dyn:
        md.append(f"  - 互联网补全捕捉到 {n_dyn} 条最新动态（含来源链接）")
    md += ["", "## 榜单总表", "",
           "| 排名 | 姓名 | T-score | 域 | 机构 |", "|---|---|---|---|---|"]
    for r in scores:
        doms = "、".join(DOMAIN_CN.get(d, d) for d in r["linked_domains"]) or "库外"
        org = data["profiles"].get(r["person_id"], {}).get("org", "")
        md.append(f"| {r['rank']} | {_cell(r['name'])} | {r['t_score'] if r['t_score'] is not None else 'N/A'}"
                  f" | {doms} | {_cell(org)} |")
    md += ["", "## Top 榜单小传", ""]
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


def render_html(run_dir: Path, data: dict) -> Path | None:
    return None  # Task 10 实现


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
    stem = re.sub(r"-\d{8}(-\d+)?$", "", run_dir.name)  # 剥掉日期与同日 -N 后缀
    if mode == "domain" and stem.startswith("domain-"):
        keyword = stem[len("domain-"):]
    render_markdown(run_dir, data, mode, keyword)
    render_final_jsonl(run_dir, data)
    render_html(run_dir, data)
    io_utils.mark_stage(run_dir, "render")
    print(f"[render] 报告已生成: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
