#!/usr/bin/env python3
"""Build an llm_input_package.json draft from a MinerU content list.

This is the upstream step of the "PPT/PDF -> courseware_structure" pipeline. It
turns a MinerU parse result (content_list_v2.json, or the legacy flat
content_list.json) into the standard llm_input_package.json consumed by
generate_courseware_structure.py.

Design boundaries (see spec/.../llm-input-package.md):
- It only fills what a parser can know for certain: per-page titles, page text,
  speaker notes (PPT presenter notes) and page image references.
- It does NOT invent page_role, knowledge nodes, relations or teaching
  candidates. Those stay for the layered LLM step.
- It does NOT fabricate element bounding boxes. MinerU's office backend has no
  coordinates, so `known_elements` is left empty and filled later by the
  python-pptx based extractor.

No third-party dependency is required.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_TASKS = [
    "generate_course",
    "generate_slides",
    "generate_knowledge_nodes",
    "generate_knowledge_relations",
    "generate_teaching_candidates",
]

DEFAULT_CONSTRAINTS = [
    "Do not claim access to the original PPTX file.",
    "Do not treat teacher_note or speaker_notes as slide text quotes.",
    "Use only schema_version 0.1 fields.",
    "Every major claim must include evidence or source_ref.",
    "Use confidence as a number from 0 to 1.",
    "Set needs_review to true when evidence is weak, inferred, or note-only.",
    "Use GUI action affordance only from known_elements.allowed_action_affordance.",
]


class Block:
    """A normalized content block, independent of content_list version."""

    __slots__ = ("kind", "text", "level", "img_path")

    def __init__(
        self,
        kind: str,
        text: str = "",
        level: int | None = None,
        img_path: str | None = None,
    ) -> None:
        self.kind = kind  # title | text | image | footnote
        self.text = text
        self.level = level
        self.img_path = img_path


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def join_spans(spans: Any) -> str:
    if not isinstance(spans, list):
        return ""
    parts = [str(span.get("content", "")) for span in spans if isinstance(span, dict)]
    return "".join(parts).strip()


def strip_markdown_bold(text: str) -> str:
    return text.replace("**", "").strip()


def normalize_v2_page(page: list[Any]) -> list[Block]:
    """content_list_v2.json: one page is a list of typed blocks."""
    blocks: list[Block] = []
    for item in page:
        if not isinstance(item, dict):
            continue
        block_type = item.get("type")
        content = item.get("content", {})
        if block_type == "title":
            text = join_spans(content.get("title_content"))
            if text:
                blocks.append(Block("title", text=text, level=content.get("level")))
        elif block_type == "paragraph":
            text = join_spans(content.get("paragraph_content"))
            if text:
                blocks.append(Block("text", text=text))
        elif block_type == "image":
            img_path = (content.get("image_source") or {}).get("path")
            if img_path:
                blocks.append(Block("image", img_path=img_path))
        elif block_type == "page_footnote":
            text = join_spans(content.get("page_footnote_content"))
            if text:
                blocks.append(Block("footnote", text=text))
    return blocks


def normalize_v1_flat(items: list[Any]) -> list[list[Block]]:
    """Legacy content_list.json: flat list of blocks carrying page_idx."""
    pages: dict[int, list[Block]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        page_idx = int(item.get("page_idx", 0))
        bucket = pages.setdefault(page_idx, [])
        block_type = item.get("type")
        if block_type == "text":
            text = strip_markdown_bold(str(item.get("text", "")))
            if not text:
                continue
            level = item.get("text_level")
            bucket.append(Block("title" if level else "text", text=text, level=level))
        elif block_type == "image":
            img_path = item.get("img_path")
            if img_path:
                bucket.append(Block("image", img_path=img_path))
        elif block_type == "page_footnote":
            text = strip_markdown_bold(str(item.get("text", "")))
            if text:
                bucket.append(Block("footnote", text=text))
    return [pages[idx] for idx in sorted(pages)]


def load_pages(path: Path) -> list[list[Block]]:
    data = read_json(path)
    if not isinstance(data, list) or not data:
        raise ValueError("content list must be a non-empty JSON array")
    first = data[0]
    if isinstance(first, list):
        return [normalize_v2_page(page) for page in data]
    if isinstance(first, dict):
        return normalize_v1_flat(data)
    raise ValueError("unrecognized content list structure")


def build_slide(blocks: list[Block], index: int, slide_prefix: str) -> dict[str, Any]:
    slide_id = f"{slide_prefix}{index:03d}"

    title_text = ""
    title_used = False
    page_text: list[dict[str, Any]] = []
    parser_evidence: list[dict[str, Any]] = []
    speaker_notes: list[dict[str, Any]] = []
    page_images: list[dict[str, Any]] = []

    text_seq = 0
    note_seq = 0
    image_seq = 0

    for block in blocks:
        if block.kind == "title" and not title_used:
            title_text = block.text
            title_used = True
            continue
        if block.kind in ("title", "text"):
            text_seq += 1
            evidence_id = f"txt_{slide_id}_{text_seq:03d}"
            page_text.append(
                {"source": "parser", "text": block.text, "evidence_id": evidence_id}
            )
            parser_evidence.append(
                {
                    "evidence_id": evidence_id,
                    "source_type": "parser_text",
                    "source_ref": {"slide_id": slide_id, "slide_index": index},
                }
            )
        elif block.kind == "footnote":
            note_seq += 1
            speaker_notes.append(
                {
                    "note_id": f"sn_{slide_id}_{note_seq:03d}",
                    "text": block.text,
                    "source": "speaker_notes",
                }
            )
        elif block.kind == "image":
            image_seq += 1
            page_images.append(
                {"image_id": f"img_{slide_id}_{image_seq:03d}", "img_path": block.img_path}
            )

    return {
        "slide_id": slide_id,
        "index": index,
        "title": {"text": title_text or f"Slide {index}", "source": "parser"},
        "page_text": page_text,
        "page_summary": {"source": "human_summary", "text": ""},
        "teacher_notes": [],
        "speaker_notes": speaker_notes,
        "page_images": page_images,
        "parser_evidence": parser_evidence,
    }


def default_course_context() -> dict[str, Any]:
    return {
        "audience": "",
        "teaching_goal": "",
        "prerequisites": [],
        "teacher_notes": [
            {
                "note_id": "tn_course_001",
                "text": "（请人工补充：目标学习者、教学目标、前置知识。builder 不会自动推断这些字段。）",
                "source": "teacher_note",
            }
        ],
    }


def build_package(
    pages: list[list[Block]],
    source_file: str,
    source_type: str,
    package_id: str,
    slide_prefix: str,
    start: int,
    end: int,
    course_context: dict[str, Any],
    tasks: list[str],
    content_list_name: str,
) -> dict[str, Any]:
    total = len(pages)
    start = max(1, start)
    end = min(total, end) if end else total
    slides = [
        build_slide(pages[i - 1], i, slide_prefix)
        for i in range(start, end + 1)
        if pages[i - 1]
    ]
    return {
        "package_id": package_id,
        "source_file": source_file,
        "source_type": source_type,
        "selected_slide_range": {"start": start, "end": end},
        "target_schema_version": "0.1",
        "course_context": course_context,
        "slides": slides,
        "known_elements": [],
        "generation_tasks": tasks,
        "constraints": list(DEFAULT_CONSTRAINTS),
        "metadata": {
            "created_by": "build_input_package.py",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_content_list": content_list_name,
            "upstream_parser": "mineru",
            "review_status": "auto_draft_requires_human_review",
            "known_elements_note": (
                "MinerU office output has no bounding boxes. Populate known_elements "
                "with a python-pptx based extractor before deriving GUI actions."
            ),
        },
    }


def run(args: argparse.Namespace) -> int:
    content_path = Path(args.content_list)
    pages = load_pages(content_path)

    source_file = args.source_file or (content_path.stem.replace("_content_list_v2", "").replace("_content_list", "") + ".pptx")
    package_id = args.package_id or f"{Path(source_file).stem}_llm_input_001"
    course_context = (
        read_json(Path(args.course_context)) if args.course_context else default_course_context()
    )

    package = build_package(
        pages=pages,
        source_file=source_file,
        source_type=args.source_type,
        package_id=package_id,
        slide_prefix=args.slide_id_prefix,
        start=args.start,
        end=args.end,
        course_context=course_context,
        tasks=args.tasks or list(DEFAULT_TASKS),
        content_list_name=content_path.name,
    )

    output_path = Path(args.output) if args.output else content_path.with_name("llm_input_package.json")
    write_json(output_path, package)

    slide_count = len(package["slides"])
    note_count = sum(len(s["speaker_notes"]) for s in package["slides"])
    text_count = sum(len(s["page_text"]) for s in package["slides"])
    image_count = sum(len(s["page_images"]) for s in package["slides"])
    print(f"Parsed pages: {len(pages)}")
    print(f"Emitted slides: {slide_count} (range {package['selected_slide_range']})")
    print(f"page_text entries: {text_count}")
    print(f"speaker_notes entries: {note_count}")
    print(f"page_images entries: {image_count}")
    print(f"known_elements: {len(package['known_elements'])} (fill via python-pptx extractor)")
    print(f"Wrote input package: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build llm_input_package.json from a MinerU content list."
    )
    parser.add_argument(
        "--content-list",
        required=True,
        help="Path to MinerU content_list_v2.json (or legacy content_list.json).",
    )
    parser.add_argument("--source-file", help="Original courseware file name, e.g. calculus.pptx.")
    parser.add_argument("--source-type", default="pptx", choices=["pptx", "pdf", "images", "unknown"])
    parser.add_argument("--package-id", help="Input package id. Defaults from source file name.")
    parser.add_argument("--slide-id-prefix", default="s", help="Slide id prefix. Default 's'.")
    parser.add_argument("--start", type=int, default=1, help="First page to include (1-based).")
    parser.add_argument("--end", type=int, default=0, help="Last page to include (1-based). 0 = all.")
    parser.add_argument("--course-context", help="Optional JSON file to override course_context.")
    parser.add_argument("--tasks", nargs="+", choices=DEFAULT_TASKS, help="Generation tasks to request.")
    parser.add_argument("--output", help="Output path. Defaults next to the content list.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv or sys.argv[1:]))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
