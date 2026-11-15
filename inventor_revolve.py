"""Native revolve feature builder for Autodesk Inventor 2018.

All sketch coordinates and dimensions are millimetres. The profile is an
explicit closed cross-section in a chosen origin plane; no drawing scale is
inferred here.
"""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters

PLANE_IDS = {"YZ": 1, "XZ": 2, "XY": 3}
OPERATIONS = {"join": 20481, "cut": 20482, "intersect": 20483, "surface": 20484}
DIRECTIONS = {"positive": 20993, "negative": 20994}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InventorBridgeError(f"{label} phải là số hữu hạn.")
    return float(value)


def validate_revolve(command):
    if not isinstance(command, dict) or command.get("op") != "create_revolve":
        raise InventorBridgeError("Lệnh phải dùng op='create_revolve'.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("Revolve bắt buộc khai báo unit='mm'.")
    plane = str(command.get("plane", "XY")).upper()
    if plane not in PLANE_IDS:
        raise InventorBridgeError("plane chỉ nhận XY, XZ hoặc YZ.")
    loops = command.get("loops")
    if not isinstance(loops, list) or not loops:
        raise InventorBridgeError("loops phải có ít nhất một biên dạng kín.")
    clean = []
    for li, loop in enumerate(loops, 1):
        if not isinstance(loop, dict):
            raise InventorBridgeError(f"loops[{li}] phải là object.")
        kind = loop.get("type", "polyline")
        if kind == "polyline":
            pts = loop.get("points")
            if not isinstance(pts, list) or len(pts) < 3:
                raise InventorBridgeError(f"Biên dạng {li} cần tối thiểu 3 điểm.")
            out = []
            for p in pts:
                if not isinstance(p, (list, tuple)) or len(p) != 2:
                    raise InventorBridgeError("Mỗi điểm phải có dạng [x,y] mm.")
                out.append([_number(p[0], "x"), _number(p[1], "y")])
            if len(set((p[0], p[1]) for p in out)) < 3:
                raise InventorBridgeError(f"Biên dạng {li} cần 3 điểm phân biệt.")
            area2 = sum(out[i][0]*out[(i+1)%len(out)][1] - out[(i+1)%len(out)][0]*out[i][1] for i in range(len(out)))
            if abs(area2) < 1e-8:
                raise InventorBridgeError(f"Biên dạng {li} có diện tích bằng 0.")
            clean.append({"type": "polyline", "points": out})
        elif kind == "circle":
            cx = _number(loop.get("center_x"), "center_x")
            cy = _number(loop.get("center_y"), "center_y")
            radius = _number(loop.get("radius"), "radius")
            if radius <= 0:
                raise InventorBridgeError("Bán kính đường tròn phải lớn hơn 0.")
            clean.append({"type": "circle", "center_x": cx, "center_y": cy, "radius": radius})
        else:
            raise InventorBridgeError("Revolve hiện hỗ trợ loop polyline và circle; dùng spline-profile cho NURBS.")
    axis = command.get("axis_points")
    if not isinstance(axis, list) or len(axis) != 2 or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in axis):
        raise InventorBridgeError("axis_points phải gồm hai điểm [x,y] nằm trên trục quay.")
    axis = [[_number(p[0], "axis.x"), _number(p[1], "axis.y")] for p in axis]
    if math.dist(axis[0], axis[1]) <= 1e-7:
        raise InventorBridgeError("Hai điểm trục quay không được trùng nhau.")
    offset = _number(command.get("offset_mm", 0), "offset_mm")
    operation = str(command.get("operation", "join")).lower()
    if operation not in OPERATIONS:
        raise InventorBridgeError("operation chỉ nhận join, cut, intersect hoặc surface.")
    full = command.get("full", True)
    if not isinstance(full, bool):
        raise InventorBridgeError("full phải là true hoặc false.")
    angle = 360.0 if full else _number(command.get("angle_deg"), "angle_deg")
    if not full and not 0 < angle < 360:
        raise InventorBridgeError("Revolve một phần phải có angle_deg trong khoảng lớn hơn 0 và nhỏ hơn 360.")
    direction = str(command.get("direction", "positive")).lower()
    if direction not in DIRECTIONS:
        raise InventorBridgeError("direction chỉ nhận positive hoặc negative.")
    name = str(command.get("feature_name", "P2I_Revolve")).strip()
    if not name or len(name) > 120:
        raise InventorBridgeError("feature_name phải có 1–120 ký tự.")
    return {"plane": plane, "loops": clean, "axis_points": axis, "offset_mm": offset,
            "operation": operation, "full": full, "angle_deg": angle,
            "direction": direction, "feature_name": name}


def create_revolve(document, inventor_app, command):
    cfg = validate_revolve(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Cần mở và lưu file IPT trước khi tạo Revolve.")
    document.Save()
    source = Path(file_path)
    backup = source.with_name(source.stem + "_Before_P2I_Revolve_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + source.suffix)
    shutil.copy2(source, backup)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(document, "PDF2Inventor Revolve")
        component = document.ComponentDefinition
        base_plane = component.WorkPlanes.Item(PLANE_IDS[cfg["plane"]])
        sketch_plane = base_plane if abs(cfg["offset_mm"]) < 1e-9 else component.WorkPlanes.AddByPlaneAndOffset(base_plane, cfg["offset_mm"] / 10.0)
        sketch = component.Sketches.Add(sketch_plane)
        tg = inventor_app.TransientGeometry
        for loop in cfg["loops"]:
            if loop["type"] == "polyline":
                points = [sketch.SketchPoints.Add(tg.CreatePoint2d(p[0]/10.0, p[1]/10.0), False) for p in loop["points"]]
                for i, point in enumerate(points):
                    sketch.SketchLines.AddByTwoPoints(point, points[(i+1) % len(points)])
            else:
                center = tg.CreatePoint2d(loop["center_x"]/10.0, loop["center_y"]/10.0)
                sketch.SketchCircles.AddByCenterRadius(center, loop["radius"]/10.0)
        axis_points = [sketch.SketchPoints.Add(tg.CreatePoint2d(p[0]/10.0, p[1]/10.0), False) for p in cfg["axis_points"]]
        axis_line = sketch.SketchLines.AddByTwoPoints(axis_points[0], axis_points[1])
        axis_line.Construction = True
        profile = sketch.Profiles.AddForSolid()
        features = component.Features.RevolveFeatures
        op = OPERATIONS[cfg["operation"]]
        if cfg["full"]:
            feature = features.AddFull(profile, axis_line, op)
        else:
            feature = features.AddByAngle(profile, axis_line, math.radians(cfg["angle_deg"]), DIRECTIONS[cfg["direction"]], op)
        sketch.Visible = False
        sketch.Name = "P2I_Revolve_Profile"
        feature.Name = cfg["feature_name"]
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        return {"document_path": file_path, "backup_path": str(backup),
                "feature_name": str(feature.Name), "operation": cfg["operation"],
                "angle_deg": cfg["angle_deg"], "plane": cfg["plane"],
                "loop_count": len(cfg["loops"]), "parameters": read_parameters(document)}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được Revolve: {type(exc).__name__}: {exc}. Backup: {backup}") from exc
