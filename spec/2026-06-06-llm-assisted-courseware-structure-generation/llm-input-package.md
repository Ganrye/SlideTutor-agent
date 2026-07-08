# LLM 输入包设计

## 1. 定位

`llm_input_package.json` 是调用 LLM 前的标准输入材料。它把课件文本、页面摘要、已知元素和教师补充说明组织成可独立消费的结构，避免 prompt 直接依赖原始 PPT / PDF 或聊天上下文。

本阶段不让 LLM 直接读取原始课件文件，也不要求它识别截图。LLM 只能基于输入包中显式提供的材料生成 `courseware_structure.json v0.1` 草案。

## 2. 设计原则

- 保留原始页码：每个 slide 必须有 `index` 和 `slide_id`。
- 区分来源：文本、摘要、OCR、人工补充和教师说明必须分开标注。
- 不预填答案：输入包提供材料，不提前写好 `page_role`、`knowledge_nodes` 或关系结论。
- 可追溯：每条材料都能回到 slide、element 或教师说明。
- 可分层调用：同一输入包可被 course、slides、knowledge_nodes、relations 和 teaching_candidates prompt 复用。

## 3. 顶层结构

```json
{
  "package_id": "calculus_intro_llm_input_001",
  "source_file": "微积分入门教学.pptx",
  "source_type": "pptx",
  "selected_slide_range": { "start": 2, "end": 6 },
  "target_schema_version": "0.1",
  "course_context": {},
  "slides": [],
  "known_elements": [],
  "generation_tasks": [],
  "constraints": [],
  "metadata": {}
}
```

## 4. 字段说明

| 字段 | 说明 |
| --- | --- |
| `package_id` | 输入包 ID，便于审查记录引用 |
| `source_file` | 原始课件文件名，不代表 LLM 可直接读取该文件 |
| `selected_slide_range` | 本次处理页码范围 |
| `target_schema_version` | 目标 `courseware_structure.json` schema 版本 |
| `course_context` | 教师补充的课程背景、学习者、前置知识和讲解目标 |
| `slides[]` | 每页输入文本、摘要和证据提示 |
| `known_elements[]` | 来自 parser、OpenXML、OCR 或人工标注的页面元素 |
| `generation_tasks[]` | 本轮要求 LLM 生成的层级 |
| `constraints[]` | 生成约束和禁止事项 |
| `metadata` | 输入包生成方式、审查状态和上游材料 |

## 5. Slide 输入结构

```json
{
  "slide_id": "s002",
  "index": 2,
  "title": {
    "text": "什么是微积分？ —— 动态世界的语言",
    "source": "parser"
  },
  "page_text": [
    {
      "source": "parser",
      "text": "微积分是一门研究“变化”的科学。",
      "evidence_id": "txt_s002_001"
    }
  ],
  "page_summary": {
    "source": "human_summary",
    "text": "本页用定义和两个核心问题引入微积分。"
  },
  "teacher_notes": [
    {
      "note_id": "tn_s002_001",
      "text": "讲解时强调“变化有多快”和“变化累积了多少”不是课件原文的新概念，而是对页面问题的教学归纳。",
      "source": "teacher_note"
    }
  ],
  "parser_evidence": [
    {
      "evidence_id": "txt_s002_001",
      "source_type": "parser_text",
      "source_ref": { "slide_id": "s002", "slide_index": 2 }
    }
  ]
}
```

## 6. Known Element 输入结构

`known_elements[]` 只表示上游已经识别出的页面对象。LLM 可以引用它们，但本阶段不能自行生成 bbox。

```json
{
  "element_id": "e_s2_core",
  "slide_id": "s002",
  "type": "text",
  "content": "核心思想：微积分是一门研究“变化”的科学。",
  "bbox": { "x": 0.135, "y": 0.232, "width": 0.771, "height": 0.111 },
  "source": "manual_from_parser",
  "evidence_hint": "定义关键短语",
  "allowed_action_affordance": ["highlight", "annotate"]
}
```

## 7. 来源标注规则

| 来源值 | 含义 | LLM 使用方式 |
| --- | --- | --- |
| `parser` | 从 PPT / PDF 文本解析得到 | 可作为课件原文证据 |
| `ocr` | OCR 得到 | 可作为证据，但通常置信度略低 |
| `human_summary` | 人工页面摘要 | 可辅助归纳，但不是课件原文 quote |
| `teacher_note` | 教师补充说明 | 只能作为教学意图或背景，不能伪装为课件原文 |
| `manual_from_parser` | 人工基于 parser 整理的元素 | 可用于 element 引用和 GUI action 候选 |

## 8. 生成任务拆分

推荐同一输入包分 5 次调用：

1. `generate_course`
2. `generate_slides`
3. `generate_knowledge_nodes`
4. `generate_knowledge_relations`
5. `generate_teaching_candidates`

后续层级必须显式读取前一层输出。例如 relations prompt 必须输入已审查或待审查的 `knowledge_nodes`，不能重新发明 node ID。

## 9. 最小验收

- 覆盖 3 到 5 页样例。
- 每页至少有文本、摘要或教师补充之一。
- 每条材料都保留 slide index。
- 教师补充说明与课件原文分离。
- `known_elements` 中的元素 ID 可被 teaching candidates 引用。
- 输入包本身不包含最终 `page_role`、知识关系方向或 teaching candidate 答案。
