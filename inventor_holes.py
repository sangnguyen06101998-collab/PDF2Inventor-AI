"""Native Inventor Hole feature from explicitly dimensioned sketch points."""
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from inventor_bridge import InventorBridgeError, get_document_info, read_parameters

PLANE_IDS={"YZ":1,"XZ":2,"XY":3}
DIRECTIONS={"positive":20993,"negative":20994}


def validate_hole_command(command):
    if not isinstance(command,dict) or command.get("op")!="create_hole":
        raise InventorBridgeError("Lệnh phải dùng op='create_hole'.")
    if command.get("unit")!="mm":
        raise InventorBridgeError("Hole bắt buộc khai báo unit='mm'.")
    plane=str(command.get("plane","XY")).upper()
    if plane not in PLANE_IDS: raise InventorBridgeError("plane chỉ nhận XY, XZ hoặc YZ.")
    offset=command.get("offset_mm",0)
    diameter=command.get("diameter")
    if isinstance(offset,bool) or not isinstance(offset,(int,float)) or not math.isfinite(float(offset)):
        raise InventorBridgeError("offset_mm phải là số hữu hạn.")
    if isinstance(diameter,bool) or not isinstance(diameter,(int,float)) or not math.isfinite(float(diameter)) or diameter<=0:
        raise InventorBridgeError("diameter phải lớn hơn 0.")
    centers=command.get("centers")
    if not isinstance(centers,list) or not centers:
        raise InventorBridgeError("centers phải có ít nhất một tâm lỗ.")
    clean=[]
    for i,p in enumerate(centers,1):
        if not isinstance(p,(list,tuple)) or len(p)!=2:
            raise InventorBridgeError(f"centers[{i}] phải là [x,y].")
        xy=[]
        for v in p:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)):
                raise InventorBridgeError("Tọa độ tâm lỗ phải là số hữu hạn.")
            xy.append(float(v))
        clean.append(xy)
    extent=str(command.get("extent","through_all")).lower()
    if extent not in {"through_all","distance"}:
        raise InventorBridgeError("extent chỉ nhận through_all hoặc distance.")
    depth=command.get("depth_mm")
    if extent=="distance" and (isinstance(depth,bool) or not isinstance(depth,(int,float)) or not math.isfinite(float(depth)) or depth<=0):
        raise InventorBridgeError("depth_mm phải lớn hơn 0 cho lỗ mù.")
    direction=str(command.get("direction","positive")).lower()
    if direction not in DIRECTIONS: raise InventorBridgeError("direction chỉ nhận positive hoặc negative.")
    return {"plane":plane,"offset_mm":float(offset),"diameter":float(diameter),
            "centers":clean,"extent":extent,"depth_mm":float(depth) if extent=="distance" else None,
            "direction":direction,"feature_name":str(command.get("feature_name","P2I_Hole")).strip()}


def create_hole(document,inventor_app,command):
    cfg=validate_hole_command(command)
    info=get_document_info(document,inventor_app)
    file_path=info.get("full_path","")
    if not file_path or Path(file_path).suffix.lower()!=".ipt" or not os.path.isfile(file_path):
        raise InventorBridgeError("Cần mở và lưu IPT trước khi tạo Hole.")
    document.Save()
    source=Path(file_path)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup=source.with_name(f"{source.stem}_Before_PDF2Inventor_Hole_{stamp}{source.suffix}")
    shutil.copy2(source,backup)
    transaction=None
    try:
        transaction=inventor_app.TransactionManager.StartTransaction(document,"PDF2Inventor Native Hole")
        component=document.ComponentDefinition
        base_plane=component.WorkPlanes.Item(PLANE_IDS[cfg["plane"]])
        sketch_plane=base_plane if abs(cfg["offset_mm"])<1e-9 else component.WorkPlanes.AddByPlaneAndOffset(base_plane,cfg["offset_mm"]/10.0)
        sketch=component.Sketches.Add(sketch_plane)
        tg=inventor_app.TransientGeometry
        points=inventor_app.TransientObjects.CreateObjectCollection()
        for x,y in cfg["centers"]:
            points.Add(sketch.SketchPoints.Add(tg.CreatePoint2d(x/10.0,y/10.0),False))
        holes=component.Features.HoleFeatures
        placement=holes.CreateSketchPlacementDefinition(points)
        if cfg["extent"]=="through_all":
            feature=holes.AddDrilledByThroughAllExtent(
                placement,f'{cfg["diameter"]:.12g} mm',DIRECTIONS[cfg["direction"]]
            )
        else:
            feature=holes.AddDrilledByDistanceExtent(
                placement,f'{cfg["diameter"]:.12g} mm',f'{cfg["depth_mm"]:.12g} mm',
                DIRECTIONS[cfg["direction"]],True
            )
        feature.Name=cfg["feature_name"] or "P2I_Hole"
        try: sketch.Visible=False
        except Exception: pass
        if abs(cfg["offset_mm"])>=1e-9:
            try: sketch_plane.Visible=False
            except Exception: pass
        document.Update()
        document.Save()
        transaction.End()
        transaction=None
        return {"document_path":file_path,"backup_path":str(backup),
                "feature_name":str(feature.Name),"hole_count":len(cfg["centers"]),
                "diameter_mm":cfg["diameter"],"extent":cfg["extent"],
                "range_box":_range_box(component),"parameters":read_parameters(document)}
    except Exception as exc:
        if transaction is not None:
            try: transaction.Abort()
            except Exception: pass
        raise InventorBridgeError(f"Không tạo được native Hole: {type(exc).__name__}: {exc}. Backup: {backup}") from exc


def _range_box(component):
    try:
        box=component.RangeBox; lo,hi=box.MinPoint,box.MaxPoint
        return {"min_mm":[round(float(lo.X)*10,4),round(float(lo.Y)*10,4),round(float(lo.Z)*10,4)],
                "max_mm":[round(float(hi.X)*10,4),round(float(hi.Y)*10,4),round(float(hi.Z)*10,4)]}
    except Exception: return None
