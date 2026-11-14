"""Extract native vector geometry and dimension text from CAD-exported PDFs.

Coordinates stay in PDF points. They are source geometry coordinates, not model
millimetres; mapping from drawing paper coordinates to real dimensions must use
explicit dimension annotations or a clearly identified drawing scale.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz


DIMENSION_TOKEN = re.compile(
    r"(?:%%[cC]|[Ø⌀∅])\s*\d+(?:[.,]\d+)?"
    r"|(?:\bR|M)\s*\d+(?:[.,]\d+)?"
    r"|\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m|inch|in)\b"
    r"|\b\d+(?:[.,]\d+)?\s*[×xX]\s*\d+(?:[.,]\d+)?"
    r"|\b\d+(?:[.,]\d+)?\b"
    r"|(?:±|⌖|⏥|⌯)\s*[\d.,]+",
    re.IGNORECASE,
)

MAX_PAGES_FOR_VECTOR_DETAILS = 20
MAX_PATHS_PER_PAGE = 320
MAX_TOTAL_PATHS = 1200
MAX_SPANS_PER_PAGE = 900
MAX_SEGMENTS_PER_PATH = 160
MAX_REPORT_CHARS = 180_000


def _xy(value: Any) -> list[float] | None:
    try:
        if hasattr(value, "x") and hasattr(value, "y"):
            return [round(float(value.x), 3), round(float(value.y), 3)]
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return [round(float(value[0]), 3), round(float(value[1]), 3)]
    except Exception:
        return None
    return None


def _rect(value: Any) -> list[float] | None:
    try:
        return [
            round(float(value.x0), 3),
            round(float(value.y0), 3),
            round(float(value.x1), 3),
            round(float(value.y1), 3),
        ]
    except Exception:
        try:
            values = list(value)
            if len(values) >= 4:
                return [round(float(x), 3) for x in values[:4]]
        except Exception:
            pass
    return None


def _quad(value: Any) -> list[list[float]] | None:
    result = []
    for name in ("ul", "ur", "lr", "ll"):
        point = _xy(getattr(value, name, None))
        if point is None:
            return None
        result.append(point)
    return result


def _path_items(path: dict[str, Any]) -> list[list[Any]]:
    converted = []
    for item in (path.get("items", []) or [])[:MAX_SEGMENTS_PER_PATH]:
        if not item:
            continue
        kind = item[0]
        if kind == "l" and len(item) >= 3:
            p1, p2 = _xy(item[1]), _xy(item[2])
            if p1 and p2:
                converted.append(["L", *p1, *p2])
        elif kind == "c" and len(item) >= 5:
            points = [_xy(point) for point in item[1:5]]
            if all(points):
                converted.append(["C", *[coordinate for point in points for coordinate in point]])
        elif kind == "re" and len(item) >= 2:
            rect = _rect(item[1])
            if rect:
                converted.append(["R", *rect, int(item[2]) if len(item) > 2 else 0])
        elif kind == "qu" and len(item) >= 2:
            points = _quad(item[1])
            if points:
                converted.append(["Q", *[coordinate for point in points for coordinate in point]])
    return converted


def _path_record(index: int, path: dict[str, Any]) -> dict[str, Any] | None:
    bbox = _rect(path.get("rect"))
    segments = _path_items(path)
    if not segments:
        return None
    if bbox is None:
        xs, ys = [], []
        for segment in segments:
            coordinates = segment[1:]
            if segment[0] == "R":
                xs.extend([coordinates[0], coordinates[2]])
                ys.extend([coordinates[1], coordinates[3]])
            elif segment[0] == "Q":
                xs.extend(coordinates[0::2])
                ys.extend(coordinates[1::2])
            else:
                xs.extend(coordinates[0::2])
                ys.extend(coordinates[1::2])
        if xs and ys:
            bbox = [min(xs), min(ys), max(xs), max(ys)]
    if bbox is None:
        return None
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return {
        "id": index,
        "bbox_pt": bbox,
        "size_pt": [round(width, 3), round(height, 3)],
        "closed": bool(path.get("closePath", False)) or any(segment[0] == "R" for segment in segments),
        "segment_count": len(segments),
        "segments_truncated": len(path.get("items", []) or []) > MAX_SEGMENTS_PER_PATH,
        "has_curve": any(segment[0] == "C" for segment in segments),
        "has_circle_or_arc_candidate": (
            bool(path.get("closePath", False))
            and width > 0
            and height > 0
            and 0.85 <= width / height <= 1.18
            and any(segment[0] == "C" for segment in segments)
        ),
        "stroke": path.get("color"),
        "fill": path.get("fill"),
        "line_width_pt": round(float(path.get("width") or 0), 4),
        "segments": segments,
    }


def _extract_text(page: fitz.Page) -> tuple[list[dict[str, Any]], list[str]]:
    spans: list[dict[str, Any]] = []
    dimension_lines: list[str] = []
    try:
        data = page.get_text("dict", sort=True)
    except Exception:
        data = page.get_text("dict")
    for block in data.get("blocks", []) or []:
        for line in block.get("lines", []) or []:
            line_parts = []
            for span in line.get("spans", []) or []:
                text = str(span.get("text") or "").strip()
                if not text:
                    continue
                bbox = _rect(span.get("bbox"))
                span_record = {
                    "text": text,
                    "bbox_pt": bbox,
                    "font": str(span.get("font") or "")[:80],
                    "font_size_pt": round(float(span.get("size") or 0), 2),
                    "flags": int(span.get("flags") or 0),
                }
                spans.append(span_record)
                line_parts.append(text)
            joined = " ".join(line_parts).strip()
            if joined:
                dimension_lines.append(joined)

    dim_candidates = []
    for line in dimension_lines:
        if DIMENSION_TOKEN.search(line):
            dim_candidates.append(line)
    return spans[:MAX_SPANS_PER_PAGE], dim_candidates[:500]


def extract_pdf_vector_report(pdf_path: str) -> dict[str, Any]:
    """Extract CAD PDF paths and drawing text without rasterizing the geometry."""
    path = Path(pdf_path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError("Hãy chọn một file PDF hợp lệ để phân tích vector.")
    document = fitz.open(path)
    try:
        page_records = []
        total_paths = 0
        total_spans = 0
        total_images = 0
        total_vector_segments = 0
        total_saved_paths = 0
        detail_page_count = min(document.page_count, MAX_PAGES_FOR_VECTOR_DETAILS)

        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_rect = page.rect
            try:
                raw_drawings = page.get_drawings()
            except Exception:
                raw_drawings = []
            spans, dimension_lines = _extract_text(page)
            image_count = len(page.get_images(full=True))
            total_images += image_count
            total_spans += len(spans)

            records = []
            remaining_path_budget = max(0, MAX_TOTAL_PATHS - total_saved_paths)
            if page_index < detail_page_count and remaining_path_budget:
                for path_index, path_data in enumerate(raw_drawings):
                    record = _path_record(path_index, path_data)
                    if record is not None:
                        records.append(record)
                records.sort(
                    key=lambda item: (
                        (item["size_pt"][0] * item["size_pt"][1]),
                        item["segment_count"],
                    ),
                    reverse=True,
                )
                records = records[:min(MAX_PATHS_PER_PAGE, remaining_path_budget)]
                total_saved_paths += len(records)
            records.sort(
                key=lambda item: (
                    (item["size_pt"][0] * item["size_pt"][1]),
                    item["segment_count"],
                ),
                reverse=True,
            )
            page_total_segments = sum(item["segment_count"] for item in records)
            total_paths += len(raw_drawings)
            total_vector_segments += page_total_segments
            page_records.append({
                "page": page_index + 1,
                "page_size_pt": [
                    round(float(page_rect.width), 3),
                    round(float(page_rect.height), 3),
                ],
                "rotation": int(page.rotation),
                "raw_path_count": len(raw_drawings),
                "vector_path_count": len(records),
                "vector_segment_count": page_total_segments,
                "embedded_image_count": image_count,
                "text_span_count": len(spans),
                "dimension_text_candidates": dimension_lines,
                "text_spans": spans,
                "paths": records[:MAX_PATHS_PER_PAGE],
            })

        return {
            "source_file": path.name,
            "page_count": document.page_count,
            "total_path_count": total_paths,
            "total_saved_vector_path_count": total_saved_paths,
            "total_vector_segment_count": total_vector_segments,
            "total_text_span_count": total_spans,
            "total_embedded_image_count": total_images,
            "pages_with_native_vector_paths": sum(1 for p in page_records if p["raw_path_count"] > 0),
            "native_vector_pdf": total_paths > 0 and total_vector_segments > 0,
            "vector_details_truncated": document.page_count > detail_page_count,
            "page_details": page_records,
        }
    finally:
        document.close()


def compact_vector_context(report: dict[str, Any], max_chars: int = MAX_REPORT_CHARS) -> str:
    """Return compact vector/text metadata suitable for a vision-model prompt."""
    working = dict(report)
    for page in working.get("page_details", []):
        page["text_spans"] = page.get("text_spans", [])[:500]
        page["paths"] = page.get("paths", [])[:MAX_PATHS_PER_PAGE]
    serialized = json.dumps(working, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return serialized

    # Gradually trim detailed paths while preserving page sizes and dimension text.
    for page in working.get("page_details", []):
        page["paths"] = page.get("paths", [])[:100]
        page["text_spans"] = page.get("text_spans", [])[:250]
    serialized = json.dumps(working, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return serialized

    for page in working.get("page_details", []):
        page["paths"] = page.get("paths", [])[:30]
        page["text_spans"] = page.get("text_spans", [])[:100]
    serialized = json.dumps(working, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return serialized

    # Last fallback: page-level counts + all extracted dimension text.
    minimal = {
        key: value for key, value in report.items()
        if key != "page_details"
    }
    minimal["page_details"] = [
        {
            "page": page["page"],
            "page_size_pt": page["page_size_pt"],
            "raw_path_count": page["raw_path_count"],
            "vector_segment_count": page["vector_segment_count"],
            "dimension_text_candidates": page["dimension_text_candidates"],
            "text_spans": page.get("text_spans", [])[:30],
        }
        for page in report.get("page_details", [])
    ]
    return json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))[:max_chars]
