# Open API 对接契约

AI4TALENT Open API 是本 skill 唯一的数据来源（阶段1 拉取）。本文档描述 `scripts/talent_identifier/api_client.py` 与 `scripts/fetch_profiles.py` 依赖的接口语义。

## 认证

- 所有请求带 `X-API-Key: <key>` 请求头。
- Key 由 AI4TALENT **super_admin** 在「系统配置 → API Key 管理」创建；明文仅创建时展示一次。
- 每个 Key 绑定一组 scope（域 × 读/写）。本 skill 只读，需要各目标域的 `<域>:read`（如 `academic:read`、`open-source:read`、`lab:read`、`competition:read`、`industry:read`）。
- 错误语义：缺失/无效/已吊销 Key → `401`；Key 有效但缺所需 scope → `403`；超限流 → `429` + `Retry-After`。
- skill 侧配置：`ai4talent.config.json` 的 `api_key` / `base_url`，环境变量 `AI4TALENT_API_KEY`、`AI4TALENT_BASE_URL` 优先级更高。

## Base URL 与文档

- 默认 `http://localhost:8003/api/v1`（可用 `AI4TALENT_BASE_URL` 覆盖）。
- Swagger UI：`http://localhost:8003/docs`（"Open API — *" 分组）。
- 权威对接文档：`D:\AI\AI4TALENT\docs\open-api\01-agent-guide.md`（本文档与之冲突时以该文档 + 实际响应为准）。

## 端点一览

| 端点 | 说明 |
|---|---|
| `GET /health` | 探活（无需鉴权）。fetch 前置检查，不可达直接 exit 2 |
| `GET /open-api/search/talents` | 跨域统一搜索：`keyword`（必填 1-200 字符）、`domains`（逗号分隔，缺省=全部已注册域）、`per_domain`（1-20，服务端默认 5，skill 端封顶 20）。响应 `{keyword, domains, unknown_domains, items, errors}`；每个请求域都要求对应 `<域>:read` |
| `GET /open-api/{domain}/talents` | 域列表。`domain` ∈ academic/open-source/lab/competition/industry；`page`≥1、`page_size` 1-100（默认 20）；各域另有筛选参数（如 `keyword`、`min_citations`、`min_stars`、`min_rating`、`rank_title`、`parent_lab`、`min_score` 等，见权威文档） |
| `GET /open-api/{domain}/talents/{id}` | 域详情（如竞赛含参赛史、学术含 selected_works） |
| `GET /open-api/{domain}/stats` | 域统计（industry 为岗位粒度） |

列表端点统一 envelope：`{"items": [...], "total": <int>, "page": <int>, "page_size": <int>}`。

## 客户端行为（api_client.py 实际语义）

- **重试**：429 / 5xx / 传输异常（`httpx.TransportError`）触发重试，共 3 次尝试，指数退避 1s/2s；耗尽后抛 `ApiUnreachable`。其他 4xx 不重试，立即抛 `httpx.HTTPStatusError`。
- **分页终止三条件**（任一满足即停）：本页 `items` 为空；累计条数 ≥ `total`（响应缺 `total` 时按累计数处理）；已拉满 `limit`。
- **跨域搜索防御性解析**：响应可能两种形态——顶层 `items` 列表，或「域名 → {items} / 域名 → []」的映射。解析规则：非 dict 载荷 → 空结果；映射形态下逐键取 `items`（或直接列表），非 list 丢弃；条目非 dict 丢弃；无 `domain`/`source_domain`/`source` 字段的条目标 `domain=unknown`；**无 `name` 且无 `real_name` 的条目丢弃**，仅有 `real_name` 的条目（competition 域）回填 `name` 后保留。
- **keyword 兜底**（fetch_profiles.py）：域列表带 `keyword` 被 4xx 拒绝或重试耗尽时，降级为无条件拉取 + 本地子串过滤（keyword 出现在整条 JSON 里即保留）；兜底也失败则记缺口继续跑，不阻塞其他域。

## 各域关键字段

| 域 | 字段 |
|---|---|
| academic | `name` `name_en` `orcid` `current_title` `role_type` `topic_tags` `works_count` `cited_by_count` `h_index`（列表即含）；详情另有 `latest_active_year` `education_school_name` `company_school_name` `lab_name` |
| open_source | `github_login` `name` `bio` `company` `email` `social_links` `blog_url` `followers_count` `public_repos_count` `total_stars_received` `primary_languages` `tech_tags` |
| lab | `name` `role_section` `role_type` `academic_level` `current_title` `homepage` `email` `department` `research_areas` `cohort_year` `lab_name` `parent_lab`（详情另有 `advisor` `co_advisor` `social_links`） |
| competition | `handle` `real_name` `school` `country_code` `current_rating` `max_rating` `rank_title` `contests_count` `medals_gold` `medals_silver` `medals_bronze`（注意：人名字段是 `real_name`，无 `name`） |
| industry | `name` `current_org` `current_title` `degree` `years_of_exp` `location` `best_match_score` `positions` |

## PII 与联系方式

- Open API 列表字段是各域白名单子集（内部原始负载如 `extra_data` 不透出）。联系方式类字段按 API Key 权限透出：当前实现中学术 `orcid`、开源 `email`/`social_links`/`blog_url`、实验室 `homepage`/`email` 均在白名单内；平台侧计划按 Key 粒度控制 PII 输出，**不要假设联系方式永远存在**。
- skill 侧语义（fetch_profiles.py `_has_contact`）：扫描该画像的全部 records（含 `homepage`/`github`/`github_login`/`email`/`social_links`），一个都没有则置 `contact_info_unavailable=true`。
- Agent 行为：画像 `contact_info_unavailable=true` 时，阶段3 探索不得再做「找联系方式/主页」类搜索，改用「名字+机构+方向」组合词（见 references/web-exploration.md 的 PII 降级）。

## 错误处理与数据缺口

- 单域拉取失败（含兜底失败）→ 该域写入 `output/<run_id>/gaps.txt`（每行一个域名），流程继续；报告方法论附录会列出缺口域。
- `/health` 探活在 fetch 前置执行，不可达时打印错误并以 **exit 2** 退出（提示先启动后端或设置 `AI4TALENT_BASE_URL`）。

## 运行时核对（每次执行前）

字段名与脱敏现状会随后端演进漂移。调用前先核对：

```bash
curl -s -H "X-API-Key: $AI4TALENT_API_KEY" \
  "$AI4TALENT_BASE_URL/open-api/academic/talents?page_size=1"
```

以实际响应为准：若字段名/脱敏情况与本文档不符，按实际响应适配（例如 academic 列表缺 `latest_active_year` 属已知偏差，见下节），并将差异回填本文档。

## 已知字段偏差（写作时核对自后端代码）

历史记录过三处漂移，前两处已在 skill 侧做兼容，仅剩一处数据局限：

1. ~~industry 返回 `best_match_score`，评分代码读 `match_score`~~ → **已兼容**：`score_industry` 优先读 `match_score`，缺失时回退 `best_match_score`（0 值视为「有 match 且为 0」）。
2. academic 列表白名单不含 `latest_active_year`/`education_school`（详情才有 `latest_active_year`/`education_school_name`）→ 列表项活跃度回退 0.3、机构为空。**唯一遗留的数据局限**，代码已有回退，无需处理。
3. ~~competition 人名字段为 `real_name`（非 `name`），跨域搜索解析丢弃无 `name` 条目~~ → **已兼容**：`_iter_cross_items` 接受仅有 `real_name` 的条目并回填 `name`，`_record_identity` 的 name/cn_name 提取链也含 `real_name`；竞赛人才走跨域搜索不再丢名。
