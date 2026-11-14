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
    if operation not in {"auto", "join", "new_body"}:
        raise InventorBridgeError("operation chỉ nhận 'auto', 'join' hoặc 'new_body'.")

    parameter_names = command.get("parameter_names") or {}
    if not isinstance(parameter_names, dict):
        raise InventorBridgeError("parameter_names phải là một đối tượng JSON.")
    names = {}
    for key, default in (
        ("length", "P2I_Length"),
        ("width", "P2I_Width"),
        ("thickness", "P2I_Thickness"),
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
            operation = "join" if body_count > 0 else "new_body"
        if operation == "join" and body_count == 0:
            raise InventorBridgeError(
                "operation='join' nhưng IPT chưa có solid body. Hãy dùng operation='new_body' hoặc 'auto'."
            )
        operation_enum = K_JOIN_OPERATION if operation == "join" else K_NEW_BODY_OPERATION
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
