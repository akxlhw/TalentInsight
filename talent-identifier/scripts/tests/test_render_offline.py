import json

import render_report


def _make_run(tmp_path, name="domain-agent-20260829"):
    run_dir = tmp_path / name
    run_dir.mkdir()
    (run_dir / "profiles.jsonl").write_text(
        '{"person_id":"p1","name":"Alice","name_en":"Alice A","org":"MIT",'
        '"records":{"academic":{"h_index":40,"cited_by_count":5000}},'
        '"linked_domains":["academic"],"link_evidence":[],"tags":["rl"],'
        '"in_library":true,"collected_at":"2026-08-29T00:00:00+00:00"}\n'
        '{"person_id":"p2","name":"Bob","name_en":null,"org":"Foo|Bar",'
        '"records":{},"linked_domains":[],"link_evidence":[],"tags":[],'
        '"in_library":false,"collected_at":"2026-08-29T00:00:00+00:00"}\n'
        '{"person_id":"p3","name":"Cara","name_en":null,"org":"Stanford",'
        '"records":{},"linked_domains":["academic","open_source","lab"],'
        '"link_evidence":[],"tags":[],"in_library":true,'
        '"collected_at":"2026-08-29T00:00:00+00:00"}\n', encoding="utf-8")
    (run_dir / "scores.jsonl").write_text(
        '{"person_id":"p1","name":"Alice","rank":1,"t_score":82.3,'
        '"domain_scores":{"academic":82.3},"score_components":{},'
        '"linked_domains":["academic"]}\n'
        '{"person_id":"p2","name":"Bob","rank":2,"t_score":null,'
        '"domain_scores":{},"score_components":{},"linked_domains":[]}\n'
        '{"person_id":"p3","name":"Cara","rank":3,"t_score":100.0,'
        '"domain_scores":{"academic":70.0,"open_source":60.0,"lab":50.0},'
        '"score_components":{},"linked_domains":["academic","open_source","lab"]}\n', encoding="utf-8")
    (run_dir / "enrichment.jsonl").write_text(
        '{"person_id":"p1","kind":"award","title":"Best Paper","date":"2026-06",'
        '"source_url":"https://x.example/a","evidence_level":"high",'
        '"summary":"获奖","collected_at":"2026-08-29T00:00:00+00:00"}\n'
        '{"person_id":"zz","kind":"paper","title":"Ghost","date":"2026-01",'
        '"source_url":"https://x.example/g","evidence_level":"low",'
        '"summary":"孤儿动态","collected_at":"2026-08-29T00:00:00+00:00"}\n', encoding="utf-8")
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
    assert "| 1 | Alice | 82.3" in md
    assert "| 2 | Bob | N/A" in md          # 无 t_score 显示 N/A
    assert "| 3 | Cara | 100.0" in md
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
    lines = finals[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    row = json.loads(lines[0])
    assert row["person_id"] == "p1"
    assert row["dynamics"][0]["kind"] == "award"
    assert "insight_md" in row
    row2 = json.loads(lines[1])
    assert row2["person_id"] == "p2"
    assert "t_score" not in row2             # t_score:null 字段省略
    assert row2["in_library"] is False       # False 保留不省略
    row3 = json.loads(lines[2])
    assert row3["person_id"] == "p3" and row3["t_score"] == 100.0


def test_render_names_mode_per_person(tmp_path):
    run_dir = _make_run(tmp_path)
    # _make_run 不写 _state.json（load_state 对缺失文件返回默认值），
    # names 模式测试先写默认 state 再改 mode
    st = {"run_id": run_dir.name, "mode": "domain", "stages_done": []}
    st["mode"] = "names"
    (run_dir / "_state.json").write_text(json.dumps(st), encoding="utf-8")
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    reports = list(run_dir.glob("report_*.md"))
    assert len(reports) == 3
    txt = (run_dir / "report_p1.md").read_text(encoding="utf-8")
    assert "Alice" in txt
    assert "## 综合画像（T-score 82.3）" in txt   # H2 不再重复人名


def test_summary_no_double_top_claim(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert md.count("居首") <= 1
    assert "#1 Alice T-score 82.3" in md     # 摘要逐条按排名标注


def test_keyword_extracted_from_suffixed_run_dir(tmp_path):
    run_dir = _make_run(tmp_path, name="domain-agent-20260829-2")
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    title = (run_dir / "report.md").read_text(encoding="utf-8").splitlines()[0]
    assert title == "# 领域人才洞察报告：agent"
    assert "20260829" not in title            # 标题不含日期


def test_insight_heading_stripped(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "### 定性洞察" not in md.splitlines()   # insight 文件自带标题剥掉
    assert "上升趋势" in md


def test_orphan_dynamics_excluded(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "互联网补全动态 1 条" in md   # 孤儿动态（zz）不计入统计
    assert "Ghost" not in md            # 也不渲染


def test_table_cell_pipe_escaped(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Foo\\|Bar" in md            # 单元格内 | 转义，表格不破
    table_lines = [l for l in md.splitlines() if l.startswith("|")]
    assert {l.replace("\\|", "").count("|") for l in table_lines} == {6}


def test_key_metrics_handles_null_org():
    out = render_report._key_metrics({"current_title": "Eng", "current_org": None})
    assert "None" not in out and "Eng" in out


def test_render_html(tmp_path):
    run_dir = _make_run(tmp_path)
    rc = render_report.main(["--run", str(run_dir)])
    assert rc == 0
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "echarts" in html.lower()          # 内联或 CDN 二选一
    assert "Alice" in html
    assert "DATA" in html                     # 数据注入 JS


def _data_payload(run_dir):
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    seg = html.split("const DATA = ")[1].split(";\n")[0]
    return json.loads(seg)


def test_render_html_escapes_injection(tmp_path):
    run_dir = _make_run(tmp_path)
    # 往 profiles/scores 里塞一个带攻击串的人（含 </script> 以覆盖 DATA 注入路径）
    attack = "<img src=x onerror=alert(1)></script>"
    profs = run_dir / "profiles.jsonl"
    rows = [json.loads(l) for l in profs.read_text(encoding="utf-8").splitlines()]
    rows.append({"person_id": "p9", "name": attack, "records": {},
                 "linked_domains": [], "in_library": False})
    with profs.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    sc = run_dir / "scores.jsonl"
    srows = [json.loads(l) for l in sc.read_text(encoding="utf-8").splitlines()]
    srows.append({"person_id": "p9", "name": attack,
                  "rank": 3, "t_score": 40.0, "domain_scores": {},
                  "score_components": {}, "linked_domains": []})
    with sc.open("w", encoding="utf-8") as f:
        for r in srows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    assert render_report.main(["--run", str(run_dir)]) == 0
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "<img src=x" not in html.split("const DATA = ")[0]  # 文档区（表格等）已转义
    assert "&lt;img src=x" in html                              # 表格内是转义形态
    assert "</script>\nfunction" not in html    # DATA 内无裸 </script>（宽松断言：DATA 段不含 </script>）
    seg = html.split("const DATA = ")[1].split(";\n")[0]
    assert attack not in seg
    assert "</script>" not in seg
    assert "\\/" in seg                         # p9 已进 bar payload，</ 被重写为 <\/


def test_hist_includes_perfect_score(tmp_path):
    run_dir = _make_run(tmp_path)
    assert render_report.main(["--run", str(run_dir)]) == 0
    payload = _data_payload(run_dir)
    assert payload["hist"]["counts"][9] == 1    # t_score=100.0 计入 90-100 桶
    assert sum(payload["hist"]["counts"]) == 2  # 82.3 与 100.0


def test_render_html_radar(tmp_path):
    run_dir = _make_run(tmp_path)
    assert render_report.main(["--run", str(run_dir)]) == 0
    payload = _data_payload(run_dir)
    assert len(payload["radars"]) == 1
    assert len(payload["radars"][0]["indicator"]) == 3
    assert payload["radars"][0]["values"] == [70.0, 60.0, 50.0]
