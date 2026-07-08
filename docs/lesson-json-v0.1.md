# lesson.json v0.1 说明

`lesson.json` 是短期框架 Demo 的核心中间表示，用来连接固定课件页面、页面元素、知识点、教学步骤、GUI 操作和问题反馈。

短期它不是正式 JSON Schema 文件，而是团队协作的数据契约。

## 顶层字段

- `lesson_id`：课程样例 id。
- `title`：课程标题。
- `source_file`：原始课件文件名。本 Demo 暂定为 `微积分入门教学.pptx`。
- `source_status`：资源状态。
  - `placeholder`：当前是占位页面；
  - `exported_from_pptx`：后续替换为真实 PPTX 导出页面。
- `canvas`：课件设计坐标系。
- `slides`：课件页面。
- `knowledge_nodes`：知识点。
- `teaching_steps`：教学步骤。
- `questions`：固定问题与反馈。

## 问题分支字段

`questions[]` 当前支持两个固定跳转字段：

- `next_step_id`：答对后进入的教学步骤；
- `review_step_id`：答错后进入的回顾步骤。

这两个字段用于短期 Demo 的固定分支逻辑。后续接入 LLM 后，可以由 Agent 根据学生回答动态决定下一步。

## 当前说明

当前真实 PPT 文件位于项目外层目录：

```text
C:\Users\13362\Desktop\腾飞科创 gui agent+教育\slidetutor\微积分入门教学.pptx
```

短期 Demo 暂时没有直接解析 PPTX，因此 `apps/web/public/slides/calculus-intro/` 中先放置 3 页 SVG 占位课件。

后续替换真实 PPTX 时，建议：

1. 将 PPTX 每页导出为 `slide-1.png`、`slide-2.png` 等图片；
2. 放入 `apps/web/public/slides/calculus-intro/`；
3. 更新 `apps/web/public/data/lesson.json` 中的 `image` 路径；
4. 根据真实页面重新调整 `elements[].bbox`。
