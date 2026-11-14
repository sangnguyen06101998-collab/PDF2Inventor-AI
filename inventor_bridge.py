"""Autodesk Inventor 2018 COM bridge for PDF2Inventor AI.

This module imports pywin32 only when a connection is requested, so PDF and
project features remain usable when Inventor is not installed.
"""
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


class InventorBridgeError(RuntimeError):
    """A user-facing Inventor automation error."""


_COM_INITIALIZED = False


def _format_com_error(exc):
    """Return a useful HRESULT string for COM connection diagnostics."""
    hresult = getattr(exc, "hresult", None)
    if hresult is None and getattr(exc, "args", None):
        first = exc.args[0]
        if isinstance(first, int):
            hresult = first
    if isinstance(hresult, int):
        unsigned = hresult & 0xFFFFFFFF
        return f"HRESULT 0x{unsigned:08X} ({hresult}) · {exc}"
    return f"{type(exc).__name__}: {exc}"


def _find_inventor_in_rot(pythoncom, win32com_client):
    """Try ROT monikers containing Inventor; never launch a new Inventor process."""
    matches = []
    try:
        rot = pythoncom.GetRunningObjectTable()
        enum = rot.EnumRunning()
        bind_context = pythoncom.CreateBindCtx(0)
        while True:
            batch = enum.Next(1)
            if not batch:
                break
            moniker = batch[0]
            try:
                display_name = str(moniker.GetDisplayName(bind_context, None))
            except Exception:
                continue
            if "inventor" not in display_name.lower():
                continue
            matches.append(display_name)
            try:
                unknown = rot.GetObject(moniker)
                dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
                return win32com_client.Dispatch(dispatch), matches
            except Exception:
                continue
    except Exception:
        pass
    return None, matches


def connect_inventor():
    """Attach to the running Inventor COM server without starting another instance."""
    global _COM_INITIALIZED
    try:
        import pythoncom
        import pywintypes
        import win32com.client
    except Exception as exc:
        raise InventorBridgeError(
            "Không nạp được pywin32/pythoncom. Hãy dùng Artifact V0.4 mới nhất, "
            "không dùng bản EXE cũ."
        ) from exc

    try:
        # PySide6 owns the GUI main thread. Explicitly initialize COM on that thread.
        if not _COM_INITIALIZED:
            pythoncom.CoInitialize()
            _COM_INITIALIZED = True

        progid = "Inventor.Application"
        clsid = pywintypes.IID(progid)

        # First obtain the already-running COM object using its resolved CLSID.
        try:
            unknown = pythoncom.GetActiveObject(clsid)
            dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
            app = win32com.client.Dispatch(dispatch)
        except Exception as primary_exc:
            # Some Inventor installations publish a ROT moniker that can be
            # attached to even when direct ProgID lookup is unavailable.
            app, rot_matches = _find_inventor_in_rot(pythoncom, win32com.client)
            if app is None:
                detail = _format_com_error(primary_exc)
                hint = (
                    "Kiểm tra Inventor và PDF2Inventor AI chạy cùng tài khoản Windows, "
                    "cùng mức quyền (cả hai bình thường hoặc cả hai Run as administrator), "
                    "và cùng phiên đăng nhập. Đóng Inventor rồi mở lại trước khi kết nối."
                )
                monikers = (
                    " ROT Inventor: " + "; ".join(rot_matches[:5])
                    if rot_matches else " Không thấy moniker chứa tên Inventor trong ROT."
                )
                raise InventorBridgeError(
                    "Không lấy được đối tượng COM của Inventor đang chạy. "
                    + detail + ". " + hint + monikers
                ) from primary_exc

        # Verify that the returned object is the real Inventor automation server.
        version = str(app.SoftwareVersion.DisplayVersion)
        if not version:
            raise RuntimeError("Inventor không trả về SoftwareVersion.")
        return app
    except InventorBridgeError:
        raise
    except Exception as exc:
        raise InventorBridgeError(
            "Lỗi khi khởi tạo/kết nối COM với Inventor: "
            + _format_com_error(exc)
            + ". Hãy bảo đảm Inventor và PDF2Inventor AI chạy cùng mức quyền Windows."
        ) from exc


def get_active_document(app):
    try:
        doc = app.ActiveDocument
        if doc is None:
            raise InventorBridgeError("Inventor chưa có tài liệu đang hoạt động.")
        return doc
    except InventorBridgeError:
        raise
    except Exception as exc:
        raise InventorBridgeError(
            "Không đọc được tài liệu đang hoạt động. Hãy mở một file IPT trong Inventor."
        ) from exc


def get_document_by_path(app, file_path):
    """Find an already-open Inventor document by its full Windows path."""
    target = os.path.normcase(os.path.abspath(str(file_path)))
    try:
        docs = app.Documents
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            try:
                current = str(doc.FullFileName or "")
            except Exception:
                current = ""
            if current and os.path.normcase(os.path.abspath(current)) == target:
                return doc
    except Exception as exc:
        raise InventorBridgeError("Không thể duyệt danh sách tài liệu đang mở trong Inventor.") from exc
    return None


