"""PDF drawing analysis with the OpenAI Responses API.

The PDF is sent as an input_file so vision-capable models can inspect both
embedded text and rendered page images. API keys are encrypted with Windows DPAPI.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pdf_vector import compact_vector_context, extract_pdf_vector_report


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4.1"
MAX_PDF_BYTES = 50 * 1024 * 1024


class PdfAIError(RuntimeError):
    """User-facing PDF analysis error."""


def _config_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        folder = Path(root) / "PDF2Inventor AI"
    else:
        folder = Path.home() / ".pdf2inventor-ai"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


def _dpapi_crypt(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise PdfAIError("Lưu khóa API an toàn cần Windows DPAPI. Có thể dùng biến môi trường OPENAI_API_KEY.")
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    source_buffer = ctypes.create_string_buffer(data)
    source_blob = DATA_BLOB(
        len(data),
        ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = DATA_BLOB()
    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

    if decrypt:
        description = wintypes.LPWSTR()
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(source_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        )
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(source_blob),
            "PDF2Inventor AI API Key",
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        )

    if not ok:
        error = ctypes.get_last_error()
        raise PdfAIError(f"Windows không thể mã hóa/giải mã khóa API (mã lỗi {error}).")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))
        if decrypt and description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))


def load_settings() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {"model": DEFAULT_MODEL, "detail": "high"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings must be object")
        data.setdefault("model", DEFAULT_MODEL)
        data.setdefault("detail", "high")
        return data
    except Exception as exc:
        raise PdfAIError(f"Không đọc được cấu hình PDF2Inventor: {exc}") from exc


def save_settings(model: str, detail: str, api_key: str | None = None) -> None:
    if detail not in {"low", "high", "auto"}:
        raise PdfAIError("Mức chi tiết PDF phải là low, high hoặc auto.")
    model = (model or "").strip()
    if not model:
        raise PdfAIError("Bạn cần nhập tên model AI.")
    path = _config_path()
    old: dict[str, Any] = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    data = {"model": model, "detail": detail}
    encrypted_key = old.get("api_key_dpapi_b64")
    if api_key is not None:
        cleaned = api_key.strip()
        if cleaned:
            encrypted_key = base64.b64encode(_dpapi_crypt(cleaned.encode("utf-8"))).decode("ascii")
        else:
            encrypted_key = None
    if encrypted_key:
        data["api_key_dpapi_b64"] = encrypted_key
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_api_key() -> str | None:
    environment_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if environment_key:
        return environment_key
    data = load_settings()
    encoded = data.get("api_key_dpapi_b64")
    if not encoded:
        return None
    try:
        encrypted = base64.b64decode(encoded, validate=True)
        return _dpapi_crypt(encrypted, decrypt=True).decode("utf-8")
    except Exception as exc:
        raise PdfAIError(
            "Không giải mã được khóa API đã lưu. Hãy nhập lại khóa trong tab AI đọc bản vẽ. "
            f"Chi tiết: {exc}"
        ) from exc


def analysis_schema() -> dict[str, Any]:
    nullable_number = {"type": ["number", "null"]}
    nullable_string = {"type": ["string", "null"]}
    command_properties = {
        "op": {"type": "string", "enum": ["create_rectangle_extrude", "create_circle_extrude", "create_profile_extrude"]},
        "component_id": {"type": "string"},
        "length": nullable_number,
        "width": nullable_number,
        "thickness": nullable_number,
        "origin_x": nullable_number,
        "origin_y": nullable_number,
        "diameter": nullable_number,
        "center_x": nullable_number,
        "center_y": nullable_number,
        "unit": {"type": "string", "enum": ["mm"]},
        "operation": {"type": "string", "enum": ["auto", "new_body"]},
        "direction": {"type": "string", "enum": ["positive", "negative"]},
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
        },
        "holes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "center_x": {"type": "number"},
                    "center_y": {"type": "number"},
                    "diameter": {"type": "number"},
                },
                "required": ["center_x", "center_y", "diameter"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
    }
    command_schema = {
        "type": "object",
        "properties": command_properties,
        "required": list(command_properties.keys()),
        "additionalProperties": False,
    }
    dimension_schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "value": nullable_number,
            "unit": {"type": "string"},
            "view": {"type": "string"},
            "page": {"type": "integer"},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["label", "value", "unit", "view", "page", "evidence", "confidence"],
        "additionalProperties": False,
    }
    scale_reference_schema = {
        "type": "object",
        "properties": {
            "dimension_text": {"type": "string"},
            "value_mm": {"type": "number"},
            "measured_length_pt": {"type": "number"},
            "mm_per_pt": {"type": "number"},
            "page": {"type": "integer"},
            "vector_path_id": {"type": "integer"},
            "segment_index": {"type": "integer"},
            "axis": {"type": "string", "enum": ["x", "y", "z"]},
            "view": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "dimension_text", "value_mm", "measured_length_pt", "mm_per_pt",
            "page", "vector_path_id", "segment_index", "axis", "view", "confidence"
        ],
        "additionalProperties": False,
    }
    schema_properties = {
        "drawing_type": {"type": "string", "enum": ["single_part", "assembly", "unknown"]},
        "drawing_title": {"type": "string"},
        "part_name": {"type": "string"},
        "units": {"type": "string", "enum": ["mm", "inch", "unknown"]},
        "overall_length_mm": nullable_number,
        "overall_width_mm": nullable_number,
        "overall_height_mm": nullable_number,
        "views_detected": {"type": "array", "items": {"type": "string"}},
        "dimensions_detected": {"type": "array", "items": dimension_schema},
        "feature_summary": {"type": "array", "items": {"type": "string"}},
        "manufacturing_notes": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "scale_status": {"type": "string", "enum": ["verified", "unverified", "conflict"]},
        "scale_references": {"type": "array", "items": scale_reference_schema},
        "cad_command": {"anyOf": [command_schema, {"type": "null"}]},
        "questions": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "properties": schema_properties,
        "required": list(schema_properties.keys()),
        "additionalProperties": False,
    }


def _analysis_prompt(project_id: str, component_id: str, part_name: str, document_path: str) -> str:
    return f"""
