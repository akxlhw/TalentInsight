from talent_identifier import normalize


def test_normalize_name():
    assert normalize.normalize_name("Andrew Y. Ng") == "andrewyng"
    assert normalize.normalize_name("吴翼") == "吴翼"
    assert normalize.normalize_name("  Yi-Wu ") == "yiwu"
    assert normalize.normalize_name(None) == ""


def test_normalize_org():
    assert normalize.normalize_org("DeepMind Inc.") == "deepmind"
    assert normalize.normalize_org("Tsinghua University") == "tsinghua"
    assert normalize.normalize_org("清华大学") == "清华"
    assert normalize.normalize_org("Meta Platforms, Inc.") == "meta platforms"
    assert normalize.normalize_org("") == ""


def test_normalize_url():
    assert normalize.normalize_url("https://www.YiWu.ai/") == "yiwu.ai"
    assert normalize.normalize_url("http://github.com/foo") == "github.com/foo"
    assert normalize.normalize_url("") == ""


def test_normalize_url_strips_query_fragment():
    assert normalize.normalize_url("https://yiwu.ai/?utm=x") == "yiwu.ai"
    assert normalize.normalize_url("https://yiwu.ai/#bio") == "yiwu.ai"
    assert normalize.normalize_url("https://yiwu.ai/path?q=1") == "yiwu.ai/path"


def test_normalize_org_cn_suffix_loop():
    assert normalize.normalize_org("阿里巴巴有限公司") == "阿里巴巴"
    assert normalize.normalize_org("某某集团股份有限公司") == "某某"
    assert normalize.normalize_org("清华大学") == "清华"  # 原行为不回归
    assert normalize.normalize_org("北京智源人工智能研究院") == "北京智源人工智能"
