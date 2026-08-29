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
