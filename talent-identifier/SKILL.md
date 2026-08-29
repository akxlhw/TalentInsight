---
name: talent-identifier
description: |
  跨域顶尖人才识别与洞察。基于 AI4TALENT 人才库 Open API（学术/开源/实验室/竞赛/行业五域），
  按技术方向识别顶尖人才榜单（硬指标 T-score 定量 + LLM 定性洞察），或对给定名单逐人深挖；
  Agent 在互联网上探索补全人才最新动态（职位/论文/项目/获奖，均带来源），最终产出
  Markdown 深度洞察报告 + HTML 可视化 + JSONL 结构化数据三件套。
  触发场景："识别XX领域顶尖人才" / "人才识别" / "跨域人才榜单" / "深挖这些人" /
  "给我一份XX方向人才洞察报告" / "talent identification"。
---

# talent-identifier：跨域顶尖人才识别

读 AI4TALENT 五域人才库 → 跨域关联 + T-score 榜单 → 互联网补全最新动态 → 三件套洞察报告。
**纯消费型 skill：只读 Open API，绝不写回平台。**

> 本文 `<skill>` 指 skill 安装目录（如 `C:\Users\Administrator\.agents\skills\talent-identifier`），
> `<base_url>` 指配置中的 API 地址（默认 `http://localhost:8003/api/v1`）。

## 前置检查（执行前必做）

1. 配置：若 skill 目录还没有 `ai4talent.config.json`，复制 `ai4talent.config.example.json`
   为 `ai4talent.config.json`（该文件已 gitignore，真实 key 不会入库）并填入 `api_key`；
   cwd 下同名文件优先生效。`api_key` 亦可用环境变量 `AI4TALENT_API_KEY` 覆盖；
   base_url 可用 `AI4TALENT_BASE_URL` 覆盖。
2. 探活：`curl -s -m 5 <base_url>/health`，不通则提示用户先启动 AI4TALENT 后端再停止。
3. 运行时：Python 3.11+；脚本依赖仅 httpx。执行命令统一用
   `uv run --with httpx python scripts/xxx.py ...`（uv 缺失且本机 python 有 httpx 时可直跑）。
4. 首次调用前按 `references/openapi-contract.md` 的「运行时核对」curl 一次确认字段与脱敏现状。

## 模式 A：领域识别（输入=技术方向）

```bash
cd <项目目录>   # 产物落在 cwd 的 output/
# 阶段1+2（确定性）
uv run --with httpx python <skill>/scripts/fetch_profiles.py --mode domain --keyword "<方向>"
uv run --with httpx python <skill>/scripts/compute_scores.py --run output/<run_id>
```

fetch 的 exit code：0 成功；1 参数错误；2 后端不可达。单域失败记 gaps.txt 继续（部分成功优于完全失败）。`--resume` 跳过已完成 fetch 的 run。可选参数：`--domains academic,lab`（限定域）、`--names-file names.txt`（名单文件，优先生效）。

## 模式 B：名单深挖（输入=人名列表）

```bash
uv run --with httpx python <skill>/scripts/fetch_profiles.py --mode names --names "名字1,名字2"
uv run --with httpx python <skill>/scripts/compute_scores.py --run output/<run_id>
```

库外人员（in_library=false）产出占位画像，T-score 为空，完全依赖阶段3 互联网拼画像。

## 阶段3：互联网探索（Agent 执行，逐人）

**先读 `references/web-exploration.md`**。对 `scores.jsonl` 的 Top N（config `top_n`，默认 20；
名单模式为全部人员）：
1. 按信源优先级与搜索词构造逐人搜索（WebSearch/WebFetch）。
2. 每条动态**立即**追加一行到 `output/<run_id>/enrichment.jsonl`
   （schema 见 web-exploration.md；无 source_url 的信息一律丢弃）。
3. 每人探索完写 `output/<run_id>/enrichment/<person_id>.md` 定性洞察（亮点/风险/趋势）。
4. 严守预算（默认每人 6 搜 4 抓）；`contact_info_unavailable=true` 者走降级搜索词。
5. 单人失败跳过并记录，不阻塞他人——部分成功优于完全失败。

## 阶段4：渲染与验收

```bash
uv run --with httpx python <skill>/scripts/render_report.py --run output/<run_id>
uv run --with httpx python <skill>/scripts/check_pipeline.py --run output/<run_id>
```

check_pipeline 必须输出 PASS（rc 0）才算完成；render 阶段完成后它会校验三件套齐全。

## 硬性约束

- 只读 Open API，不写回 AI4TALENT；不触碰任何需要登录的站点，不绕验证码/风控。
- 评分与关联全部由脚本完成，Agent 不得手改 scores.jsonl；定性观点必须有动态或指标支撑。
- 中断续跑：fetch 加 `--resume`；后续阶段幂等可直接重跑。
- 中英名字、同名不同人歧义时，宁可少合并不多合并（低置信只提示）。

## 完成标准

- 榜单非空（或名单模式每人有报告）；check_pipeline 返回 PASS。
- 三件套齐全：report.md（或逐人 report_*.md）、report.html、final/*.jsonl。
- 每条动态带来源；报告含方法论附录。

## 参考文件

- references/openapi-contract.md — Open API 契约、字段表与运行时核对
- references/scoring-model.md — T-score 口径、映射表与已裁决语义
- references/identity-linking.md — 跨域关联规则与置信度
- references/web-exploration.md — 互联网探索手册（阶段3 必读）
- references/report-templates.md — 报告结构与写作规范