def get_document_info(doc, app=None):
    try:
        full_path = str(doc.FullFileName or "")
    except Exception:
        full_path = ""
    try:
        display_name = str(doc.DisplayName or "")
    except Exception:
        display_name = Path(full_path).name if full_path else "Tài liệu chưa lưu"
    version = "Không xác định"
    if app is not None:
        try:
            version = str(app.SoftwareVersion.DisplayVersion)
        except Exception:
            pass
    return {
        "display_name": display_name,
        "full_path": full_path,
        "version": version,
        "extension": Path(full_path).suffix.lower() if full_path else "",
    }


def _parse_expression(expression):
    text = str(expression).strip()
    match = re.fullmatch(
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-zµ°/]+)?",
        text,
    )
    if not match:
        return {"value": None, "unit": None, "expression": text}

    value = float(match.group(1))
    if not math.isfinite(value):
        return {"value": None, "unit": None, "expression": text}
    if value.is_integer():
        value = int(value)
    unit = (match.group(2) or "").strip().lower()
    return {"value": value, "unit": unit, "expression": text}


def read_parameters(doc):
    """Read model and user parameters into a JSON-serializable dictionary."""
    try:
        params = doc.ComponentDefinition.Parameters
        count = int(params.Count)
    except Exception as exc:
        raise InventorBridgeError(
            "Tài liệu đang mở không cung cấp ComponentDefinition.Parameters. "
            "V0.4 hiện hỗ trợ tài liệu chi tiết IPT."
        ) from exc

    result = {}
    for index in range(1, count + 1):
        try:
            parameter = params.Item(index)
            name = str(parameter.Name)
            expression = str(parameter.Expression)
            result[name] = _parse_expression(expression)
        except Exception:
            continue
    return result


def _format_expression(value, unit):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InventorBridgeError("Giá trị tham số phải là số, không nhận giá trị true/false.")
    number = float(value)
    if not math.isfinite(number):
        raise InventorBridgeError("Giá trị tham số phải là số hữu hạn.")
    number_text = format(number, ".12g")
    clean_unit = str(unit or "").strip().lower()
    allowed_units = {"mm", "cm", "m", "in", "inch", "deg", "rad"}
    if clean_unit and clean_unit not in allowed_units:
        raise InventorBridgeError(
            f"Đơn vị '{unit}' chưa được cho phép trong V0.4. Hiện hỗ trợ mm, cm, m, in, deg, rad."
        )
    return f"{number_text} {clean_unit}".strip()


def apply_parameter_changes(doc, changes):
    """Backup, apply parameter expressions, update, and save one IPT document."""
    info = get_document_info(doc)
    file_path = info["full_path"]
    if not file_path:
        raise InventorBridgeError("Tài liệu Inventor chưa được lưu thành file. Hãy Save As thành IPT trước.")
    if info["extension"] != ".ipt":
        raise InventorBridgeError("V0.4 hiện chỉ áp dụng thay đổi tham số cho file chi tiết .ipt.")
    if not changes:
        raise InventorBridgeError("Không có tham số nào cần thay đổi.")

    try:
        doc.Save()
    except Exception as exc:
        raise InventorBridgeError(f"Không thể lưu file IPT trước khi sao lưu: {exc}") from exc

    source = Path(file_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = source.with_name(f"{source.stem}_Before_PDF2Inventor_{stamp}{source.suffix}")
    try:
        shutil.copy2(source, backup)
    except Exception as exc:
        raise InventorBridgeError(f"Không tạo được bản sao dự phòng: {exc}") from exc

    old_expressions = {}
    try:
        params = doc.ComponentDefinition.Parameters
        new_expressions = {}
        for item in changes:
            name = str(item.get("parameter", "")).strip()
            if not name:
                raise InventorBridgeError("Có lệnh thiếu tên parameter.")
            try:
                parameter = params.Item(name)
            except Exception as exc:
                raise InventorBridgeError(f"Inventor không có tham số '{name}'.") from exc
            if name not in old_expressions:
                old_expressions[name] = str(parameter.Expression)
            new_expressions[name] = _format_expression(item.get("value"), item.get("unit"))

        for name, expression in new_expressions.items():
            params.Item(name).Expression = expression

        doc.Update()
        doc.Save()
        verified = read_parameters(doc)
        for name in new_expressions:
            if name not in verified:
                raise InventorBridgeError(f"Không đọc lại được tham số '{name}' sau khi cập nhật.")
        return {
            "backup_path": str(backup),
            "document_path": file_path,
            "parameters": verified,
            "updated": new_expressions,
        }

    except Exception as exc:
        rollback_message = ""
        try:
            params = doc.ComponentDefinition.Parameters
            for name, old_expression in old_expressions.items():
                params.Item(name).Expression = old_expression
            doc.Update()
            doc.Save()
            rollback_message = "Đã khôi phục các giá trị tham số cũ."
        except Exception as rollback_exc:
            rollback_message = (
                "Không thể xác nhận khôi phục tự động; hãy mở bản sao dự phòng: "
                f"{backup}. Chi tiết rollback: {rollback_exc}"
            )
        detail = str(exc) if isinstance(exc, InventorBridgeError) else f"{type(exc).__name__}: {exc}"
        raise InventorBridgeError(
            f"Không áp dụng được thay đổi vào Inventor: {detail}. {rollback_message} "
            f"Bản sao dự phòng: {backup}"
        ) from exc