Bạn là kỹ sư thiết kế cơ khí và trợ lý chuyển bản vẽ PDF sang Autodesk Inventor 2018.
Hãy đọc TOÀN BỘ các trang PDF, kết hợp chữ trích xuất và hình ảnh trang bản vẽ.

Ngữ cảnh đích:
- project_id: {project_id}
- component_id: {component_id}
- tên chi tiết trong dự án: {part_name}
- file IPT đang mở/liên kết: {document_path}

YÊU CẦU PHÂN TÍCH:
1. Xác định bản vẽ là chi tiết đơn, bản lắp hay không rõ.
2. Nhận dạng hình chiếu đứng/cạnh/bằng, hình chiếu trục đo, mặt cắt và chi tiết phóng to.
3. Đọc kích thước ghi trực tiếp trên bản vẽ; ghi rõ view, bằng chứng và độ tin cậy.
4. Đơn vị của lệnh CAD luôn phải chuyển về mm. Nếu bản vẽ dùng inch, chỉ đổi sang mm khi đơn vị inch được xác định rõ.
5. Không suy ra kích thước chỉ từ tỷ lệ hình vẽ khi không có kích thước chuẩn.
6. Không tự đặt chiều dày, bán kính, vị trí lỗ, dung sai hoặc vật liệu còn thiếu.
7. Phân biệt kích thước tổng thể với kích thước chi tiết; không cộng trùng các kích thước.
8. Nêu rõ các đặc tính hình học cần dựng: bậc, rãnh, lỗ, ren, vát, bo, gân, hốc, mặt nghiêng...
9. Nếu có nhiều chi tiết trong bản lắp, không được giả làm một khối đơn.

