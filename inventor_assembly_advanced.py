"""Native IAM Mate, Flush, Insert constraints and interference checking."""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InventorBridgeError(f"{label} phải là số hữu hạn.")
    return float(value)


def _entity(value, label):
    if not isinstance(value, dict):
        raise InventorBridgeError(f"{label} phải là object.")
    occurrence = value.get("occurrence")
    kind = str(value.get("kind", "")).lower()
    if not isinstance(occurrence, str) or not occurrence.strip():
        raise InventorBridgeError(f"{label}.occurrence phải là tên ComponentOccurrence.")
    if kind not in {"face", "edge", "work_plane", "work_axis"}:
        raise InventorBridgeError(f"{label}.kind chỉ nhận face, edge, work_plane hoặc work_axis.")
    index = value.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise InventorBridgeError(f"{label}.index phải là số nguyên dương 1-based.")
    return {"occurrence": occurrence.strip(), "kind": kind, "index": index}


def validate_assembly_constraints(command):
    if not isinstance(command, dict) or command.get("op") != "create_assembly_constraints":
        raise InventorBridgeError("Lệnh phải dùng op='create_assembly_constraints'.")
    constraints = command.get("constraints")
    if not isinstance(constraints, list) or not constraints:
        raise InventorBridgeError("constraints phải có ít nhất một ràng buộc.")
    clean = []
    for i, item in enumerate(constraints, 1):
        if not isinstance(item, dict):
            raise InventorBridgeError(f"constraints[{i}] phải là object.")
        kind = str(item.get("type", "")).lower()
        if kind not in {"mate", "flush", "insert"}:
            raise InventorBridgeError("type chỉ nhận mate, flush hoặc insert.")
        one = _entity(item.get("entity_one"), f"constraints[{i}].entity_one")
        two = _entity(item.get("entity_two"), f"constraints[{i}].entity_two")
        if one["occurrence"] == two["occurrence"]:
            raise InventorBridgeError("Hai entity của cùng một constraint phải thuộc hai occurrence khác nhau.")
        offset = _number(item.get("offset_mm", 0), "offset_mm")
        if kind in {"mate", "flush"} and (one["kind"] not in {"face", "work_plane"} or two["kind"] not in {"face", "work_plane"}):
            raise InventorBridgeError(f"{kind} chỉ nhận planar face hoặc work_plane.")
        if kind == "insert" and (one["kind"] != "edge" or two["kind"] != "edge"):
            raise InventorBridgeError("insert cần hai circular edge; index phải được xác nhận trên đúng chi tiết.")
        clean.append({"type": kind, "entity_one": one, "entity_two": two,
                      "offset_mm": offset, "axes_opposed": bool(item.get("axes_opposed", False)),
                      "name": str(item.get("name", f"P2I_{kind.title()}_{i}"))})
    return {"constraints": clean}


def validate_interference(command):
    if not isinstance(command, dict) or command.get("op") != "analyze_assembly_interference":
        raise InventorBridgeError("Lệnh phải dùng op='analyze_assembly_interference'.")
    names = command.get("occurrence_names", [])
    if not isinstance(names, list) or any(not isinstance(n, str) or not n.strip() for n in names):
        raise InventorBridgeError("occurrence_names phải là danh sách tên occurrence.")
    if len(set(names)) != len(names):
        raise InventorBridgeError("occurrence_names không được trùng.")
    return {"occurrence_names": [n.strip() for n in names]}


def _require_iam(document, inventor_app=None):
    info = get_document_info(document, inventor_app)
    path = info.get("full_path", "")
    if not path or Path(path).suffix.lower() != ".iam" or not os.path.isfile(path):
        raise InventorBridgeError("Hãy mở và lưu một file IAM trước khi thao tác lắp ráp.")
    return path


def _occurrence(component, name):
    for i in range(1, int(component.Occurrences.Count)+1):
        item = component.Occurrences.Item(i)
        if str(item.Name) == name:
            return item
    raise InventorBridgeError("Không tìm thấy occurrence có tên chính xác: " + name)


