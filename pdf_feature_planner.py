"""Conservative PDF-vector to Inventor Feature-plan generator.

Only closed, line-only vector loops are accepted for automatic profile creation.
A user-supplied mm/point calibration and extrusion depth are mandatory. Curves,
hidden-line interpretation, orthographic-view matching and depth inference are
never guessed by this module.
"""
import math
from inventor_bridge import InventorBridgeError
from inventor_advanced import validate_advanced_profile


def _point(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            x, y = float(value[0]), float(value[1])
            if math.isfinite(x) and math.isfinite(y):
                return [x, y]
        except Exception:
            return None
    return None


def _area(points):
    return abs(sum(points[i][0]*points[(i+1)%len(points)][1] -
                   points[(i+1)%len(points)][0]*points[i][1]
                   for i in range(len(points))) / 2.0)


def _extract_closed_lines(path):
    items = path.get("items", [])
    if not path.get("closed") or not items:
        return None
    if len(items) == 1 and items[0].get("type") == "re":
        data = items[0].get("data", [])
        rect = data[0] if data and isinstance(data[0], (list, tuple)) else data
        if isinstance(rect, (list, tuple)) and len(rect) >= 4:
            x0, y0, x1, y1 = map(float, rect[:4])
            pts = [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
            return pts if abs(x1-x0) > 0.01 and abs(y1-y0) > 0.01 else None
    if any(item.get("type") != "l" for item in items):
        return None
    segments = []
    for item in items:
        data = item.get("data", [])
        if len(data) < 2:
            return None
        a, b = _point(data[0]), _point(data[1])
        if a is None or b is None:
            return None
        segments.append((a,b))
    points = [segments[0][0]]
    for start, end in segments:
        if math.dist(points[-1], start) > 0.75:
            return None
        points.append(end)
    if math.dist(points[-1], points[0]) > 0.75:
        return None
    points.pop()
    if len(points) < 3:
        return None
    if len(set((round(p[0],3),round(p[1],3)) for p in points)) < 3:
        return None
    return points


def list_closed_profile_candidates(report, page_number):
    pages = report.get("pages", [])
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1 or page_number > len(pages):
        raise InventorBridgeError("page_number không hợp lệ.")
    page = pages[page_number-1]
    width, height = page.get("page_size_pt", [0, 0])
    page_area = max(float(width)*float(height), 1.0)
    found = []
    for index, path in enumerate(page.get("vector_paths", []), 1):
        points = _extract_closed_lines(path)
        if points is None:
            continue
        box = path.get("bbox_pt") or [min(p[0] for p in points), min(p[1] for p in points),
                                     max(p[0] for p in points), max(p[1] for p in points)]
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        x0, y0, x1, y1 = map(float, box)
        bbox_area = max(0.0, x1-x0) * max(0.0, y1-y0)
        # Exclude page frame/border-sized outlines, which are not part profiles.
        if bbox_area <= 1.0 or bbox_area / page_area >= 0.78:
            continue
        found.append({"path_index": index, "point_count": len(points),
                      "bbox_pt": [round(x0,3),round(y0,3),round(x1,3),round(y1,3)],
                      "bbox_area_pt2": round(bbox_area,3)})
    return found


def build_pdf_feature_plan(report, page_number, path_indices, mm_per_pt, depth_mm,
                           component_id, plane="XY", operation="new_body"):
    if not isinstance(path_indices, list) or not path_indices:
        raise InventorBridgeError("Chọn ít nhất một vector path kín.")
    scale = float(mm_per_pt)
    depth = float(depth_mm)
    if not math.isfinite(scale) or scale <= 0:
        raise InventorBridgeError("mm_per_pt phải được hiệu chuẩn và lớn hơn 0.")
    if not math.isfinite(depth) or depth <= 0:
        raise InventorBridgeError("depth_mm phải được xác định và lớn hơn 0.")
    if not isinstance(component_id, str) or not component_id.strip():
        raise InventorBridgeError("component_id phải là chi tiết IPT đã liên kết.")
    pages = report.get("pages", [])
    if isinstance(page_number, bool) or not isinstance(page_number, int) or not 1 <= page_number <= len(pages):
        raise InventorBridgeError("page_number không hợp lệ.")
    page = pages[page_number-1]
    paths = page.get("vector_paths", [])
    loops = []
    used = []
    for index in path_indices:
        if isinstance(index, bool) or not isinstance(index, int) or index < 1 or index > len(paths):
            raise InventorBridgeError(f"Vector path index {index!r} không hợp lệ.")
        points = _extract_closed_lines(paths[index-1])
        if points is None:
            raise InventorBridgeError(f"Path {index} không phải vòng kín chỉ gồm line/re; không tự xấp xỉ curve.")
        used.append(index)
        if len(loops) == 0:
            origin_x = min(p[0] for p in points)
            origin_y = max(p[1] for p in points)
        local = [[round((p[0]-origin_x)*scale, 6),
                  round((origin_y-p[1])*scale, 6)] for p in points]
        loops.append({"type": "polyline", "points": local})
    command = {"op": "create_profile_extrude", "component_id": component_id.strip(),
               "unit": "mm", "plane": str(plane).upper(), "loops": loops,
               "distance": depth, "operation": str(operation).lower(),
               "direction": "positive", "feature_name": "P2I_PDF_Vector_Profile"}
    validate_advanced_profile(command)
    return {
        "schema": "pdf2inventor.feature-plan.v1",
        "source_file": report.get("source_file"),
        "page_number": page_number,
        "calibration": {"mm_per_pt": scale, "method": "explicit user calibration"},
        "selected_vector_path_indices": used,
        "automatic_inference": {"scale_from_pdf": False, "extrusion_depth_inferred": False,
                                "orthographic_views_matched": False, "curves_auto_reconstructed": False},
        "warnings": [
            "Kiểm tra hình chiếu đã chọn trước khi áp dụng; path có thể là nét phụ hoặc đường bao khác.",
            "Chiều sâu Extrude do người dùng nhập, không được suy ra từ PDF.",
            "Chỉ vector kín dạng line/re được chuyển tự động; arc/spline/hidden line/section view chưa tự diễn giải."
        ],
        "commands": [command]
    }
