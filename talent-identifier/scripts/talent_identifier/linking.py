"""跨域身份关联：DSU 合并 + high/medium/low 三档置信度。

规则（设计文档 §7）：
- high   ：homepage / github / orcid / email 任一相同 → 合并
- medium ：规范化名字相同 + 规范化机构相同 → 合并（机构未知不合并）
- low    ：仅名字相同 + 标签重叠(Jaccard>0.2) → 不合并，仅 suspected_same_person 提示
          （双方机构已知且不同则抑制提示）
- 同域两条记录永不合并；传递合并若会使组内出现同域冲突，放弃该次合并
  （保守方向：宁可漏合并，防止 records 按域键覆盖而丢数据）
"""
import hashlib

from .normalize import normalize_name, normalize_org, normalize_url

STRONG_KEYS = ("homepage", "github", "orcid", "email")
DOMAIN_PRIORITY = ("academic", "lab", "open_source", "competition", "industry")


def _item_of(rec: dict) -> dict:
    """兼容 {domain, item} 嵌套与字段平铺两种记录形态。"""
    item = rec.get("item")
    return item if isinstance(item, dict) else rec


def _first_social_github(social) -> str:
    if isinstance(social, list):
        values = [str(v) for v in social]
    elif isinstance(social, dict):
        values = [str(v) for v in social.values()]
    else:
        return ""
    for v in values:
        lv = v.lower()
        if "github.com/" in lv:
            login = lv.split("github.com/")[1].split("/")[0]
            return f"https://github.com/{login}"
    return ""


def _canonical_github(item: dict) -> str:
    github = item.get("github_login") or item.get("github") or ""
    if not github:
        github = _first_social_github(item.get("social_links"))
    # 裸 login（如 "yiwu"）补全为 URL 形态，与 social_links 中的主页链接可比
    if github and "github.com/" not in github.lower():
        github = f"https://github.com/{github}"
    return normalize_url(github)


def _flatten_tags(item: dict) -> set[str]:
    tags: set[str] = set()
    # "tags"：跨域搜索摘要（UnifiedTalentSummary）的标签键
    for key in ("topic_tags", "tech_tags", "research_areas", "tags"):
        val = item.get(key)
        if isinstance(val, list):
            entries = val
        elif isinstance(val, str):
            entries = val.replace("，", ",").split(",")
        else:
            continue
        for v in entries:
            tag = normalize_name(str(v))
            if tag:
                tags.add(tag)
    return tags


def _record_identity(item: dict) -> dict:
    org = (item.get("education_school") or item.get("company_school")
           or item.get("school") or item.get("current_org")
           or item.get("company") or item.get("lab_name") or "")
    return {
        # name 链 name_en > name > real_name；cn_name 链 name > real_name
        #（后端 competition 域人名只有 real_name）
        "name": normalize_name(item.get("name_en") or item.get("name")
                               or item.get("real_name") or ""),
        "cn_name": normalize_name(item.get("name") or item.get("real_name") or ""),
        # url 回退：跨域搜索摘要无 homepage，主页字段叫 url（可触发 high 合并）
        "homepage": normalize_url(item.get("homepage") or item.get("url") or ""),
        "github": _canonical_github(item),
        "orcid": (item.get("orcid") or "").lower().strip(),
        "email": (item.get("email") or "").lower().strip(),
        "org": normalize_org(str(org)),
        "tags": _flatten_tags(item),
    }


class _DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _append_hint(profile: dict, person_id: str) -> None:
    """按 person_id 去重地追加 suspected_same_person 提示。"""
    hints = profile.setdefault("suspected_same_person", [])
    if all(h["person_id"] != person_id for h in hints):
        hints.append({"person_id": person_id, "basis": "name+tags"})


def link_records(records: list[dict]) -> list[dict]:
    """records: [{domain, item}]（item 字段平铺在记录上亦可）→ 统一画像列表。"""
    n = len(records)
    ids = [_record_identity(_item_of(r)) for r in records]
    dsu = _DSU(n)
    # 与 DSU 并行维护：每个连通分量已包含的域集合（防止传递合并造成同域覆盖）
    comp_domains = [{records[i].get("domain", "")} for i in range(n)]
    evidence: dict[tuple[int, int], dict] = {}
    low_pairs: list[tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            if records[i].get("domain") == records[j].get("domain"):
                continue
            a, b = ids[i], ids[j]
            strong = next((k for k in STRONG_KEYS
                           if a[k] and a[k] == b[k]), None)
            names_equal = (a["name"] and a["name"] == b["name"]) or \
                          (a["cn_name"] and a["cn_name"] == b["cn_name"])
            if strong or (names_equal and a["org"] and a["org"] == b["org"]):
                ri, rj = dsu.find(i), dsu.find(j)
                if comp_domains[ri] & comp_domains[rj]:
                    continue  # 组间同域冲突：保守放弃合并，不记 evidence
                dsu.union(i, j)
                comp_domains[dsu.find(i)] = comp_domains[ri] | comp_domains[rj]
                if strong:
                    evidence[(i, j)] = {"field": strong, "value": a[strong],
                                        "confidence": "high"}
                else:
                    evidence[(i, j)] = {"field": "name+org",
                                        "value": f'{a["name"] or a["cn_name"]}@{a["org"]}',
                                        "confidence": "medium"}
                continue
            if names_equal and a["tags"] and b["tags"]:
                # 双方机构已知且不同：明显不同的人，不给"疑似同一人"提示
                if a["org"] and b["org"] and a["org"] != b["org"]:
                    continue
                jac = len(a["tags"] & b["tags"]) / len(a["tags"] | b["tags"])
                if jac > 0.2:
                    low_pairs.append((i, j))

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(dsu.find(idx), []).append(idx)

    profiles = []
    by_member: dict[int, dict] = {}
    for members in groups.values():
        members.sort(key=lambda i: DOMAIN_PRIORITY.index(records[i].get("domain", ""))
                     if records[i].get("domain", "") in DOMAIN_PRIORITY else 99)
        lead = members[0]
        lead_item = _item_of(records[lead])
        profile = {
            # 展示名链 name > name_en > real_name（竞赛域记录只有 real_name）
            "name": lead_item.get("name") or lead_item.get("name_en")
            or lead_item.get("real_name") or "",
            "name_en": lead_item.get("name_en") or "",
            "records": {records[m].get("domain", ""): _item_of(records[m]) for m in members},
            "linked_domains": [records[m].get("domain", "") for m in members],
            # 仅枚举 i<j 的成员对，避免同一条证据重复出现
            "link_evidence": [evidence[(i, j)]
                              for i in members for j in members
                              if i < j and (i, j) in evidence],
            "suspected_same_person": [],
        }
        ident = ids[lead]
        profile["org"] = next((ids[m]["org"] for m in members if ids[m]["org"]), "")
        profile["homepage"] = ident["homepage"]
        profile["github"] = ident["github"]
        profile["orcid"] = ident["orcid"]
        profile["email"] = ident["email"]
        profile["tags"] = sorted({t for m in members for t in ids[m]["tags"]})
        profiles.append(profile)
        for m in members:
            by_member[m] = profile

    # person_id：规范化姓名哈希；冲突追加序号
    seen: dict[str, int] = {}
    for p in profiles:
        key = normalize_name(p["name_en"] or p["name"])
        base = "p_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
        seen[base] = seen.get(base, 0) + 1
        p["person_id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"

    for i, j in low_pairs:
        if dsu.find(i) != dsu.find(j):
            _append_hint(by_member[i], by_member[j]["person_id"])
            _append_hint(by_member[j], by_member[i]["person_id"])

    return profiles