def _native_entity(occurrence, spec):
    component = occurrence.Definition
    kind, index = spec["kind"], spec["index"]
    if kind == "face":
        body = component.SurfaceBodies.Item(1)
        if index > int(body.Faces.Count):
            raise InventorBridgeError(f"Face index {index} vượt quá giới hạn của {occurrence.Name}.")
        native = body.Faces.Item(index)
    elif kind == "edge":
        body = component.SurfaceBodies.Item(1)
        if index > int(body.Edges.Count):
            raise InventorBridgeError(f"Edge index {index} vượt quá giới hạn của {occurrence.Name}.")
        native = body.Edges.Item(index)
    elif kind == "work_plane":
        if index > int(component.WorkPlanes.Count):
            raise InventorBridgeError(f"WorkPlane index {index} vượt quá giới hạn của {occurrence.Name}.")
        native = component.WorkPlanes.Item(index)
    else:
        if index > int(component.WorkAxes.Count):
            raise InventorBridgeError(f"WorkAxis index {index} vượt quá giới hạn của {occurrence.Name}.")
        native = component.WorkAxes.Item(index)
    proxy = occurrence.CreateGeometryProxy(native)
    if isinstance(proxy, tuple):
        proxy = proxy[-1]
    if proxy is None:
        raise InventorBridgeError("Inventor không tạo được geometry proxy cho " + occurrence.Name)
    return proxy


def create_assembly_constraints(document, inventor_app, command):
    cfg = validate_assembly_constraints(command)
    path = _require_iam(document, inventor_app)
    document.Save()
    source = Path(path)
    backup = source.with_name(source.stem + "_Before_P2I_AssemblyConstraints_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + source.suffix)
    shutil.copy2(source, backup)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(document, "PDF2Inventor Assembly Constraints")
        component = document.ComponentDefinition
        results = []
        for item in cfg["constraints"]:
            occurrence_one = _occurrence(component, item["entity_one"]["occurrence"])
            occurrence_two = _occurrence(component, item["entity_two"]["occurrence"])
            entity_one = _native_entity(occurrence_one, item["entity_one"])
            entity_two = _native_entity(occurrence_two, item["entity_two"])
            if item["type"] == "insert":
                for occurrence, spec in ((occurrence_one, item["entity_one"]), (occurrence_two, item["entity_two"])):
                    native_edge = occurrence.Definition.SurfaceBodies.Item(1).Edges.Item(spec["index"])
                    try:
                        radius = float(native_edge.Geometry.Radius)
                    except Exception as exc:
                        raise InventorBridgeError(f"Insert yêu cầu cạnh tròn; cạnh {spec['index']} của {occurrence.Name} không phải cung tròn.") from exc
                    if not math.isfinite(radius) or radius <= 0:
                        raise InventorBridgeError(f"Insert yêu cầu bán kính hợp lệ tại {occurrence.Name}, cạnh {spec['index']}.")
            offset = f'{item["offset_mm"]:.12g} mm'
            if item["type"] == "mate":
                constraint = component.Constraints.AddMateConstraint(entity_one, entity_two, offset)
            elif item["type"] == "flush":
                constraint = component.Constraints.AddFlushConstraint(entity_one, entity_two, offset)
            else:
                constraint = component.Constraints.AddInsertConstraint(
                    entity_one, entity_two, item["axes_opposed"], offset)
            try:
                constraint.Name = item["name"]
            except Exception:
                pass
            results.append({"type": item["type"], "name": str(getattr(constraint, "Name", item["name"])),
                            "occurrence_one": occurrence_one.Name, "occurrence_two": occurrence_two.Name})
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        return {"document_path": path, "backup_path": str(backup), "constraints_added": len(results),
                "constraints": results}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được ràng buộc IAM: {type(exc).__name__}: {exc}. Backup: {backup}") from exc


def analyze_assembly_interference(document, inventor_app, command):
    cfg = validate_interference(command)
    _require_iam(document, inventor_app)
    component = document.ComponentDefinition
    selected = cfg["occurrence_names"]
    occurrences = []
    if selected:
        occurrences = [_occurrence(component, name) for name in selected]
    else:
        occurrences = [component.Occurrences.Item(i) for i in range(1, int(component.Occurrences.Count)+1)]
    if len(occurrences) < 2:
        raise InventorBridgeError("Cần ít nhất hai occurrence để kiểm tra va chạm.")
    collection = inventor_app.TransientObjects.CreateObjectCollection()
    for occurrence in occurrences:
        collection.Add(occurrence)
    results = component.AnalyzeInterference(collection)
    overlaps = []
    for i in range(1, int(results.Count)+1):
        result = results.Item(i)
        volume_cm3 = float(result.Volume)
        overlaps.append({
            "occurrence_one": str(result.OccurrenceOne.Name),
            "occurrence_two": str(result.OccurrenceTwo.Name),
            "interference_volume_mm3": round(volume_cm3 * 1000.0, 6)
        })
    return {"document_path": str(document.FullFileName), "checked_occurrences": [str(o.Name) for o in occurrences],
            "interference_count": len(overlaps), "interferences": overlaps}
