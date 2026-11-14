"""Read-only Inventor B-rep topology inventory for stable edge/face selection."""
def inspect_topology(document):
    component=document.ComponentDefinition
    result={"bodies":[],"features":[]}
    try:
        for fi in range(1,int(component.Features.Count)+1):
            feature=component.Features.Item(fi)
            result["features"].append({"feature_index":fi,"name":str(feature.Name),"type":str(getattr(feature,"Type","unknown"))})
    except Exception:
        pass
    for bi in range(1,int(component.SurfaceBodies.Count)+1):
        body=component.SurfaceBodies.Item(bi)
        faces=[]
        for fi in range(1,int(body.Faces.Count)+1):
            face=body.Faces.Item(fi)
            surface_type=str(getattr(face,"SurfaceType","unknown"))
            entry={"face_index":fi,"surface_type":surface_type,"edge_count":int(face.Edges.Count)}
            try:
                entry["radius_mm"]=round(float(face.Geometry.Radius)*10,4)
            except Exception:
                pass
            try:
                box=face.RangeBox
                entry["range_mm"]={
                    "min":[round(float(box.MinPoint.X)*10,4),round(float(box.MinPoint.Y)*10,4),round(float(box.MinPoint.Z)*10,4)],
                    "max":[round(float(box.MaxPoint.X)*10,4),round(float(box.MaxPoint.Y)*10,4),round(float(box.MaxPoint.Z)*10,4)]
                }
            except Exception:
                pass
            faces.append(entry)
        edges=[]
        for ei in range(1,int(body.Edges.Count)+1):
            edge=body.Edges.Item(ei)
            item={"edge_index":ei,"curve_type":str(getattr(edge.Geometry,"CurveType","unknown"))}
            try:
                item["length_mm"]=round(float(edge.Evaluator.Length)*10,4)
            except Exception:
                pass
            edges.append(item)
        result["bodies"].append({"body_index":bi,"face_count":len(faces),"edge_count":len(edges),
                                 "faces":faces,"edges":edges})
    return result
