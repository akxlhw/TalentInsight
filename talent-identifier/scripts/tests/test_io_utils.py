import json

from talent_identifier import io_utils


def test_slugify():
    assert io_utils.slugify("大模型推理优化") == "大模型推理优化"
    assert io_utils.slugify("LLM Inference & Serving!") == "llm-inference-serving"
    assert len(io_utils.slugify("a" * 100)) == 40


def test_new_run_dir(tmp_path):
    run_id, run_dir = io_utils.new_run_dir(tmp_path, "domain", "LLM 推理")
    assert run_id.startswith("domain-")
    assert run_dir.is_dir() and run_dir.parent == tmp_path
    rid2, _ = io_utils.new_run_dir(tmp_path, "names", None)
    assert rid2.startswith("names-")


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "x.jsonl"
    rows = [{"a": 1}, {"b": "中文"}]
    io_utils.write_jsonl(p, rows)
    assert io_utils.read_jsonl(p) == rows


def test_new_run_dir_conflict_suffix(tmp_path):
    id1, _ = io_utils.new_run_dir(tmp_path, "domain", "same-topic")
    id2, _ = io_utils.new_run_dir(tmp_path, "domain", "same-topic")
    assert id2 == id1 + "-2"


def test_append_jsonl(tmp_path):
    p = tmp_path / "sub" / "x.jsonl"
    io_utils.append_jsonl(p, {"a": 1})
    io_utils.append_jsonl(p, {"b": "中文"})
    assert io_utils.read_jsonl(p) == [{"a": 1}, {"b": "中文"}]


def test_read_jsonl_missing_returns_empty(tmp_path):
    assert io_utils.read_jsonl(tmp_path / "nope.jsonl") == []


def test_state_stages(tmp_path):
    io_utils.mark_stage(tmp_path, "fetch", run_id="r1", mode="domain")
    st = io_utils.load_state(tmp_path)
    assert st["run_id"] == "r1" and st["mode"] == "domain"
    assert st["stages_done"] == ["fetch"]
    io_utils.mark_stage(tmp_path, "score")
    io_utils.mark_stage(tmp_path, "fetch")  # 重复标记不重复追加
    assert io_utils.load_state(tmp_path)["stages_done"] == ["fetch", "score"]
