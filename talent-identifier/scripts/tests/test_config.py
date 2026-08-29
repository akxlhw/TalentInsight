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


def test_exploration_merges_across_layers(tmp_path, monkeypatch):
    monkeypatch.delenv("AI4TALENT_API_KEY", raising=False)
    skill_dir, cwd = tmp_path / "skill", tmp_path / "cwd"
    skill_dir.mkdir(); cwd.mkdir()
    (skill_dir / "ai4talent.config.json").write_text(
        json.dumps({"exploration": {"max_searches": 10}}), encoding="utf-8")
    (cwd / "ai4talent.config.json").write_text(
        json.dumps({"exploration": {"max_fetches": 8}}), encoding="utf-8")
    cfg = config.load_config(skill_dir, cwd)
    assert cfg["exploration"] == {"max_searches": 10, "max_fetches": 8}


def test_env_overrides(tmp_path, monkeypatch):
    skill_dir, cwd = tmp_path / "skill", tmp_path / "cwd"
    skill_dir.mkdir(); cwd.mkdir()
    monkeypatch.setenv("AI4TALENT_API_KEY", "sk-123")
    monkeypatch.setenv("AI4TALENT_BASE_URL", "http://other:9000/api/v1")
    cfg = config.load_config(skill_dir, cwd)
    assert cfg["api_key"] == "sk-123"
    assert cfg["base_url"] == "http://other:9000/api/v1"


def test_domains_not_aliased_to_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AI4TALENT_API_KEY", raising=False)
    monkeypatch.delenv("AI4TALENT_BASE_URL", raising=False)
    skill_dir, cwd = tmp_path / "skill", tmp_path / "cwd"
    skill_dir.mkdir(); cwd.mkdir()
    cfg = config.load_config(skill_dir, cwd)
    cfg["domains"].append("polluted")
    assert config.load_config(skill_dir, cwd)["domains"] == \
        ["academic", "open_source", "lab", "competition", "industry"]
