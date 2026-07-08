#!/usr/bin/env python3
"""Generate a courseware structure draft from an LLM input package.

The script supports two execution modes:
- mock: split an existing sample draft into the same artifacts produced by API mode.
- api: call an OpenAI-compatible chat completions endpoint with layered prompts.

No third-party dependency is required. API keys can be read from an ignored
local config file or environment variables and are never written to output
files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any
from urllib import error, request


SPEC_DIR = (
    Path(__file__).resolve().parents[1]
    / "spec"
    / "2026-06-06-llm-assisted-courseware-structure-generation"
)
DEFAULT_LOCAL_CONFIG = Path("config") / "llm.local.json"

DEFAULT_TASKS = [
    "generate_course",
    "generate_slides",
    "generate_knowledge_nodes",
    "generate_knowledge_relations",
    "generate_teaching_candidates",
]

TASK_OUTPUT_FILES = {
    "generate_course": ("course", "course.json"),
    "generate_slides": ("slides", "slides.json"),
    "generate_knowledge_nodes": ("knowledge_nodes", "knowledge_nodes.json"),
    "generate_knowledge_relations": ("knowledge_relations", "knowledge_relations.json"),
    "generate_teaching_candidates": ("teaching_candidates", "teaching_candidates.json"),
}

ALLOWED_RELATION_TYPES = {
    "prerequisite_of",
    "part_of",
    "explains",
    "example_of",
    "contrasts_with",
    "derives_to",
    "applies_to",
    "summarizes",
    "review_target_for",
}

TASK_PROMPTS = {
    "generate_course": """Generate the course layer JSON object.
Required fields: course_id, title, source_file, source_type, topic, audience,
learning_objectives, prerequisites, module_structure, key_concepts,
narrative_flow, summary, source_ref, confidence, needs_review.
learning_objectives MUST be a non-empty JSON array of 3-6 concrete,
student-facing objectives (what the learner should be able to do). Never
return an empty learning_objectives array.
module_structure MUST be a JSON array, not an object. Each module item must
include module_id, title, slide_ids, purpose. Use slide_ids, not slides.
Only use the input package. Do not claim access to the original PPT/PDF.""",
    "generate_slides": """Generate the slides layer as a JSON array.
Each item must include: slide_id, index, title, page_role, core_message,
teaching_intent, text_summary, related_concepts, previous_next_relation,
element_ids, source_ref, evidence, confidence, needs_review.
element_ids must reference known_elements in the input package.""",
    "generate_knowledge_nodes": """Generate knowledge_nodes as a JSON array.
Each item must include: node_id, type, title, description, difficulty,
source_slides, source_elements, prerequisites, common_confusions,
teaching_notes, evidence, confidence, needs_review.
Do not turn every sentence into a node.""",
    "generate_knowledge_relations": """Generate knowledge_relations as a JSON array.
Each item must include: relation_id, source_id, target_id, relation_type,
description, source_slides, source_elements, evidence, confidence, needs_review.
source_id and target_id must reference existing knowledge node IDs.
relation_type MUST be exactly one of: prerequisite_of, part_of, explains,
example_of, contrasts_with, derives_to, applies_to, summarizes,
review_target_for. Do not invent other relation types.""",
    "generate_teaching_candidates": """Generate teaching_candidates as a JSON array.
