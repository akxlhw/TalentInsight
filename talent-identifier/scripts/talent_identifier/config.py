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
    cfg["domains"] = list(DEFAULT_CONFIG["domains"])
    for path in (skill_dir / "ai4talent.config.json", cwd / "ai4talent.config.json"):
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            merged_exploration = {**cfg["exploration"], **loaded.get("exploration", {})}
            cfg.update(loaded)
            cfg["exploration"] = merged_exploration
    if os.environ.get("AI4TALENT_API_KEY"):
        cfg["api_key"] = os.environ["AI4TALENT_API_KEY"]
    if os.environ.get("AI4TALENT_BASE_URL"):
        cfg["base_url"] = os.environ["AI4TALENT_BASE_URL"]
    return cfg
