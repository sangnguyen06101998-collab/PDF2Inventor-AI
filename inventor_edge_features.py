"""Native edge finishing features for Inventor 2018.

Edge indices are 1-based indices in the current body's Edges collection. They
must be selected against the exact current IPT revision; never reuse them after
topology-changing features without re-inspection.
"""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters


def validate_edge_finish(command):
    if not isinstance(command, dict) or command.get("op") not in {"create_fillet", "create_chamfer"}:
        raise InventorBridgeError("Lệnh phải là create_fillet hoặc create_chamfer.")
    if command.get("unit") != "mm":
        raise InventorBridgeError("Bắt buộc khai báo unit='mm'.")
    indices = command.get("edge_indices")
    if not isinstance(indices, list) or not indices:
        raise InventorBridgeError("edge_indices phải là danh sách cạnh 1-based không rỗng.")
    clean = []
    for value in indices:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InventorBridgeError("Mỗi edge_index phải là số nguyên dương, bắt đầu từ 1.")
        if value in clean:
            raise InventorBridgeError("edge_indices không được chứa phần tử trùng.")
        clean.append(value)
    field = "radius" if command["op"] == "create_fillet" else "distance"
    value = command.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
        raise InventorBridgeError(f"{field} phải là số hữu hạn lớn hơn 0.")
    return {"op": command["op"], "edge_indices": clean, field: float(value), "unit": "mm"}


def create_edge_finish(document, inventor_app, command):
    cfg = validate_edge_finish(command)
    info = get_document_info(document, inventor_app)
    file_path = info.get("full_path", "")
    if not file_path or Path(file_path).suffix.lower() != ".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Cần mở và lưu file IPT trước khi bo/vát cạnh.")
    document.Save()
    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = source.with_name(f"{source.stem}_Before_PDF2Inventor_Edge_{stamp}{source.suffix}")
    shutil.copy2(source, backup)
    transaction = None
    try:
        transaction = inventor_app.TransactionManager.StartTransaction(document, "PDF2Inventor Edge Finish")
        component = document.ComponentDefinition
        if component.SurfaceBodies.Count < 1:
            raise InventorBridgeError("IPT chưa có solid body.")
        body = component.SurfaceBodies.Item(1)
        edge_set = inventor_app.TransientObjects.CreateObjectCollection()
        for index in cfg["edge_indices"]:
            if index > body.Edges.Count:
                raise InventorBridgeError(f"Cạnh số {index} vượt quá tổng {body.Edges.Count} cạnh hiện tại.")
            edge_set.Add(body.Edges.Item(index))
        if cfg["op"] == "create_fillet":
            definitions = component.Features.FilletFeatures
            definition = definitions.CreateFilletDefinition()
            definition.AddConstantRadiusEdgeSet(edge_set, cfg["radius"] / 10.0, True)
            feature = definitions.Add(definition)
        else:
            definitions = component.Features.ChamferFeatures
            definition = definitions.CreateChamferDefinition()
            definition.AddUsingDistance(edge_set, cfg["distance"] / 10.0, True)
            feature = definitions.Add(definition)
        feature.Name = "P2I_Fillet" if cfg["op"] == "create_fillet" else "P2I_Chamfer"
        document.Update()
        document.Save()
        transaction.End()
        transaction = None
        return {"document_path": file_path, "backup_path": str(backup),
                "feature_name": str(feature.Name), "edge_indices": cfg["edge_indices"],
                "size_mm": cfg.get("radius", cfg.get("distance")),
                "range_box": _range_box(component), "parameters": read_parameters(document)}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(
            f"Không tạo được {cfg['op']} trên các cạnh {cfg['edge_indices']}: {type(exc).__name__}: {exc}. Backup: {backup}"
        ) from exc


def _range_box(component):
    try:
        box = component.RangeBox
        lo, hi = box.MinPoint, box.MaxPoint
        return {"min_mm":[round(float(lo.X)*10,4),round(float(lo.Y)*10,4),round(float(lo.Z)*10,4)],
                "max_mm":[round(float(hi.X)*10,4),round(float(hi.Y)*10,4),round(float(hi.Z)*10,4)]}
    except Exception:
        return None
