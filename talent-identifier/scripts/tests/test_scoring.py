from talent_identifier import scoring


def _prof(pid, name, **domains):
    return {"person_id": pid, "name": name,
            "records": domains, "linked_domains": list(domains)}


def test_lognorm_bounds_and_flat():
    assert scoring._lognorm([0, 0]) == [0.5, 0.5]
    out = scoring._lognorm([0, 10, 100])
    assert out[0] == 0.0 and out[2] == 1.0 and 0 < out[1] < 1


def test_academic_weights_sum_to_one():
    comps = scoring.ACADEMIC_WEIGHTS
    assert abs(sum(comps.values()) - 1.0) < 1e-9


def test_single_domain_tscore_equals_subscore():
    profs = [_prof("p1", "A", academic={"h_index": 50, "cited_by_count": 10000,
                                        "works_count": 100, "latest_active_year": 2026}),
             _prof("p2", "B", academic={"h_index": 5, "cited_by_count": 100,
                                        "works_count": 10, "latest_active_year": 2020})]
    rows = scoring.compute_scores(profs)
    assert rows[0]["t_score"] == rows[0]["domain_scores"]["academic"]
    assert rows[0]["rank"] == 1 and rows[0]["person_id"] == "p1"


def test_cross_domain_bonus_formula():
    profs = [_prof("p1", "A",
                   academic={"h_index": 50, "cited_by_count": 9999, "works_count": 50,
                             "latest_active_year": 2026},
                   open_source={"total_stars_received": 50000, "followers_count": 5000,
                                "primary_languages": ["Python", "C++", "Rust", "Go"]}),
             _prof("p2", "B", academic={"h_index": 10, "cited_by_count": 100,
                                        "works_count": 5, "latest_active_year": 2026})]
    rows = scoring.compute_scores(profs)
    p1 = rows[0]
    expected = min(100.0, 0.7 * max(p1["domain_scores"].values())
                   + 0.3 * (sum(p1["domain_scores"].values()) - max(p1["domain_scores"].values()))
                   + 5)
    assert p1["t_score"] == round(expected, 1)


def test_cross_domain_cap_reached():
    # 三域全部拉满：0.7*100 + 0.3*100 + 10 = 110 → 截断 100（cap 真正触发）
    profs = [_prof("p1", "A",
                   academic={"h_index": 50, "cited_by_count": 9999, "works_count": 50,
                             "latest_active_year": 2026},
                   open_source={"total_stars_received": 50000, "followers_count": 5000,
                                "primary_languages": ["Python", "C++", "Rust", "Go"]},
                   competition={"max_rating": 3000, "medals_gold": 3,
                                "rank_title": "Legendary Grandmaster"}),
             _prof("p2", "B",
                   academic={"h_index": 1, "cited_by_count": 1, "works_count": 1,
                             "latest_active_year": 2026},
                   open_source={"total_stars_received": 1, "followers_count": 1,
                                "primary_languages": ["Python"]},
                   competition={"max_rating": 1000, "medals_gold": 0,
                                "rank_title": "newbie"})]
    rows = scoring.compute_scores(profs)
    p1 = rows[0]
    assert set(p1["domain_scores"]) == {"academic", "open_source", "competition"}
    assert all(v == 100.0 for v in p1["domain_scores"].values())
    assert p1["t_score"] == 100.0 and p1["rank"] == 1


def test_no_metrics_null_and_ranked_last():
    # p2 无任何 records → 无可评分信号 → t_score=None 且尾置
    profs = [_prof("p1", "A", academic={"h_index": 10, "cited_by_count": 100,
                                        "works_count": 5, "latest_active_year": 2026}),
             _prof("p2", "B")]
    rows = scoring.compute_scores(profs)
    null_row = next(r for r in rows if r["person_id"] == "p2")
    assert null_row["t_score"] is None
    assert rows[-1]["person_id"] == "p2"


def test_signal_less_domain_skipped():
    # 指标全缺的域不参与计算：空行业/实验室记录不产生子分
    profs = [_prof("p1", "A", industry={}),
             _prof("p2", "B", lab={}),
             _prof("p3", "C", industry={"current_org": "OpenAI"})]
    rows = scoring.compute_scores(profs)
    by = {r["person_id"]: r for r in rows}
    assert by["p1"]["t_score"] is None       # 空行业记录无信号 → 不参与
    assert by["p2"]["t_score"] is None       # 空实验室记录无信号 → 不参与
    assert "industry" in by["p3"]["domain_scores"]  # 仅有 org 也算有信号
    assert by["p3"]["rank"] == 1


def test_signal_less_academic_os_comp_skipped():
    # 指标全缺的学术/开源/竞赛记录不产生合成分（names 模式跨域搜索摘要无指标，必然触发）
    profs = [_prof("p1", "A", academic={}),
             _prof("p2", "B", open_source={}),
             _prof("p3", "C", competition={})]
    rows = scoring.compute_scores(profs)
    assert all(r["t_score"] is None for r in rows)


