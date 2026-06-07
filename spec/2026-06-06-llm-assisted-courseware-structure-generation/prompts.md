# 分层 Prompt 模板

## 1. 使用方式

这些 prompt 用于通过 LLM API 生成课件结构草案。每次只生成一个层级，输出必须是纯 JSON，不能包含 Markdown 代码块、解释文字或额外注释。

共同输入：

- `llm_input_package.json`
- `courseware_structure.json v0.1 schema`
- 已完成的上一层输出
- 当前任务名和 prompt 版本

共同输出规则：

- 只输出合法 JSON。
- 字段名必须对齐 v0.1 schema。
- 每个核心结论必须包含 `source_ref` 或 `evidence`。
- `confidence` 必须是 0 到 1 的数字。
- `needs_review` 必须是布尔值。
- 当结论来自教师说明、模型推断或证据不足时，必须设置 `needs_review: true`。
- 不允许把 `teacher_note` 写成课件原文 quote。

API 调用要求：

- 如果模型服务支持 JSON mode 或 JSON schema，应强制使用。
- raw output 必须保存，不能直接覆盖人工修正后的输出。
- 每次调用应记录模型名称、任务名、prompt 版本、输入包 ID 和 token 使用。
- 如果返回 Markdown 包裹、自然语言解释或不完整 JSON，应进入 repair 或 rerun，而不是直接 assemble。

## 2. Course Prompt

### 输入

- 完整 `llm_input_package.json`
- v0.1 schema 中 `course` 字段说明

### Prompt

```text
你是课件结构分析助手。请基于输入包生成 course 层 JSON。

任务：
1. 归纳课件主题 topic。
2. 生成学习目标 learning_objectives，但不得超出输入页覆盖范围。
3. 根据 selected_slide_range 和 slides[] 生成 module_structure。
4. 生成 key_concepts 的候选 ID。ID 应采用稳定英文 snake_case，如 k_derivative。
5. 生成 narrative_flow 和 summary。

约束：
- 你不能读取原始 PPT/PDF，只能使用输入包材料。
- teacher_note 只能作为教学背景，不能作为课件原文证据。
- 如果某个学习目标主要来自 teacher_note 或推断，请降低 confidence 并标记 needs_review。
- module_structure.slide_ids 必须只引用输入包中存在的 slide_id。
- key_concepts 只是候选，后续 knowledge_nodes 必须复用或解释调整。

输出：
只输出一个 JSON object，字段必须为：
course_id, title, source_file, source_type, topic, audience, learning_objectives,
prerequisites, module_structure, key_concepts, narrative_flow, summary,
source_ref, confidence, needs_review
```

### 输出片段

```json
{
  "course_id": "calculus_intro_llm_draft_001",
  "title": "微积分入门教学",
  "source_file": "微积分入门教学.pptx",
  "source_type": "pptx",
  "topic": "微积分中的变化率与累积思想",
  "audience": "微积分初学者或自学者",
  "learning_objectives": [
    "理解微积分围绕变化展开",
    "区分微分学与积分学"
  ],
  "prerequisites": ["函数", "斜率", "面积"],
  "module_structure": [
    {
      "module_id": "m001",
      "title": "变化问题引入",
      "slide_ids": ["s002", "s003"],
      "purpose": "建立变化率与累积的双主线。"
    }
  ],
  "key_concepts": ["k_change", "k_derivative", "k_integral"],
  "narrative_flow": "从变化问题开始，拆分为微分与积分，再用基本定理收束。",
  "summary": "本输入范围构成一个微积分入门链条。",
  "source_ref": {
    "source_file": "微积分入门教学.pptx",
    "slide_id": null,
    "slide_index": null,
    "element_id": null,
    "page_region": "slides_2_to_6"
  },
  "confidence": 0.84,
  "needs_review": false
}
```

## 3. Slides Prompt

### 输入

- `llm_input_package.json`
- 已生成或人工确认的 `course`
- v0.1 schema 中 `slides[]` 字段说明

### Prompt

```text
你是页面教学功能分析助手。请为输入包中每一页生成 slides[] JSON。

任务：
1. 为每页生成 page_role，必须从 v0.1 枚举中选择。
2. 用一句话写 core_message。
3. 写 teaching_intent，说明讲解该页的教学用途。
4. 写 text_summary，只基于 page_text 和 page_summary。
5. 生成 related_concepts，优先使用 course.key_concepts。
6. 生成 previous_next_relation。
7. element_ids 只能引用 known_elements 中属于该 slide 的元素。

约束：
- 不要只复述标题作为 page_role。
- 不确定的页面承接关系要写明推断来源，并标记 needs_review。
- evidence.quote 只能来自 page_text 或 known_elements.content；teacher_note 只能放在 evidence.note 中说明教学意图来源。
- related_concepts 中的 ID 后续必须能被 knowledge_nodes 复用或人工修正。

输出：
只输出 JSON array。每个对象包含：
slide_id, index, title, page_role, core_message, teaching_intent, text_summary,
related_concepts, previous_next_relation, element_ids, source_ref, evidence,
confidence, needs_review
```

