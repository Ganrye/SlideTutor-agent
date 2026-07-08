# SlideTutor Agent

SlideTutor Agent 是一个面向高中与大学自学复习场景的交互式 PPT / PDF 讲解 Agent。

当前仓库处于短期框架 Demo 阶段：先用固定课件页面和固定 `lesson.json`，在前端模拟 GUI Agent 对课件执行 highlight、mask、jump、question popup 和 feedback。

## 当前阶段定位

项目已经从单纯的前端交互 Demo，转向先构建面向 PPT / PDF 的知识中间层。当前首要任务是根据课件内容建立 Agent 可理解的结构化知识基础，使 Agent 不只是把 PPT / PDF 当作普通文档读取，而是能够理解文档背后的叙述逻辑、讲述主题、知识点分布以及知识点之间的逻辑联系。

这个知识中间层后续将作为讲解 Agent 的基础输入，支撑从“课件页面内容”到“可讲解、可提问、可反馈的教学流程”的转换。

当前新开发分支：

```text
feature/llm-vlm-courseware-structure
```

该分支的重点是开发一个基于 LLM / VLM 理解能力的课件内容结构化输出功能，将 PPT / PDF 转化为可被 Agent 使用的 `courseware_structure.json` 或类似知识中间层。

建议的主链路是：

```text
PPT / PDF
  -> Courseware Teaching Graph
  -> Teaching Plan / Teaching Story
  -> lesson.json
  -> GUI Actions / Questions / Feedback
  -> Interactive Learning Process
```

### 阶段任务

1. 课件与输入信息的知识结构化

   - 核心目标：将静态教学材料转化为 Agent 能理解的底层知识逻辑。
   - 具体内容：深入解析 PPT / PDF 背后的知识结构和逻辑关联，并结合教师输入的文本描述、前置知识或教学意图，构建结构化知识基础。这是后续辅助讲解与交互设计的重要前提。

2. 从结构化知识到叙述性知识的转化

   - 核心目标：把零散、结构化的知识点，转化为更易传递、更有逻辑深度的课堂表达。
   - 具体内容：探索 Agent 如何辅助教师提炼和加工信息，包括理解什么是好的知识讲述、如何形成清晰的讲解路径，以及如何通过方法设计、模型微调或接入知识库，让 Agent 辅助产出更好懂、逻辑性更强、更有深度的授课内容。

3. 基于学生动态反馈的复杂交互与个性化定制

   - 核心目标：处理学生接入后的复杂互动，实现课堂或自学过程的动态迭代。
   - 具体内容：当学生提出问题、表达困惑或希望深入了解某个点时，Agent 需要根据实时反馈做出个性化响应与讲解调整，逐步实现根据学生学习状态辅助教学。

### 当前功能设计思路

本阶段将课件知识中间层理解为一个“可教学、可交互、可操控的多层课件图谱”。

结构上参考 `SlideAgent` 对多页视觉文档的分层理解：

- Global：整份课件的主题、教学目标、整体知识路径和前置知识；
- Page：每一页的教学功能、核心信息、讲解意图和跨页关系；
- Element：页面中的文本、公式、图表、箭头、图片等可操作对象，以及它们的语义角色和 GUI action 适配能力。

交互上参考 `Generative Lecture` 的思想：AI 内容不应脱离原始学习材料单独存在，而应嵌入课件界面，服务即时澄清、主动提问、反馈、复习总结和后续个性化讲解。

因此，当前功能的目标不是直接生成讲稿，而是先输出稳定的结构化中间层，再由后续模块把结构转化为讲解路径、问题、反馈和 GUI actions。

## 当前 Demo

暂定课件：

```text
微积分入门教学.pptx
```

该 PPTX 当前位于：

```text
C:\Users\13362\Desktop\腾飞科创 gui agent+教育\slidetutor\微积分入门教学.pptx
```

短期 Demo 先使用 3 页“微积分入门教学”占位 slide。后续把 PPTX 导出为图片后，可以替换 `apps/web/public/slides/calculus-intro/` 中的资源，并同步调整 `apps/web/public/data/lesson.json`。

## 项目结构

