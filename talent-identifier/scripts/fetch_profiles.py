#!/usr/bin/env python3
"""阶段1：从 AI4TALENT Open API 拉取候选人才并做跨域关联，产出 profiles.jsonl。

用法:
  python scripts/fetch_profiles.py --mode domain --keyword "大模型推理优化" [--domains academic,lab]
  python scripts/fetch_profiles.py --mode names --names "张三,李四" | --names-file names.txt
选项: --out <dir>(默认 ./output)  --resume(跳过已完成阶段)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from talent_identifier import api_client, config, io_utils, linking
from talent_identifier.normalize import normalize_name


def _make_person_id(name: str) -> str:
    return "p_" + hashlib.sha256(normalize_name(name).encode("utf-8")).hexdigest()[:8]


def _client_side_filter(items: list[dict], keyword: str) -> list[dict]:
    kw = keyword.lower()
    return [it for it in items
            if kw in json.dumps(it, ensure_ascii=False).lower()]


def _fetch_domain(client, domain: str, keyword: str, limit: int):
    """带兜底：keyword 参数被拒时降级为无条件拉取 + 本地过滤。

    两种触发：4xx（HTTPStatusError，keyword 参数被后端拒绝）/
    传输错误与 5xx 重试耗尽（ApiUnreachable）；兜底调用也失败则记缺口继续。
    """
    try:
        return client.list_domain(domain, {"keyword": keyword}, limit), None
    except api_client.httpx.HTTPStatusError:
        # 4xx：keyword 参数被拒时降级为无条件拉取+本地过滤
        try:
            items = client.list_domain(domain, {}, limit)
        except Exception as e:  # 兜底也失败 → 记缺口继续
            return [], f"fallback: {e}"
        return _client_side_filter(items, keyword), None
    except api_client.ApiUnreachable:
        try:
            items = client.list_domain(domain, {}, limit)
        except Exception as e:  # 兜底也失败 → 记缺口继续
            return [], f"fallback: {e}"
        return _client_side_filter(items, keyword), None
    except Exception as e:  # 单域失败不阻塞
        return [], str(e)


def _name_matches(query_norm: str, item: dict) -> bool:
    for key in ("name", "name_en"):
        n = normalize_name(item.get(key))
        if n and (n == query_norm or n in query_norm or query_norm in n):
            return True
    return False


def _has_contact(p: dict) -> bool:
    if p.get("homepage") or p.get("github") or p.get("email"):
        return True
    for it in p.get("records", {}).values():
        if not isinstance(it, dict):
            continue
        if it.get("homepage") or it.get("github") or it.get("github_login") \
                or it.get("email") or it.get("social_links"):
            return True
    return False


def _finalize(profiles: list[dict], run_dir: Path, mode: str) -> None:
    for p in profiles:
        p["in_library"] = bool(p.get("records"))
        p["contact_info_unavailable"] = not _has_contact(p)
        p["collected_at"] = io_utils.utc_now()
        if not p.get("suspected_same_person"):
            p.pop("suspected_same_person", None)
    io_utils.write_jsonl(run_dir / "profiles.jsonl", profiles)
    io_utils.mark_stage(run_dir, "fetch", run_id=run_dir.name, mode=mode)


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["domain", "names"], required=True)
    ap.add_argument("--keyword")
    ap.add_argument("--domains", help="逗号分隔，默认全部五域")
    ap.add_argument("--names")
    ap.add_argument("--names-file")
    ap.add_argument("--out", default="output")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)

    skill_dir = Path(__file__).resolve().parent.parent
    cfg = config.load_config(skill_dir, Path.cwd())
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else cfg["domains"]

    if args.mode == "domain" and not args.keyword:
        print("ERROR: --mode domain 需要 --keyword", file=sys.stderr)
        return 1
    names = []
    if args.mode == "names":
        if args.names_file:
            if not Path(args.names_file).exists():
                print(f"ERROR: --names-file 不存在: {args.names_file}", file=sys.stderr)
                return 1
            names = [l.strip() for l in
                     Path(args.names_file).read_text(encoding="utf-8").splitlines() if l.strip()]
        elif args.names:
            names = [n.strip() for n in args.names.split(",") if n.strip()]
        names = list(dict.fromkeys(names))  # 去重，防重复名产生同 person_id 双画像
        if not names:
            print("ERROR: --mode names 需要 --names 或 --names-file", file=sys.stderr)
            return 1

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    if args.resume:
        candidates = sorted([d for d in out_root.iterdir() if d.is_dir()], reverse=True)
        run_dir = next((d for d in candidates
                        if "fetch" in io_utils.load_state(d)["stages_done"]), None)
        if run_dir:
            print(f"[resume] 跳过 fetch：{run_dir}")
            return 0

    if client is None:
        client = api_client.OpenApiClient(cfg["base_url"], cfg["api_key"])
    if not client.health():
        print(f"ERROR: AI4TALENT 后端不可达（{cfg['base_url']}）。"
              f"请先启动后端，或用 AI4TALENT_BASE_URL 指定地址。", file=sys.stderr)
        return 2
    run_id, run_dir = io_utils.new_run_dir(out_root, args.mode,
                                           args.keyword if args.mode == "domain" else None)

    gaps: list[str] = []
    records: list[dict] = []
    if args.mode == "domain":
        for domain in domains:
            items, err = _fetch_domain(client, domain, args.keyword, cfg["per_domain_limit"])
            if err:
                gaps.append(domain)
                print(f"[gap] {domain}: {err}", file=sys.stderr)
            records += [{"domain": domain, "item": it} for it in items]
        profiles = linking.link_records(records)
    else:
        profiles = []
        for name in names:
            try:
                found = [it for it in client.cross_search(name, domains)
                         if _name_matches(normalize_name(name), it)]
            except Exception as e:
                print(f"[gap] 跨域搜索失败: {name}: {e}", file=sys.stderr)
                found = []
            if found:
                profiles += linking.link_records(
                    [{"domain": it.get("domain", "unknown"), "item": it} for it in found])
            else:
                profiles.append({"person_id": _make_person_id(name), "name": name,
                                 "name_en": "", "records": {}, "linked_domains": [],
                                 "link_evidence": [], "org": "", "homepage": "",
                                 "github": "", "orcid": "", "email": "", "tags": []})

    if gaps:
        (run_dir / "gaps.txt").write_text("\n".join(gaps) + "\n", encoding="utf-8")
    _finalize(profiles, run_dir, args.mode)
    linked = sum(1 for p in profiles if len(p.get("linked_domains", [])) > 1)
    print(f"[fetch] run={run_id} 人数={len(profiles)} 跨域合并={linked} 缺口域={gaps or '无'}")
    print(f"[fetch] 产物: {run_dir / 'profiles.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
