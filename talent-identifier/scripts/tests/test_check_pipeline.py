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
    assert "PASS" in capsys.readouterr().out


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


def test_corrupt_enrichment_line_fails(tmp_path, capsys):
    run = tmp_path / "r5"
    _write(run / "profiles.jsonl", [{"person_id": "p1", "name": "A"}])
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": 90.0}])
    (run / "enrichment.jsonl").write_text(
        '{"person_id":"p1","kind":"award","title":"T","source_url":"https://a",'
        '"evidence_level":"high"}\n{broken json\n', encoding="utf-8")
    assert check_pipeline.main(["--run", str(run)]) == 1


def _make_rendered_run(tmp_path, name, *, with_html=True):
    run = tmp_path / name
    _write(run / "profiles.jsonl", [{"person_id": "p1", "name": "A"}])
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": 90.0}])
    (run / "_state.json").write_text(
        json.dumps({"stages_done": ["fetch", "score", "render"]}), encoding="utf-8")
    if with_html:
        (run / "report.html").write_text("<html></html>", encoding="utf-8")
    (run / "report.md").write_text("# R", encoding="utf-8")
    fin = run / "final"
    fin.mkdir()
    (fin / "talents_x.jsonl").write_text("{}\n", encoding="utf-8")
    return run


def test_render_stage_artifacts_pass(tmp_path, capsys):
    run = _make_rendered_run(tmp_path, "r6")
    assert check_pipeline.main(["--run", str(run)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_render_stage_missing_html_fails(tmp_path, capsys):
    run = _make_rendered_run(tmp_path, "r7", with_html=False)
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "report.html" in capsys.readouterr().out


def test_render_stage_not_done_skips_artifact_check(tmp_path, capsys):
    run = _make_rendered_run(tmp_path, "r8")
    (run / "report.html").unlink()          # render 未完成时不应 FAIL
    (run / "_state.json").write_text(
        json.dumps({"stages_done": ["fetch", "score"]}), encoding="utf-8")
    assert check_pipeline.main(["--run", str(run)]) == 0


def test_kinds_match_render_enum():
    import render_report
    assert check_pipeline.KINDS == set(render_report.KIND_CN.keys())


def test_non_dict_profile_row_fails(tmp_path, capsys):
    run = tmp_path / "r9"
    run.mkdir()
    (run / "profiles.jsonl").write_text('"just a string"\n', encoding="utf-8")
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": 90.0}])
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "非对象行" in capsys.readouterr().out


def test_string_t_score_fails(tmp_path, capsys):
    run = tmp_path / "r10"
    _write(run / "profiles.jsonl", [{"person_id": "p1", "name": "A"}])
    _write(run / "scores.jsonl",
           [{"person_id": "p1", "name": "A", "rank": 1, "t_score": "90.0"}])
    assert check_pipeline.main(["--run", str(run)]) == 1
    assert "非数值" in capsys.readouterr().out
