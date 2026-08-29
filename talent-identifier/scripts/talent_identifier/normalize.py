"""身份关联用的规范化函数。"""
import re

_PUNCT = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")
_ORG_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "lp", "corp", "corporation",
    "co", "company", "holdings", "university", "univ", "college", "group", "labs",
    "大学", "学院", "公司", "研究院",
}
_CN_ORG_SUFFIXES = ("有限责任公司", "股份有限公司", "有限公司", "研究院", "大学", "学院", "公司", "集团")  # 最长优先
# 已知跟踪参数白名单：仅当 query 全部参数都在白名单内时才整体剥除，
# 身份参数（如 scholar 的 ?user=xxx）必须保留，防止高置信误合并
_TRACKING_PARAM = re.compile(r"^(utm(_\w+)?|fbclid|gclid|ref|source|spm|igshid|si)$")


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
    # 中文后缀循环剥离（无空格分词，需字符串级处理；整词即后缀的情形由上面的
    # 英文 while 处理（"公司"等在 _ORG_SUFFIXES 中），len 守卫防止剥空）
    while tokens:
        last = tokens[-1]
        for suf in _CN_ORG_SUFFIXES:
            if last.endswith(suf) and len(last) > len(suf):
                tokens[-1] = last[: -len(suf)]
                break
        else:
            break
    return " ".join(tokens)


def normalize_url(u: str | None) -> str:
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = re.sub(r"#.*$", "", u)  # fragment 始终剥除
    qpos = u.find("?")
    if qpos != -1:
        base, query = u[:qpos], u[qpos + 1:]
        params = [p.split("=")[0] for p in query.split("&") if p]
        if params and all(_TRACKING_PARAM.match(p) for p in params):
            u = base  # 全为跟踪参数才剥 query
    return u.rstrip("/")
