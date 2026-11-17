"""Small, defensive COM bridge for Autodesk Inventor 2018."""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any


class InventorBridgeError(RuntimeError):
    pass


class InventorBridge:
    def __init__(self) -> None:
        self._app = None

    def _connect(self):
        if os.name != "nt":
            raise InventorBridgeError("Inventor COM bridge only runs on Windows.")
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                self._app = win32com.client.GetActiveObject("Inventor.Application")
            except Exception:
                # Do not launch a second Inventor session silently.
                raise InventorBridgeError(
                    "Cannot find a running Inventor instance. Open Inventor 2018 first."
                )
            return self._app
        except InventorBridgeError:
            raise
        except Exception as exc:
            raise InventorBridgeError(f"COM connection failed: {exc}") from exc

    def status(self) -> dict[str, Any]:
        app = self._connect()
        doc_info = None
        try:
            doc = app.ActiveDocument
            doc_info = {
                "name": str(doc.DisplayName),
                "full_file_name": str(doc.FullFileName or ""),
                "document_type": int(doc.DocumentType),
            }
        except Exception:
            pass
        return {
            "connected": True,
            "application": str(app.Name),
            "version": str(app.SoftwareVersion.DisplayVersion),
            "active_document": doc_info,
        }

    def _active_part(self):
        app = self._connect()
        try:
            doc = app.ActiveDocument
            # Inventor kPartDocumentObject = 12290
            if int(doc.DocumentType) != 12290:
                raise InventorBridgeError("The active document is not a Part (.ipt).")
            return app, doc, doc.ComponentDefinition
        except InventorBridgeError:
            raise
        except Exception as exc:
            raise InventorBridgeError(f"No active part document: {exc}") from exc

    def list_parameters(self) -> dict[str, Any]:
        _, doc, comp_def = self._active_part()
        values = []
        for parameter in comp_def.Parameters:
            try:
                values.append({
                    "name": str(parameter.Name),
                    "expression": str(parameter.Expression),
                    "value_internal": float(parameter.Value),
                    "units": str(parameter.Units),
                })
            except Exception:
                continue
        return {
            "document": str(doc.DisplayName),
            "full_file_name": str(doc.FullFileName or ""),
            "parameters": values,
        }

    def create_extruded_rectangle(
        self, length_mm: float, width_mm: float, thickness_mm: float, output_ipt: str
    ) -> dict[str, Any]:
        vals = (length_mm, width_mm, thickness_mm)
        if not all(math.isfinite(float(v)) and float(v) > 0 for v in vals):
            raise InventorBridgeError("All dimensions must be finite positive millimetres.")
        if max(vals) > 100000:
            raise InventorBridgeError("Dimension exceeds the 100000 mm safety limit.")

        app = self._connect()
        target = Path(output_ipt).expanduser()
        if target.suffix.lower() != ".ipt":
            raise InventorBridgeError("Output file must use the .ipt extension.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise InventorBridgeError(
                f"Refusing to overwrite existing file: {target}. Choose a new filename."
            )

        try:
            # Inventor API internal length units are centimetres.
            length_cm, width_cm, thickness_cm = (
                float(length_mm) / 10.0,
                float(width_mm) / 10.0,
                float(thickness_mm) / 10.0,
            )
            part_doc_type = 12290  # kPartDocumentObject
            template = app.FileManager.GetTemplateFile(part_doc_type)
            doc = app.Documents.Add(part_doc_type, template, True)
            comp_def = doc.ComponentDefinition
            sketch = comp_def.Sketches.Add(comp_def.WorkPlanes.Item(3))
            tg = app.TransientGeometry
            p1 = tg.CreatePoint2d(0.0, 0.0)
            p2 = tg.CreatePoint2d(length_cm, width_cm)
            sketch.SketchLines.AddAsTwoPointRectangle(p1, p2)
            profile = sketch.Profiles.AddForSolid()
            extrude_def = comp_def.Features.ExtrudeFeatures.CreateExtrudeDefinition(
                profile, 20481  # kJoinOperation
            )
            extrude_def.SetDistanceExtent(
                thickness_cm, 20993  # kPositiveExtentDirection
            )
            comp_def.Features.ExtrudeFeatures.Add(extrude_def)
            doc.Update()
            doc.SaveAs(str(target.resolve()), False)
            return {
                "success": True,
                "file": str(target.resolve()),
                "dimensions_mm": {
                    "length": float(length_mm),
                    "width": float(width_mm),
                    "thickness": float(thickness_mm),
                },
                "note": "Primitive smoke-test only; verify dimensions in Inventor before production use.",
            }
        except InventorBridgeError:
            raise
        except Exception as exc:
            try:
                if "doc" in locals():
                    doc.Close(True)
            except Exception:
                pass
            raise InventorBridgeError(
                f"Inventor failed to create the extrusion: {exc}"
            ) from exc