GIỚI HẠN CAD HIỆN TẠI:
- Có thể tạo một feature cho mỗi lần chạy: Sketch chữ nhật + Extrude; Sketch tròn + Extrude; hoặc Sketch biên dạng đa giác kín + Extrude, kèm các lỗ tròn xuyên suốt.
- Biên dạng đa giác chỉ dùng cạnh thẳng; mỗi lỗ tròn phải có đường kính và tọa độ tâm rõ ràng.
- Chỉ đề xuất cad_command khi bản vẽ là chi tiết đơn dạng lăng trụ có tiết diện không đổi theo chiều dày và đủ kích thước tường minh. Nếu có mặt nghiêng 3D, cung tròn ngoài, rãnh không tròn, bậc chiều sâu hoặc nhiều feature thì không phát lệnh.
- Với mọi bản vẽ phức tạp hơn, hãy trả cad_command = null, liệt kê các câu hỏi/feature chưa hỗ trợ. Không được tạo một khối đơn giản sai hình dạng rồi tuyên bố hoàn tất.
- Không được dùng component_id khác với component_id được cung cấp.
- Nếu đề xuất create_rectangle_extrude: điền length, width, thickness bằng mm; các trường khác không dùng thì null; unit=mm; operation=new_body; direction=positive; origin_x=origin_y=0 trừ khi bản vẽ chỉ rõ tọa độ đặt khác.
- Nếu đề xuất create_circle_extrude: điền diameter và thickness bằng mm; các trường hình học không dùng thì null hoặc mảng rỗng; unit=mm; operation=new_body; direction=positive; center_x=center_y=0 trừ khi bản vẽ chỉ rõ vị trí khác.
- Nếu đề xuất create_profile_extrude: điền points là danh sách tọa độ x/y theo mm của đường bao ngoài theo thứ tự liên tiếp, đóng kín tự động; gốc XY ở góc trái-dưới của hình chiếu chính. Điền holes cho lỗ tròn xuyên suốt với center_x/center_y/diameter bằng mm; nếu không có lỗ dùng mảng rỗng. Điền thickness bằng mm; unit=mm; operation=new_body; direction=positive. Các trường riêng cho hình chữ nhật/hình tròn phải null.
- Không dùng lệnh cut hoặc tự phối hợp nhiều feature trong bản phát hành này.

