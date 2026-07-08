# LLM API 接入设计

## 1. 目标定位

本阶段希望从“离线 prompt 方案”推进到“可接入真实 LLM API 的结构化生成方案”。目标不是让大模型直接读取原始 PPT / PDF 文件，而是让工程侧先把课件整理成 `llm_input_package.json`，再依赖大模型的语言理解、概念抽象、关系推理和教学设计能力，输出可解析、可审查的结构化文本。

目标链路：

```text
PPT / PDF
  -> parser / OCR / 人工补充
  -> llm_input_package.json
  -> LLM API
  -> course.json / slides.json / knowledge_nodes.json / knowledge_relations.json / teaching_candidates.json
  -> validator
  -> courseware_structure.draft.json
  -> human review
```

## 2. 大模型负责什么

LLM 主要负责文本语义和教学结构推理：

- 从页面文本和摘要中归纳课件主题；
- 判断每页的教学角色和核心信息；
- 抽象知识节点；
- 建立知识点之间的解释、前置、应用、总结关系；
- 生成讲解目标、检查问题、反馈策略和 GUI action 候选；
- 对证据不足、公式边界不清、视觉信息不足的位置标记 `needs_review`。

LLM 不负责：

- 直接读取 `.pptx` / `.pdf` 文件；
- 生成或校准 bbox；
- 判断截图中的复杂视觉布局；
- 把草案直接变成最终 `lesson.json`；
- 替代人工审查。

## 3. 推荐模型分工

| 任务 | 推荐模型类型 | 说明 |
| --- | --- | --- |
| 主结构生成 | 长上下文文本模型，如 `DeepSeek-V3-64K` 或 `Qwen3-32B-64K` | 适合处理 schema、prompt、输入包和多页课件文本 |
| 关系审查 | 推理模型，如 `DeepSeek-R1-64K` 或 `QwQ-32B-32K` | 用于复核 prerequisite 方向、发现无证据推断 |
| 视觉补充 | 多模态模型，如 `Qwen2.5-VL-72B-32K` | 属于阶段三，用于页面截图、图表、公式和空间布局 |

最小工程版本可以先只接一个长上下文文本模型。多模态模型不阻塞阶段二，但应在输出中保留需要 VLM 补证据的位置。

## 4. API 调用策略

推荐分层调用，而不是一次生成整包：

```text
call_1: generate_course
call_2: generate_slides
call_3: generate_knowledge_nodes
call_4: generate_knowledge_relations
call_5: generate_teaching_candidates
```

分层调用的好处：

- 每层输出更短，更容易稳定生成合法 JSON；
- 某一层失败时可以只重跑该层；
- 人工审查可以定位到 course、slides、nodes、relations 或 candidates；
- 预算可控，低价值层级可跳过或延后。

## 5. API 请求格式

工程侧应构造一个统一请求对象：

```json
{
  "model": "DeepSeek-V3-64K",
  "task": "generate_knowledge_nodes",
  "schema_version": "0.1",
  "input_package": {},
  "previous_outputs": {
    "course": {},
    "slides": []
  },
  "constraints": [
    "Return valid JSON only.",
    "Do not invent unsupported concepts.",
    "Use confidence from 0 to 1.",
    "Set needs_review to true when evidence is weak."
  ]
}
```

实际 API 层可拆成：

- `system_prompt`：角色、边界、JSON-only 规则；
- `developer_prompt`：schema、字段、枚举、证据规则；
- `user_prompt`：当前输入包和当前任务；
- `response_format`：如果平台支持 JSON schema 或 JSON mode，应强制开启。

## 6. 输出格式要求

LLM API 返回值必须是纯 JSON。工程侧接收后先保存原始输出，再解析：

```text
raw_outputs/
  course.raw.json
  slides.raw.json
  knowledge_nodes.raw.json
  knowledge_relations.raw.json
  teaching_candidates.raw.json

validated_outputs/
  course.json
  slides.json
  knowledge_nodes.json
  knowledge_relations.json
  teaching_candidates.json
```

如果模型返回 Markdown、解释性文字或不完整 JSON，不能直接进入 assembled 草案，必须进入 repair 或 rerun。

## 7. Validator 要求

每次 API 输出后必须做本地校验：

- JSON parse；
- 必需字段检查；
- `confidence` 类型和范围检查；
- `needs_review` 类型检查；
- enum 检查；
- slide / element / node ID 引用检查；
- evidence quote 是否能回到输入包文本或 known element；
- teacher note 是否被误当成课件原文；
- 预算和 token 使用记录。

校验失败处理：

| 失败类型 | 处理 |
| --- | --- |
| JSON 无法解析 | 尝试一次 repair prompt，仍失败则重跑 |
| 字段缺失 | 小范围自动补空值并标记 review，或重跑该层 |
| 引用不存在 | 删除或重跑该层 |
| evidence 不存在 | 降低 confidence，设置 `needs_review`，严重时删除 |
| 课件外编造 | 删除并记录为 hallucination |

## 8. 预算控制

2000 元预算下，推荐先做小范围实验：

1. 每次只处理 3-5 页；
2. 先跑文本模型，不先跑 VLM；
3. 只在公式、图表、布局重要页面调用 VLM；
4. raw output 和 validated output 都落盘，避免重复调用；
5. 对 relations 和 candidates 允许局部重跑；
6. 长文档采用 slide chunk，再做全局合并。

推荐预算使用：

```text
60%-70%: 主文本结构生成
20%-30%: VLM 页面视觉补充
10%: 关系审查、失败重跑和实验余量
```

## 9. 最小工程接口

建议先实现一个 CLI：

```text
generate-courseware-structure --input 微积分入门教学.pptx --slides 2-6 --model DeepSeek-V3-64K
```

第一版输出：

```text
outputs/微积分入门教学/
  llm_input_package.json
  raw_outputs/
  validated_outputs/
  courseware_structure.draft.json
  validation_report.md
```

## 10. 成功标准

最小 API 接入成功标准：

- 给定一个已有输入包，能调用 LLM API 生成至少 course、slides、knowledge_nodes、knowledge_relations 四层；
- 输出能被 JSON parser 解析；
- 至少 90% 的 ID 引用能通过 validator；
- 所有低证据结论有 `needs_review: true`；
- 能 assemble 成 `courseware_structure.draft.json`；
- raw output、validated output 和 validation report 都可追踪。