def test_partial_signal_scores_and_skipped_excluded_from_norm():
    # 部分信号仍评分（academic 仅 latest_active_year 也算有信号）；
    # 无信号者不进批量归一化列表——否则会以全 0 拉偏其他人的归一化分位
    profs = [_prof("p1", "A", academic={"h_index": 50, "cited_by_count": 9999,
                                        "works_count": 50}),
             _prof("p2", "B", academic={}),  # 无信号 → 跳过
             _prof("p3", "C", open_source={"primary_languages": ["Python", "Rust"]}),
             _prof("p4", "D", competition={"rank_title": "grandmaster"}),
             _prof("p5", "E", academic={"latest_active_year": 2026})]
    rows = scoring.compute_scores(profs)
    by = {r["person_id"]: r for r in rows}
    assert by["p2"]["t_score"] is None
    # p1/p5 参与学术归一化（p2 被排除）：p1 各 log 指标取满 1.0 而非被 0 值稀释
    assert by["p1"]["score_components"]["academic"]["h_index"] == 1.0
    assert "academic" in by["p5"]["domain_scores"]  # 仅活跃年份也算有信号
    assert "open_source" in by["p3"]["domain_scores"]
    assert "competition" in by["p4"]["domain_scores"]


def test_role_weight_postdoc_first():
    # 复合词优先：postdoc 必须先于 researcher 命中，否则被静默打高
    assert scoring._role_weight("Postdoctoral Researcher", "") == 0.6
    assert scoring._role_weight("Research Scientist", "") == 0.8
    assert scoring._role_weight("Researcher", "") == 0.8


def test_lab_role_and_prestige():
    assert scoring._role_weight("Faculty", "") == 1.0
    assert scoring._role_weight("PhD Students", "") == 0.3
    assert scoring._lab_prestige("OpenAI") == 1.0
    assert scoring._lab_prestige("北京智源人工智能研究院") == 0.85
    assert scoring._lab_prestige("Somewhere Lab") == 0.7


def test_rank_title_scores():
    assert scoring._rank_title_score("Legendary Grandmaster") == 1.0
    assert scoring._rank_title_score("master") == 0.7
    assert scoring._rank_title_score("newbie") == 0.2
    assert scoring._rank_title_score(None) == 0.3  # 缺失保守值


def test_competition_rating_fallback_and_medals():
    # pb 同时给 max/current：必须取 max_rating（若误用 current 则归一方向反转）
    profs = [_prof("pa", "A", competition={"current_rating": 2000, "medals_gold": 2,
                                           "medals_silver": 1, "medals_bronze": 1,
                                           "rank_title": "master"}),
             _prof("pb", "B", competition={"max_rating": 1000, "current_rating": 3000,
                                           "medals_gold": 0, "medals_silver": 0,
                                           "medals_bronze": 3, "rank_title": "expert"})]
    rows = scoring.compute_scores(profs)
    by = {r["person_id"]: r for r in rows}
    comps_a = by["pa"]["score_components"]["competition"]
    comps_b = by["pb"]["score_components"]["competition"]
    # rating：pa=2000(current 回退) > pb=1000(max 优先) → pa 1.0 / pb 0.0
    assert comps_a["rating"] == 1.0 and comps_b["rating"] == 0.0
    # 奖牌复合式 gold*3+silver*2+bronze*1：9 vs 3 → 1.0 / 0.0
    assert comps_a["medals"] == 1.0 and comps_b["medals"] == 0.0
    # 子分：pa = 100*(0.6*1.0 + 0.25*0.7 + 0.15*1.0) = 92.5
    assert by["pa"]["domain_scores"]["competition"] == 92.5
    assert by["pa"]["rank"] == 1


def test_industry_renormalize_without_match_score():
    w = scoring._industry_weights(has_match=False)
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_industry_reads_best_match_score():
    # 后端 industry 返回 best_match_score（无 match_score）：match=80 应走三因子权重路径
    profs = [_prof("p1", "A", industry={"current_org": "OpenAI",
                                        "current_title": "Principal",
                                        "best_match_score": 80})]
    rows = scoring.compute_scores(profs)
    by = {r["person_id"]: r for r in rows}
    w = scoring._industry_weights(has_match=True)
    expected = 100 * (w["org"] * 1.0 + w["title"] * 0.95 + w["match"] * 0.8)
    assert by["p1"]["domain_scores"]["industry"] == round(expected, 1)  # 94.5
    assert by["p1"]["score_components"]["industry"]["match"] == 0.8

    # best_match_score=0 视为「有 match 且为 0」，而非无 match（否则误走两因子权重）
    rows0 = scoring.compute_scores([_prof("p2", "B", industry={
        "current_org": "OpenAI", "current_title": "Principal", "best_match_score": 0})])
    by0 = {r["person_id"]: r for r in rows0}
    expected0 = 100 * (w["org"] * 1.0 + w["title"] * 0.95 + w["match"] * 0.0)
    assert by0["p2"]["domain_scores"]["industry"] == round(expected0, 1)  # 78.5，非两因子的 98.1
    assert by0["p2"]["score_components"]["industry"]["match"] == 0.0


def test_industry_with_match_score():
    profs = [_prof("p1", "A", industry={"current_org": "OpenAI",
                                        "current_title": "Research Scientist",
                                        "match_score": 100}),
             _prof("p2", "B", industry={"current_org": "OpenAI",
                                        "current_title": "Research Scientist",
                                        "match_score": 50})]
    rows = scoring.compute_scores(profs)
    by = {r["person_id"]: r for r in rows}
    wt = scoring._industry_weights(has_match=True)
    assert abs(sum(wt.values()) - 1.0) < 1e-9  # {org .5, title .3, match .2}
    # org=1.0 / title=0.5（默认）：p1 = 100*(.5*1+.3*.5+.2*1) = 85.0
    assert by["p1"]["domain_scores"]["industry"] == 85.0
    # p2 = 100*(.5*1+.3*.5+.2*.5) = 75.0
    assert by["p2"]["domain_scores"]["industry"] == 75.0
    assert by["p1"]["rank"] == 1
