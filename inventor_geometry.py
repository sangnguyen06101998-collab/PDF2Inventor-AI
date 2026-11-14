"""Parametric sketch and extrusion helpers for Autodesk Inventor 2018 COM."""
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters


# Autodesk Inventor API enum values (stable since early Inventor releases).
K_HORIZONTAL_DIM = 19201
K_VERTICAL_DIM = 19202
K_POSITIVE_EXTENT_DIRECTION = 20993
K_NEGATIVE_EXTENT_DIRECTION = 20994
K_JOIN_OPERATION = 20481
K_CUT_OPERATION = 20482
K_NEW_BODY_OPERATION = 20485


def _number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InventorBridgeError(f"'{label}' phải là số.")
    result = float(value)
    if not math.isfinite(result):
        raise InventorBridgeError(f"'{label}' phải là số hữu hạn.")
    if positive and result <= 0:
        raise InventorBridgeError(f"'{label}' phải lớn hơn 0.")
    return result


def validate_rectangle_command(command):
    """Validate and normalize a rectangle + extrusion command without COM access."""
    if not isinstance(command, dict):
        raise InventorBridgeError("Lệnh hình học phải là một đối tượng JSON.")
    if command.get("op") != "create_rectangle_extrude":
        raise InventorBridgeError("V0.5 chưa hỗ trợ loại lệnh hình học này.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("V0.5 yêu cầu unit='mm' rõ ràng cho lệnh Sketch/Extrude.")

    length = _number(command.get("length"), "length", positive=True)
    width = _number(command.get("width"), "width", positive=True)
    thickness = _number(command.get("thickness"), "thickness", positive=True)
    origin_x = _number(command.get("origin_x", 0), "origin_x")
    origin_y = _number(command.get("origin_y", 0), "origin_y")

    direction = str(command.get("direction", "positive")).strip().lower()
    if direction not in {"positive", "negative"}:
        raise InventorBridgeError("direction chỉ nhận 'positive' hoặc 'negative'.")

    operation = str(command.get("operation", "auto")).strip().lower()
    if operation not in {"auto", "join", "new_body", "cut"}:
        raise InventorBridgeError("operation chỉ nhận auto, join, new_body hoặc cut.")

    parameter_names = command.get("parameter_names") or {}
    if not isinstance(parameter_names, dict):
        raise InventorBridgeError("parameter_names phải là một đối tượng JSON.")
    names = {}
    for key, default in (
        ("length", "Length"),
        ("width", "Width"),
        ("thickness", "Thickness"),
    ):
        name = str(parameter_names.get(key, default)).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise InventorBridgeError(
                f"Tên tham số '{name}' không hợp lệ. Chỉ dùng chữ, số và dấu gạch dưới; ký tự đầu phải là chữ hoặc _."
            )
        names[key] = name

    if len(set(names.values())) != 3:
        raise InventorBridgeError("Ba tên tham số Length, Width và Thickness phải khác nhau.")

    return {
        "length": length,
        "width": width,
        "thickness": thickness,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "direction": direction,
        "operation": operation,
        "parameter_names": names,
        "unit": "mm",
    }


def _unique_parameter_name(parameters, requested_name):
    candidate = requested_name
    suffix = 2
    while True:
        try:
            parameters.Item(candidate)
        except Exception:
            return candidate
        candidate = f"{requested_name}_{suffix}"
        suffix += 1


def _range_box_mm(component_definition):
    try:
        box = component_definition.RangeBox
        minimum = box.MinPoint
        maximum = box.MaxPoint
        # Inventor API database length units are centimeters.
        return {
            "min_mm": [round(float(minimum.X) * 10, 4),
                       round(float(minimum.Y) * 10, 4),
                       round(float(minimum.Z) * 10, 4)],
            "max_mm": [round(float(maximum.X) * 10, 4),
                       round(float(maximum.Y) * 10, 4),
                       round(float(maximum.Z) * 10, 4)],
        }
    except Exception:
        return None


def create_rectangle_extrude(document, inventor_app, command):
    """Create a fully dimensioned XY rectangle and extrude it in an existing IPT.

    The sketch is constrained horizontal/vertical, its first corner is grounded,
    and its two driving dimensions reference named user parameters. The extrusion
    distance references a third named user parameter.
    """
    cfg = validate_rectangle_command(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt":
        raise InventorBridgeError(
            "Lệnh Sketch/Extrude chỉ chạy trên file .ipt đã lưu. Hãy Save As IPT trước."
        )
    if not os.path.isfile(file_path):
        raise InventorBridgeError(f"Không tìm thấy file IPT: {file_path}")

    try:
        document.Save()
    except Exception as exc:
        raise InventorBridgeError(f"Không lưu được IPT trước khi tạo backup: {exc}") from exc

    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = source.with_name(f"{source.stem}_Before_PDF2Inventor_V05_{stamp}{source.suffix}")
    try:
        shutil.copy2(source, backup)
    except Exception as exc:
        raise InventorBridgeError(f"Không tạo được bản sao dự phòng: {exc}") from exc

    transaction = None
    save_attempted = False
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(
            document, "PDF2Inventor V0.5 - Rectangle Extrude"
        )
        component = document.ComponentDefinition
        all_parameters = component.Parameters
        user_parameters = all_parameters.UserParameters

        actual_names = {
            key: _unique_parameter_name(all_parameters, requested)
            for key, requested in cfg["parameter_names"].items()
        }
        user_parameters.AddByExpression(
            actual_names["length"], f'{cfg["length"]:.12g} mm', "mm"
        )
        user_parameters.AddByExpression(
            actual_names["width"], f'{cfg["width"]:.12g} mm', "mm"
        )
        user_parameters.AddByExpression(
            actual_names["thickness"], f'{cfg["thickness"]:.12g} mm', "mm"
        )

        # Create the sketch on the XY origin plane. API coordinates are cm.
        sketch = component.Sketches.Add(component.WorkPlanes.Item(3))
        geometry = inventor_app.TransientGeometry
        x0 = cfg["origin_x"] / 10.0
        y0 = cfg["origin_y"] / 10.0
        x1 = (cfg["origin_x"] + cfg["length"]) / 10.0
        y1 = (cfg["origin_y"] + cfg["width"]) / 10.0

        p0 = sketch.SketchPoints.Add(geometry.CreatePoint2d(x0, y0), False)
        p1 = sketch.SketchPoints.Add(geometry.CreatePoint2d(x1, y0), False)
        p2 = sketch.SketchPoints.Add(geometry.CreatePoint2d(x1, y1), False)
        p3 = sketch.SketchPoints.Add(geometry.CreatePoint2d(x0, y1), False)

        line_bottom = sketch.SketchLines.AddByTwoPoints(p0, p1)
        line_right = sketch.SketchLines.AddByTwoPoints(p1, p2)
        line_top = sketch.SketchLines.AddByTwoPoints(p2, p3)
        line_left = sketch.SketchLines.AddByTwoPoints(p3, p0)

        geometric = sketch.GeometricConstraints
        geometric.AddHorizontal(line_bottom)
        geometric.AddVertical(line_right)
        geometric.AddHorizontal(line_top)
        geometric.AddVertical(line_left)
        geometric.AddGround(p0)

        dimensions = sketch.DimensionConstraints
        length_dimension = dimensions.AddTwoPointDistance(
            p0, p1, K_HORIZONTAL_DIM,
            geometry.CreatePoint2d((x0 + x1) / 2.0, y0 - max(0.5, cfg["width"] / 100.0)),
            False,
        )
        length_dimension.Parameter.Expression = actual_names["length"]

        width_dimension = dimensions.AddTwoPointDistance(
            p1, p2, K_VERTICAL_DIM,
            geometry.CreatePoint2d(x1 + max(0.5, cfg["length"] / 100.0), (y0 + y1) / 2.0),
            False,
        )
        width_dimension.Parameter.Expression = actual_names["width"]

        profile = sketch.Profiles.AddForSolid()
        try:
            body_count = int(component.SurfaceBodies.Count)
        except Exception:
            body_count = 0
        operation = cfg["operation"]
        if operation == "auto":
            # Use join only when the new extrusion's bounding box overlaps an
            # existing solid; otherwise create a separate solid body.
            current_box = _range_box_mm(component)
            operation = "new_body"
            if body_count > 0 and current_box:
                existing_min = current_box["min_mm"]
                existing_max = current_box["max_mm"]
                new_z_min = 0.0 if cfg["direction"] == "positive" else -cfg["thickness"]
                new_z_max = cfg["thickness"] if cfg["direction"] == "positive" else 0.0
                new_min = [cfg["origin_x"], cfg["origin_y"], new_z_min]
                new_max = [
                    cfg["origin_x"] + cfg["length"],
                    cfg["origin_y"] + cfg["width"],
                    new_z_max,
                ]
                overlaps = all(
                    min(existing_max[axis], new_max[axis])
                    - max(existing_min[axis], new_min[axis]) > 1e-6
                    for axis in range(3)
                )
                if overlaps:
                    operation = "join"
        if operation in {"join", "cut"} and body_count == 0:
            raise InventorBridgeError(
                f"operation={operation} nhưng IPT chưa có solid body. Hãy tạo solid trước hoặc dùng operation=new_body."
            )
        operation_enum = {"join": K_JOIN_OPERATION, "new_body": K_NEW_BODY_OPERATION, "cut": K_CUT_OPERATION}[operation]
        direction_enum = (
            K_POSITIVE_EXTENT_DIRECTION
            if cfg["direction"] == "positive"
            else K_NEGATIVE_EXTENT_DIRECTION
        )

        extrudes = component.Features.ExtrudeFeatures
        definition = extrudes.CreateExtrudeDefinition(profile, operation_enum)
        definition.SetDistanceExtent(actual_names["thickness"], direction_enum)
        extrude = extrudes.Add(definition)

        try:
            sketch.Visible = False
        except Exception:
            pass
        try:
            extrude.Name = "P2I_Rectangle_Extrude"
            sketch.Name = "P2I_Rectangle_Sketch"
        except Exception:
            pass

        document.Update()
        save_attempted = True
        document.Save()
        transaction.End()
        transaction = None

        return {
            "document_path": file_path,
            "backup_path": str(backup),
            "sketch_name": str(getattr(sketch, "Name", "P2I_Rectangle_Sketch")),
            "feature_name": str(getattr(extrude, "Name", "P2I_Rectangle_Extrude")),
            "operation": operation,
            "direction": cfg["direction"],
            "dimensions_mm": {
                "length": cfg["length"],
                "width": cfg["width"],
                "thickness": cfg["thickness"],
                "origin_x": cfg["origin_x"],
                "origin_y": cfg["origin_y"],
            },
            "parameter_names": actual_names,
            "parameters": read_parameters(document),
            "range_box": _range_box_mm(component),
        }

    except Exception as exc:
        rollback_message = ""
        if transaction is not None:
            try:
                transaction.Abort()
                rollback_message = "Đã hủy transaction hình học trong Inventor."
            except Exception as abort_exc:
                rollback_message = f"Không xác nhận được rollback transaction: {abort_exc}"
        if save_attempted:
            try:
                shutil.copy2(backup, file_path)
                rollback_message += (
                    " Đã khôi phục nội dung file trên ổ đĩa từ bản backup; "
                    "hãy đóng IPT bằng lựa chọn không lưu rồi mở lại file."
                )
            except Exception as restore_exc:
                rollback_message += f" Không thể khôi phục file tự động: {restore_exc}"
        detail = str(exc) if isinstance(exc, InventorBridgeError) else f"{type(exc).__name__}: {exc}"
        raise InventorBridgeError(
            f"Không tạo được Sketch/Extrude: {detail}. {rollback_message} "
            f"Backup: {backup}"
        ) from exc


def validate_circle_command(command):
    """Validate a circle extrusion/cut command without connecting to COM."""
    if not isinstance(command, dict) or command.get("op") != "create_circle_extrude":
        raise InventorBridgeError("Lệnh hình tròn phải dùng op='create_circle_extrude'.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("V0.5 yêu cầu unit='mm' cho lệnh Sketch tròn/Extrude.")
    diameter = _number(command.get("diameter"), "diameter", positive=True)
    thickness = _number(command.get("thickness"), "thickness", positive=True)
    center_x = _number(command.get("center_x", 0), "center_x")
    center_y = _number(command.get("center_y", 0), "center_y")
    direction = str(command.get("direction", "positive")).strip().lower()
    if direction not in {"positive", "negative"}:
        raise InventorBridgeError("direction chỉ nhận positive hoặc negative.")
    operation = str(command.get("operation", "auto")).strip().lower()
    if operation not in {"auto", "join", "new_body", "cut"}:
        raise InventorBridgeError("operation chỉ nhận auto, join, new_body hoặc cut.")
    parameter_names = command.get("parameter_names") or {}
    if not isinstance(parameter_names, dict):
        raise InventorBridgeError("parameter_names phải là một đối tượng JSON.")
    names = {}
    for key, default in (("diameter", "Diameter"), ("thickness", "Thickness")):
        name = str(parameter_names.get(key, default)).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise InventorBridgeError("Tên tham số không hợp lệ: " + name)
        names[key] = name
    if len(set(names.values())) != 2:
        raise InventorBridgeError("Tên Diameter và Thickness phải khác nhau.")
    return {
        "diameter": diameter,
        "thickness": thickness,
        "center_x": center_x,
        "center_y": center_y,
        "direction": direction,
        "operation": operation,
        "parameter_names": names,
        "unit": "mm",
    }


def create_circle_extrude(document, inventor_app, command):
    """Create a dimensioned XY circle and extrude it or cut it in an existing IPT."""
    cfg = validate_circle_command(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Lệnh Sketch tròn chỉ chạy trên file .ipt đã lưu và tồn tại.")

    try:
        document.Save()
    except Exception as exc:
        raise InventorBridgeError("Không lưu được IPT trước khi tạo backup: " + str(exc)) from exc
    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = source.with_name(source.stem + "_Before_PDF2Inventor_V05_" + stamp + source.suffix)
    try:
        shutil.copy2(source, backup)
    except Exception as exc:
        raise InventorBridgeError("Không tạo được bản sao dự phòng: " + str(exc)) from exc

    transaction = None
    save_attempted = False
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(
            document, "PDF2Inventor V0.5 - Circle Extrude"
        )
        component = document.ComponentDefinition
        all_parameters = component.Parameters
        user_parameters = all_parameters.UserParameters
        actual_names = {
            key: _unique_parameter_name(all_parameters, requested)
            for key, requested in cfg["parameter_names"].items()
        }
        user_parameters.AddByExpression(
            actual_names["diameter"], str(cfg["diameter"]) + " mm", "mm"
        )
        user_parameters.AddByExpression(
            actual_names["thickness"], str(cfg["thickness"]) + " mm", "mm"
        )

        geometry = inventor_app.TransientGeometry
        sketch = component.Sketches.Add(component.WorkPlanes.Item(3))
        cx = cfg["center_x"] / 10.0
        cy = cfg["center_y"] / 10.0
        radius = cfg["diameter"] / 20.0
        center = sketch.SketchPoints.Add(geometry.CreatePoint2d(cx, cy), False)
        circle = sketch.SketchCircles.AddByCenterRadius(center, radius)
        sketch.GeometricConstraints.AddGround(center)
        diameter_dimension = sketch.DimensionConstraints.AddDiameter(
            circle, geometry.CreatePoint2d(cx + radius + max(0.5, radius * 0.2), cy), False
        )
        diameter_dimension.Parameter.Expression = actual_names["diameter"]

        profile = sketch.Profiles.AddForSolid()
        try:
            body_count = int(component.SurfaceBodies.Count)
        except Exception:
            body_count = 0
        operation = cfg["operation"]
        if operation == "auto":
            operation = "new_body"
            current_box = _range_box_mm(component)
            if body_count > 0 and current_box:
                existing_min = current_box["min_mm"]
                existing_max = current_box["max_mm"]
                z_min = 0.0 if cfg["direction"] == "positive" else -cfg["thickness"]
                z_max = cfg["thickness"] if cfg["direction"] == "positive" else 0.0
                new_min = [
                    cfg["center_x"] - cfg["diameter"] / 2.0,
                    cfg["center_y"] - cfg["diameter"] / 2.0,
                    z_min,
                ]
                new_max = [
                    cfg["center_x"] + cfg["diameter"] / 2.0,
                    cfg["center_y"] + cfg["diameter"] / 2.0,
                    z_max,
                ]
                overlaps = all(
                    min(existing_max[i], new_max[i]) - max(existing_min[i], new_min[i]) > 1e-6
                    for i in range(3)
                )
                if overlaps:
                    operation = "join"
        if operation in {"join", "cut"} and body_count == 0:
            raise InventorBridgeError(
                "operation=" + operation + " nhưng IPT chưa có solid body. Hãy tạo solid trước."
            )
        operation_enum = {
            "join": K_JOIN_OPERATION,
            "new_body": K_NEW_BODY_OPERATION,
            "cut": K_CUT_OPERATION,
        }[operation]
        direction_enum = (
            K_POSITIVE_EXTENT_DIRECTION
            if cfg["direction"] == "positive"
            else K_NEGATIVE_EXTENT_DIRECTION
        )
        extrudes = component.Features.ExtrudeFeatures
        definition = extrudes.CreateExtrudeDefinition(profile, operation_enum)
        definition.SetDistanceExtent(actual_names["thickness"], direction_enum)
        extrude = extrudes.Add(definition)
        try:
            sketch.Visible = False
            sketch.Name = "P2I_Circle_Sketch"
            extrude.Name = "P2I_Circle_Extrude"
        except Exception:
            pass
        document.Update()
        save_attempted = True
        document.Save()
        transaction.End()
        transaction = None
        return {
            "document_path": file_path,
            "backup_path": str(backup),
            "sketch_name": str(getattr(sketch, "Name", "P2I_Circle_Sketch")),
            "feature_name": str(getattr(extrude, "Name", "P2I_Circle_Extrude")),
            "operation": operation,
            "direction": cfg["direction"],
            "dimensions_mm": {
                "diameter": cfg["diameter"],
                "thickness": cfg["thickness"],
                "center_x": cfg["center_x"],
                "center_y": cfg["center_y"],
            },
            "parameter_names": actual_names,
            "parameters": read_parameters(document),
            "range_box": _range_box_mm(component),
        }
    except Exception as exc:
        rollback_message = ""
        if transaction is not None:
            try:
                transaction.Abort()
                rollback_message = "Đã hủy transaction hình học trong Inventor."
            except Exception as abort_exc:
                rollback_message = "Không xác nhận được rollback transaction: " + str(abort_exc)
        if save_attempted:
            try:
                shutil.copy2(backup, file_path)
                rollback_message += " Đã khôi phục file trên ổ đĩa từ backup; hãy đóng IPT không lưu rồi mở lại."
            except Exception as restore_exc:
                rollback_message += " Không thể khôi phục file tự động: " + str(restore_exc)
        detail = str(exc) if isinstance(exc, InventorBridgeError) else type(exc).__name__ + ": " + str(exc)
        raise InventorBridgeError(
            "Không tạo được Sketch tròn/Extrude: " + detail + ". " + rollback_message + " Backup: " + str(backup)
        ) from exc


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p, eps=1e-8):
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
        and abs(_cross(a, b, p)) <= eps
    )


def _segments_intersect(a, b, c, d):
    o1, o2 = _cross(a, b, c), _cross(a, b, d)
    o3, o4 = _cross(c, d, a), _cross(c, d, b)
    eps = 1e-8
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    ):
        return True
    return (
        _on_segment(a, b, c)
        or _on_segment(a, b, d)
        or _on_segment(c, d, a)
        or _on_segment(c, d, b)
    )


def _point_in_polygon(point, polygon):
    x, y = point
    inside = False
    count = len(polygon)
    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]
        if _on_segment((x1, y1), (x2, y2), point):
            return False
        if (y1 > y) != (y2 > y):
            intersection_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < intersection_x:
                inside = not inside
    return inside