Each item must include: candidate_id, target_concept, target_slide,
target_elements, explanation_goal, suggested_question, suggested_gui_actions,
feedback_strategy, review_strategy, source_ref, evidence, confidence,
needs_review. GUI action types must come from allowed_action_affordance.
target_concept MUST be an existing knowledge node_id from previous_outputs
(e.g. "kn_003"), NOT the node title text. target_slide MUST be a known
slide_id and target_elements MUST be known element_ids.""",
}


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a JSON object: {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def utc_now_text() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"[{utc_now_text()}] {message}", flush=True)


def timestamp_suffix() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_output_dir(
    input_package: dict[str, Any],
    output_dir: str | None,
    add_timestamp: bool = True,
) -> Path:
    if output_dir:
        base = Path(output_dir)
        if not add_timestamp:
            return base
        return base.with_name(f"{base.name}_{timestamp_suffix()}")
    source_stem = Path(str(input_package.get("source_file", "courseware"))).stem
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in source_stem)
    if add_timestamp:
        safe = f"{safe}_{timestamp_suffix()}"
    return Path("outputs") / safe


def make_indexes(input_package: dict[str, Any]) -> dict[str, set[str]]:
    slide_ids = {slide["slide_id"] for slide in input_package.get("slides", []) if "slide_id" in slide}
    element_ids = {
        element["element_id"]
        for element in input_package.get("known_elements", [])
        if "element_id" in element
    }
    element_to_slide = {
        element["element_id"]: element.get("slide_id")
        for element in input_package.get("known_elements", [])
        if "element_id" in element
    }
    return {
        "slide_ids": slide_ids,
        "element_ids": element_ids,
        "element_to_slide": element_to_slide,  # type: ignore[dict-item]
    }


def validate_scalar_fields(obj: dict[str, Any], where: str, report: ValidationReport) -> None:
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        report.error(f"{where}: confidence must be a number from 0 to 1")
    if not isinstance(obj.get("needs_review"), bool):
        report.error(f"{where}: needs_review must be boolean")


def require_fields(obj: dict[str, Any], fields: list[str], where: str, report: ValidationReport) -> None:
    for field in fields:
        if field not in obj:
            report.error(f"{where}: missing required field '{field}'")


def ensure_list(value: Any, where: str, report: ValidationReport) -> list[Any]:
    if not isinstance(value, list):
        report.error(f"{where}: expected list")
        return []
    return value


def validate_layer(
    task: str,
    data: Any,
    input_package: dict[str, Any],
    previous_outputs: dict[str, Any],
) -> ValidationReport:
    report = ValidationReport()
    indexes = make_indexes(input_package)
    slide_ids: set[str] = indexes["slide_ids"]  # type: ignore[assignment]
    element_ids: set[str] = indexes["element_ids"]  # type: ignore[assignment]
    element_to_slide: dict[str, str] = indexes["element_to_slide"]  # type: ignore[assignment]

    if task == "generate_course":
        if not isinstance(data, dict):
            report.error("course: expected object")
            return report
        require_fields(
            data,
            [
                "course_id",
                "title",
                "source_file",
                "source_type",
                "topic",
                "audience",
                "learning_objectives",
                "module_structure",
                "key_concepts",
                "confidence",
                "needs_review",
            ],
            "course",
            report,
        )
        validate_scalar_fields(data, "course", report)
        objectives = data.get("learning_objectives")
        if not isinstance(objectives, list) or not [o for o in objectives if str(o).strip()]:
            report.error("course.learning_objectives: must be a non-empty list")
        for module in ensure_list(data.get("module_structure", []), "course.module_structure", report):
            if not isinstance(module, dict):
                report.error("course.module_structure[]: expected object")
                continue
            for sid in module.get("slide_ids", []):
                if sid not in slide_ids:
                    report.error(f"course.module_structure: unknown slide_id '{sid}'")
        return report

    if task == "generate_slides":
        slides = ensure_list(data, "slides", report)
        for i, slide in enumerate(slides):
            where = f"slides[{i}]"
            if not isinstance(slide, dict):
                report.error(f"{where}: expected object")
                continue
            require_fields(
                slide,
                [
                    "slide_id",
                    "index",
                    "title",
                    "page_role",
                    "core_message",
                    "teaching_intent",
                    "text_summary",
                    "related_concepts",
                    "previous_next_relation",
                    "element_ids",
                    "source_ref",
                    "evidence",
                    "confidence",
                    "needs_review",
                ],
                where,
                report,
            )
            validate_scalar_fields(slide, where, report)
            if slide.get("slide_id") not in slide_ids:
                report.error(f"{where}: unknown slide_id '{slide.get('slide_id')}'")
            for eid in slide.get("element_ids", []):
                if eid not in element_ids:
                    report.error(f"{where}: unknown element_id '{eid}'")
                elif element_to_slide.get(eid) != slide.get("slide_id"):
                    report.error(f"{where}: element_id '{eid}' belongs to another slide")
        return report

    if task == "generate_knowledge_nodes":
        nodes = ensure_list(data, "knowledge_nodes", report)
        seen: set[str] = set()
        for i, node in enumerate(nodes):
            where = f"knowledge_nodes[{i}]"
            if not isinstance(node, dict):
                report.error(f"{where}: expected object")
                continue
            require_fields(
                node,
                [
                    "node_id",
                    "type",
                    "title",
                    "description",
                    "difficulty",
                    "source_slides",
                    "source_elements",
                    "prerequisites",
                    "evidence",
                    "confidence",
                    "needs_review",
                ],
                where,
                report,
            )
            validate_scalar_fields(node, where, report)
            node_id = node.get("node_id")
            if node_id in seen:
                report.error(f"{where}: duplicate node_id '{node_id}'")
            seen.add(node_id)
            for sid in node.get("source_slides", []):
                if sid not in slide_ids:
                    report.error(f"{where}: unknown source_slide '{sid}'")
            for eid in node.get("source_elements", []):
                if eid not in element_ids:
                    report.error(f"{where}: unknown source_element '{eid}'")
        return report

    node_ids = {
        node.get("node_id")
        for node in previous_outputs.get("knowledge_nodes", [])
        if isinstance(node, dict)
    }

    if task == "generate_knowledge_relations":
        relations = ensure_list(data, "knowledge_relations", report)
        seen_relation_ids: set[str] = set()
        for i, relation in enumerate(relations):
            where = f"knowledge_relations[{i}]"
            if not isinstance(relation, dict):
                report.error(f"{where}: expected object")
                continue
            require_fields(
                relation,
                [
                    "relation_id",
                    "source_id",
                    "target_id",
                    "relation_type",
                    "description",
                    "source_slides",
                    "source_elements",
                    "evidence",
                    "confidence",
                    "needs_review",
                ],
                where,
                report,
            )
            validate_scalar_fields(relation, where, report)
            relation_id = relation.get("relation_id")
            if relation_id in seen_relation_ids:
                report.error(f"{where}: duplicate relation_id '{relation_id}'")
            seen_relation_ids.add(relation_id)
            relation_type = relation.get("relation_type")
            if relation_type not in ALLOWED_RELATION_TYPES:
                report.error(
                    f"{where}: invalid relation_type '{relation_type}' "
                    f"(allowed: {', '.join(sorted(ALLOWED_RELATION_TYPES))})"
                )
            for key in ("source_id", "target_id"):
                if relation.get(key) not in node_ids:
                    report.error(f"{where}: unknown {key} '{relation.get(key)}'")
            for sid in relation.get("source_slides", []):
                if sid not in slide_ids:
                    report.error(f"{where}: unknown source_slide '{sid}'")
            for eid in relation.get("source_elements", []):
                if eid not in element_ids:
                    report.error(f"{where}: unknown source_element '{eid}'")
        return report

    if task == "generate_teaching_candidates":
        candidates = ensure_list(data, "teaching_candidates", report)
        for i, candidate in enumerate(candidates):
            where = f"teaching_candidates[{i}]"
            if not isinstance(candidate, dict):
                report.error(f"{where}: expected object")
                continue
            require_fields(
                candidate,
                [
                    "candidate_id",
                    "target_concept",
                    "target_slide",
                    "target_elements",
                    "explanation_goal",
                    "suggested_question",
                    "suggested_gui_actions",
                    "feedback_strategy",
                    "review_strategy",
                    "source_ref",
                    "evidence",
                    "confidence",
                    "needs_review",
                ],
                where,
                report,
            )
            validate_scalar_fields(candidate, where, report)
            if candidate.get("target_concept") not in node_ids:
                report.error(f"{where}: unknown target_concept '{candidate.get('target_concept')}'")
            target_slide = candidate.get("target_slide")
            if target_slide not in slide_ids:
                report.error(f"{where}: unknown target_slide '{target_slide}'")
            for eid in candidate.get("target_elements", []):
                if eid not in element_ids:
                    report.error(f"{where}: unknown target_element '{eid}'")
                elif target_slide in slide_ids and element_to_slide.get(eid) != target_slide:
                    report.error(f"{where}: target_element '{eid}' belongs to another slide")
        return report

    report.error(f"unknown task '{task}'")
    return report


def parse_json_from_model(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
        ends = [pos for pos in (text.rfind("}"), text.rfind("]")) if pos >= 0]
        if not starts or not ends:
            raise
        return json.loads(text[min(starts) : max(ends) + 1])


def call_openai_compatible(
    api_base: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: int,
    max_retries: int = 0,
    retry_backoff: float = 65.0,
) -> tuple[str, dict[str, Any]]:
    url = api_base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SlideTutor-LLM-Runner/0.1",
        },
        method="POST",
    )
    started = time.time()
    attempt = 0
    while True:
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < max_retries:
                attempt += 1
                wait = retry_backoff * attempt
                print(
                    f"[{utc_now_text()}] Rate limited (429); waiting {wait:.0f}s "
                    f"then retry {attempt}/{max_retries}",
                    flush=True,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, socket.timeout, http.client.RemoteDisconnected, error.URLError) as exc:
            if attempt < max_retries:
                attempt += 1
                wait = min(retry_backoff, 20.0) * attempt
                print(
                    f"[{utc_now_text()}] Connection issue ({exc}); waiting {wait:.0f}s "
                    f"then retry {attempt}/{max_retries}",
                    flush=True,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"API connection failed before a complete response was received: {exc}. "
                "For this endpoint/model, try increasing --timeout, running fewer --tasks, "
                "or checking proxy/API service stability."
            ) from exc
    elapsed_ms = int((time.time() - started) * 1000)
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected API response shape: {response_payload}") from exc
    usage = response_payload.get("usage", {})
    usage["elapsed_ms"] = elapsed_ms
    return content, usage


def build_messages(task: str, input_package: dict[str, Any], previous_outputs: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "task": task,
        "schema_version": input_package.get("target_schema_version", "0.1"),
        "input_package": input_package,
        "previous_outputs": previous_outputs,
        "constraints": [
            "Return valid JSON only.",
            "Do not wrap JSON in Markdown.",
            "Do not invent unsupported concepts.",
            "Use confidence from 0 to 1.",
            "Set needs_review to true when evidence is weak.",
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "You generate structured courseware analysis JSON for SlideTutor. "
                "You cannot read raw PPT/PDF files. Use only the supplied input package.\n\n"
                f"Task-specific instructions:\n{TASK_PROMPTS[task]}"
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_smoke_test_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "Return valid JSON only. Do not include Markdown.",
        },
        {
            "role": "user",
            "content": 'Return exactly this JSON object: {"ok": true, "service": "reachable"}',
        },
    ]


def layer_from_sample(sample: dict[str, Any], task: str) -> Any:
    key, _ = TASK_OUTPUT_FILES[task]
    if key not in sample:
        raise KeyError(f"sample draft has no '{key}' layer")
    return sample[key]


def assemble_draft(
    input_package: dict[str, Any],
    outputs: dict[str, Any],
    mode: str,
    model: str,
) -> dict[str, Any]:
    elements = [
        {
            **element,
            "semantic_role": element.get("semantic_role", "upstream_known_element"),
            "functional_purpose": element.get("functional_purpose", "evidence_anchor"),
            "relation_to_slide": element.get("relation_to_slide", "supports generated slide structure"),
            "importance": element.get("importance", "medium"),
            "related_concepts": element.get("related_concepts", []),
            "action_affordance": element.get(
                "action_affordance", element.get("allowed_action_affordance", [])
            ),
            "confidence": element.get("confidence", 1.0),
            "needs_review": element.get("needs_review", False),
        }
        for element in input_package.get("known_elements", [])
    ]
    return {
        "schema_version": input_package.get("target_schema_version", "0.1"),
        "course": outputs.get("course"),
        "slides": outputs.get("slides", []),
        "elements": elements,
        "knowledge_nodes": outputs.get("knowledge_nodes", []),
        "knowledge_relations": outputs.get("knowledge_relations", []),
        "teaching_candidates": outputs.get("teaching_candidates", []),
        "metadata": {
            "draft_id": f"{input_package.get('package_id', 'courseware')}_{mode}_draft",
            "input_package": input_package.get("package_id"),
            "generated_by": f"{mode}:{model}",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "review_status": "draft_requires_human_review",
        },
    }


def write_report(
    path: Path,
    mode: str,
    model: str,
    tasks: list[str],
    reports: dict[str, ValidationReport],
    usage_log: list[dict[str, Any]],
) -> None:
    lines = [
        "# Validation Report",
        "",
        f"- mode: `{mode}`",
        f"- model: `{model}`",
        f"- tasks: `{', '.join(tasks)}`",
        f"- generated_at: `{dt.datetime.now(dt.timezone.utc).isoformat()}`",
        "",
        "## Task Results",
        "",
    ]
    for task in tasks:
        report = reports[task]
        status = "pass" if report.ok else "fail"
        lines.append(f"### {task}: {status}")
        if report.errors:
            lines.append("")
            lines.extend(f"- ERROR: {item}" for item in report.errors)
        if report.warnings:
            lines.append("")
            lines.extend(f"- WARN: {item}" for item in report.warnings)
        if not report.errors and not report.warnings:
            lines.append("")
            lines.append("- No validation issues.")
        lines.append("")
    if usage_log:
        lines.extend(["## Usage", ""])
        for item in usage_log:
            safe = {k: v for k, v in item.items() if k != "api_key"}
            lines.append(f"- `{item['task']}`: `{json.dumps(safe, ensure_ascii=False)}`")
        lines.append("")
    write_text(path, "\n".join(lines))


def run(args: argparse.Namespace) -> int:
    local_config = read_optional_json(Path(args.config))
    model = args.model or local_config.get("model")
    api_base = args.api_base or local_config.get("api_base") or os.environ.get("SLIDETUTOR_LLM_API_BASE")
    if not api_base:
        api_base = "https://api.openai.com/v1"
    if args.smoke_test:
        api_key = local_config.get("api_key") or os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Set config file {args.config} or environment variable {args.api_key_env}."
            )
        log(f"Smoke test model: {model}", args.quiet)
        log(f"Smoke test endpoint/base: {api_base}", args.quiet)
        raw_text, usage = call_openai_compatible(
            api_base=api_base,
            model=model,
            api_key=api_key,
            messages=build_smoke_test_messages(),
            temperature=0,
            timeout=args.timeout,
        )
        log(f"Smoke test response_chars={len(raw_text)}", args.quiet)
        print(raw_text)
        if usage:
            safe_usage = {k: v for k, v in usage.items() if k != "api_key"}
            print(json.dumps(safe_usage, ensure_ascii=False))
        return 0

    input_path = Path(args.input)
    input_package = read_json(input_path)
    output_dir = normalize_output_dir(
        input_package,
        args.output_dir,
        add_timestamp=not args.no_timestamp_output,
    )
    raw_dir = output_dir / "raw_outputs"
    validated_dir = output_dir / "validated_outputs"

    log(f"Loaded input package: {input_path}", args.quiet)
    log(f"Mode: {args.mode}", args.quiet)
    log(f"Model: {model}", args.quiet)
    if args.mode == "api":
        log(f"API endpoint/base: {api_base}", args.quiet)
    log(f"Output directory: {output_dir}", args.quiet)

    tasks = args.tasks or DEFAULT_TASKS
    for task in tasks:
        if task not in TASK_OUTPUT_FILES:
            raise ValueError(f"Unsupported task: {task}")
    log(f"Tasks: {', '.join(tasks)}", args.quiet)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "llm_input_package.json", input_package)

    sample_draft = read_json(Path(args.sample_draft)) if args.mode == "mock" else None
    api_key = None
    if args.mode == "api":
        api_key = local_config.get("api_key") or os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Set config file {args.config}, "
                f"environment variable {args.api_key_env}, or use --mode mock."
            )

    outputs: dict[str, Any] = {}
    reports: dict[str, ValidationReport] = {}
    usage_log: list[dict[str, Any]] = []

    if args.reuse_validated:
        for other_task, (key, file_name) in TASK_OUTPUT_FILES.items():
            if other_task in tasks:
                continue
            existing = validated_dir / file_name
            if existing.exists():
                outputs[key] = read_json(existing)
                log(f"Reusing validated output for {other_task}: {existing}", args.quiet)

    for task in tasks:
        key, file_name = TASK_OUTPUT_FILES[task]
        log(f"Starting task: {task}", args.quiet)
        if args.mode == "mock":
            log(f"Using mock sample layer for {task}", args.quiet)
            data = layer_from_sample(sample_draft, task)  # type: ignore[arg-type]
            raw_text = json.dumps(data, ensure_ascii=False, indent=2)
            usage = {"task": task, "mode": "mock"}
        else:
            log(f"Building messages for {task}", args.quiet)
            messages = build_messages(task, input_package, outputs)
            approx_chars = sum(len(message.get("content", "")) for message in messages)
            log(f"Calling LLM API for {task}; message_chars={approx_chars}", args.quiet)
            raw_text, usage = call_openai_compatible(
                api_base=api_base,
                model=model,
                api_key=api_key or "",
                messages=messages,
                temperature=args.temperature,
                timeout=args.timeout,
                max_retries=args.max_retries,
                retry_backoff=args.retry_backoff,
            )
            log(f"Received LLM response for {task}; response_chars={len(raw_text)}", args.quiet)
            data = parse_json_from_model(raw_text)
            log(f"Parsed JSON for {task}", args.quiet)
            usage = {"task": task, "mode": "api", "model": model, **usage}
            usage_brief = {
                k: usage[k]
                for k in ("prompt_tokens", "completion_tokens", "total_tokens", "elapsed_ms")
                if k in usage
            }
            if usage_brief:
                log(f"Usage for {task}: {json.dumps(usage_brief, ensure_ascii=False)}", args.quiet)

        write_text(raw_dir / file_name.replace(".json", ".raw.json"), raw_text)
        log(f"Saved raw output: {raw_dir / file_name.replace('.json', '.raw.json')}", args.quiet)
        report = validate_layer(task, data, input_package, outputs)
        reports[task] = report
        if report.ok:
            write_json(validated_dir / file_name, data)
            outputs[key] = data
            log(f"Validation passed for {task}; saved {validated_dir / file_name}", args.quiet)
        elif args.keep_invalid:
            write_json(validated_dir / file_name.replace(".json", ".invalid.json"), data)
            log(f"Validation failed for {task}; kept invalid output", args.quiet)
        else:
            write_report(
                output_dir / "validation_report.md",
                args.mode,
                model,
                tasks,
                reports,
                usage_log,
            )
            raise RuntimeError(f"Validation failed for {task}. See validation_report.md")
        usage_log.append(usage)

    draft = assemble_draft(input_package, outputs, args.mode, model)
    write_json(output_dir / "courseware_structure.draft.json", draft)
    write_report(output_dir / "validation_report.md", args.mode, model, tasks, reports, usage_log)
    log(f"Assembled draft: {output_dir / 'courseware_structure.draft.json'}", args.quiet)
    log(f"Wrote validation report: {output_dir / 'validation_report.md'}", args.quiet)
    print(f"Generated draft: {output_dir / 'courseware_structure.draft.json'}")
    print(f"Validation report: {output_dir / 'validation_report.md'}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate courseware_structure.draft.json from an LLM input package."
    )
    parser.add_argument("--input", help="Path to llm_input_package.json")
    parser.add_argument(
        "--output-dir",
        help="Output directory base name. A timestamp is appended by default.",
    )
    parser.add_argument(
        "--no-timestamp-output",
        action="store_true",
        help="Write exactly to --output-dir instead of appending a timestamp.",
    )
    parser.add_argument("--mode", choices=["mock", "api"], default="mock")
    parser.add_argument("--model", help="Model name. Overrides config/llm.local.json.")
    parser.add_argument("--api-base", help="OpenAI-compatible API base URL. Overrides config/llm.local.json.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_LOCAL_CONFIG),
        help="Ignored local JSON config path. Defaults to config/llm.local.json.",
    )
    parser.add_argument("--api-key-env", default="SLIDETUTOR_LLM_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Retries on HTTP 429 (per-minute token limit). 0 disables.",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=65.0,
        help="Base seconds to wait per 429 retry. Default 65s to clear a per-minute window.",
    )
    parser.add_argument("--keep-invalid", action="store_true")
    parser.add_argument(
        "--reuse-validated",
        action="store_true",
        help="Seed previous_outputs from existing validated_outputs so you can re-run only some tasks.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Call the configured API with a tiny fixed prompt and no courseware content.",
    )
    parser.add_argument(
        "--sample-draft",
        default=str(SPEC_DIR / "courseware_structure.draft.sample.json"),
        help="Sample draft used by mock mode.",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=DEFAULT_TASKS,
        help="Tasks to run. Defaults to all layered tasks.",
    )
    args = parser.parse_args(argv)
    if not args.smoke_test and not args.input:
        parser.error("--input is required unless --smoke-test is used")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv or sys.argv[1:]))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
