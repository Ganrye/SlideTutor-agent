# 最小 LLM Runner

## 1. 目标

`scripts/generate_courseware_structure.py` 用于把本阶段的方案推进到可运行闭环：

```text
llm_input_package.json
  -> mock 或 LLM API
  -> raw_outputs/
  -> validated_outputs/
  -> courseware_structure.draft.json
  -> validation_report.md
```

这个 runner 不负责解析原始 PPT / PDF，也不直接生成最终 `lesson.json`。它只处理已经整理好的 `llm_input_package.json`，并依赖大模型或样例草案生成结构化文本。

## 2. 离线 mock 验证

无 API key 时先跑 mock 模式。mock 会读取 `courseware_structure.draft.sample.json`，拆成分层输出，再走同一套校验和装配流程。

```powershell
cd SlideTutor-agent
python scripts/generate_courseware_structure.py `
  --mode mock `
  --input spec/2026-06-06-llm-assisted-courseware-structure-generation/llm_input_package.sample.json `
  --output-dir outputs/calculus_intro_mock
```

默认会在输出目录名后追加时间戳，避免覆盖旧结果。例如上面的命令实际可能生成：

```text
outputs/calculus_intro_mock_20260606_194500/
```

如果确实想覆盖固定目录，可以加 `--no-timestamp-output`。

期望输出：

```text
outputs/calculus_intro_mock_<timestamp>/
  llm_input_package.json
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
  courseware_structure.draft.json
  validation_report.md
```

## 3. 本地 API 配置

推荐把 API URL 和 key 放到本地配置文件，不要每次手动输入，也不要提交到 Git。

先复制模板：

```powershell
cd SlideTutor-agent
Copy-Item config/llm.example.json config/llm.local.json
```

然后编辑 `config/llm.local.json`：

```json
{
  "api_base": "https://your-api-host.example/v1",
  "api_key": "你的 API key",
  "model": "DeepSeek-V3-64K"
}
```

`api_base` 可以填 base URL，例如 `https://your-api-host.example/v1`；也可以填完整接口，例如 `https://api.modelarts-maas.com/v2/chat/completions`。runner 会自动避免重复拼接 `/chat/completions`。

`config/llm.local.json` 已被 `.gitignore` 忽略。这个文件可以长期保存在本机，但不要把真实 key 写进 `config/llm.example.json`。

优先级：

```text
命令行参数
  -> config/llm.local.json
  -> 环境变量
  -> 脚本默认值
```

## 4. 真实 API 调用

真实 API 调用使用 OpenAI-compatible `/chat/completions` 接口。API key 从 `config/llm.local.json` 或环境变量读取，不写入输出日志。

```powershell
cd SlideTutor-agent
python scripts/generate_courseware_structure.py `
  --mode api `
  --input spec/2026-06-06-llm-assisted-courseware-structure-generation/llm_input_package.sample.json `
  --output-dir outputs/calculus_intro_api
```

如果临时想覆盖本地配置，可以继续传命令行参数：

```powershell
python scripts/generate_courseware_structure.py `
  --mode api `
  --model Qwen3-32B-64K `
  --api-base https://another-api-host.example/v1 `
  --input spec/2026-06-06-llm-assisted-courseware-structure-generation/llm_input_package.sample.json `
  --output-dir outputs/calculus_intro_api
```

也可以继续使用环境变量：

```powershell
$env:SLIDETUTOR_LLM_API_KEY="你的 API key"
$env:SLIDETUTOR_LLM_API_BASE="https://your-api-host.example/v1"
```

## 5. 分层任务

默认按顺序运行：

```text
generate_course
generate_slides
generate_knowledge_nodes
generate_knowledge_relations
generate_teaching_candidates
```

也可以只跑部分层级：

```powershell
python scripts/generate_courseware_structure.py `
  --mode mock `
  --input spec/2026-06-06-llm-assisted-courseware-structure-generation/llm_input_package.sample.json `
  --output-dir outputs/calculus_intro_course_only `
  --tasks generate_course generate_slides
```

注意：relations 和 teaching_candidates 依赖前面的 nodes 输出。单独运行后置任务时，需要确保前置层已经存在，或后续扩展脚本支持读取已有 validated outputs。

## 6. 校验范围

当前 validator 已检查：

- JSON parse；
- 必需字段；
- `confidence` 是否为 0 到 1；
- `needs_review` 是否为布尔值；
- slide ID 引用；
- element ID 引用；
- relation 的 node ID 引用；
- teaching candidate 的 target concept / slide / element 引用。

当前 validator 还没有做：

- 严格 JSON Schema 校验；
- evidence quote 回查全文；
- teacher_note 与课件原文混淆检查；
- action_type 与每个元素 affordance 的逐项比对；
- token 预算上限拦截；
- repair prompt 自动修复。

这些是后续工程化优先补强点。

## 7. 当前完成状态

至此，本阶段已经从“API-ready 文档设计”推进到“最小可运行 runner”：

- 没有 API key 时，可以用 mock 验证文件组织、校验和 assembled draft；
- 有 API key 时，可以调用长上下文文本模型生成分层结构化文本；
- 所有输出先进入 `courseware_structure.draft.json` 和人工审查，不直接覆盖前端 demo 数据。
