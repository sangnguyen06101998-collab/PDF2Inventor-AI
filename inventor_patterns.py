"""Native Inventor 2018 circular and rectangular feature patterns."""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters

K_IDENTICAL_PATTERN_COMPUTE = 20481


def validate_pattern(command):
    if not isinstance(command, dict) or command.get("op") not in {"create_circular_pattern", "create_rectangular_pattern"}:
        raise InventorBridgeError("Lệnh pattern không hợp lệ.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("Pattern bắt buộc unit='mm'.")
    names = command.get("feature_names")
    if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n.strip() for n in names):
        raise InventorBridgeError("feature_names phải là danh sách tên Feature hiện có.")
    if len(set(names)) != len(names):
        raise InventorBridgeError("feature_names không được trùng.")
    axis = command.get("axis_index", 1)
    if isinstance(axis, bool) or not isinstance(axis, int) or axis < 1:
        raise InventorBridgeError("axis_index phải là số nguyên dương trong WorkAxes.")
    result = {"op": command["op"], "feature_names": names, "axis_index": axis, "unit": "mm"}
    if command["op"] == "create_circular_pattern":
        count = command.get("count")
        angle = command.get("angle_deg", 360)
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise InventorBridgeError("count của circular pattern phải >= 2.")
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not math.isfinite(float(angle)) or not 0 < angle <= 360:
            raise InventorBridgeError("angle_deg phải trong khoảng (0, 360].")
        result.update({"count": count, "angle_deg": float(angle),
                       "natural_axis_direction": bool(command.get("natural_axis_direction", True))})
    else:
        for key in ("count_x", "count_y"):
            value = command.get(key, 1)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InventorBridgeError(f"{key} phải là số nguyên >= 1.")
            result[key] = value
        for key in ("spacing_x", "spacing_y"):
            value = command.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise InventorBridgeError(f"{key} phải là số >= 0.")
            result[key] = float(value)
        result["axis_x_index"] = axis
        result["axis_y_index"] = command.get("axis_y_index", 2)
        if isinstance(result["axis_y_index"], bool) or not isinstance(result["axis_y_index"], int) or result["axis_y_index"] < 1:
            raise InventorBridgeError("axis_y_index phải là số nguyên dương.")
        if result["count_x"] == 1 and result["count_y"] == 1:
            raise InventorBridgeError("Rectangular pattern cần count_x hoặc count_y lớn hơn 1.")
    return result


def create_pattern(document, inventor_app, command):
    cfg = validate_pattern(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Pattern chỉ chạy trên IPT đã lưu.")
    document.Save()
    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = source.with_name(f"{source.stem}_Before_PDF2Inventor_Pattern_{stamp}{source.suffix}")
    shutil.copy2(source, backup)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(document, "PDF2Inventor Pattern")
        component = document.ComponentDefinition
        objects = inventor_app.TransientObjects.CreateObjectCollection()
        for name in cfg["feature_names"]:
            try:
                objects.Add(component.Features.Item(name))
            except Exception as exc:
                raise InventorBridgeError(f"Không tìm thấy Feature '{name}' trong IPT.") from exc
        if cfg["op"] == "create_circular_pattern":
            axis = component.WorkAxes.Item(cfg["axis_index"])
            patterns = component.Features.CircularPatternFeatures
            definition = patterns.CreateDefinition(
                objects, axis, cfg["natural_axis_direction"], cfg["count"],
                inventor_app.TransientGeometry.CreateAngle(cfg["angle_deg"] * math.pi / 180.0),
                True, K_IDENTICAL_PATTERN_COMPUTE
            )
        else:
            axis_x = component.WorkAxes.Item(cfg["axis_x_index"])
            axis_y = component.WorkAxes.Item(cfg["axis_y_index"])
            patterns = component.Features.RectangularPatternFeatures
            definition = patterns.CreateDefinition(
                objects, axis_x, True, cfg["count_x"],
                f'{cfg["spacing_x"]:.12g} mm',
                axis_y, True, cfg["count_y"],
                f'{cfg["spacing_y"]:.12g} mm',
                K_IDENTICAL_PATTERN_COMPUTE
            )
        feature = patterns.Add(definition)
        feature.Name = "P2I_CircularPattern" if cfg["op"] == "create_circular_pattern" else "P2I_RectangularPattern"
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        return {"document_path": file_path, "backup_path": str(backup),
                "feature_name": str(feature.Name), "pattern_type": cfg["op"],
                "range_box": _range_box(component), "parameters": read_parameters(document)}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được pattern: {type(exc).__name__}: {exc}. Backup: {backup}") from exc


def _range_box(component):
    try:
        box=component.RangeBox; lo,hi=box.MinPoint,box.MaxPoint
        return {"min_mm":[round(float(lo.X)*10,4),round(float(lo.Y)*10,4),round(float(lo.Z)*10,4)],
                "max_mm":[round(float(hi.X)*10,4),round(float(hi.Y)*10,4),round(float(hi.Z)*10,4)]}
    except Exception: return None
