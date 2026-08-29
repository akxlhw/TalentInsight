"""T-score 评分模型（设计文档 §6）：候选集内归一化，各域子分 0-100。"""
import math
from datetime import datetime

ACADEMIC_WEIGHTS = {"h_index": 0.35, "cited_by": 0.35, "works": 0.15, "activity": 0.15}
OS_WEIGHTS = {"stars": 0.45, "followers": 0.35, "breadth": 0.20}
COMP_WEIGHTS = {"rating": 0.60, "rank_title": 0.25, "medals": 0.15}

# 顺序即优先级：复合词/长键必须在前（子串匹配，先命中先返回）
ROLE_RULES = [("faculty", 1.0), ("professor", 1.0), ("research scientist", 0.8),
              ("postdoc", 0.6), ("researcher", 0.8), ("alumni", 0.5),
              ("phd", 0.3), ("student", 0.3)]
# 顺序即优先级：复合词/长键必须在前（子串匹配，先命中先返回）
LAB_PRESTIGE = [("stanford ai lab", 1.0), ("mit csail", 1.0), ("csail", 1.0),
                ("deepmind", 1.0), ("fair", 1.0), ("meta ai", 1.0), ("openai", 1.0),
                ("anthropic", 1.0), ("microsoft research", 1.0), ("msr", 1.0), ("bair", 1.0),
                ("智源", 0.85), ("tsinghua", 0.85), ("清华", 0.85)]
# 顺序即优先级：复合词/长键必须在前（子串匹配，先命中先返回）
RANK_TITLE_SCORES = [("legendary", 1.0), ("international grandmaster", 0.95),
                     ("grandmaster", 0.9), ("international master", 0.8),
                     ("candidate master", 0.6), ("master", 0.7), ("expert", 0.5),
                     ("specialist", 0.4), ("pupil", 0.3), ("newbie", 0.2)]
# 顺序即优先级：复合词/长键必须在前（子串匹配，先命中先返回）
TITLE_RULES = [("distinguished", 1.0), ("fellow", 1.0), ("chief", 0.9),
               ("principal", 0.95), ("staff", 0.85), ("lead", 0.75),
               ("senior", 0.7), ("junior", 0.3)]
# 顺序即优先级：复合词/长键必须在前（子串匹配，先命中先返回）
ORG_PRESTIGE = [("openai", 1.0), ("anthropic", 1.0), ("deepmind", 1.0), ("google", 1.0),
                ("meta", 1.0), ("microsoft", 1.0), ("nvidia", 1.0), ("bytedance", 0.95),
                ("字节", 0.95), ("alibaba", 0.9), ("阿里", 0.9), ("tencent", 0.9),
                ("腾讯", 0.9), ("huawei", 0.9), ("华为", 0.9), ("baidu", 0.85), ("百度", 0.85)]


def _lognorm(values: list[float]) -> list[float]:
    vals = [math.log(v + 1) for v in values]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


def _first_match(rules, text, default):
    s = (text or "").lower()
    for key, w in rules:
        if key in s:
            return w
    return default


def _role_weight(role_section, role_type):
    return _first_match(ROLE_RULES, f"{role_section or ''} {role_type or ''}", 0.6)


def _lab_prestige(lab_name):
    return _first_match(LAB_PRESTIGE, str(lab_name or ""), 0.7)


def _rank_title_score(rank_title):
    return _first_match(RANK_TITLE_SCORES, rank_title, 0.3)


def _title_weight(title):
    return _first_match(TITLE_RULES, str(title or ""), 0.5)


def _org_prestige(org):
    return _first_match(ORG_PRESTIGE, str(org or ""), 0.6)


def _activity(year):
    if not year:
        return 0.3
    try:
        lag = max(0, datetime.now().year - int(year))
    except (TypeError, ValueError):
        return 0.3  # 非法年份 → 保守值
    return max(0.0, 1.0 - lag / 5.0)


def _industry_weights(has_match: bool):
    if has_match:
        return {"org": 0.5, "title": 0.3, "match": 0.2}
    return {"org": 0.625, "title": 0.375, "match": 0.0}


