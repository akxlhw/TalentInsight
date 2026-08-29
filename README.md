# TalentInsight

> 跨域顶尖人才识别与洞察 —— 基于 AI4TALENT 人才库 Open API 的 Agent Skill

输入一个技术方向（如"大模型推理优化"）或一份人名名单，TalentInsight 从 AI4TALENT 五域人才库（学术 / 开源 / 实验室 / 竞赛 / 行业）拉取候选人才，完成**跨域身份关联**与 **T-score 硬指标评分**，再由 Agent 在互联网上探索补全每个人的最新动态（职位变动 / 新论文 / 新项目 / 获奖，均带来源），最终产出三件套洞察报告：

- `report.md` —— Markdown 深度报告（执行摘要 / 榜单总表 / Top 小传 / 跨域专题 / 方法论附录）
- `report.html` —— 单文件可视化（ECharts 评分分布 / 域构成 / Top 榜 / 个人雷达，可直接分享）
- `final/*.jsonl` —— 结构化总数据（画像 + 评分 + 关联证据 + 动态）

**设计原则**：纯消费型——只读 Open API，绝不写回平台；评分与关联全部确定性脚本完成（可复现可解释），智能环节（互联网探索 / 定性洞察）交给 Agent 并强制带来源；同名歧义时宁可少合并不多合并。

## 架构

混合流水线（确定性脚本 + Agent 智能环节，阶段间以文件接力、支持断点续跑）：

```
阶段1 fetch_profiles.py    拉取五域候选 + 跨域身份关联（DSU + high/medium/low 三档置信度）
      ↓ output/<run>/profiles.jsonl
阶段2 compute_scores.py    T-score 评分（各域候选集内 log 归一化 + 跨域融合加分）
      ↓ scores.jsonl
阶段3 Agent 互联网探索      逐人 WebSearch/WebFetch 补全最新动态（预算熔断、证据分级、无来源不写）
      ↓ enrichment.jsonl + enrichment/<person_id>.md
阶段4 render_report.py     渲染三件套
      ↓ check_pipeline.py 产物完整性校验（PASS 才算完成）
```

```
talent-identifier/
├── SKILL.md                    # Agent 执行入口文档（触发场景/流水线/约束/完成标准）
├── references/                 # 五份契约与手册
│   ├── openapi-contract.md     #   AI4TALENT Open API 对接契约（端点/字段/PII/已知偏差）
│   ├── scoring-model.md        #   T-score 口径、映射表与已裁决语义
│   ├── identity-linking.md     #   跨域关联规则与置信度分级
│   ├── web-exploration.md      #   互联网探索手册（阶段3 必读）
│   └── report-templates.md     #   报告结构与写作规范
├── scripts/
│   ├── talent_identifier/      # 共享包：config / io_utils / normalize / api_client / linking / scoring
│   ├── fetch_profiles.py       # 阶段1 CLI（--mode domain|names 两模式）
│   ├── compute_scores.py       # 阶段2 CLI
│   ├── render_report.py        # 阶段4 CLI（Markdown + HTML + final JSONL）
│   ├── check_pipeline.py       # 产物校验
│   └── tests/                  # 103 项单元/离线集成测试
└── assets/echarts.min.js       # HTML 报告内联图表库（离线可用）
```

## 快速开始

### 前置

- Python 3.11+（唯一运行时依赖 `httpx`；测试另需 `pytest`，推荐用 [uv](https://docs.astral.sh/uv/) 免安装执行）
- 运行中的 AI4TALENT 后端（默认 `http://localhost:8003/api/v1`）与一个含五域 `:read` scope 的 `X-API-Key`
- 配置：`cp talent-identifier/ai4talent.config.example.json talent-identifier/ai4talent.config.json`
  并填入 `api_key`（本地文件已 gitignore，不会泄露；cwd 下同名文件优先生效），或用环境变量
  `AI4TALENT_API_KEY` / `AI4TALENT_BASE_URL`

### 领域识别（输入=技术方向）

```bash
cd <你的工作目录>   # 产物落在 cwd 的 output/
uv run --with httpx python <skill目录>/scripts/fetch_profiles.py --mode domain --keyword "大模型推理优化"
uv run --with httpx python <skill目录>/scripts/compute_scores.py --run output/<run_id>
# Agent 按 SKILL.md 阶段3 对 Top N 逐人互联网探索（写 enrichment.jsonl）
uv run --with httpx python <skill目录>/scripts/render_report.py --run output/<run_id>
uv run --with httpx python <skill目录>/scripts/check_pipeline.py --run output/<run_id>   # 须 PASS
```

### 名单深挖（输入=人名列表）

```bash
uv run --with httpx python <skill目录>/scripts/fetch_profiles.py --mode names --names "吴翼,Andrew Ng"
# 后续同上；库外人员自动占位，完全依赖互联网拼画像
```

### 作为 ZCode/Claude Code Skill 使用

将 `talent-identifier/` 复制到 `~/.agents/skills/`（或对应 skills 目录）即可。Skill 会由"识别XX领域顶尖人才"、"深挖这些人"等自然语言触发，Agent 自动完成全部四个阶段（含互联网探索）。

## 开发与测试

```bash
cd talent-identifier
uv run --with httpx --with pytest python -m pytest scripts/tests -v   # 103 passed
```

- 全部测试离线（Open API 客户端经 FakeClient 注入），不依赖真实后端
- 开发流程文档见 `docs/superpowers/specs/`（设计文档）与 `docs/superpowers/plans/`（实施计划）

## 已知限制与路线图

- 学术域列表接口暂缺 `latest_active_year` / `education_school`（活跃度回退默认值、机构为空导致 medium 合并对含学术域的配对不可用）——待 AI4TALENT 平台侧补字段
- 名单深挖模式的跨域搜索摘要无机构/指标字段（无 medium 合并、无 T-score），可用 `/open-api/{domain}/talents/{id}` 详情补全（排期中）
- 回写通道（洞察结果推送回平台）为明确范围外，未来按需另立设计

## 关联项目

- **AI4TALENT**（私有）：智能人才库平台——academic / open_source / lab / competition / industry 五域数据与 Open API
- 同生态采集 skill：ai-lab-talent-crawler、comp-talent-crawler、smart-talent-sourcing（数据"进"，本 skill 负责"洞察出"）

## License

[MIT](LICENSE)
