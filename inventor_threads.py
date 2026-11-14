"""Native Inventor cosmetic/modelled thread feature on an existing cylindrical face."""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters


def validate_thread(command):
    if not isinstance(command,dict) or command.get("op")!="create_thread":
        raise InventorBridgeError("Lệnh phải dùng op='create_thread'.")
    if command.get("unit")!="mm":
        raise InventorBridgeError("Thread bắt buộc unit='mm'.")
    for key in ("face_index","start_edge_index"):
        v=command.get(key)
        if isinstance(v,bool) or not isinstance(v,int) or v<1:
            raise InventorBridgeError(f"{key} phải là số nguyên dương theo thứ tự hiện tại.")
    designation=command.get("designation")
    thread_type=command.get("thread_type","ISO Metric Profile")
    thread_class=command.get("thread_class","6H")
    if not isinstance(designation,str) or not designation.strip():
        raise InventorBridgeError("designation phải là chuỗi ren hợp lệ, ví dụ M8x1.25.")
    if not isinstance(thread_type,str) or not thread_type.strip():
        raise InventorBridgeError("thread_type không được để trống.")
    if not isinstance(thread_class,str) or not thread_class.strip():
        raise InventorBridgeError("thread_class không được để trống.")
    internal=command.get("internal",True)
    right_handed=command.get("right_handed",True)
    full_depth=command.get("full_depth",True)
    if not all(isinstance(v,bool) for v in (internal,right_handed,full_depth)):
        raise InventorBridgeError("internal, right_handed và full_depth phải là boolean.")
    depth=command.get("depth_mm")
    if not full_depth and (isinstance(depth,bool) or not isinstance(depth,(int,float)) or not math.isfinite(float(depth)) or depth<=0):
        raise InventorBridgeError("Ren không hết chiều dài cần depth_mm lớn hơn 0.")
    return {"face_index":command["face_index"],"start_edge_index":command["start_edge_index"],
            "designation":designation.strip(),"thread_type":thread_type.strip(),"thread_class":thread_class.strip(),
            "internal":internal,"right_handed":right_handed,"full_depth":full_depth,
            "depth_mm":float(depth) if not full_depth else None,
            "direction_reversed":bool(command.get("direction_reversed",False))}


def create_thread(document,inventor_app,command):
    cfg=validate_thread(command)
    info=get_document_info(document,inventor_app)
    file_path=info.get("full_path","")
    if not file_path or Path(file_path).suffix.lower()!=".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Cần mở và lưu IPT trước khi tạo ren.")
    document.Save()
    source=Path(file_path)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup=source.with_name(f"{source.stem}_Before_PDF2Inventor_Thread_{stamp}{source.suffix}")
    shutil.copy2(source,backup)
    transaction=None
    try:
        transaction=inventor_app.TransactionManager.StartTransaction(document,"PDF2Inventor Native Thread")
        component=document.ComponentDefinition
        body=component.SurfaceBodies.Item(1)
        if cfg["face_index"]>body.Faces.Count:
            raise InventorBridgeError(f"face_index vượt quá tổng {body.Faces.Count} mặt.")
        face=body.Faces.Item(cfg["face_index"])
        if cfg["start_edge_index"]>face.Edges.Count:
            raise InventorBridgeError(f"start_edge_index vượt quá {face.Edges.Count} cạnh của mặt này.")
        edge=face.Edges.Item(cfg["start_edge_index"])
        threads=component.Features.ThreadFeatures
        thread_info=threads.CreateStandardThreadInfo(
            cfg["internal"],cfg["right_handed"],cfg["thread_type"],cfg["designation"],cfg["thread_class"]
        )
        if cfg["full_depth"]:
            feature=threads.Add(face,edge,thread_info,cfg["direction_reversed"],True)
        else:
            feature=threads.Add(face,edge,thread_info,cfg["direction_reversed"],False,f'{cfg["depth_mm"]:.12g} mm')
        feature.Name=str(command.get("feature_name","P2I_Thread"))
        document.Update()
        document.Save()
        transaction.End()
        transaction=None
        return {"document_path":file_path,"backup_path":str(backup),"feature_name":str(feature.Name),
                "designation":cfg["designation"],"internal":cfg["internal"],"parameters":read_parameters(document)}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được ren {cfg['designation']}: {type(exc).__name__}: {exc}. Backup: {backup}") from exc