def score_academic(profiles):
    """学术域子分：h/引用/作品 log 归一 + 活跃度衰减。"""
    rows = [p for p in profiles if "academic" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["academic"] for p in rows]
    h = _lognorm([it.get("h_index") or 0 for it in items])
    c = _lognorm([it.get("cited_by_count") or 0 for it in items])
    w = _lognorm([it.get("works_count") or 0 for it in items])
    out = {}
    for i, p in enumerate(rows):
        comps = {"h_index": h[i], "cited_by": c[i], "works": w[i],
                 "activity": _activity(items[i].get("latest_active_year"))}
        out[p["person_id"]] = {"sub": 100 * sum(
            ACADEMIC_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_open_source(profiles):
    """开源域子分：star/粉丝 log 归一 + 语言广度。"""
    rows = [p for p in profiles if "open_source" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["open_source"] for p in rows]
    stars = _lognorm([it.get("total_stars_received") or 0 for it in items])
    foll = _lognorm([it.get("followers_count") or 0 for it in items])
    langs = [it.get("primary_languages") or [] for it in items]
    breadth = _lognorm([len(l) for l in langs])
    out = {}
    for i, p in enumerate(rows):
        comps = {"stars": stars[i], "followers": foll[i], "breadth": breadth[i]}
        out[p["person_id"]] = {"sub": 100 * sum(
            OS_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_lab(profiles):
    """实验室域子分：角色权重 × 实验室声望；角色与实验室信息全缺则不参与。"""
    out = {}
    for p in profiles:
        it = p["records"].get("lab")
        if not it:
            continue
        has_role = bool(it.get("role_section") or it.get("role_type"))
        has_lab = bool(it.get("lab_name") or it.get("parent_lab"))
        if not has_role and not has_lab:
            continue  # 指标全缺的域不参与计算
        rw = _role_weight(it.get("role_section"), it.get("role_type"))
        pr = _lab_prestige(it.get("lab_name") or it.get("parent_lab"))
        comps = {"role_weight": rw, "lab_prestige": pr}
        out[p["person_id"]] = {"sub": 100 * rw * pr, "components": comps}
    return out


def score_competition(profiles):
    """竞赛域子分：rating log 归一（max 优先，缺失回退 current）+ 段位 + 奖牌复合式。"""
    rows = [p for p in profiles if "competition" in p["records"]]
    if not rows:
        return {}
    items = [p["records"]["competition"] for p in rows]
    rating = _lognorm([it.get("max_rating") or it.get("current_rating") or 0 for it in items])
    medals = _lognorm([(it.get("medals_gold") or 0) * 3 + (it.get("medals_silver") or 0) * 2
                       + (it.get("medals_bronze") or 0) for it in items])
    out = {}
    for i, p in enumerate(rows):
        rt = _rank_title_score(items[i].get("rank_title"))
        comps = {"rating": rating[i], "rank_title": rt, "medals": medals[i]}
        out[p["person_id"]] = {"sub": 100 * sum(
            COMP_WEIGHTS[k] * comps[k] for k in comps), "components": comps}
    return out


def score_industry(profiles):
    """行业域子分：org 声望 + 职级权重（有 match_score/best_match_score 时三项加权）；
    org/title 全缺则不参与。后端字段是 best_match_score，match_score 优先、缺失回退。"""
    rows = [p for p in profiles if "industry" in p["records"]]
    if not rows:
        return {}
    out = {}
    for p in rows:
        it = p["records"]["industry"]
        if not it.get("current_org") and not it.get("current_title"):
            continue  # 指标全缺的域不参与计算
        match = it.get("match_score") if it.get("match_score") is not None \
            else it.get("best_match_score")
        has_match = match is not None  # 0 值视为「有 match 且为 0」
        wts = _industry_weights(has_match)
        comps = {"org": _org_prestige(it.get("current_org")),
                 "title": _title_weight(it.get("current_title")),
                 "match": (match or 0) / 100.0 if has_match else 0.0}
        out[p["person_id"]] = {"sub": 100 * sum(wts[k] * comps[k] for k in comps),
                               "components": comps}
    return out


def compute_scores(profiles: list[dict]) -> list[dict]:
    """profiles → 按序榜单行（t_score 降序、null 尾置、rank 1..n）。"""
    per_domain = {"academic": score_academic(profiles),
                  "open_source": score_open_source(profiles),
                  "lab": score_lab(profiles),
                  "competition": score_competition(profiles),
                  "industry": score_industry(profiles)}
    rows = []
    for p in profiles:
        domain_scores, components = {}, {}
        for dom, table in per_domain.items():
            if p["person_id"] in table:
                domain_scores[dom] = round(table[p["person_id"]]["sub"], 1)
                components[dom] = {k: round(v, 3) for k, v
                                   in table[p["person_id"]]["components"].items()}
        if domain_scores:
            subs = list(domain_scores.values())
            if len(subs) == 1:
                t = subs[0]
            else:
                top = max(subs)
                rest_mean = (sum(subs) - top) / (len(subs) - 1)
                t = min(100.0, 0.7 * top + 0.3 * rest_mean + min(10, 5 * (len(subs) - 1)))
            t_score = round(t, 1)
        else:
            t_score = None
        rows.append({"person_id": p["person_id"], "name": p.get("name") or "",
                     "t_score": t_score, "domain_scores": domain_scores,
                     "score_components": components,
                     "linked_domains": p.get("linked_domains", [])})
    rows.sort(key=lambda r: (r["t_score"] is None, -(r["t_score"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