Chỉ trả dữ liệu theo JSON Schema đã cung cấp. Không thêm Markdown.
""".strip()


def _extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in response.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "refusal":
                raise PdfAIError("AI từ chối phân tích PDF: " + str(content.get("refusal", "")))
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if chunks:
        return "\n".join(chunks).strip()
    status = response.get("status")
    details = response.get("incomplete_details")
    raise PdfAIError(f"AI không trả nội dung phân tích hoàn chỉnh (status={status}, details={details}).")


def analyze_pdf(
    pdf_path: str,
    api_key: str,
    model: str,
    detail: str,
    project_id: str,
    component_id: str,
    part_name: str,
    document_path: str,
) -> dict[str, Any]:
    """Send one PDF to the Responses API and return validated drawing analysis."""
    path = Path(pdf_path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise PdfAIError("Hãy chọn một file PDF bản vẽ hợp lệ.")
    size = path.stat().st_size
    if size <= 0:
        raise PdfAIError("File PDF đang rỗng.")
    if size > MAX_PDF_BYTES:
        raise PdfAIError("PDF vượt giới hạn 50 MB cho một file. Hãy giảm dung lượng hoặc tách bản vẽ.")
    if detail not in {"low", "high", "auto"}:
        raise PdfAIError("Chất lượng phân tích PDF không hợp lệ.")
    if not api_key or not api_key.strip():
        raise PdfAIError("Chưa cấu hình OpenAI API Key trong tab AI đọc bản vẽ.")

    try:
        encoded_pdf = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise PdfAIError(f"Không đọc được PDF: {exc}") from exc

    payload = {
        "model": model.strip() or DEFAULT_MODEL,
        "store": False,
        "max_output_tokens": 8000,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": path.name,
                        "file_data": "data:application/pdf;base64," + encoded_pdf,
                        "detail": detail,
                    },
                    {
                        "type": "input_text",
                        "text": _analysis_prompt(project_id, component_id, part_name, document_path),
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "mechanical_drawing_analysis",
                "strict": True,
                "schema": analysis_schema(),
            }
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + api_key.strip(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
            error_data = json.loads(error_body)
            message = error_data.get("error", {}).get("message", error_body)
        except Exception:
            message = str(exc)
        if exc.code == 401:
            raise PdfAIError("OpenAI API Key không hợp lệ hoặc không được phép sử dụng API.") from exc
        if exc.code == 429:
            raise PdfAIError("OpenAI API báo hết hạn mức hoặc giới hạn tốc độ. Kiểm tra billing/quota API.") from exc
        raise PdfAIError(f"OpenAI API lỗi HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise PdfAIError(f"Không kết nối được OpenAI API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PdfAIError("Phân tích PDF quá thời gian chờ. Hãy thử lại với PDF ít trang hơn hoặc detail=low.") from exc

    try:
        response_data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise PdfAIError("OpenAI API trả dữ liệu không phải JSON hợp lệ.") from exc
    text = _extract_output_text(response_data)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PdfAIError(f"Không đọc được JSON phân tích do AI trả về: {exc}") from exc

    if not isinstance(result, dict):
        raise PdfAIError("Dữ liệu phân tích AI không phải một đối tượng JSON.")
    result.setdefault("questions", [])
    result.setdefault("warnings", [])
    result.setdefault("cad_command", None)
    command = result.get("cad_command")
    if command is not None:
        if not isinstance(command, dict):
            raise PdfAIError("cad_command không đúng cấu trúc.")
        allowed_ops = {"create_rectangle_extrude", "create_circle_extrude", "create_profile_extrude"}
        if command.get("op") not in allowed_ops:
            raise PdfAIError("AI trả về loại feature chưa được hỗ trợ.")
        command["component_id"] = component_id
        command["unit"] = "mm"
    return result


def build_command_document(
    analysis: dict[str, Any],
    project_id: str,
    component_id: str,
) -> dict[str, Any]:
    command = analysis.get("cad_command")
    if not isinstance(command, dict):
        raise PdfAIError("Bản vẽ này chưa đủ điều kiện để tự dựng bằng các feature V0.6 hiện có.")
    command = dict(command)
    command["component_id"] = component_id
    command["unit"] = "mm"
    try:
        if command.get("op") == "create_rectangle_extrude":
            from inventor_geometry import validate_rectangle_command
            validate_rectangle_command(command)
        elif command.get("op") == "create_circle_extrude":
            from inventor_geometry import validate_circle_command
            validate_circle_command(command)
        elif command.get("op") == "create_profile_extrude":
            from inventor_geometry import validate_profile_command
            validate_profile_command(command)
        else:
            raise PdfAIError("Loại feature AI đề xuất chưa được hỗ trợ.")
    except PdfAIError:
        raise
    except Exception as exc:
        raise PdfAIError("Lệnh CAD AI tạo ra không hợp lệ: " + str(exc)) from exc
    return {
        "project_id": project_id,
        "commands": [command],
        "questions": list(analysis.get("questions") or []),
        "warnings": list(analysis.get("warnings") or []),
    }


def format_analysis_report(analysis: dict[str, Any]) -> str:
    lines = [
        "KẾT QUẢ PHÂN TÍCH BẢN VẼ",
        "==========================",
        "Tên bản vẽ: " + str(analysis.get("drawing_title") or "Chưa xác định"),
        "Tên chi tiết: " + str(analysis.get("part_name") or "Chưa xác định"),
        "Loại bản vẽ: " + str(analysis.get("drawing_type") or "unknown"),
        "Đơn vị: " + str(analysis.get("units") or "unknown"),
        "Độ tin cậy tổng thể: " + str(analysis.get("confidence") or "unknown"),
        "",
        "KÍCH THƯỚC TỔNG THỂ (mm)",
        "Dài: " + str(analysis.get("overall_length_mm")),
        "Rộng: " + str(analysis.get("overall_width_mm")),
        "Cao: " + str(analysis.get("overall_height_mm")),
        "",
        "HÌNH CHIẾU / MẶT CẮT",
    ]
    lines.extend("- " + str(item) for item in analysis.get("views_detected") or [])
    lines += ["", "KÍCH THƯỚC ĐỌC ĐƯỢC"]
    for item in analysis.get("dimensions_detected") or []:
        lines.append(
            "- {label}: {value} {unit} · {view} · tin cậy {confidence}".format(
                label=item.get("label"),
                value=item.get("value"),
                unit=item.get("unit"),
                view=item.get("view"),
                confidence=item.get("confidence"),
            )
        )
        if item.get("evidence"):
            lines.append("  Bằng chứng: " + str(item["evidence"]))
    lines += ["", "ĐẶC TÍNH HÌNH HỌC"]
    lines.extend("- " + str(item) for item in analysis.get("feature_summary") or [])
    lines += ["", "GHI CHÚ"]
    lines.extend("- " + str(item) for item in analysis.get("manufacturing_notes") or [])
    lines += ["", "CÂU HỎI CẦN LÀM RÕ"]
    lines.extend("- " + str(item) for item in analysis.get("questions") or [])
    lines += ["", "CẢNH BÁO"]
    lines.extend("- " + str(item) for item in analysis.get("warnings") or [])
    if analysis.get("cad_command"):
        lines += ["", "CAD COMMAND: Có lệnh dựng hình cơ bản, chờ kiểm tra và xác nhận của người dùng."]
    else:
        lines += ["", "CAD COMMAND: Chưa tạo lệnh. Bản vẽ cần thêm feature hoặc làm rõ kích thước."]
    return "\n".join(lines)
