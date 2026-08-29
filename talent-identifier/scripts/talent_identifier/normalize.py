"""身份关联用的规范化函数。"""
import re

_PUNCT = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")
_ORG_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "lp", "corp", "corporation",
    "co", "company", "holdings", "university", "univ", "college",
    "大学", "学院", "公司", "研究院",
}
_CN_ORG_SUFFIXES = ("研究院", "大学", "学院", "公司")  # 最长优先


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    return _PUNCT.sub("", s.lower())


def normalize_org(s: str | None) -> str:
    if not s:
        return ""
    tokens = _PUNCT.sub(" ", s.lower()).split()
    while tokens and tokens[-1] in _ORG_SUFFIXES:
        tokens.pop()
    # 中文机构名无空格分词，整词匹配不到后缀（如“清华大学”），需按字符串后缀剥离
    if tokens:
        for suffix in _CN_ORG_SUFFIXES:
            if tokens[-1].endswith(suffix) and len(tokens[-1]) > len(suffix):
                tokens[-1] = tokens[-1][: -len(suffix)]
                break
    return " ".join(tokens)


def normalize_url(u: str | None) -> str:
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")
