"""Additional Inventor 2018 native features: spline profile, sweep, loft, shell and mirror.

Sweep and Loft consume explicitly named sketches already present in the IPT.
This avoids guessing profile/path correspondence from a 2D drawing.
"""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters

PLANE_IDS = {"YZ": 1, "XZ": 2, "XY": 3}
OPERATIONS = {"join": 20481, "cut": 20482, "intersect": 20483, "surface": 20484, "new_body": 20485}
DIRECTIONS = {"positive": 20993, "negative": 20994}
SHELL_DIRECTIONS = {"inside": 41217, "outside": 41218, "both_sides": 41219}
SWEEP_PATH_TYPE = 104449


def _num(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InventorBridgeError(f"{label} phải là số hữu hạn.")
    return float(value)


def _feature_name(value, default):
    name = str(value or default).strip()
    if not name or len(name) > 120:
        raise InventorBridgeError("feature_name phải có 1–120 ký tự.")
    return name


def _index(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InventorBridgeError(f"{label} phải là số nguyên dương 1-based.")
    return value


def validate_spline_profile(command):
    if command.get("unit") != "mm":
        raise InventorBridgeError("Spline profile bắt buộc unit='mm'.")
    plane = str(command.get("plane", "XY")).upper()
    if plane not in PLANE_IDS:
        raise InventorBridgeError("plane chỉ nhận XY, XZ hoặc YZ.")
    loops = command.get("loops")
    if not isinstance(loops, list) or not loops:
        raise InventorBridgeError("loops phải có ít nhất một spline kín.")
    clean = []
    for li, loop in enumerate(loops, 1):
        if not isinstance(loop, dict) or loop.get("type") != "spline":
            raise InventorBridgeError(f"loops[{li}] phải có type='spline'.")
        points = loop.get("control_points")
        if not isinstance(points, list) or len(points) < 4:
            raise InventorBridgeError(f"Spline {li} cần ít nhất 4 control_points, gồm điểm đóng.")
        out = []
        for p in points:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise InventorBridgeError("Mỗi control point phải có dạng [x,y] mm.")
            out.append([_num(p[0], "control.x"), _num(p[1], "control.y")])
        if math.dist(out[0], out[-1]) > 0.01:
            raise InventorBridgeError(f"Spline {li} phải lặp lại điểm đầu ở cuối để đóng kín.")
        if len(set((p[0], p[1]) for p in out[:-1])) < 3:
            raise InventorBridgeError(f"Spline {li} cần ít nhất 3 điểm điều khiển phân biệt.")
        clean.append({"type": "spline", "control_points": out})
    distance = _num(command.get("distance"), "distance")
    if distance <= 0:
        raise InventorBridgeError("distance phải lớn hơn 0.")
    operation = str(command.get("operation", "new_body")).lower()
    direction = str(command.get("direction", "positive")).lower()
    if operation not in OPERATIONS or direction not in DIRECTIONS:
        raise InventorBridgeError("operation hoặc direction không hợp lệ.")
    return {"plane": plane, "offset_mm": _num(command.get("offset_mm", 0), "offset_mm"),
            "loops": clean, "distance": distance, "operation": operation,
            "direction": direction, "feature_name": _feature_name(command.get("feature_name"), "P2I_Spline_Extrude")}


def validate_sweep(command):
    if command.get("unit") != "mm":
        raise InventorBridgeError("Sweep bắt buộc unit='mm'.")
    for key in ("profile_sketch_name", "path_sketch_name"):
        if not isinstance(command.get(key), str) or not command[key].strip():
            raise InventorBridgeError(f"{key} phải là tên Sketch hiện có.")
    curve_type = str(command.get("path_curve_type", "line")).lower()
    if curve_type not in {"line", "arc", "spline"}:
        raise InventorBridgeError("path_curve_type chỉ nhận line, arc hoặc spline.")
    index = _index(command.get("path_curve_index", 1), "path_curve_index")
    operation = str(command.get("operation", "new_body")).lower()
    if operation not in OPERATIONS:
        raise InventorBridgeError("operation không hợp lệ.")
    return {"profile_sketch_name": command["profile_sketch_name"].strip(),
            "path_sketch_name": command["path_sketch_name"].strip(),
            "path_curve_type": curve_type, "path_curve_index": index,
            "operation": operation,
            "feature_name": _feature_name(command.get("feature_name"), "P2I_Sweep")}


def validate_loft(command):
    if command.get("unit") != "mm":
        raise InventorBridgeError("Loft bắt buộc unit='mm'.")
    names = command.get("section_sketch_names")
    if not isinstance(names, list) or len(names) < 2 or any(not isinstance(n, str) or not n.strip() for n in names):
        raise InventorBridgeError("section_sketch_names cần ít nhất hai tên Sketch mặt cắt theo đúng thứ tự.")
    if len(set(names)) != len(names):
        raise InventorBridgeError("section_sketch_names không được trùng.")
    operation = str(command.get("operation", "new_body")).lower()
    if operation not in OPERATIONS:
        raise InventorBridgeError("operation không hợp lệ.")
    return {"section_sketch_names": [n.strip() for n in names], "operation": operation,
            "merge_tangent_faces": bool(command.get("merge_tangent_faces", True)),
            "feature_name": _feature_name(command.get("feature_name"), "P2I_Loft")}


def validate_shell(command):
    if command.get("unit") != "mm":
        raise InventorBridgeError("Shell bắt buộc unit='mm'.")
    thickness = _num(command.get("thickness_mm"), "thickness_mm")
    if thickness <= 0:
        raise InventorBridgeError("thickness_mm phải lớn hơn 0.")
    direction = str(command.get("direction", "inside")).lower()
    if direction not in SHELL_DIRECTIONS:
        raise InventorBridgeError("direction chỉ nhận inside, outside hoặc both_sides.")
    indices = command.get("remove_face_indices", [])
    if not isinstance(indices, list):
        raise InventorBridgeError("remove_face_indices phải là danh sách.")
    clean = sorted(set(_index(v, "face index") for v in indices))
    return {"thickness_mm": thickness, "direction": direction,
            "remove_face_indices": clean,
            "feature_name": _feature_name(command.get("feature_name"), "P2I_Shell")}


def validate_mirror(command):
    if command.get("unit") != "mm":
        raise InventorBridgeError("Mirror bắt buộc unit='mm'.")
    names = command.get("feature_names")
    if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n.strip() for n in names):
        raise InventorBridgeError("feature_names phải là danh sách Feature có sẵn.")
    if len(set(names)) != len(names):
        raise InventorBridgeError("feature_names không được trùng.")
    return {"feature_names": [n.strip() for n in names],
            "work_plane_index": _index(command.get("work_plane_index"), "work_plane_index"),
            "feature_name": _feature_name(command.get("feature_name"), "P2I_Mirror")}


def _document_backup(document, inventor_app, operation_name):
    info = get_document_info(document, inventor_app)
    path = info.get("full_path", "")
    if not path or Path(path).suffix.lower() != ".ipt" or not os.path.isfile(path):
        raise InventorBridgeError("Cần mở và lưu file IPT trước khi tạo Feature.")
    document.Save()
    source = Path(path)
    backup = source.with_name(source.stem + "_Before_P2I_" + operation_name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + source.suffix)
    shutil.copy2(source, backup)
    return path, backup


def _run(document, inventor_app, label, operation):
    path, backup = _document_backup(document, inventor_app, label)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(document, "PDF2Inventor " + label)
        result = operation(document.ComponentDefinition)
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        result.update({"document_path": path, "backup_path": str(backup),
                       "parameters": read_parameters(document)})
        return result
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được {label}: {type(exc).__name__}: {exc}. Backup: {backup}") from exc


def create_spline_profile_extrude(document, inventor_app, command):
    cfg = validate_spline_profile(command)
    def build(component):
        plane = component.WorkPlanes.Item(PLANE_IDS[cfg["plane"]])
        sketch_plane = plane if abs(cfg["offset_mm"]) < 1e-9 else component.WorkPlanes.AddByPlaneAndOffset(plane, cfg["offset_mm"]/10.0)
        sketch = component.Sketches.Add(sketch_plane)
        tg = inventor_app.TransientGeometry
        for loop in cfg["loops"]:
            collection = inventor_app.TransientObjects.CreateObjectCollection()
            for p in loop["control_points"]:
                collection.Add(tg.CreatePoint2d(p[0]/10.0, p[1]/10.0))
            sketch.SketchControlPointSplines.Add(collection)
        profile = sketch.Profiles.AddForSolid()
        definition = component.Features.ExtrudeFeatures.CreateExtrudeDefinition(profile, OPERATIONS[cfg["operation"]])
        definition.SetDistanceExtent(f'{cfg["distance"]:.12g} mm', DIRECTIONS[cfg["direction"]])
        feature = component.Features.ExtrudeFeatures.Add(definition)
        sketch.Visible = False
        sketch.Name = "P2I_Spline_Profile_Sketch"
        feature.Name = cfg["feature_name"]
        return {"feature_name": str(feature.Name), "sketch_name": str(sketch.Name),
                "loop_count": len(cfg["loops"]), "distance_mm": cfg["distance"],
                "operation": cfg["operation"]}
    return _run(document, inventor_app, "Spline_Extrude", build)


def _sketch_curve(sketch, curve_type, index):
    collection = {"line": sketch.SketchLines, "arc": sketch.SketchArcs,
                  "spline": sketch.SketchSplines}[curve_type]
    if index > int(collection.Count):
        raise InventorBridgeError(f"Sketch path không có {curve_type} index {index}.")
    return collection.Item(index)


def create_sweep(document, inventor_app, command):
    cfg = validate_sweep(command)
    def build(component):
        profile_sketch = component.Sketches.Item(cfg["profile_sketch_name"])
        path_sketch = component.Sketches.Item(cfg["path_sketch_name"])
        profile = profile_sketch.Profiles.AddForSolid()
        curve = _sketch_curve(path_sketch, cfg["path_curve_type"], cfg["path_curve_index"])
        path = component.Features.CreatePath(curve)
        definition = component.Features.SweepFeatures.CreateSweepDefinition(
            SWEEP_PATH_TYPE, profile, path, OPERATIONS[cfg["operation"]])
        feature = component.Features.SweepFeatures.Add(definition)
        feature.Name = cfg["feature_name"]
        return {"feature_name": str(feature.Name), "profile_sketch": cfg["profile_sketch_name"],
                "path_sketch": cfg["path_sketch_name"], "operation": cfg["operation"]}
    return _run(document, inventor_app, "Sweep", build)


def create_loft(document, inventor_app, command):
    cfg = validate_loft(command)
    def build(component):
        sections = inventor_app.TransientObjects.CreateObjectCollection()
        for name in cfg["section_sketch_names"]:
            sketch = component.Sketches.Item(name)
            sections.Add(sketch.Profiles.AddForSolid())
        definition = component.Features.LoftFeatures.CreateLoftDefinition(sections, OPERATIONS[cfg["operation"]])
        definition.MergeTangentFaces = cfg["merge_tangent_faces"]
        feature = component.Features.LoftFeatures.Add(definition)
        feature.Name = cfg["feature_name"]
        return {"feature_name": str(feature.Name), "section_sketch_names": cfg["section_sketch_names"],
                "operation": cfg["operation"]}
    return _run(document, inventor_app, "Loft", build)


def create_shell(document, inventor_app, command):
    cfg = validate_shell(command)
    def build(component):
        face_collection = inventor_app.TransientObjects.CreateFaceCollection()
        bodies = component.SurfaceBodies
        if int(bodies.Count) < 1:
            raise InventorBridgeError("IPT không có SurfaceBody để tạo Shell.")
        body = bodies.Item(1)
        for index in cfg["remove_face_indices"]:
            if index > int(body.Faces.Count):
                raise InventorBridgeError(f"Face index {index} vượt quá số mặt hiện có ({body.Faces.Count}).")
            face_collection.Add(body.Faces.Item(index))
        definition = component.Features.ShellFeatures.CreateShellDefinition(
            face_collection, f'{cfg["thickness_mm"]:.12g} mm', SHELL_DIRECTIONS[cfg["direction"]])
        feature = component.Features.ShellFeatures.Add(definition)
        feature.Name = cfg["feature_name"]
        return {"feature_name": str(feature.Name), "thickness_mm": cfg["thickness_mm"],
                "removed_face_indices": cfg["remove_face_indices"], "direction": cfg["direction"]}
    return _run(document, inventor_app, "Shell", build)


def _find_feature(component, name):
    for i in range(1, int(component.Features.Count)+1):
        feature = component.Features.Item(i)
        if str(getattr(feature, "Name", "")) == name:
            return feature
    raise InventorBridgeError("Không tìm thấy Feature có tên chính xác: " + name)


def create_mirror(document, inventor_app, command):
    cfg = validate_mirror(command)
    def build(component):
        parents = inventor_app.TransientObjects.CreateObjectCollection()
        for name in cfg["feature_names"]:
            parents.Add(_find_feature(component, name))
        plane = component.WorkPlanes.Item(cfg["work_plane_index"])
        definition = component.Features.MirrorFeatures.CreateDefinition(parents, plane, 47363)
        feature = component.Features.MirrorFeatures.AddByDefinition(definition)
        feature.Name = cfg["feature_name"]
        return {"feature_name": str(feature.Name), "mirrored_features": cfg["feature_names"],
                "work_plane_index": cfg["work_plane_index"]}
    return _run(document, inventor_app, "Mirror", build)


ADVANCED_PART_OPS = {
    "create_spline_profile_extrude", "create_sweep", "create_loft",
    "create_shell", "create_mirror"
}


def validate_advanced_part(command):
    if not isinstance(command, dict):
        raise InventorBridgeError("Command phải là object.")
    op = command.get("op")
    validators = {
        "create_spline_profile_extrude": validate_spline_profile,
        "create_sweep": validate_sweep,
        "create_loft": validate_loft,
        "create_shell": validate_shell,
        "create_mirror": validate_mirror,
    }
    if op not in validators:
        raise InventorBridgeError("Advanced part operation không được hỗ trợ: " + str(op))
    return validators[op](command)


def create_advanced_part(document, inventor_app, command):
    op = command.get("op")
    functions = {
        "create_spline_profile_extrude": create_spline_profile_extrude,
        "create_sweep": create_sweep,
        "create_loft": create_loft,
        "create_shell": create_shell,
        "create_mirror": create_mirror,
    }
    if op not in functions:
        raise InventorBridgeError("Advanced part operation không được hỗ trợ: " + str(op))
    return functions[op](document, inventor_app, command)
