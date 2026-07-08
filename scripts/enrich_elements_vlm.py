#!/usr/bin/env python3
"""Enrich extracted elements with model-based (visual) understanding.

This is the "understanding" layer for elements. It takes the deterministic
known_elements produced by extract_elements_pptx.py and asks a model to add
teaching-oriented semantics that a parser cannot know:
- semantic_role / functional_purpose / relation_to_slide
- teaching_role and importance
- for image elements: a visual_description of what the figure actually shows
- a refined action_affordance (subset of the allowed set)

Two modes:
- mock: rule-based enrichment, no network. Lets you see the output shape.
- api : call an OpenAI-compatible chat endpoint. Image elements are sent as a
        multimodal message (base64 data URL); text/formula elements as text.

The deterministic bbox/content/type are never overwritten; enrichment is added
alongside them. API keys are read from an ignored local config or environment
variable and never written to output.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib import error, request


DEFAULT_LOCAL_CONFIG = Path("config") / "llm.local.json"

ENRICH_FIELDS = [
    "semantic_role",
    "functional_purpose",
    "relation_to_slide",
    "teaching_role",
    "importance",
    "visual_description",
    "refined_action_affordance",
    "confidence",
    "needs_review",
]

SYSTEM_PROMPT = (
    "You analyze a single slide element for a teaching agent. "
    "Return ONLY a JSON object, no Markdown. "
    "Fields: semantic_role (e.g. slide_title, definition, key_formula, "
    "illustrative_diagram, example, comparison_item, summary_statement), "
    "functional_purpose (what this element does on the page), "
    "relation_to_slide (how it supports the page's core message), "
    "teaching_role (how a tutor would use it: introduce/explain/prove/"
    "illustrate/ask/review/summarize), "
    "importance (low|medium|high), "
    "visual_description (for images: describe what the figure actually shows; "
    "for text/formula: empty string), "
    "refined_action_affordance (a subset of the provided allowed list), "
    "confidence (0..1), needs_review (boolean). "
    "For images, ground your reading in the picture, not just the caption."
)


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


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
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            raise
        return json.loads(text[start : end + 1])


def load_known_elements(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "known_elements" in data:
        return data, list(data["known_elements"])
    if isinstance(data, list):
        return None, data
    raise ValueError("input must be a list or an object with known_elements")


def image_data_url(image_path: Path) -> str:
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_user_content(element: dict[str, Any], image_base: Path) -> Any:
    meta = {
        "type": element.get("type"),
        "content": element.get("content"),
        "allowed_action_affordance": element.get("allowed_action_affordance", []),
        "bbox": element.get("bbox"),
    }
    prompt = "Analyze this slide element and return the JSON object.\n" + json.dumps(
        meta, ensure_ascii=False
    )
    image_rel = element.get("image_path")
    if element.get("type") == "image" and image_rel:
        image_path = image_base / image_rel
        if image_path.exists():
            return [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url(image_path)}},
            ]
    return prompt


def call_api(
    api_base: str,
    model: str,
    api_key: str,
    user_content: Any,
    timeout: int,
) -> str:
    url = api_base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SlideTutor-VLM-Enricher/0.1",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        response_payload = json.loads(resp.read().decode("utf-8"))
    return response_payload["choices"][0]["message"]["content"]


def call_api_with_retry(
    api_base: str,
    model: str,
    api_key: str,
    user_content: Any,
    timeout: int,
    max_retries: int,
    backoff: float,
) -> str:
    attempt = 0
    while True:
        try:
            return call_api(api_base, model, api_key, user_content, timeout)
        except error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                attempt += 1
                wait = backoff * attempt
                print(f"    rate limited (429); waiting {wait:.0f}s then retry {attempt}/{max_retries}", flush=True)
                time.sleep(wait)
                continue
            raise


def mock_enrichment(element: dict[str, Any]) -> dict[str, Any]:
    etype = element.get("type")
    content = element.get("content", "")
    bbox = element.get("bbox", {})
    is_top = bbox.get("y", 1) < 0.15 and bbox.get("width", 0) > 0.6
    if is_top and etype == "text":
        semantic_role = "slide_title"
        teaching_role = "introduce"
        importance = "high"
    elif etype == "formula":
        semantic_role = "key_formula"
        teaching_role = "explain"
        importance = "high"
    elif etype == "image":
        semantic_role = "illustrative_diagram"
        teaching_role = "illustrate"
        importance = "high"
    else:
        semantic_role = "explanatory_text"
        teaching_role = "explain"
        importance = "medium"
    allowed = element.get("allowed_action_affordance", [])
    return {
        "semantic_role": semantic_role,
        "functional_purpose": f"(mock) 承载页面中的{semantic_role}",
        "relation_to_slide": "(mock) 支撑本页核心信息",
        "teaching_role": teaching_role,
        "importance": importance,
        "visual_description": (
            "(mock) 需真实 VLM 读取该图并描述其展示内容" if etype == "image" else ""
        ),
        "refined_action_affordance": allowed[:2] if allowed else [],
        "confidence": 0.5,
        "needs_review": True,
    }


def apply_enrichment(element: dict[str, Any], enrichment: dict[str, Any], enriched_by: str) -> dict[str, Any]:
    merged = dict(element)
    for field in ENRICH_FIELDS:
        if field in enrichment:
            merged[field] = enrichment[field]
    raa = merged.get("refined_action_affordance")
    if isinstance(raa, str):
        raa = [raa]
    if isinstance(raa, list):
        allowed = element.get("allowed_action_affordance", [])
        merged["refined_action_affordance"] = [a for a in raa if a in allowed] or raa
    if "enrichment_error" in enrichment:
        merged["enrichment_error"] = enrichment["enrichment_error"]
    else:
        merged.pop("enrichment_error", None)
    merged["enriched_by"] = enriched_by
    return merged


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    container, elements = load_known_elements(input_path)
    image_base = Path(args.image_base) if args.image_base else input_path.parent

    if args.slides:
        wanted = set(args.slides)
        target_idx = [i for i, e in enumerate(elements) if e.get("slide_id") in wanted]
    else:
        target_idx = list(range(len(elements)))
    if args.retry_failed:
        target_idx = [i for i in target_idx if elements[i].get("enrichment_error")]
    if args.limit:
        target_idx = target_idx[: args.limit]

    model = args.model
    api_base = args.api_base
    api_key = None
    if args.mode == "api":
        local_config = read_optional_json(Path(args.config))
        model = model or local_config.get("model")
        api_base = api_base or local_config.get("api_base") or os.environ.get("SLIDETUTOR_LLM_API_BASE")
        api_key = local_config.get("api_key") or os.environ.get(args.api_key_env)
        if not (api_base and model and api_key):
            raise RuntimeError("api mode needs api_base, model and api_key (config or env).")

    enriched_by = f"{args.mode}:{model}" if args.mode == "api" else "mock"
    result = list(elements)
    stats = {"enriched": 0, "vision_calls": 0, "failed": 0}

    for i in target_idx:
        element = elements[i]
        if args.mode == "mock":
            enrichment = mock_enrichment(element)
        else:
            user_content = build_user_content(element, image_base)
            is_vision = isinstance(user_content, list)
            try:
                raw = call_api_with_retry(
                    api_base, model, api_key or "", user_content, args.timeout, args.max_retries, args.backoff
                )
                enrichment = parse_json_from_model(raw)
                if is_vision:
                    stats["vision_calls"] += 1
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
                print(f"  {element['element_id']}: API HTTP {exc.code} ({'vision' if is_vision else 'text'}): {detail}", file=sys.stderr)
                stats["failed"] += 1
                enrichment = {"needs_review": True, "enrichment_error": f"http_{exc.code}"}
            except Exception as exc:
                print(f"  {element['element_id']}: call failed: {exc}", file=sys.stderr)
                stats["failed"] += 1
                enrichment = {"needs_review": True, "enrichment_error": str(exc)[:120]}
        result[i] = apply_enrichment(element, enrichment, enriched_by)
        stats["enriched"] += 1
        if args.mode == "api" and args.sleep > 0:
            time.sleep(args.sleep)

    output_path = Path(args.output)
    if container is not None:
        container["known_elements"] = result
        container.setdefault("metadata", {})["elements_enriched_by"] = enriched_by
        container["metadata"]["enriched_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(output_path, container)
    else:
        write_json(output_path, {"known_elements": result})

    print(f"Mode: {args.mode} ({enriched_by})")
    print(f"Elements enriched: {stats['enriched']} / {len(elements)}")
    if args.mode == "api":
        print(f"Vision calls: {stats['vision_calls']}, failed: {stats['failed']}")
    print(f"Wrote: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich known_elements with model understanding.")
    parser.add_argument("--input", required=True, help="known_elements JSON or package with known_elements.")
    parser.add_argument("--output", required=True, help="Output path.")
    parser.add_argument("--mode", choices=["mock", "api"], default="mock")
    parser.add_argument("--image-base", help="Base dir for image_path. Default: input file's dir.")
    parser.add_argument("--slides", nargs="+", help="Only enrich these slide_ids.")
    parser.add_argument("--retry-failed", action="store_true", help="Only re-enrich elements that have a prior enrichment_error.")
    parser.add_argument("--limit", type=int, default=0, help="Max elements to enrich (0 = all).")
    parser.add_argument("--model", help="Model name. Overrides config.")
    parser.add_argument("--api-base", help="OpenAI-compatible API base. Overrides config.")
    parser.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    parser.add_argument("--api-key-env", default="SLIDETUTOR_LLM_API_KEY")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=1.5, help="Seconds to wait between api calls.")
    parser.add_argument("--max-retries", type=int, default=4, help="Retries on HTTP 429.")
    parser.add_argument("--backoff", type=float, default=21.0, help="Base seconds per 429 retry (vision limit ~3/min).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        return run(parse_args(argv or sys.argv[1:]))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
