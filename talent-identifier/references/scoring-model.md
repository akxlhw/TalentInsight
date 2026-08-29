# T-score 评分模型

口径来源：`scripts/talent_identifier/scoring.py`（本文档全部数字与代码一一对应）。T-score 为 **0-100**，榜单按 t_score 降序、null 尾置、rank 1..n。

## 核心告示：候选集内归一化

所有连续指标经 `_lognorm` 在**本次候选集内**归一化：`log(v+1)` 后 min-max 到 [0,1]；候选集内全部相等时取 0.5。因此 **T-score 只在本次榜单内可比**，跨批次/跨主题比较无意义。报告中必须保留此口径说明。

## 五域子分构成

| 域 | 构成（权重 × 组件） |
|---|---|
| academic | `h_index 0.35 + cited_by 0.35 + works 0.15 + activity 0.15`（前三项 lognorm，activity 见衰减公式） |
| open_source | `stars 0.45 + followers 0.35 + breadth 0.20`（breadth = `len(primary_languages)` 的 lognorm） |
| lab | `100 × role_weight × lab_prestige`（无其他组件） |
| competition | `rating 0.60 + rank_title 0.25 + medals 0.15`；rating 取 `max_rating`（缺失回退 `current_rating`）lognorm；medals = `gold×3 + silver×2 + bronze` 的 lognorm |
| industry | 有 `match_score` 或 `best_match_score` 时（`match_score` 优先、缺失回退 `best_match_score`；`is not None` 判断，**0 值=有 match 且为 0**）：`org 0.5 + title 0.3 + match 0.2`（match = 分数/100）；两者均无时：`org 0.625 + title 0.375` |

子分 = `100 × Σ(权重 × 组件值)`，写入 scores.jsonl 前先 `round(x, 1)`。

## 活跃度衰减

`activity(year)`：年份缺失或非法 → **0.3**；否则 `lag = max(0, 当前年 - year)`，`activity = max(0, 1 - lag/5)`（5 年前及更早归 0）。`rank_title` 缺失 → **0.3**。

## 映射表（子串匹配，先命中先返回）

> **顺序即优先级：复合词/长键必须在前。** 匹配是对整个字符串的子串包含（小写化后）；顺序错位会导致 "candidate master" 被 "master" 抢先命中。

**ROLE_RULES**（匹配 `role_section + " " + role_type`，未知 0.6）：

| 顺序 | 键 | 分 |
|---|---|---|
| 1 | faculty | 1.0 |
| 2 | professor | 1.0 |
| 3 | research scientist | 0.8 |
| 4 | **postdoc** | **0.6** |
| 5 | researcher | 0.8 |
| 6 | alumni | 0.5 |
| 7 | phd | 0.3 |
| 8 | student | 0.3 |

> 裁决注：postdoc 排在 researcher **前**（尽管分更低）——"Postdoctoral Researcher" 应命中 postdoc 0.6，而非 researcher 0.8。

**LAB_PRESTIGE**（默认 0.7）：

| 分 | 键 |
|---|---|
| 1.0 | stanford ai lab / mit csail / csail / deepmind / fair / meta ai / openai / anthropic / microsoft research / msr / bair |
| 0.85 | 智源 / tsinghua / 清华 |

**RANK_TITLE_SCORES**（默认 0.3）：legendary 1.0、international grandmaster 0.95、grandmaster 0.9、international master 0.8、**candidate master 0.6**（在 master 前）、master 0.7、expert 0.5、specialist 0.4、pupil 0.3、newbie 0.2。

**TITLE_RULES**（默认 0.5）：distinguished 1.0、fellow 1.0、chief 0.9、principal 0.95、staff 0.85、lead 0.75、senior 0.7、junior 0.3。

**ORG_PRESTIGE**（默认 0.6）：openai/anthropic/deepmind/google/meta/microsoft/nvidia 1.0；bytedance/字节 0.95；alibaba/阿里/tencent/腾讯/huawei/华为 0.9；baidu/百度 0.85。

## 跨域融合

- 单域：`t_score = 子分`。
- 跨域（n≥2）：`t = min(100, 0.7×最高子分 + 0.3×其余子分均值 + min(10, 5×(n-1)))`——广度加分每多一个域 +5，上限 +10。
- **子分先 round 到 1 位小数，再进入融合**；融合结果再 round 到 1 位。

## 已裁决语义（不得"顺手修复"）

1. **指标全缺的域不参与计算**：industry 需 `current_org`/`current_title` 至少其一；lab 需角色信息（`role_section`/`role_type`）与实验室信息（`lab_name`/`parent_lab`）至少其一；academic 需 `h_index`/`cited_by_count`/`works_count`/`latest_active_year` 至少其一；open_source 需 `total_stars_received`/`followers_count`/`primary_languages` 至少其一；competition 需 `max_rating`/`current_rating`/`rank_title`/`medals_gold`/`medals_silver`/`medals_bronze` 至少其一。全缺 → 该域无子分、不出现在 domain_scores，且**不进该域批量归一化列表**（否则全 0 值会拉偏其他人的归一化分位）。
2. **所有域均缺 → t_score=null**，榜单尾置，rank 照编。
3. **子串误匹配面**：机构/实验室匹配是子串包含，"Fairfield" 会命中 `fair`（LAB_PRESTIGE 1.0）——已知启发式限制，报告如遇可人工复核，不改代码。
4. **match_score=0 怪异点**：`match_score=0`（含回退得到的 `best_match_score=0`，非 None）走三因子权重，行业子分 = `100×(0.5×org+0.3×title)`，低于无 match 时的 `100×(0.625×org+0.375×title)`；默认锚点（org 0.6、title 0.5）下即 **45.0 vs 56.2**——0 分锚点低于默认锚点，已知怪异点，保留。

## 默认值一览

| 场景 | 默认 |
|---|---|
| 未知角色（ROLE_RULES 未命中） | 0.6 |
| 未知机构（ORG_PRESTIGE 未命中） | 0.6 |
| 未知实验室（LAB_PRESTIGE 未命中） | 0.7 |
| 未知头衔（TITLE_RULES 未命中） | 0.5 |
| 未知段位（RANK_TITLE_SCORES 未命中） | 0.3 |
| 年份缺失/非法（activity） | 0.3 |
