# talent-identifier Skill 设计文档

- 日期：2026-08-29
- 状态：已与用户逐节确认
- 工作区：`D:\AI\IdentifyAgent`（运行时数据落盘处）
- Skill 安装位置：`C:\Users\Administrator\.agents\skills\talent-identifier\`

## 1. 背景与目标

AI4TALENT 智能人才库（`D:\AI\AI4TALENT`）已建成 5 个人才域（学术/开源/实验室/竞赛/行业）并开放了面向 Agent 的 Open API，但各域评分体系相互独立、无跨域统一人才画像。现有 3 个采集型 skill（ai-lab-talent-crawler、comp-talent-crawler、smart-talent-sourcing）解决"数据进"，本 skill 解决"洞察出"：

**基于 AI4TALENT 人才库数据 + Open API，识别跨学术、开源、AI（实验室）、竞赛、行业领域的顶尖人才，对已识别人才在互联网上探索补全最新信息，输出详细洞察报告。**

## 2. 需求决定（澄清结果）

| 维度 | 决定 |
|---|---|
| 触发模式 | ① 领域/方向识别（技术方向关键词 → 跨域榜单+报告）② 名单深挖（人名列表 → 逐人深度报告） |
| 互联网探索范围 | 仅库内人才的信息补全（最新动态/新闻/职位变动/获奖）；不做库外新人发现 |
| 评估逻辑 | 硬指标定量 T-score 打底 + LLM 定性洞察 |
| 报告输出 | Markdown 报告 + JSONL 结构化数据 + HTML 可视化，三件套 |
| 数据对接 | AI4TALENT Open API（X-API-Key）；平台侧后续优化提供 PII 字段，skill 内做降级 |
| 跨域身份 | 规则自动关联 + 置信度标注；低置信不合并仅提示 |
| 回写策略 | 纯读不回写，所有结果留在本地 output/ |

## 3. 方案选型

| 方案 | 描述 | 结论 |
|---|---|---|
| A 轻指令型 | 仅 SKILL.md，Agent 现场执行全部环节 | 否决：结果漂移、T-score 不可复现、百人规模超会话预算 |
| B 重脚本型 | 全流程 Python 包，脚本内调 LLM API | 否决：开发量大、需额外 LLM API key、失去 Agent 灵活性 |
| **C 混合流水线** | 确定性环节（拉取/关联/评分/渲染）脚本化，智能环节（互联网探索/定性洞察）由 Agent 按 SKILL.md 执行 | **采纳**：与 comp-talent-crawler 成熟模式一致，T-score 可复现，智能环节复用 Agent 自带搜索能力 |

## 4. 总体架构

### 4.1 Skill 目录结构

```
talent-identifier/
├── SKILL.md                    # 主流程：两种模式的端到端指令
├── references/
│   ├── openapi-contract.md     # AI4TALENT Open API 契约（endpoint/字段/PII 降级）
│   ├── scoring-model.md        # T-score 评分模型（各域指标/归一化/权重）
│   ├── identity-linking.md     # 跨域身份关联规则与置信度分级
│   ├── web-exploration.md      # 互联网探索手册（搜索策略/信源/证据分级/预算）
│   └── report-templates.md     # 榜单报告/个人报告/洞察写作模板
├── scripts/
│   ├── fetch_profiles.py       # 阶段1：Open API 拉取 + 跨域关联
│   ├── compute_scores.py       # 阶段2：T-score 计算
│   ├── render_report.py        # 阶段4：Markdown + HTML + JSONL 渲染
│   └── check_pipeline.py       # 各阶段产物完整性校验
└── .gitignore                  # output/
```

### 4.2 运行时产物目录（落在启动时 cwd，如 `D:\AI\IdentifyAgent\output\`）

```
output/<run_id>/
├── profiles.jsonl        # 阶段1产物：统一画像（含跨域关联证据）
├── scores.jsonl          # 阶段2产物：T-score 榜单（有序）
├── enrichment/           # 阶段3产物（Agent 写入）
│   └── <person_id>.md    #   逐人探索笔记
├── enrichment.jsonl      #   结构化动态汇总
├── report.md             # 阶段4产物：Markdown 报告（名单模式为 report_<person>.md 多份）
├── report.html           #   单文件可视化（ECharts 内联）
├── final/
│   └── talents_<run_id>.jsonl  # 总数据：画像+评分+动态
└── _state.json           # 断点续跑状态
```

run_id 规则：`domain-<主题slug>-<YYYYMMDD>` 或 `names-<YYYYMMDD>-<HHMM>`。阶段间以文件接力，`--resume` 跳过已完成阶段。

## 5. 两种模式的数据流

### 5.1 模式 A：领域识别（domain-scan）

输入：技术方向关键词（如"大模型推理优化"），可选域子集。

1. **阶段1** `fetch_profiles.py --mode domain --keyword "…" [--domains academic,open_source,lab,competition,industry]`
   - 主通道：跨域统一搜索 `GET /open-api/search/talents?keyword=…&domains=…&per_domain=20`
   - 补充深捞（各域条件筛选，上限 `per_domain_limit` 默认 50）：
     - 学术 `GET /open-api/academic/talents?keyword=…`（h-index/引用排序）
     - 开源 `GET /open-api/open-source/talents`（tech_tags 匹配、stars 排序）
     - 竞赛 `GET /open-api/competition/talents?keyword=…`（rating 排序）
     - 实验室 `GET /open-api/lab/talents`（research_areas 匹配）
     - 行业 `GET /open-api/industry/talents?keyword=…`
   - 跨域身份关联（见 §7）→ `profiles.jsonl`（每人一条统一画像）
2. **阶段2** `compute_scores.py --run <run_id>` → 各域归一化 T-score + 榜单排序 → `scores.jsonl`
3. **阶段3 Agent 探索**：对 Top N（默认 20）逐人互联网补全（见 §8），产出 `enrichment/`
4. **阶段4** `render_report.py --run <run_id>` → 三件套

### 5.2 模式 B：名单深挖（name-dig）

输入：人名列表（`--names "张三,李四"` 或 `--names-file names.txt`）。

1. **阶段1** `fetch_profiles.py --mode names`：每个名字 `GET /open-api/search/talents?keyword=<名字>&domains=all`，跨域关联聚合成统一画像；全域查无 → `in_library: false` 记录（仅名字占位）
2. **阶段2** 仅有库内记录者算 T-score
3. **阶段3 Agent 探索**：逐人深挖；`in_library: false` 者完全依赖互联网拼画像
4. **阶段4** `render_report.py --mode person`：每人一份 `report_<person>.md` + 汇总 `report.html` + JSONL

## 6. T-score 评分模型（0-100）

原则：**在本次候选集内归一化**（log 变换 + min-max），避免不同量纲不可比；榜单可比性限于本次 run，报告方法论附录必须声明。

| 域 | 子分构成（权重细节在 references/scoring-model.md） |
|---|---|
| 学术 | h_index（0.35，log 归一）+ cited_by_count（0.35，log）+ works_count（0.15，log）+ 活跃度（0.15，latest_active_year 距今年数衰减） |
| 开源 | total_stars_received（0.45，log）+ followers_count（0.35，log）+ 语言/项目广度（0.20） |
| 实验室 | role_type 权重（Faculty/Research Scientist 0.5-1.0 > PhD Student 0.3）× 实验室声望分级（顶级 1.0 / 一线 0.85 / 其他 0.7，分级表维护在 scoring-model.md） |
| 竞赛 | max_rating 百分位（0.6）+ rank_title 映射分（Legendary/GM=1.0 递减，0.25）+ 奖牌数（0.15） |
| 行业 | current_org 声望（0.5，知名企业清单映射）+ title 级别（0.3，Principal/Staff/Distinguished 递减）+（若存在）match_score（0.2） |

融合规则（各域子分先统一缩放至 0-100 再参与融合）：
- 单域人才：T-score = 该域子分
- 跨域人才：T-score = max(子分) × 0.7 + 其余子分均值 × 0.3 + 广度加分（每多一个域 +5，封顶 +10）；总分截断至 100
- 指标全缺的域不参与计算；所有域均缺 → T-score 为 null，榜单尾置并标注

## 7. 跨域身份关联规则

证据链从强到弱：

| 置信度 | 证据 | 处理 |
|---|---|---|
| high | homepage URL / GitHub 链接 / ORCID / email 任一相同（PII 可用时） | 自动合并进统一画像 |
| medium | 英文名完全一致（含大小写规范化）+ 机构一致（学校/公司名规范化匹配） | 自动合并，画像标注 |
| low | 仅名字一致 + 研究方向/技术标签重叠 | **不合并**，报告中以"疑似同一人"提示 |

- 合并产出的统一画像记录：`person_id`、`linked_domains`、每条关联的 `evidence`（字段+值）与 `confidence`
- `person_id` 生成：`p_` + sha256(规范化姓名)[:8]；同一 run 内冲突时追加 `-2`、`-3` 序号；跨 run 不保证稳定（探索笔记与报告仅在本次 run 内引用）
- 名字规范化：中文保留、英文 lower+去标点；机构规范化：剔除 Inc./Ltd./大学/University 等后缀后小写比对
- 名单深挖模式额外规则：搜索结果中名字完全不同的记录不纳入（防止同名误聚）

## 8. 互联网探索（Agent 阶段，SKILL.md 指令 + web-exploration.md 手册）

- **目标信息**：职位变动、新论文/新项目、获奖荣誉、演讲活动、博客观点、社媒动态；优先近 12 个月
- **信源优先级**：个人主页 > Google Scholar > GitHub > X/Twitter > LinkedIn > 权威媒体 > 学术数据库
- **证据分级**：官方页面（高）> 权威媒体（中）> 本人社媒（中）> 二手转述（低）；**无来源链接的动态不写入报告**
- **预算熔断**：每人默认 ≤6 次搜索 + ≤4 次页面抓取（config 可调）；单人失败标记 `exploration_failed` 后跳过，不阻塞整体
- **PII 降级**：Open API 未返回 homepage/社媒链接时，改用"名字+机构+方向"构造搜索词，报告标注 `contact_info_unavailable`
- 结构化产出 `enrichment.jsonl`：`{person_id, kind: position_change|paper|project|award|talk|blog|social, title, date, source_url, evidence_level, summary}`

## 9. 报告输出（三件套）

### 9.1 Markdown 报告

领域模式《领域人才洞察报告》：
1. 执行摘要（方向概况、人才地图、关键发现 3-5 条）
2. 榜单总表（排名/姓名/T-score/域/机构/关键指标）
3. Top N 逐人小传（画像、硬指标、最新动态、LLM 定性洞察：亮点/风险/趋势）
4. 跨域人才专题（多域关联成功者，展示关联证据与置信度）
5. 方法论附录（数据来源与采集时间、评分口径、关联置信度、数据缺口、PII 降级说明）

名单模式每人一份深度报告：
1. 基本画像（跨域档案聚合，标注关联置信度）
2. 分域影响力（学术/开源/实验室/竞赛/行业，有则展示）
3. 最新动态时间线（互联网补全，每条带来源链接）
4. 综合评估（T-score + LLM 定性：优势/风险/趋势判断/适合的合作或触达场景）

### 9.2 HTML 可视化

`render_report.py` 内嵌 Jinja2 风格字符串模板生成**单文件** HTML（ECharts JS 内联，无外部依赖、可直接分享）：
- 评分分布直方图、领域构成饼图、Top N T-score 条形图、个人能力雷达图（各域子分）

### 9.3 JSONL 总数据

`final/talents_<run_id>.jsonl`，每行一个人才：
`{person_id, name, name_en, unified_profile, linked_domains[], t_score, domain_scores{}, rank, evidence[], dynamics[], generated_at, run_id}`
Schema 铁律（沿用生态通用约定）：字段缺失直接省略，不写 null/空串/猜测值；每行合法 JSON；ISO8601 时间戳。

## 10. 配置与容错

`ai4talent.config.json`（skill 目录内模板 + 项目 cwd 查找优先）：

```json
{
  "base_url": "http://localhost:8003/api/v1",
  "api_key": "",
  "top_n": 20,
  "per_domain_limit": 50,
  "domains": ["academic", "open_source", "lab", "competition", "industry"],
  "exploration": { "max_searches": 6, "max_fetches": 4 }
}
```

`api_key` 可被环境变量 `AI4TALENT_API_KEY` 覆盖。

容错矩阵：

| 故障 | 处理 |
|---|---|
| 后端不可达 | 探活提示（`curl /api/v1/health`），保留断点退出 |
| 单域搜索超时/失败 | 跳过该域，记入报告"数据缺口"（Open API 跨域搜索本身有单域 5s 降级） |
| HTTP 429 | 指数退避重试（最多 3 次） |
| PII 字段被脱敏 | 标记 `contact_info_unavailable`，探索阶段走降级搜索词 |
| 单人探索失败 | 标记跳过，部分成功优于完全失败 |
| 阶段中断 | `_state.json` 记录已完成阶段，`--resume` 续跑 |

## 11. 测试与验收

- **纯函数单测（pytest）**：T-score 归一化/加权/广度加分、身份关联三档判定、名字与机构规范化
- **`check_pipeline.py`**：校验各阶段 JSONL（每行合法 JSON、必填字段、confidence 枚举、榜单降序）
- **冒烟验收**（后端在跑时）：
  - domain-scan：`--keyword "agent" --top_n 5`，产物三件套齐全、报告可读、HTML 浏览器可开
  - name-dig：3 个真实人名（库内 2 个 + 库外 1 个），逐人报告生成
- **SKILL.md 完成标准**：榜单非空、每行 JSONL 可解析、每条动态带来源、报告含方法论附录

## 12. 依赖与对接点

| 依赖 | 说明 |
|---|---|
| AI4TALENT Open API | `GET /open-api/search/talents`（跨域）、`GET /open-api/{domain}/talents[/…]`、`GET /open-api/{domain}/stats`；X-API-Key 头，scope `<域>:read`；响应 envelope `{items, total, page, page_size}`，page_size 1-100 默认 20。契约文档 `D:\AI\AI4TALENT\docs\open-api\01-agent-guide.md` |
| **平台侧待办（用户负责）** | 优化 Open API 提供 PII 字段（homepage/社媒/email），可按 key scope 控制；未提供前 skill 走降级路径 |
| 后端服务 | 本地 `http://localhost:8003`（Docker 8000），Swagger `/docs` |
| Python 运行时 | 3.11+，httpx（API 调用）、pytest（测试）；HTML 渲染不引入重依赖，字符串模板实现 |
| Agent 能力 | WebSearch / WebFetch（互联网探索阶段） |

## 13. 范围外（明确不做）

- 不回写 AI4TALENT（不新增/修改平台任何数据；未来如需回写另立设计）
- 不发现库外新人才（不做"新兴人才雷达"）
- 不做无人值守定时运行（依赖 Agent 会话执行探索阶段；后续如需可演进为方案 B）
- 不做 JD 匹配（与平台 jd_match、smart-talent-sourcing 已有功能重叠，划清边界）
