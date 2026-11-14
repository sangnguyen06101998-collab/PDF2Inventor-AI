"""Advanced, explicit profile geometry for Autodesk Inventor 2018.

Coordinates are millimetres in the selected origin work plane. This module
never estimates missing dimensions. Each operation creates native Inventor
Sketch/Extrude features and records a backup before editing the IPT.
"""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters

PLANE_IDS = {"YZ": 1, "XZ": 2, "XY": 3}
OPERATION_IDS = {"join": 20481, "cut": 20482, "new_body": 20485}
DIRECTION_IDS = {"positive": 20993, "negative": 20994}


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InventorBridgeError(f"{label} phải là số hữu hạn.")
    return float(value)


def validate_advanced_profile(command):
    if not isinstance(command, dict) or command.get("op") != "create_profile_extrude":
        raise InventorBridgeError("Lệnh phải dùng op='create_profile_extrude'.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("Bắt buộc khai báo unit='mm'.")
    plane = str(command.get("plane", "XY")).upper()
    if plane not in PLANE_IDS:
        raise InventorBridgeError("plane chỉ nhận XY, XZ hoặc YZ.")
    loops = command.get("loops")
    if not isinstance(loops, list) or not loops:
        raise InventorBridgeError("loops phải chứa ít nhất một biên dạng kín.")
    normalized = []
    for li, loop in enumerate(loops, 1):
        if not isinstance(loop, dict):
            raise InventorBridgeError(f"loops[{li}] phải là object.")
        kind = loop.get("type", "polyline")
        if kind == "polyline":
            points = loop.get("points")
            if not isinstance(points, list) or len(points) < 3:
                raise InventorBridgeError(f"Biên dạng {li} cần tối thiểu 3 điểm.")
            pts = []
            for pi, point in enumerate(points, 1):
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise InventorBridgeError(f"Điểm {pi} của biên dạng {li} phải là [x,y].")
                pts.append([_finite_number(point[0], "x"), _finite_number(point[1], "y")])
            if len({(p[0], p[1]) for p in pts}) < 3:
                raise InventorBridgeError(f"Biên dạng {li} phải có ít nhất 3 điểm phân biệt.")
            area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
            if abs(area2) < 1e-8:
                raise InventorBridgeError(f"Biên dạng {li} có diện tích bằng 0.")
            normalized.append({"type": "polyline", "points": pts})
        elif kind == "circle":
            cx = _finite_number(loop.get("center_x"), "center_x")
            cy = _finite_number(loop.get("center_y"), "center_y")
            radius = _finite_number(loop.get("radius"), "radius")
            if radius <= 0:
                raise InventorBridgeError("Bán kính đường tròn phải lớn hơn 0.")
            normalized.append({"type": "circle", "center_x": cx, "center_y": cy, "radius": radius})
        else:
            raise InventorBridgeError("Loại loop chỉ nhận polyline hoặc circle.")
    distance = _finite_number(command.get("distance"), "distance")
    if distance <= 0:
        raise InventorBridgeError("distance phải lớn hơn 0.")
    operation = str(command.get("operation", "new_body")).lower()
    if operation not in OPERATION_IDS:
        raise InventorBridgeError("operation chỉ nhận join, cut hoặc new_body.")
    direction = str(command.get("direction", "positive")).lower()
    if direction not in DIRECTION_IDS:
        raise InventorBridgeError("direction chỉ nhận positive hoặc negative.")
    return {"plane": plane, "loops": normalized, "distance": distance,
            "operation": operation, "direction": direction, "unit": "mm"}


def create_profile_extrude(document, inventor_app, command):
    """Create arbitrary polygon/circle profile loops on XY/XZ/YZ and extrude."""
    cfg = validate_advanced_profile(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Cần mở và lưu file IPT trước khi dựng hình.")
    try:
        document.Save()
    except Exception as exc:
        raise InventorBridgeError("Không lưu được IPT trước khi backup: " + str(exc)) from exc
    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = source.with_name(f"{source.stem}_Before_PDF2Inventor_Advanced_{stamp}{source.suffix}")
    shutil.copy2(source, backup)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(
            document, "PDF2Inventor Advanced Profile Extrude"
        )
        component = document.ComponentDefinition
        sketch = component.Sketches.Add(component.WorkPlanes.Item(PLANE_IDS[cfg["plane"]]))
        geometry = inventor_app.TransientGeometry
        for loop in cfg["loops"]:
            if loop["type"] == "polyline":
                pts = loop["points"]
                for i, p in enumerate(pts):
                    q = pts[(i + 1) % len(pts)]
                    a = geometry.CreatePoint2d(p[0] / 10.0, p[1] / 10.0)
                    b = geometry.CreatePoint2d(q[0] / 10.0, q[1] / 10.0)
                    sketch.SketchLines.AddByTwoPoints(a, b)
            else:
                center = geometry.CreatePoint2d(loop["center_x"] / 10.0, loop["center_y"] / 10.0)
                sketch.SketchCircles.AddByCenterRadius(center, loop["radius"] / 10.0)
        profile = sketch.Profiles.AddForSolid()
        definition = component.Features.ExtrudeFeatures.CreateExtrudeDefinition(
            profile, OPERATION_IDS[cfg["operation"]]
        )
        definition.SetDistanceExtent(
            f'{cfg["distance"]:.12g} mm', DIRECTION_IDS[cfg["direction"]]
        )
        feature = component.Features.ExtrudeFeatures.Add(definition)
        sketch.Visible = False
        sketch.Name = "P2I_Advanced_Profile_Sketch"
        feature.Name = "P2I_Advanced_Profile_Extrude"
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        return {
            "document_path": file_path, "backup_path": str(backup),
            "sketch_name": str(sketch.Name), "feature_name": str(feature.Name),
            "plane": cfg["plane"], "distance_mm": cfg["distance"],
            "operation": cfg["operation"], "loop_count": len(cfg["loops"]),
            "range_box": _range_box_mm(component), "parameters": read_parameters(document)
        }
    except Exception as exc:
        if transaction is not None:
            try:
                transaction.Abort()
            except Exception:
                pass
        raise InventorBridgeError(
            f"Không tạo được profile/extrude trên mặt phẳng {cfg['plane']}: {type(exc).__name__}: {exc}. "
            f"Backup được giữ tại: {backup}"
        ) from exc


def _range_box_mm(component_definition):
    try:
        box = component_definition.RangeBox
        lo, hi = box.MinPoint, box.MaxPoint
        return {"min_mm": [round(float(lo.X)*10, 4), round(float(lo.Y)*10, 4), round(float(lo.Z)*10, 4)],
                "max_mm": [round(float(hi.X)*10, 4), round(float(hi.Y)*10, 4), round(float(hi.Z)*10, 4)]}
    except Exception:
        return None
