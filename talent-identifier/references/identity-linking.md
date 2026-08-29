# 跨域身份关联

实现：`scripts/talent_identifier/linking.py`（DSU 合并）+ `normalize.py`（规范化）。目标：把五域 records 合并为统一 person 画像，宁可漏合并，不可误合并。

## 三档证据

| 档 | 条件 | 动作 |
|---|---|---|
| high | `homepage` / `github` / `orcid` / `email` 任一**规范化后相同**（双侧均非空） | 合并，evidence 记 `{field, value, confidence: high}` |
| medium | 规范化名字相同（英文名或中文名任一）**且**规范化机构相同——**双侧机构已知**，任一侧机构未知不合并（保守裁决） | 合并，evidence 记 `{field: "name+org", value: "名字@机构", confidence: medium}` |
| low | 名字相同 + 双方标签集非空 + 标签 Jaccard > 0.2；**双方机构已知且不同 → 抑制提示**（明显是两个人）；orgs 不同但有一侧未知 → 仅提示 | **不合并**，双向写 `suspected_same_person: [{person_id, basis: "name+tags"}]`（按 person_id 去重） |

辅助规则：

- **同域两条记录永不合并**（比较前直接跳过同 domain 对）。
- **传递合并的域冲突守卫**：DSU 合并时维护每个连通分量的域集合，两组件的域集合**相交则放弃本次 union**（且不记 evidence）——防止 records 按域键覆盖丢数据。
- evidence 只记「合并生成树」：仅记录实际触发合并的成员对；已成组后的冗余对不重复记（输出时只枚举 i<j 的在册对）。

## 三档示例（与实现逐一对应）

**high（homepage）**：academic 记录 `homepage="https://www.yiwu.ai/"`，industry 记录 `homepage="http://WWW.YIWU.AI"` → 规范化后均为 `yiwu.ai` → 合并。

**high（github）**：open_source 记录 `github_login="yiwu"`（裸 login 补全为 `https://github.com/yiwu`）；lab 记录 `social_links=["https://github.com/Yiwu/"]`（取 `github.com/` 后首段、小写）→ 双侧规范化为 `github.com/yiwu` → 合并。

**medium**：academic `name_en="Yi Wu"` + `education_school="Tsinghua University"`；open_source `name="Yi Wu"` + `company="Tsinghua University"` → 名字均规范化为 `yiwu`，机构均剥掉 `university` 后缀得 `tsinghua` → 合并，evidence 记 `name+org = yiwu@tsinghua`。

**medium 不触发**：任一侧机构字段全空（六字段链取不到）→ org="" → 不合并；若双侧标签 Jaccard>0.2 则降级为 low 提示。

**low 抑制**：名字相同，一侧机构 `tsinghua`、另一侧 `pku`（双方已知且不同）→ 明显是两个人，**连提示都不给**。

**域冲突守卫**：A(academic)+B(open_source) 已合并成组 `{academic, open_source}`；另有 C(academic) 与 B 的 github 相同 → 两组件域集合相交（都含 academic）→ 放弃合并，C 保持独立画像。

## 字段提取链

- **github**：`github_login` > `github` > `social_links` 中第一个含 `github.com/` 的链接（social_links 为 list 取各值、为 dict 取各 value；取 `github.com/` 后第一段为 login）；裸 login（无 `github.com/`）补全为 `https://github.com/<login>`；最后过 `normalize_url`。比较全程大小写不敏感。
- **机构**：六字段取第一个非空——`education_school` > `company_school` > `school` > `current_org` > `company` > `lab_name`（取单一值，不拼接）。
- **名字**：英文名 = `name_en`（回退 `name`）、中文名 = `name`，各自规范化后独立比较，任一相等即名字相同。
- **标签扁平化**：`topic_tags` + `tech_tags` + `research_areas` 三键并集；list 直接用，字符串按 `,`/`，` 切分；每项过 `normalize_name`。
- `orcid`/`email`：仅 lower + strip。

## 规范化定义（normalize.py）

- **名字** `normalize_name`：仅保留 `[0-9a-zA-Z\u4e00-\u9fff]`，其余（标点/空格/连字符）删除，转小写。中文保留。
- **机构** `normalize_org`：标点转空格后分词；循环弹出**英文后缀词**（整词等于后缀才算）：`inc / incorporated / ltd / limited / llc / lp / corp / corporation / co / company / holdings / university / univ / college / group / labs / 大学 / 学院 / 公司 / 研究院`；再对最后一个 token **循环剥离中文后缀**（最长优先）：`有限责任公司 / 股份有限公司 / 有限公司 / 研究院 / 大学 / 学院 / 公司 / 集团`——带长度守卫，剥空即停。
- **URL** `normalize_url`：去协议 `http(s)://`、去 `www.`、去 fragment（`#...` 恒剥）、去尾斜杠，全程小写。**query 仅当全部参数都是跟踪参数时才整体剥除**，跟踪参数白名单正则：`^(utm(_\w+)?|fbclid|gclid|ref|source|spm|igshid|si)$`；混入任何身份参数（如 Google Scholar 的 `?user=xxx`）则 query 原样保留——防止不同人的主页被误判相同（评审裁决的防误合并语义）。

## person_id 与画像组装

- `person_id = "p_" + sha256(规范化姓名)[:8]`；同哈希冲突时追加 `-2`、`-3`。姓名取 `name_en`，无则 `name`。
- 组内 lead 按 `DOMAIN_PRIORITY`（academic > lab > open_source > competition > industry）选第一个成员：画像的 `name`/`name_en`/`homepage`/`github`/`orcid`/`email` 取 lead 的身份字段；`org` 取组内**第一个非空**机构；`tags` 为全组并集排序。
- `records` 按域键存放（每域至多一条，冲突守卫保证）；`linked_domains` 为成员域列表。

## 输出画像字段速览（profiles.jsonl 每行）

| 字段 | 含义 |
|---|---|
| `person_id` / `name` / `name_en` | 标识（lead 记录的名字） |
| `records` | 域 → 原始条目（每域至多一条） |
| `linked_domains` | 成员域列表（长度 >1 即跨域人才） |
| `link_evidence` | 合并生成树证据（field/value/confidence） |
| `suspected_same_person` | low 档双向提示（仅存在时出现） |
| `org` / `homepage` / `github` / `orcid` / `email` / `tags` | lead 身份 + 组内汇总 |
| `in_library` | 是否有库内 records（names 模式未命中为 false） |
| `contact_info_unavailable` | 全部 records 无任何联系方式字段时 true |
| `collected_at` | 采集时间（UTC ISO-8601） |

## Agent 判读指引（写报告时遵守）

- `suspected_same_person`（low）**需人工确认**：报告中只能表述为「疑似与 p_xxx 为同一人，未合并」，不得当作同一人陈述或合并他们的动态。
- `link_evidence` 中 confidence=medium 表示仅靠名字+机构匹配，中文同名者较多，涉及时在报告措辞上留余地。
- 名字模式下库内搜不到的人会生成空 records 画像（`in_library=false`），无任何关联证据，完全依赖阶段3 互联网拼画像。
