# 阶段总结：LLM 辅助课件结构生成

## 1. 本阶段完成内容

本阶段围绕“让 LLM API 基于结构化输入材料生成 `courseware_structure.json v0.1` 草案”完成了一条 API-ready 闭环设计：

```text
llm_input_package.sample.json
  -> prompts.md
  -> llm-api-integration-design.md
  -> scripts/generate_courseware_structure.py
  -> courseware_structure.draft.sample.json
  -> review_record.sample.md
  -> llm-vs-manual-comparison.md
```

完成产物：

| 产物 | 作用 |
| --- | --- |
| `llm-input-package.md` | 定义 LLM 输入包格式和来源标注规则 |
| `llm_input_package.sample.json` | 基于“微积分入门教学”第 2-6 页的最小输入包 |
| `prompts.md` | Course、Slides、Nodes、Relations、Candidates 五层 prompt 模板 |
| `llm-api-integration-design.md` | LLM API 接入、模型分工、调用策略、输出校验和预算控制 |
| `llm-runner.md` | 最小 runner 的 mock / API 运行方式和输出目录说明 |
| `../../scripts/generate_courseware_structure.py` | 读取输入包、分层调用、保存 raw / validated outputs、装配 draft 的最小 CLI |
| `courseware_structure.draft.sample.json` | 可解析的 assembled 草案样例 |
| `human-review-workflow.md` | 人工审查、错误分类和重跑规则 |
| `review_record.sample.md` | 一份带具体问题的人工审查记录样例 |
| `llm-vs-manual-comparison.md` | LLM 草案与上一阶段人工样例的差异对照 |

## 2. 最小闭环验证

本阶段最小闭环已经覆盖：

- 5 页输入材料：第 2-6 页。
- 10 个 known elements：来自上一阶段人工样例。
- 5 类分层 prompt：course、slides、knowledge_nodes、knowledge_relations、teaching_candidates。
- 1 份 assembled JSON 草案。
- 6 条人工审查问题记录。
- 7 条 LLM 与人工样例差异。
- 1 个最小 runner：支持 mock 离线验证和 OpenAI-compatible API 调用。

## 3. LLM 适合生成的层

本阶段明确依赖大模型能力完成文本结构化生成。LLM 不是 parser，而是对 parser/OCR/人工补充后的输入包进行语义理解和教学结构推理。

### Course

适合。LLM 可以基于页面标题、文本和摘要归纳主题、学习目标、模块结构和叙事路径。

风险：

- 学习目标可能超出课件范围。
- key concepts 可能与后续节点 ID 不完全一致。

处理：

- 要求每个目标能回到 slide range。
- 在 nodes 层复核 key concepts。

### Slides

基本适合。LLM 可以判断页面角色、核心信息、教学意图和前后承接。

风险：

- 对输入范围首尾页，可能引用未输入页面。
- 对公式页或图示页，可能过度解释。

处理：

- 起止页允许 previous/next 为 null。
- 图示和公式不足时设置 `needs_review: true`。

### Knowledge Nodes

适合生成第一版。LLM 能从页面文本中抽象主要概念、方法、过程和应用。

风险：

- 节点粒度可能过细或过泛。
- 对视觉概念和公式概念的证据不足。

处理：

- 用人工样例检查粒度。
- 缺少视觉证据时保留 review 标记。

### Knowledge Relations

可生成草案，但必须人工审查。基础关系如 `part_of`、`explains` 通常可靠；跨页 `prerequisite_of` 更依赖教学判断。

风险：

- 把共现误判为关系。
- prerequisite 方向错误。
- 关系证据只有页面顺序。

处理：

- 要求 description 解释方向。
- 跨页推断降低 confidence。

### Teaching Candidates

适合作为候选，不适合作为最终脚本。LLM 能生成问题、反馈和 GUI action 草案，但覆盖稳定性不够。

风险：

- 漏掉某个模块。
- GUI action 引用不适合现有前端转换。
- 跨页 review strategy 需要转换器支持。

处理：

- 要求每个 module 至少一个 candidate。
- action_type 必须来自 known element affordance。
- 标明需要转换器处理的位置。

## 4. LLM 不适合单独完成的内容

本阶段明确不让 LLM 单独生成：

- 元素 bbox。
- 页面截图视觉语义。
- 图表、箭头、面积分割图的真实视觉关系。
- 公式严谨边界。
- 最终可执行 `lesson.json`。
- 前端播放步骤、跳转逻辑和题型适配。

这些内容应交给阶段三 VLM、人工标注或后续工程转换器。

## 5. API 接入后的目标能力

完成最小 API 接入后，本阶段应能支持：

```text
llm_input_package.json
  -> LLM API
  -> raw_outputs/*.json
  -> validator
  -> validated_outputs/*.json
  -> courseware_structure.draft.json
```

最低能力不是“任意 PPT / PDF 全自动理解”，而是“给定结构化输入包，依赖 LLM 输出对应的结构化文本草案”。这一步完成后，parser 和 VLM 可以作为上游模块继续增强输入质量。

当前已经新增 `scripts/generate_courseware_structure.py`，具备：

- `mock` 模式：把现有样例草案拆成 raw / validated outputs，并重新装配 draft；
- `api` 模式：通过 OpenAI-compatible `/chat/completions` 调用真实文本模型；
- 本地基础 validator：检查 JSON、字段、confidence、needs_review、slide / element / node 引用；
- 输出 `validation_report.md`，用于人工审查和后续修复。

## 6. 与上一阶段的关系

上一阶段定义了 `courseware_structure.json v0.1` schema 和人工样例。本阶段没有重新定义 schema，而是把该 schema 转化为：

- LLM 输入包；
- 分层生成 prompt；
- 草案 JSON；
- 人工审查流程；
- 与人工样例的差异对照方法。

本阶段产物仍是 `lesson.json` 的上游，不直接替换 `apps/web/public/data/lesson.json`。

## 7. 阶段三输入需求

进入 VLM 或工程转换器阶段前，需要保留以下输入：

- `courseware_structure.draft.sample.json`
- 人工修正后的 review record
- known elements 与 bbox
- 需要视觉补足的节点和候选
- 需要转换器处理的 teaching candidates

阶段三重点应补：

- 元素视觉角色确认；
- bbox 与页面截图对齐；
- 图示、箭头、公式和面积分割图的视觉语义；
- teaching candidates 到 `lesson.json` 的稳定转换规则。

## 8. 当前阶段完成判断

本阶段满足完成定义：

- 有可复用的 LLM 输入包格式。
- 有分层 prompt 模板。
- 有 LLM API 接入设计。
- 有一份可解析的结构草案样例。
- 有人工校正规则和审查记录样例。
- 有与上一阶段人工样例的对照方法。
- 能明确说明 LLM 结构生成的能力边界和下一阶段 VLM 需要补足的内容。

## 9. 下一步建议

下一阶段建议优先做两个小闭环：

1. 用真实模型 API 跑一次 `api` 模式，比较 raw output 与 mock 样例差异。
2. 扩展 validator：增加 evidence quote 回查、teacher_note 误用检查、action affordance 检查。
3. 基于 `courseware_structure.draft.sample.json` 标出需要 VLM 补证据的 element 和 node。
4. 设计一个 `courseware_structure -> teaching_story -> lesson.json` 的最小转换器，只转换 2-3 个已审查 teaching candidates。
