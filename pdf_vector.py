"""Local, vector-first PDF inspection for mechanical CAD drawings.

This module extracts source PDF text and vector path geometry. It deliberately
does not infer 3D depth or invent dimensions from drawing scale.
"""
import json
import re
from pathlib import Path

import fitz

DIMENSION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:Ø\s*)?(?:R\s*)?[-+]?\d+(?:[.,]\d+)?"
    r"(?:\s*(?:mm|毫米|cm|m|°))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _point(value):
    try:
        return [round(float(value.x), 4), round(float(value.y), 4)]
    except Exception:
        return None


def _rect(value):
    try:
        return [round(float(v), 4) for v in value]
    except Exception:
        return None


def _json_value(value):
    if hasattr(value, "x") and hasattr(value, "y"):
        return _point(value)
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        try:
            return [_json_value(v) for v in value]
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def analyze_pdf_vector(pdf_path, max_paths_per_page=12000):
    """Extract text spans, dimension-like tokens, vector paths and page metrics."""
    path = Path(pdf_path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError("Hãy chọn một tệp PDF hợp lệ.")
    report = {
        "schema": "pdf2inventor.local-vector-analysis.v1",
        "source_file": path.name,
        "source_path": str(path.resolve()),
        "engine": "PyMuPDF local vector extraction",
        "units_note": (
            "Tọa độ PDF được báo theo point (1/72 inch), không tự coi là mm. "
            "Kích thước ghi trên bản vẽ phải được dùng để hiệu chuẩn."
        ),
        "safety": {
            "automatic_scale_claim": False,
            "automatic_3d_inference": False,
            "dimensions_are_verified": False,
            "note": "Không tự suy ra chiều sâu hoặc kích thước thiếu từ một hình chiếu."
        },
        "pages": []
    }
    with fitz.open(str(path)) as doc:
        report["page_count"] = doc.page_count
        for page_number, page in enumerate(doc, 1):
            text_dict = page.get_text("dict")
            spans = []
            full_text = page.get_text("text", sort=True)
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        value = str(span.get("text", "")).strip()
                        if value:
                            spans.append({
                                "text": value,
                                "bbox_pt": _rect(span.get("bbox")),
                                "font": span.get("font"),
                                "size_pt": round(float(span.get("size", 0)), 3)
                            })
            dimension_tokens = []
            for match in DIMENSION_RE.finditer(full_text):
                token = match.group(0).strip()
                if any(ch.isdigit() for ch in token):
                    dimension_tokens.append(token)
            drawings = page.get_drawings()
            vector_paths = []
            for drawing in drawings[:max_paths_per_page]:
                items = []
                for item in drawing.get("items", []):
                    items.append({
                        "type": str(item[0]) if item else "unknown",
                        "data": [_json_value(v) for v in item[1:]]
                    })
                vector_paths.append({
                    "bbox_pt": _rect(drawing.get("rect")),
                    "items": items,
                    "item_count": len(items),
                    "closed": bool(drawing.get("closePath", False)),
                    "fill": _json_value(drawing.get("fill")),
                    "color": _json_value(drawing.get("color")),
                    "width_pt": round(float(drawing.get("width", 0) or 0), 4)
                })
            page_report = {
                "page": page_number,
                "page_size_pt": [round(float(page.rect.width), 4), round(float(page.rect.height), 4)],
                "rotation_deg": int(page.rotation),
                "text": full_text,
                "text_spans": spans,
                "dimension_candidates": dimension_tokens,
                "vector_path_count": len(drawings),
                "vector_paths_truncated": len(drawings) > max_paths_per_page,
                "vector_paths": vector_paths,
                "embedded_image_count": len(page.get_images(full=True)),
                "has_vector_content": bool(drawings)
            }
            report["pages"].append(page_report)
    report["summary"] = {
        "pages_with_vectors": sum(1 for p in report["pages"] if p["has_vector_content"]),
        "total_vector_paths": sum(p["vector_path_count"] for p in report["pages"]),
        "total_text_spans": sum(len(p["text_spans"]) for p in report["pages"]),
        "total_dimension_candidates": sum(len(p["dimension_candidates"]) for p in report["pages"]),
        "pages_with_embedded_images": sum(1 for p in report["pages"] if p["embedded_image_count"])
    }
    return report


def format_analysis_summary(report):
    summary = report.get("summary", {})
    lines = [
        "PHÂN TÍCH PDF CỤC BỘ · VECTOR-FIRST",
        f"Tệp: {report.get('source_file')}",
        f"Số trang: {report.get('page_count', 0)}",
        f"Vector paths: {summary.get('total_vector_paths', 0)}",
        f"Text spans: {summary.get('total_text_spans', 0)}",
        f"Kích thước dạng chữ tìm thấy: {summary.get('total_dimension_candidates', 0)}",
        f"Trang có ảnh nhúng: {summary.get('pages_with_embedded_images', 0)}",
        "",
        "LƯU Ý: tọa độ gốc là point PDF, không phải mm. Chưa tự xác nhận tỷ lệ."
    ]
    for page in report.get("pages", []):
        lines.extend([
            "",
            f"TRANG {page['page']} · {page['page_size_pt'][0]} × {page['page_size_pt'][1]} pt",
            f"Vector: {page['vector_path_count']} · Ảnh: {page['embedded_image_count']}",
            "Kích thước đọc được: " + (", ".join(page["dimension_candidates"][:60]) or "Chưa tìm thấy")
        ])
    return "\n".join(lines)


def save_analysis_report(report, output_path):
    Path(output_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
