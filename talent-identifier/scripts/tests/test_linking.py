from talent_identifier import linking


def _rec(domain, **kw):
    base = {"name": kw.get("name", "Yi Wu"), "domain": domain}
    base.update({k: v for k, v in kw.items() if k != "name"})
    return base


def test_high_confidence_merge_on_github():
    records = [
        _rec("open_source", github_login="yiwu", name="Yi Wu", company="OpenAI"),
        _rec("academic", name="Yi Wu", homepage="https://yiwu.ai", email="a@b.c",
             education_school="OpenAI"),
        _rec("lab", name="Wu Yi", social_links={"github": "https://github.com/yiwu"}),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert set(profiles[0]["linked_domains"]) == {"open_source", "academic", "lab"}
    assert any(e["confidence"] == "high" for e in profiles[0]["link_evidence"])


def test_medium_confidence_merge_on_name_plus_org():
    records = [
        _rec("academic", name="Andrew Ng", education_school="Stanford University"),
        _rec("industry", name="Andrew Ng", current_org="Stanford"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert profiles[0]["link_evidence"][0]["confidence"] == "medium"
    assert "name+org" == profiles[0]["link_evidence"][0]["field"]


def test_no_merge_same_name_different_org():
    records = [
        _rec("academic", name="Wei Li", education_school="Tsinghua University"),
        _rec("open_source", name="Wei Li", company="Alibaba"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    assert all(not p.get("suspected_same_person") for p in profiles)


def test_low_hint_only_when_tags_overlap():
    records = [
        _rec("academic", name="Wei Li", education_school="Tsinghua", topic_tags=["llm", "rl"]),
        _rec("open_source", name="Wei Li", tech_tags="llm, cuda"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    hinted = [p for p in profiles if p.get("suspected_same_person")]
    assert len(hinted) == 2
    assert hinted[0]["suspected_same_person"][0]["basis"] == "name+tags"


def test_no_merge_when_both_orgs_unknown():
    records = [
        _rec("academic", name="Yi Wu"),
        _rec("open_source", name="Yi Wu"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2   # 机构未知时仅凭名字不合并


def test_same_domain_records_never_merge():
    records = [
        _rec("academic", name="Yi Wu", education_school="A"),
        _rec("academic", name="Yi Wu", education_school="B"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2


def test_person_id_collision_suffix():
    records = [
        _rec("academic", name="Yi Wu", education_school="A"),
        _rec("open_source", name="Yi Wu", company="B"),
    ]
    profiles = linking.link_records(records)
    ids = sorted(p["person_id"] for p in profiles)
    assert ids[0].startswith("p_")
    assert ids[0] != ids[1]


def test_tags_flatten():
    r = linking._record_identity({"name": "X", "topic_tags": ["LLM", "RL", 42],
                                  "research_areas": "llm, agents"})
    assert "llm" in r["tags"] and "rl" in r["tags"] and "agents" in r["tags"]
    assert "42" in r["tags"]  # 非字符串元素不崩


def test_transitive_same_domain_conflict_skips_merge():
    records = [
        _rec("open_source", github_login="shared", name="A One"),
        _rec("academic", github_login="shared", name="A One", education_school="X"),
        _rec("academic", github_login="shared", name="A Two", education_school="X"),
    ]
    profiles = linking.link_records(records)
    # 第二个 academic 与 open_source 组有同域冲突 → 保守不并
    assert len(profiles) == 2
    assert all(len(p["records"]) == len(p["linked_domains"]) for p in profiles)


def test_transitive_github_then_org_nested_shape():
    records = [
        {"domain": "open_source", "item": {"name": "Yi Wu", "github_login": "yiwu",
                                           "company": "OpenAI"}},
        {"domain": "academic", "item": {"name": "Yi Wu", "github_login": "yiwu",
                                        "education_school": "OpenAI"}},
        {"domain": "industry", "item": {"name": "Yi Wu", "current_org": "OpenAI"}},
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert set(profiles[0]["linked_domains"]) == {"open_source", "academic", "industry"}
    assert profiles[0]["records"]["academic"]["education_school"] == "OpenAI"
    assert {e["confidence"] for e in profiles[0]["link_evidence"]} == {"high", "medium"}


def test_strong_merge_on_email_and_orcid():
    records = [
        _rec("academic", name="A B", email="same@x.io"),
        _rec("industry", name="B A", email="SAME@X.IO"),
        _rec("competition", name="C D", orcid="0000-0002-1825-0097"),
        _rec("lab", name="D C", orcid="0000-0002-1825-0097"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    assert {e["field"] for p in profiles for e in p["link_evidence"]} == {"email", "orcid"}


def test_cn_name_medium_merge():
    records = [
        _rec("academic", name="吴翼", education_school="清华大学"),
        _rec("industry", name="吴翼", current_org="清华大学"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1
    assert profiles[0]["link_evidence"][0]["field"] == "name+org"
    assert profiles[0]["link_evidence"][0]["confidence"] == "medium"


def test_low_hint_dedup_by_person_id():
    records = [
        _rec("academic", name="Wei Li", orcid="0000-1", topic_tags=["llm", "rl"]),
        _rec("competition", name="Wei Li", orcid="0000-1", topic_tags=["llm", "rl"]),
        _rec("open_source", name="Wei Li", tech_tags="llm, cuda"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    for p in profiles:
        targets = [h["person_id"] for h in p["suspected_same_person"]]
        assert len(targets) == len(set(targets))


def test_low_hint_suppressed_when_orgs_conflict():
    records = [
        _rec("academic", name="Wei Li", education_school="Tsinghua", topic_tags=["llm", "rl"]),
        _rec("open_source", name="Wei Li", company="Startup", tech_tags="llm, cuda"),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 2
    assert all(not p.get("suspected_same_person") for p in profiles)


def test_record_identity_reads_real_name():
    # 后端 competition 域人名只有 real_name：name/cn_name 提取链需覆盖（name_en 仍优先）
    ident = linking._record_identity({"real_name": "Gennady Korotkevich"})
    assert ident["name"] == "gennadykorotkevich"  # 归一化非空
    assert ident["cn_name"] == "gennadykorotkevich"


def test_github_match_case_insensitive():
    records = [
        _rec("open_source", github_login="yiwu"),
        _rec("lab", github="https://GitHub.com/yiwu/"),
        _rec("competition", social_links={"github": "https://GITHUB.com/yiwu"}),
    ]
    profiles = linking.link_records(records)
    assert len(profiles) == 1


def test_profile_name_falls_back_to_real_name():
    # 竞赛域记录只有 real_name：画像展示名组装链需回退，否则 name 为空串
    profiles = linking.link_records(
        [{"domain": "competition",
          "item": {"real_name": "Gennady Korotkevich", "handle": "tourist",
                   "max_rating": 3900, "rank_title": "Legendary Grandmaster"}}])
    assert profiles[0]["name"] == "Gennady Korotkevich"
    assert profiles[0]["person_id"].startswith("p_")
