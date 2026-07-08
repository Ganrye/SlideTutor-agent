# LLM / VLM 课件内容结构化输出验证方案

## 1. 验证目标

本阶段验证目标不是证明模型完全自动化可用，而是确认结构化输出是否足以支撑后续 Agent 教学行为。

核心验证问题：

```text
这份结构化输出能不能让 Agent 知道：
  - 课件整体在讲什么；
  - 每页为什么出现；
  - 关键知识点是什么；
  - 哪些知识点有关联；
  - 哪些页面元素可以被 GUI action 操作；
  - 学生答错后应该回到哪里补讲。
```

## 2. 验证方式

短期采用“人工审查 + 样例映射”的方式。

基本流程：

1. 选择一份 PPT / PDF；
2. 构造 3-5 页 `courseware_structure.json` 样例；
3. 人工检查全局层、页面层、元素层和关系层；
4. 尝试从结构中派生 teaching candidates；
5. 检查这些 candidates 是否能转成现有 `lesson.json` 风格的教学步骤和 GUI actions。

## 3. 全局层检查

验收标准：

- `course.topic` 能概括课件主题；
- `learning_objectives` 与课件内容一致；
- `module_structure` 能反映课件叙述顺序；
- `key_concepts` 覆盖主要知识点；
- 不出现课件中没有依据的核心主题。

失败情况：

- 只是逐页摘要，没有整体结构；
- 把无关外部知识写成课件主线；
- 学习目标和课件实际内容不匹配。

## 4. 页面层检查

验收标准：

- 每页有明确 `page_role`；
- `core_message` 能说明这一页的核心教学信息；
- `teaching_intent` 能说明这一页应该怎么讲；
- `previous_next_relation` 能说明与前后页关系；
- 页面层信息能帮助生成讲解顺序。

失败情况：

- 每页都被标成普通内容页；
- 页面角色和实际页面不符；
- 无法解释这一页在整节课中的作用。

## 5. 元素层检查

验收标准：

- 关键文本、公式、图表、箭头或图片被识别；
- 每个关键元素有 `semantic_role`；
- 元素有可用 `bbox` 或等价定位信息；
- `action_affordance` 能支撑 highlight / mask / zoom / annotate 等动作；
- 元素能关联到知识点。

失败情况：

- 只抽取文字，忽略视觉元素；
- 元素定位无法用于前端 overlay；
- 公式、图表或箭头没有语义解释；
- GUI action 无法指向具体对象。

## 6. 知识关系检查

验收标准：

- 至少包含前置、例证、解释、对比或应用关系；
- 每条关系有明确 `relation_type`；
- 每条关系有简短解释或 evidence；
- 关系能支持答错回顾或跨页跳转。

失败情况：

- 只有知识点列表，没有关系；
- 关系类型模糊；
- 关系不能用于教学路径决策；
- 关系脱离课件证据。

## 7. 教学候选检查

验收标准：

- 至少能生成 3 个 teaching candidates；
- 每个 candidate 有目标知识点、目标页面和目标元素；
- 每个 candidate 至少包含一个讲解目标或问题；
- 至少 2 个 candidate 能映射到 GUI action；
- 至少 1 个 candidate 能设计答错回顾。

失败情况：

- candidate 只是讲稿文本；
- 没有目标元素；
- 无法转成 `lesson.json`；
- 答错后不知道回顾哪一页或哪个概念。

## 8. 追溯性检查

验收标准：

- 核心字段能追溯到 slide/page；
- 重要推断有 `evidence`；
- 不确定内容被标记为 `needs_review`；
- 人工审查者能根据 source_ref 找回原始课件位置。

失败情况：

- 无法判断某个知识点来自哪里；
- LLM 生成内容和课件事实混在一起；
- 低置信度推断没有标记。

## 9. 与现有 Demo 的映射检查

验收标准：

- `slides` 可映射到 `lesson.json.slides`；
- `elements` 可映射到 `lesson.json.elements`；
- `knowledge_nodes` 可映射到 `lesson.json.knowledge_nodes`；
- `teaching_candidates` 可派生 `teaching_steps`；
- `suggested_gui_actions` 可派生 `gui_actions`。

失败情况：

- 结构化输出很好看但前端无法使用；
- 字段和现有数据结构完全脱节；
- 需要大量人工重写才能进入 Demo。

## 10. LLM / VLM 流程检查

验收标准：

- 有明确的分阶段输入输出；
- LLM 页面语义、VLM 元素理解、知识抽象、关系生成和教学候选生成职责清晰；
- prompt 草案要求输出合法 JSON；
- prompt 草案要求保留 evidence、confidence 和 needs_review；
- 有人工校正点和低置信度处理规则；
- 不要求当前阶段接入真实模型 API。

失败情况：

- 只有泛泛 prompt，没有说明字段如何进入分层 JSON；
- LLM / VLM 职责混在一起，无法判断哪一步出错；
- 没有处理模型推断和课件证据的边界；
- 生成结果无法人工审查或回溯。

## 11. 最低通过标准

一份样例结构化输出最低需要满足：

- 至少 3 页；
- 至少 5 个知识节点；
- 至少 5 个关键元素；
- 至少 3 条知识关系；
- 至少 3 个 teaching candidates；
- 至少 2 个 GUI action 候选；
- 至少 1 条答错回顾路径；
- 所有核心内容能追溯到课件页面或元素。
