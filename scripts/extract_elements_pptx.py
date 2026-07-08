#!/usr/bin/env python3
"""Deterministically extract slide elements and bounding boxes from a .pptx.

This is the "perception" layer for the PPTX pipeline. A .pptx is structured
XML, so every shape already carries an exact position (EMU). We convert those
to normalized bboxes and pull the text / picture bytes. No model is involved
here on purpose: extraction is plumbing, understanding happens downstream.

Output can be written standalone (known_elements.json) or merged into an
existing llm_input_package.json produced by build_input_package.py.

Requires: python-pptx.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


FORMULA_HINTS = ("=", "∫", "∑", "lim", "Δ", "→", "√", "±", "≈", "≤", "≥", "'(", "dx", "dt", "f(x)")

AFFORDANCE_BY_TYPE = {
    "text": ["highlight", "mask", "annotate"],
    "formula": ["highlight", "annotate", "zoom"],
    "image": ["highlight", "zoom", "annotate"],
    "table": ["highlight", "zoom"],
    "chart": ["highlight", "zoom", "annotate"],
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def looks_like_formula(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return any(hint in stripped for hint in FORMULA_HINTS)


def norm_bbox(shape: Any, slide_w: int, slide_h: int) -> dict[str, float] | None:
    if shape.left is None or shape.top is None or shape.width is None or shape.height is None:
        return None
    x = shape.left / slide_w
    y = shape.top / slide_h
    w = shape.width / slide_w
    h = shape.height / slide_h

    def clamp(v: float) -> float:
        return round(min(1.0, max(0.0, v)), 4)

    return {"x": clamp(x), "y": clamp(y), "width": clamp(w), "height": clamp(h)}


def is_full_bleed(bbox: dict[str, float]) -> bool:
    return bbox["x"] <= 0.02 and bbox["y"] <= 0.02 and bbox["width"] >= 0.97 and bbox["height"] >= 0.97


def group_text(shape: Any) -> str:
    parts: list[str] = []
    for child in shape.shapes:
        if child.shape_type == MSO_SHAPE_TYPE.GROUP:
            parts.append(group_text(child))
        elif child.has_text_frame and child.text_frame.text.strip():
            parts.append(child.text_frame.text.strip())
    return " ".join(p for p in parts if p).strip()


def extract_slide_elements(
    slide: Any,
    slide_id: str,
    slide_w: int,
    slide_h: int,
    image_dir: Path | None,
    min_area: float,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    seq = 0

    for shape in slide.shapes:
        bbox = norm_bbox(shape, slide_w, slide_h)
        if bbox is None:
            continue
        area = bbox["width"] * bbox["height"]

        element_type: str | None = None
        content = ""
        image_path: str | None = None

        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            element_type = "image"
            content = f"[image] {shape.name}"
            if image_dir is not None:
                try:
                    image = shape.image
                    ext = image.ext or "png"
                    seq_name = f"{slide_id}_{seq + 1:03d}.{ext}"
                    image_dir.mkdir(parents=True, exist_ok=True)
                    (image_dir / seq_name).write_bytes(image.blob)
                    image_path = f"{image_dir.name}/{seq_name}"
                except Exception:
                    image_path = None
        elif shape.has_table:
            element_type = "table"
            content = "[table]"
        elif getattr(shape, "has_chart", False):
            element_type = "chart"
            content = "[chart]"
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            text = group_text(shape)
            if not text:
                continue
            element_type = "formula" if looks_like_formula(text) else "text"
            content = text
        elif shape.has_text_frame and shape.text_frame.text.strip():
            text = shape.text_frame.text.strip()
            element_type = "formula" if looks_like_formula(text) else "text"
            content = text
        else:
            continue

        if element_type != "image" and is_full_bleed(bbox):
            continue
        if element_type == "image" and area < min_area:
            # Tiny decorative icons are skipped to avoid noise.
            continue

        seq += 1
        element_id = f"e_{slide_id}_{seq:03d}"
        element: dict[str, Any] = {
            "element_id": element_id,
            "slide_id": slide_id,
            "type": element_type,
            "content": content,
            "bbox": bbox,
            "source": "pptx_parser",
            "allowed_action_affordance": AFFORDANCE_BY_TYPE.get(element_type, ["highlight"]),
        }
        if image_path:
            element["image_path"] = image_path
        elements.append(element)

    return elements


def run(args: argparse.Namespace) -> int:
    presentation = Presentation(args.pptx)
    slide_w = presentation.slide_width
    slide_h = presentation.slide_height
    slides = list(presentation.slides)
    total = len(slides)
    start = max(1, args.start)
    end = min(total, args.end) if args.end else total

    output_path = Path(args.output)
    image_dir = None
    if args.image_dir:
        image_dir = Path(args.image_dir)
    elif not args.no_images:
        image_dir = output_path.parent / "element_images"

    all_elements: list[dict[str, Any]] = []
    per_slide: list[tuple[str, int]] = []
    for i in range(start, end + 1):
        slide_id = f"{args.slide_id_prefix}{i:03d}"
        elements = extract_slide_elements(
            slides[i - 1], slide_id, slide_w, slide_h, image_dir, args.min_image_area
        )
        all_elements.extend(elements)
        per_slide.append((slide_id, len(elements)))

    if args.input_package:
        package = json.loads(Path(args.input_package).read_text(encoding="utf-8"))
        package["known_elements"] = all_elements
        package.setdefault("metadata", {})["known_elements_source"] = "extract_elements_pptx.py"
        write_json(output_path, package)
    else:
        write_json(output_path, {"known_elements": all_elements})

    type_counts: dict[str, int] = {}
    for element in all_elements:
        type_counts[element["type"]] = type_counts.get(element["type"], 0) + 1

    print(f"Slides processed: {end - start + 1} (range {start}-{end} of {total})")
    print(f"Elements extracted: {len(all_elements)}")
    print(f"By type: {json.dumps(type_counts, ensure_ascii=False)}")
    for slide_id, count in per_slide:
        print(f"  {slide_id}: {count} elements")
    if image_dir is not None:
        print(f"Picture blobs exported to: {image_dir}")
    print(f"Wrote: {output_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract elements + bbox from a .pptx.")
    parser.add_argument("--pptx", required=True, help="Path to the .pptx file.")
    parser.add_argument(
        "--input-package",
        help="Optional llm_input_package.json to merge known_elements into.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--image-dir", help="Directory to export picture blobs. Default: <output>/element_images.")
    parser.add_argument("--no-images", action="store_true", help="Do not export picture blobs.")
    parser.add_argument("--slide-id-prefix", default="s")
    parser.add_argument("--start", type=int, default=1, help="First slide (1-based).")
    parser.add_argument("--end", type=int, default=0, help="Last slide (1-based). 0 = all.")
    parser.add_argument(
        "--min-image-area",
        type=float,
        default=0.01,
        help="Skip picture elements smaller than this fraction of the page area.",
    )
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