```text
SlideTutor-agent/
  apps/
    web/                  # Vite + React + TypeScript 前端 Demo
  docs/
    lesson-json-v0.1.md   # lesson.json v0.1 说明
  spec/                   # LLM / VLM 课件结构化输出功能规格
  specs/                  # 项目使命、技术栈、路线图、短期 Demo 规格
```

## 已完成任务组

### 任务组 A：前端工程骨架

- 基于现有 `apps/web` Vite 工程合并 Demo；
- 替换默认模板页为 SlideTutor Agent Demo；
- 添加基础交互界面和样式；
- 保持 `npm run dev` / `npm run build` 工作流。

### 任务组 B：固定课件资源

当前占位资源：

- `apps/web/public/slides/calculus-intro/slide-1.svg`
- `apps/web/public/slides/calculus-intro/slide-2.svg`
- `apps/web/public/slides/calculus-intro/slide-3.svg`

这些是短期占位资源，用于模拟 PPT 页面。

### 任务组 C：`lesson.json v0.1`

- `apps/web/public/data/lesson.json`
- `docs/lesson-json-v0.1.md`

当前 `lesson.json` 包含：

- `slides`
- `elements`
- `knowledge_nodes`
- `teaching_steps`
- `gui_actions`
- `questions`
- 固定反馈与回顾路径

### 任务组 D：Slide Player

- `apps/web/src/components/SlidePlayer.tsx`
- 支持固定课件页面展示；
- 支持当前步骤进度显示；
- 支持由 `jump` action 切换当前 slide；
- 支持在 slide 上叠加 highlight / mask overlay。

### 任务组 E：GUI Action Executor

- `apps/web/src/runtime/actionRuntime.ts`
- 支持从 teaching step 中提取 overlay action；
- 支持从 teaching step 中解析 question；
- 支持从 teaching step 中解析 jump 目标；
- 支持答题后选择下一步；
- 未知或无效 action 不会阻断整个页面渲染。

### 任务组 F：提问、反馈与学习总结

- `apps/web/src/components/QuestionPanel.tsx`
- `apps/web/src/components/FeedbackPanel.tsx`
- `apps/web/src/components/SummaryPanel.tsx`
- 答对后进入 `next_step_id`；
- 答错后进入 `review_step_id`；
- 学习结束后输出固定模板总结。

## 本地启动

从仓库根目录启动前端 Demo：

```bash
cd SlideTutor-agent/apps/web
npm install
npm run dev
```

访问地址：

```text
http://127.0.0.1:5173
```

进入前端目录：

```bash
cd apps/web
```

安装依赖：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

## 短期验证目标

启动后应能看到：

- 固定课件页面；
- `Next Step` 推进教学步骤；
- `highlight` 高亮；
- `mask` 遮罩；
- `question_popup` 固定选择题；
- 答错后跳转到回顾页；
- 答对后跳过回顾页，进入导数定义；
- 最后显示简单学习总结。

## 项目文档

- `specs/mission.md`
- `specs/tech-stack.md`
- `specs/roadmap.md`
- `specs/2026-05-24-short-term-framework-demo/plan.md`
- `specs/2026-05-24-short-term-framework-demo/requirements.md`
- `specs/2026-05-24-short-term-framework-demo/validation.md`
- `spec/mission.md`
- `spec/tech-stack.md`
- `spec/roadmap.md`
- `spec/2026-06-05-llm-vlm-courseware-structure-output/plan.md`
- `spec/2026-06-05-llm-vlm-courseware-structure-output/requirements.md`
- `spec/2026-06-05-llm-vlm-courseware-structure-output/validation.md`

## 论文参考材料

以下论文 Markdown 是当前知识层构造和结构化输出功能的重要参考：

- `SlideAgent_paper/`
  - 主要用于查询多页视觉文档的 global / page / element 分层理解、跨页关系、页面元素语义和视觉布局推理。
- `generative Lecture/`
  - 主要用于查询如何把静态学习材料转化为可提问、可补充、可反馈、可嵌入原始材料的交互式学习过程。

## 当前不做

- 不接入 LLM；
- 不接入后端；
- 不做真实 PPT/PDF 自动解析；
- 不做用户系统；
- 不做复杂游戏化模块。