def _point_segment_distance(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-16:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    closest = (x1 + t * dx, y1 + t * dy)
    return math.hypot(px - closest[0], py - closest[1])


def validate_profile_command(command):
    """Validate a closed polygon profile with circular holes and inner cutout loops."""
    if not isinstance(command, dict) or command.get("op") != "create_profile_extrude":
        raise InventorBridgeError("Lệnh biên dạng phải dùng op='create_profile_extrude'.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("V0.6 yêu cầu unit='mm' cho biên dạng.")
    thickness = _number(command.get("thickness"), "thickness", positive=True)
    direction = str(command.get("direction", "positive")).strip().lower()
    if direction not in {"positive", "negative"}:
        raise InventorBridgeError("direction chỉ nhận positive hoặc negative.")

    def parse_polygon(raw, label):
        if not isinstance(raw, list) or not 3 <= len(raw) <= 200:
            raise InventorBridgeError(f"{label} cần từ 3 đến 200 điểm.")
        polygon = []
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                raise InventorBridgeError(f"{label}, điểm {index} không hợp lệ.")
            polygon.append((
                _number(item.get("x"), f"{label}[{index}].x"),
                _number(item.get("y"), f"{label}[{index}].y"),
            ))
        if len(set(polygon)) < 3:
            raise InventorBridgeError(f"{label} có dưới 3 điểm khác nhau.")
        for index in range(len(polygon)):
            if math.dist(polygon[index], polygon[(index + 1) % len(polygon)]) <= 1e-6:
                raise InventorBridgeError(f"{label} có cạnh bằng 0.")
        area2 = sum(
            polygon[i][0] * polygon[(i + 1) % len(polygon)][1]
            - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
            for i in range(len(polygon))
        )
        if abs(area2) <= 1e-6:
            raise InventorBridgeError(f"Diện tích {label} bằng 0.")
        for i in range(len(polygon)):
            a, b = polygon[i], polygon[(i + 1) % len(polygon)]
            for j in range(i + 1, len(polygon)):
                if j == (i + 1) % len(polygon) or i == (j + 1) % len(polygon):
                    continue
                if _segments_intersect(a, b, polygon[j], polygon[(j + 1) % len(polygon)]):
                    raise InventorBridgeError(f"{label} tự giao nhau.")
        return polygon

    points = parse_polygon(command.get("points"), "Biên dạng ngoài")
    point_count = len(points)

    raw_holes = command.get("holes") or []
    if not isinstance(raw_holes, list) or len(raw_holes) > 50:
        raise InventorBridgeError("Danh sách lỗ phải là mảng, tối đa 50 lỗ tròn.")
    holes = []
    for index, item in enumerate(raw_holes, 1):
        if not isinstance(item, dict):
            raise InventorBridgeError(f"Lỗ {index} phải có center_x, center_y, diameter.")
        center = (
            _number(item.get("center_x"), f"holes[{index}].center_x"),
            _number(item.get("center_y"), f"holes[{index}].center_y"),
        )
        diameter = _number(item.get("diameter"), f"holes[{index}].diameter", positive=True)
        radius = diameter / 2.0
        if not _point_in_polygon(center, points):
            raise InventorBridgeError(f"Tâm lỗ {index} nằm ngoài hoặc trên biên dạng.")
        edge_clearance = min(
            _point_segment_distance(center, points[i], points[(i + 1) % point_count])
            for i in range(point_count)
        )
        if edge_clearance <= radius + 1e-6:
            raise InventorBridgeError(f"Lỗ {index} chạm hoặc vượt ra ngoài biên dạng.")
        for previous_index, previous in enumerate(holes, 1):
            required = radius + previous["diameter"] / 2.0
            if math.dist(center, (previous["center_x"], previous["center_y"])) <= required + 1e-6:
                raise InventorBridgeError(f"Lỗ {index} giao hoặc chồng lên lỗ {previous_index}.")
        holes.append({
            "center_x": center[0],
            "center_y": center[1],
            "diameter": diameter,
        })

    raw_cutouts = command.get("cutouts") or []
    if not isinstance(raw_cutouts, list) or len(raw_cutouts) > 50:
        raise InventorBridgeError("Danh sách cutout phải là mảng, tối đa 50 biên dạng.")
    cutouts = []
    for cutout_index, raw_cutout in enumerate(raw_cutouts, 1):
        polygon = parse_polygon(raw_cutout, f"Cutout {cutout_index}")
        for point_index in range(len(polygon)):
            a, b = polygon[point_index], polygon[(point_index + 1) % len(polygon)]
            if not _point_in_polygon(a, points):
                raise InventorBridgeError(f"Cutout {cutout_index} nằm ngoài hoặc chạm biên dạng ngoài.")
            for outer_index in range(point_count):
                if _segments_intersect(
                    a, b, points[outer_index], points[(outer_index + 1) % point_count]
                ):
                    raise InventorBridgeError(f"Cutout {cutout_index} cắt qua đường bao ngoài.")
        for previous_index, previous in enumerate(cutouts, 1):
            if any(_point_in_polygon(point, previous) for point in polygon) or any(
                _point_in_polygon(point, polygon) for point in previous
            ):
                raise InventorBridgeError(f"Cutout {cutout_index} chồng lên cutout {previous_index}.")
            for i in range(len(polygon)):
                for j in range(len(previous)):
                    if _segments_intersect(
                        polygon[i], polygon[(i + 1) % len(polygon)],
                        previous[j], previous[(j + 1) % len(previous)],
                    ):
                        raise InventorBridgeError(f"Cutout {cutout_index} giao với cutout {previous_index}.")
        cutouts.append(polygon)

    for hole_index, hole in enumerate(holes, 1):
        center = (hole["center_x"], hole["center_y"])
        radius = hole["diameter"] / 2.0
        for cutout_index, polygon in enumerate(cutouts, 1):
            if _point_in_polygon(center, polygon):
                raise InventorBridgeError(f"Lỗ tròn {hole_index} nằm trong cutout {cutout_index}.")
            clearance = min(
                _point_segment_distance(center, polygon[i], polygon[(i + 1) % len(polygon)])
                for i in range(len(polygon))
            )
            if clearance <= radius + 1e-6:
                raise InventorBridgeError(f"Lỗ tròn {hole_index} chạm cutout {cutout_index}.")

    parameter_names = command.get("parameter_names") or {}
    if not isinstance(parameter_names, dict):
        raise InventorBridgeError("parameter_names phải là một đối tượng JSON.")
    thickness_name = str(parameter_names.get("thickness", "Thickness")).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", thickness_name):
        raise InventorBridgeError("Tên tham số Thickness không hợp lệ.")

    return {
        "points": points,
        "holes": holes,
        "cutouts": cutouts,
        "thickness": thickness,
        "direction": direction,
        "parameter_names": {"thickness": thickness_name},
        "unit": "mm",
    }


def create_profile_extrude(document, inventor_app, command):
    """Create an editable planar polygon sketch with circular holes and extrude it."""
    cfg = validate_profile_command(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Lệnh biên dạng chỉ chạy trên file .ipt đã lưu và tồn tại.")

    try:
        document.Save()
    except Exception as exc:
        raise InventorBridgeError("Không lưu được IPT trước khi tạo backup: " + str(exc)) from exc
    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = source.with_name(source.stem + "_Before_PDF2Inventor_V06_" + stamp + source.suffix)
    try:
        shutil.copy2(source, backup)
    except Exception as exc:
        raise InventorBridgeError("Không tạo được bản sao dự phòng: " + str(exc)) from exc

    transaction = None
    save_attempted = False
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(
            document, "PDF2Inventor V0.6 - Profile Extrude"
        )
        component = document.ComponentDefinition
        parameters = component.Parameters
        user_parameters = parameters.UserParameters
        thickness_name = _unique_parameter_name(
            parameters, cfg["parameter_names"]["thickness"]
        )
        user_parameters.AddByExpression(
            thickness_name, str(cfg["thickness"]) + " mm", "mm"
        )

        sketch = component.Sketches.Add(component.WorkPlanes.Item(3))
        geometry = inventor_app.TransientGeometry
        sketch_points = [
            sketch.SketchPoints.Add(
                geometry.CreatePoint2d(x / 10.0, y / 10.0), False
            )
            for x, y in cfg["points"]
        ]
        for index in range(len(sketch_points)):
            sketch.SketchLines.AddByTwoPoints(
                sketch_points[index],
                sketch_points[(index + 1) % len(sketch_points)],
            )
        sketch.GeometricConstraints.AddGround(sketch_points[0])

        hole_parameter_names = []
        for index, hole in enumerate(cfg["holes"], 1):
            center = sketch.SketchPoints.Add(
                geometry.CreatePoint2d(
                    hole["center_x"] / 10.0,
                    hole["center_y"] / 10.0,
                ),
                False,
            )
            circle = sketch.SketchCircles.AddByCenterRadius(
                center, hole["diameter"] / 20.0
            )
            sketch.GeometricConstraints.AddGround(center)
            requested = "Hole" + str(index) + "_Diameter"
            actual = _unique_parameter_name(parameters, requested)
            user_parameters.AddByExpression(
                actual, str(hole["diameter"]) + " mm", "mm"
            )
            diameter_dimension = sketch.DimensionConstraints.AddDiameter(
                circle,
                geometry.CreatePoint2d(
                    (hole["center_x"] + hole["diameter"]) / 10.0,
                    hole["center_y"] / 10.0,
                ),
                False,
            )
            diameter_dimension.Parameter.Expression = actual
            hole_parameter_names.append(actual)

        profile = sketch.Profiles.AddForSolid()
        direction_enum = (
            K_POSITIVE_EXTENT_DIRECTION
            if cfg["direction"] == "positive"
            else K_NEGATIVE_EXTENT_DIRECTION
        )
        extrudes = component.Features.ExtrudeFeatures
        definition = extrudes.CreateExtrudeDefinition(profile, K_NEW_BODY_OPERATION)
        definition.SetDistanceExtent(thickness_name, direction_enum)
        extrude = extrudes.Add(definition)

        try:
            sketch.Name = "P2I_Profile_Sketch"
            extrude.Name = "P2I_Profile_Extrude"
            sketch.Visible = False
        except Exception:
            pass

        document.Update()
        save_attempted = True
        document.Save()
        transaction.End()
        transaction = None

        return {
            "document_path": file_path,
            "backup_path": str(backup),
            "sketch_name": str(getattr(sketch, "Name", "P2I_Profile_Sketch")),
            "feature_name": str(getattr(extrude, "Name", "P2I_Profile_Extrude")),
            "operation": "new_body",
            "direction": cfg["direction"],
            "dimensions_mm": {
                "thickness": cfg["thickness"],
                "points": [
                    {"x": point[0], "y": point[1]} for point in cfg["points"]
                ],
                "holes": cfg["holes"],
            },
            "parameter_names": {
                "thickness": thickness_name,
                "holes": hole_parameter_names,
            },
            "parameters": read_parameters(document),
            "range_box": _range_box_mm(component),
        }
    except Exception as exc:
        rollback_message = ""
        if transaction is not None:
            try:
                transaction.Abort()
                rollback_message = "Đã hủy transaction hình học trong Inventor."
            except Exception as abort_exc:
                rollback_message = "Không xác nhận được rollback transaction: " + str(abort_exc)
        if save_attempted:
            try:
                shutil.copy2(backup, file_path)
                rollback_message += " Đã khôi phục file trên ổ đĩa từ backup; hãy đóng IPT không lưu rồi mở lại."
            except Exception as restore_exc:
                rollback_message += " Không thể khôi phục file tự động: " + str(restore_exc)
        detail = str(exc) if isinstance(exc, InventorBridgeError) else type(exc).__name__ + ": " + str(exc)
        raise InventorBridgeError(
            "Không tạo được Sketch biên dạng/Extrude: " + detail + ". "
            + rollback_message + " Backup: " + str(backup)
        ) from exc
