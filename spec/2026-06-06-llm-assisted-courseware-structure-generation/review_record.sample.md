# 人工审查记录样例

## 基本信息

| 字段 | 内容 |
| --- | --- |
| Input Package | `llm_input_package.sample.json` |
| Draft | `courseware_structure.draft.sample.json` |
| Baseline | `../2026-06-05-llm-vlm-courseware-structure-output/courseware_structure.sample.json` |
| Reviewer | human-review-placeholder |
| Review Date | 2026-06-06 |
| Status | `accepted_with_review_flags` |

## 审查结论

草案 JSON 可解析，主要字段与 v0.1 schema 对齐。第 2-5 页的页面角色、核心信息、节点和关系基本可用。第 6 页涉及微积分基本定理的公式解释、互逆关系拆分和跨页前置关系，需要保留人工审查标记，不应直接进入最终 `lesson.json`。

## 问题记录

### ISSUE-001

| 字段 | 内容 |
| --- | --- |
| Layer | `slides` |
| Location | `slides[s006].text_summary` |
| Error Type | `unsupported_evidence` |
| Original | `若 F'(x)=f(x)，则积分可表示为 F(x)+C；变化率的累积等于总变化量。` |
| Revision | 保留原文摘要，但将 `confidence` 维持在 `0.72`，并设置 `needs_review: true` |
| Reason | 输入包只提供公式性文本，没有区分不定积分、定积分和基本定理完整表述，适合人工复核。 |
| Action | 局部保留并标记 |
| Needs Rerun | No |
| Status | Open for human review |

### ISSUE-002

| 字段 | 内容 |
| --- | --- |
| Layer | `knowledge_nodes` |
| Location | `knowledge_nodes[k_tangent_slope].teaching_notes` |
| Error Type | `missing_visual_evidence` |
| Original | `适合结合切线斜率讲解。` |
| Revision | `输入包没有图形细节，后续需要 VLM 或人工补充图像解释。` |
| Reason | 只有文本“切线的斜率 = 该点的导数”，没有图形或割线趋近切线的视觉证据。 |
| Action | 局部修正 |
| Needs Rerun | No |
| Status | Revised |

### ISSUE-003

| 字段 | 内容 |
| --- | --- |
| Layer | `knowledge_nodes` |
| Location | `knowledge_nodes[k_inverse_relation]` |
| Error Type | `concept_granularity` |
| Original | 互逆关系被作为独立节点生成 |
| Revision | 保留节点，但设置 `needs_review: true`，要求人工判断是否并入 `k_fundamental_theorem` |
| Reason | 人工样例中互逆关系可独立作为解释性节点，但在更小输入包中也可能作为基本定理说明的一部分。 |
| Action | 保留待审查 |
| Needs Rerun | No |
| Status | Open for human review |

### ISSUE-004

| 字段 | 内容 |
| --- | --- |
| Layer | `knowledge_relations` |
| Location | `knowledge_relations[r006]`, `knowledge_relations[r007]` |
| Error Type | `unsupported_evidence` |
| Original | `k_derivative -> k_fundamental_theorem` 和 `k_integral -> k_fundamental_theorem` 均为 `prerequisite_of` |
| Revision | 保留方向，降低 confidence 到 `0.72`，设置 `needs_review: true` |
| Reason | 从教学顺序看方向合理，但输入包中对基本定理的公式解释不完整，不能给高置信度。 |
| Action | 局部标记 |
| Needs Rerun | No |
| Status | Open for human review |

### ISSUE-005

| 字段 | 内容 |
| --- | --- |
| Layer | `teaching_candidates` |
| Location | `teaching_candidates[tc003].review_strategy` |
| Error Type | `needs_frontend_conversion` |
| Original | 回顾第 4、5、6 页并 highlight `e_s6_core` |
| Revision | 保留 candidate，但设置 `needs_review: true` |
| Reason | 该候选依赖跨页回顾；现有前端可支持部分 highlight，但是否转换为具体教学步骤需后续转换器判断。 |
| Action | 保留待转换 |
| Needs Rerun | No |
| Status | Open for converter design |

### ISSUE-006

| 字段 | 内容 |
| --- | --- |
| Layer | `elements` |
| Location | all `elements[]` |
| Error Type | `phase_boundary` |
| Original | 草案中包含 `elements[]` |
| Revision | 在 metadata 中说明 elements 来自 known_elements，不由 LLM 推断 bbox |
| Reason | 本阶段 LLM 不应自行生成 bbox；草案包含 elements 只是为了 assembled JSON 可被后续引用检查。 |
| Action | 边界说明 |
| Needs Rerun | No |
| Status | Accepted with note |

## 未解决问题

- 第 6 页公式层面的数学表述仍需教师或人工标注者复核。
- 切线斜率、面积分割等视觉语义需要阶段三 VLM 或人工图像标注补足。
- `tc003` 是否能直接转成现有前端步骤，需要等 courseware-to-lesson 转换器设计后再确认。

## 是否重跑 Prompt

暂不重跑。当前问题主要是边界和局部置信度问题，不是结构整体失控。建议在下一次 relations 和 teaching_candidates prompt 中加入：

- “跨页前置关系若只来自教学顺序，confidence 不高于 0.8。”
- “涉及公式边界或 teacher_note 提醒时必须 needs_review。”
- “跨页 GUI action 候选必须标明需要转换器处理。”
