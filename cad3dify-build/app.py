import hashlib
import os
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image
import fitz

from cad3dify import generate_step_from_2d_cad_image

st.set_page_config(page_title="Cad3Dify · 2D Drawing to 3D CAD", page_icon="📐", layout="wide")
st.title("Cad3Dify — Ảnh/PDF bản vẽ 2D → STEP 3D")
st.caption("Bản đóng gói Windows từ dự án mã nguồn mở neka-nat/cad3dify.")

st.warning(
    "Cad3Dify dùng AI qua API và chạy mã CadQuery do AI sinh ra trên máy tính này. "
    "Ảnh/PDF sẽ được gửi đến nhà cung cấp AI mà anh chọn. Chỉ thử với bản vẽ được phép chia sẻ; "
    "hãy kiểm tra STEP trước khi dùng cho sản xuất. Công cụ không bảo đảm tự động đúng mọi kích thước."
)

with st.sidebar:
    st.header("Cấu hình AI")
    choices = {
        "OpenAI · GPT-5 (cần OPENAI_API_KEY)": "gpt",
        "Anthropic · Claude Opus 4.5 (cần ANTHROPIC_API_KEY)": "claude",
        "Google · Gemini 3 Pro (cần GOOGLE_API_KEY)": "gemini",
    }
    model_label = st.selectbox("Mô hình", list(choices.keys()), index=0)
    model_type = choices[model_label]
    env_name = {"gpt": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY"}[model_type]
    api_key = st.text_input(env_name, type="password", help="Khóa chỉ được giữ trong bộ nhớ phiên chạy; không ghi vào file .env.")
    if api_key.strip():
        os.environ[env_name] = api_key.strip()
    st.caption("API có thể tính phí riêng theo mức sử dụng. Đây không phải API miễn phí.")
    refinements = st.slider(
        "Số lần AI chỉnh lại mô hình",
        min_value=0, max_value=3, value=1,
        help="Mỗi lần chỉnh lại có thể phát sinh thêm yêu cầu API. Để 0 khi muốn thử lần tạo đầu tiên."
    )
    pdf_dpi = st.slider("Độ phân giải khi mở PDF", 150, 500, 300, 25)
    st.divider()
    accepted = st.checkbox(
        "Tôi hiểu ảnh bản vẽ sẽ gửi tới nhà cung cấp AI và mã Python AI sinh ra sẽ được chạy trên máy này."
    )
    if st.button("Thoát Cad3Dify", use_container_width=True):
        st.info("Đang đóng Cad3Dify…")
        os._exit(0)

upload = st.file_uploader(
    "Chọn bản vẽ 2D",
    type=["pdf", "png", "jpg", "jpeg"],
    help="Có thể chọn PDF nhiều trang hoặc ảnh PNG/JPG. Với PDF, chọn trang cần chuyển."
)

def prepare_input(uploaded, page_index, dpi):
    suffix = Path(uploaded.name).suffix.lower()
    temp_dir = Path(tempfile.mkdtemp(prefix="cad3dify_"))
    input_path = temp_dir / "drawing.png"
    raw = uploaded.getvalue()
    if suffix == ".pdf":
        with fitz.open(stream=raw, filetype="pdf") as pdf:
            if page_index < 0 or page_index >= pdf.page_count:
                raise ValueError("Số trang PDF không hợp lệ.")
            page = pdf.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
            pix.save(str(input_path))
    else:
        with Image.open(uploaded) as image:
            image.convert("RGB").save(input_path, format="PNG")
    return input_path, temp_dir

if upload is not None:
    suffix = Path(upload.name).suffix.lower()
    page_index = 0
    if suffix == ".pdf":
        try:
            with fitz.open(stream=upload.getvalue(), filetype="pdf") as pdf:
                if pdf.page_count > 0:
                    page_index = st.selectbox(
                        "Trang PDF cần chuyển",
                        options=list(range(pdf.page_count)),
                        format_func=lambda value: f"Trang {value + 1}",
                        index=0
                    )
                    st.caption(f"PDF có {pdf.page_count} trang.")
        except Exception as exc:
            st.error(f"Không đọc được PDF: {exc}")
    try:
        preview_path, _preview_dir = prepare_input(upload, page_index, pdf_dpi)
        st.image(str(preview_path), caption="Ảnh đầu vào gửi cho AI", use_container_width=True)
        input_bytes = preview_path.read_bytes()
        input_hash = hashlib.sha256(input_bytes + model_type.encode("utf-8")).hexdigest()
        if st.session_state.get("input_hash") != input_hash:
            st.session_state.pop("step_bytes", None)
            st.session_state.pop("step_name", None)
            st.session_state["input_hash"] = input_hash

        ready = bool(api_key.strip()) and accepted
        if not api_key.strip():
            st.info(f"Nhập {env_name} ở thanh bên trái trước khi tạo STEP.")
        if not accepted:
            st.info("Đánh dấu xác nhận an toàn ở thanh bên trái để bật nút tạo STEP.")

        if st.button("TẠO MÔ HÌNH 3D / STEP", type="primary", disabled=not ready, use_container_width=True):
            output_path = preview_path.parent / "cad3dify_output.step"
            try:
                with st.spinner("AI đang đọc bản vẽ, sinh CadQuery và tạo mô hình 3D…"):
                    generate_step_from_2d_cad_image(
                        str(preview_path),
                        str(output_path),
                        num_refinements=int(refinements),
                        model_type=model_type,
                    )
                if not output_path.is_file() or output_path.stat().st_size == 0:
                    raise RuntimeError("Pipeline kết thúc nhưng không tạo được file STEP.")
                st.session_state["step_bytes"] = output_path.read_bytes()
                st.session_state["step_name"] = Path(upload.name).stem + "_Cad3Dify.step"
                st.success("Đã tạo file STEP. Hãy kiểm tra lại hình học và mọi kích thước.")
            except Exception as exc:
                st.error(f"Tạo STEP thất bại: {type(exc).__name__}: {exc}")

        if st.session_state.get("step_bytes"):
            st.download_button(
                "TẢI FILE STEP",
                data=st.session_state["step_bytes"],
                file_name=st.session_state.get("step_name", "Cad3Dify.step"),
                mime="application/step",
                type="primary",
                use_container_width=True,
            )
    except Exception as exc:
        st.error(f"Không chuẩn bị được bản vẽ: {type(exc).__name__}: {exc}")
else:
    st.info("Tải lên một bản vẽ PDF hoặc ảnh PNG/JPG để bắt đầu.")
