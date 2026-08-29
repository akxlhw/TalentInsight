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


def test_score_preserves_fetch_state(tmp_path):
    from talent_identifier import io_utils
    run_dir = tmp_path / "names-20260829-1200"
    run_dir.mkdir()
    io_utils.mark_stage(run_dir, "fetch", run_id="names-20260829-1200", mode="names")
    (run_dir / "profiles.jsonl").write_text(
        '{"person_id":"p1","name":"A","records":{"academic":{"h_index":10,'
        '"cited_by_count":100,"works_count":5,"latest_active_year":2026}},'
        '"linked_domains":["academic"]}\n', encoding="utf-8")
    assert compute_scores.main(["--run", str(run_dir)]) == 0
    state = json.loads((run_dir / "_state.json").read_text(encoding="utf-8"))
    assert state["run_id"] == "names-20260829-1200"   # 保留，不被覆盖
    assert state["mode"] == "names"
    assert state["stages_done"] == ["fetch", "score"]
