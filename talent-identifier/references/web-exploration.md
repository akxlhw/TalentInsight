# 阶段3 手册：互联网探索（enrichment）

目标：对 run 内画像补全近期动态与定性洞察。产物经 `check_pipeline.py` 校验——**kind 非法、source_url 缺失/不以 http 开头、evidence_level 非法都会判 FAIL**。

## 目标信息七类（kind 枚举，固定拼写）

`position_change`（职位变动）/ `paper`（论文）/ `project`（项目）/ `award`（获奖）/ `talk`（演讲）/ `blog`（博客）/ `social`（社媒动态）。

## 信源优先级（从高到低）

1. 本人官方页面（个人主页、实验室主页）
2. Google Scholar
3. GitHub
4. X/Twitter
5. LinkedIn
6. 权威媒体报道
7. 学术数据库（DBLP/OpenAlex 等）

同一事件多信源时取最高优先级信源为 source_url，不重复收录。

## 证据分级与铁律

- `high`：官方页面（本人/所在机构/官方榜单）。
- `medium`：权威媒体报道、本人社媒账号发言。
- `low`：二手转述（论坛、聚合站、他人转推）。
- **无 source_url 不写入**（铁律）：任何没有可点开原始出处的信息一律丢弃，禁止编造或补全 URL。

## 搜索词构造

- 基础式：`"<name>" <org> <topic> 2026`（引号锁定全名，topic 取 tags 中最具体的 1-2 个）。
- 事件式：`"<name>" <org> (joined OR appointed OR award OR paper)`。
- 英文名与中文名都试；竞赛 handle 可单独搜（如 codeforces handle）。
- **PII 降级**：画像 `contact_info_unavailable=true` 时，不做「找主页/找邮箱/找社媒账号」类搜索，改用「名字+机构+研究方向」组合词获取动态即可。

## 预算与收束

- 每人 **≤ `exploration.max_searches` 次搜索、≤ `exploration.max_fetches` 次抓取**（默认 6 / 4，`ai4talent.config.json` 可调）。
- 达到任一上限立即收束该人，写下手头已有结果，不为凑数继续。
- 时效优先：**近 12 个月**的动态优先；更早的仅在标志性事件（顶级奖项/代表作）时收录。
- `date` 精确到月（`YYYY-MM`）；确实未知则**省略 date 字段**，不要猜。

## 写入规范

每确认一条动态，**立即**追加一行 JSONL 到 `output/<run_id>/enrichment.jsonl`（不要攒批，中断时已写入的仍有效）：

```json
{"person_id": "p_ab12cd34", "kind": "paper", "title": "…", "date": "2026-03",
 "source_url": "https://…", "evidence_level": "high", "summary": "一句话中文摘要",
 "collected_at": "2026-08-29T01:23:45+00:00"}
```

- `person_id` 必须与 profiles.jsonl 一致——孤儿动态（person_id 对不上）渲染时会被丢弃，等于白写。
- `collected_at` 用 UTC ISO-8601（秒级）。

单人探索结束后写 `output/<run_id>/enrichment/<person_id>.md` 定性洞察：

- 固定三小节：`## 亮点` / `## 风险` / `## 趋势`，每节 2-4 句。
- 每个观点必须引用具体动态（标题/日期）或库内指标（h-index、stars 等）支撑，禁止无依据推断。
- **首行不要写标题**（渲染器会剥离首行 `#` 标题，但最好一开始就不写，直接以 `## 亮点` 开头）。
- 没有可靠信息就不写该文件（渲染器会显示「本次未生成洞察」），不要写空话凑数。

## 中断与失败

- 单人探索失败（搜索不可用、预算内无收获）→ 跳过该人，在最终汇报中说明，**不写任何伪造行**。
- 部分成功优于完全失败：其他人的结果照常写盘。
- 进程中断后重跑：enrichment.jsonl 为追加式，注意不要对同一人重复写入同一条动态（先读现有行再写）。

## 名单模式的库外者

`in_library=false`（names 模式下库内搜索无命中）的画像 records 为空、无 T-score 参考指标，**完全依赖本阶段互联网信息拼出画像**：至少尝试定位其主页/Scholar/GitHub 之一确认身份，再按常规流程收集动态与洞察。