## 4. Knowledge Nodes Prompt

### 输入

- `llm_input_package.json`
- `course`
- `slides[]`
- v0.1 schema 中 `knowledge_nodes[]` 字段说明

### Prompt

```text
你是知识节点抽象助手。请从 slides[] 和 known_elements[] 中抽象 knowledge_nodes[]。

任务：
1. 抽取教学上有意义的概念、方法、公式、过程或应用。
2. 不要把每句页面文字机械转成节点。
3. 每个节点必须至少引用一个 source_slide。
4. source_elements 只能引用 known_elements 中存在的 element_id。
5. prerequisites 优先引用已生成 node_id；课件外前置知识可以保留自然语言，但不能伪造成 node_id。
6. common_confusions 必须和输入材料或常见初学误解相关，不能脱离本课件主题。

约束：
- 节点粒度过细、证据不足、只来自 teacher_note 时必须 needs_review。
- 如果 course.key_concepts 中的候选概念被删除或合并，请在 evidence.note 中说明。
- 不允许新增课件完全未覆盖的核心概念。

输出：
只输出 JSON array。每个对象包含：
node_id, type, title, description, difficulty, source_slides, source_elements,
prerequisites, common_confusions, teaching_notes, evidence, confidence, needs_review
```

## 5. Knowledge Relations Prompt

### 输入

- `llm_input_package.json`
- 已生成或人工确认的 `knowledge_nodes[]`
- `slides[]`
- v0.1 schema 中 `knowledge_relations[]` 字段说明

### Prompt

```text
你是知识关系生成助手。请基于 knowledge_nodes[] 和 slides[] 生成 knowledge_relations[]。

任务：
1. 生成对教学顺序、提问、答错回顾有用的关系。
2. relation_type 必须从 v0.1 枚举中选择。
3. source_id 和 target_id 必须引用已存在 node_id。
4. source_slides 和 source_elements 必须能支撑关系判断。
5. description 必须解释方向为什么成立。

约束：
- prerequisite_of 的方向必须是“前置知识 -> 后续知识”。
- 不要把单纯共现当作关系。
- 如果关系主要来自页面顺序而不是直接文本证据，confidence 不应高于 0.8，并设置 needs_review。
- 关系证据不足时宁可少生成，也不要编造。

输出：
只输出 JSON array。每个对象包含：
relation_id, source_id, target_id, relation_type, description, source_slides,
source_elements, evidence, confidence, needs_review
```

## 6. Teaching Candidates Prompt

### 输入

- `llm_input_package.json`
- 已生成或人工确认的 `slides[]`
- 已生成或人工确认的 `knowledge_nodes[]`
- 已生成或人工确认的 `knowledge_relations[]`
- v0.1 schema 中 `teaching_candidates[]` 字段说明

### Prompt

```text
你是教学候选生成助手。请生成 teaching_candidates[] 草案。

任务：
1. 为核心知识节点生成可转成讲解、问题、反馈和 GUI action 的候选。
2. target_concept 必须引用已存在 node_id。
3. target_slide 必须引用已存在 slide_id。
4. target_elements 必须引用该页 known_elements 中存在的 element_id。
5. suggested_gui_actions.action_type 必须来自目标元素的 allowed_action_affordance。
6. review_strategy 应优先利用 knowledge_relations 中的前置或回顾关系。

约束：
- 本阶段不要求生成最终 lesson.json。
- 如果 action 需要前端转换，请在 evidence.note 或 review_strategy.reason 中标明。
- 问题答案必须能从输入材料判断。
- 如果 target_elements 不足以支持 GUI action，保留空数组并设置 needs_review。

输出：
只输出 JSON array。每个对象包含：
candidate_id, target_concept, target_slide, target_elements, explanation_goal,
suggested_question, suggested_gui_actions, feedback_strategy, review_strategy,
source_ref, evidence, confidence, needs_review
```

## 7. 推荐调用顺序

```text
llm_input_package.sample.json
  -> Course Prompt
  -> Slides Prompt
  -> Knowledge Nodes Prompt
  -> Knowledge Relations Prompt
  -> Teaching Candidates Prompt
  -> human review
  -> optional assemble to courseware_structure.draft.json
```

## 8. 重跑规则

- 如果 course 的 `key_concepts` 大面积偏离输入材料，重跑 course。
- 如果 slides 的 `page_role` 多页机械重复，重跑 slides。
- 如果 knowledge_nodes 粒度失控，重跑 knowledge_nodes，并在 prompt 中加入正反例。
- 如果 relations 出现方向性错误，可局部修正；若超过三分之一关系方向错误，重跑 relations。
- 如果 teaching candidates 引用不存在的元素，应先局部修正引用；若问题答案不可从课件判断，重跑 candidates。
