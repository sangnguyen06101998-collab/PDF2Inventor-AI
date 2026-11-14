"""Create native Inventor IAM assemblies from explicitly positioned IPT files."""
import math
import os
from pathlib import Path

from inventor_bridge import InventorBridgeError


def validate_assembly_command(command):
    if not isinstance(command, dict) or command.get("op") != "create_assembly_iam":
        raise InventorBridgeError("Lệnh phải dùng op='create_assembly_iam'.")
    output = command.get("output_path")
    if not isinstance(output, str) or not output.lower().endswith(".iam"):
        raise InventorBridgeError("output_path phải là đường dẫn file .iam.")
    components = command.get("components")
    if not isinstance(components, list) or not components:
        raise InventorBridgeError("components phải có ít nhất một chi tiết IPT.")
    normalized = []
    for i, item in enumerate(components, 1):
        if not isinstance(item, dict):
            raise InventorBridgeError(f"components[{i}] phải là object.")
        path = item.get("ipt_path")
        if not isinstance(path, str) or not path.lower().endswith(".ipt"):
            raise InventorBridgeError(f"components[{i}] cần ipt_path hợp lệ.")
        pos = item.get("position_mm", [0, 0, 0])
        if not isinstance(pos, list) or len(pos) != 3:
            raise InventorBridgeError(f"components[{i}].position_mm phải là [x,y,z].")
        vals = []
        for value in pos:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise InventorBridgeError("Tọa độ lắp ráp phải là số hữu hạn.")
            vals.append(float(value))
        normalized.append({"ipt_path": path, "position_mm": vals,
                           "occurrence_name": str(item.get("occurrence_name", f"Component_{i}"))})
    return {"output_path": output, "components": normalized}


def create_assembly_iam(inventor_app, command):
    cfg = validate_assembly_command(command)
    output = Path(cfg["output_path"]).expanduser()
    if not output.parent.is_dir():
        raise InventorBridgeError("Thư mục lưu IAM không tồn tại.")
    for item in cfg["components"]:
        if not os.path.isfile(item["ipt_path"]):
            raise InventorBridgeError("Không tìm thấy IPT: " + item["ipt_path"])
    if output.exists():
        raise InventorBridgeError("File IAM đích đã tồn tại; hãy chọn tên file mới để không ghi đè.")
    assembly = None
    try:
        assembly = inventor_app.Documents.Add(12291, "", True)
        definition = assembly.ComponentDefinition
        geometry = inventor_app.TransientGeometry
        for item in cfg["components"]:
            matrix = geometry.CreateMatrix()
            vector = geometry.CreateVector(
                item["position_mm"][0] / 10.0,
                item["position_mm"][1] / 10.0,
                item["position_mm"][2] / 10.0
            )
            matrix.SetTranslation(vector, False)
            occurrence = definition.Occurrences.Add(item["ipt_path"], matrix)
            try:
                occurrence.Name = item["occurrence_name"]
            except Exception:
                pass
        assembly.Update()
        assembly.SaveAs(str(output), False)
        return {"assembly_path": str(output), "occurrence_count": len(cfg["components"]),
                "components": cfg["components"]}
    except Exception as exc:
        try:
            if assembly is not None:
                assembly.Close(True)
        except Exception:
            pass
        raise InventorBridgeError(f"Không tạo được IAM: {type(exc).__name__}: {exc}") from exc
