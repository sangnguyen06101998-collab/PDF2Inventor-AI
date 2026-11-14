import sys, json, os, copy
from pathlib import Path
from datetime import datetime
import fitz
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QTextEdit, QFileDialog, QMessageBox, QSplitter,
    QGroupBox, QLineEdit, QTabWidget, QInputDialog, QDialog, QComboBox
)
from inventor_bridge import InventorBridgeError, connect_inventor, get_active_document, get_document_by_path, get_document_info, read_parameters, apply_parameter_changes
from inventor_geometry import create_rectangle_extrude, validate_rectangle_command, create_circle_extrude, validate_circle_command
from pdf_ai import (
    PdfAIError, analyze_pdf, build_command_document, format_analysis_report,
    get_api_key, load_settings, save_settings, DEFAULT_MODEL
)

APP_TITLE = "PDF2Inventor AI · V0.6 PDF Vision + Inventor COM"
SCHEMA_VERSION = "0.2"

def now():
    return datetime.now().isoformat(timespec="seconds")

class PdfPreviewLabel(QLabel):
    fileDropped = Signal(str)

    def __init__(self, text=""):
        super().__init__(text)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for url in urls:
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.fileDropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()


class PdfAnalysisWorker(QThread):
    analysis_ready = Signal(object)
    analysis_failed = Signal(str)

    def __init__(self, args, parent=None):
        super().__init__(parent)
        self.args = args

    def run(self):
        try:
            api_key = get_api_key()
            if not api_key:
                raise PdfAIError("Chưa có OpenAI API Key. Hãy nhập khóa trong tab AI đọc bản vẽ.")
            result = analyze_pdf(api_key=api_key, **self.args)
            self.analysis_ready.emit(result)
        except Exception as exc:
            self.analysis_failed.emit(str(exc))


def default_project():
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": "PROJECT_001",
        "project_name": "New CAD Project",
        "source_pdf": None,
        "units": "mm",
        "components": [],
        "assembly_relations": [],
        "change_history": [],
        "notes": [
            "Chỉ đưa cho ChatGPT thông tin cần thiết; không gửi PDF nếu không cần.",
            "V0.5 hỗ trợ cập nhật tham số và dựng Sketch chữ nhật + Extrude trên IPT đã liên kết; mọi lệnh phải được xác nhận trước khi áp dụng."
        ]
    }

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1320, 860)
        self.project = default_project()
        self.project_path = None
        self.pdf = None
        self.pdf_path = None
        self.page_index = 0
        self.pending_commands = None
        self.inventor_app = None
        self.ai_worker = None
        self.ai_analysis = None

        self.setAcceptDrops(True)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self.build_project_tab(), "Dự án CAD")
        tabs.addTab(self.build_pdf_tab(), "PDF")
        self.ai_tab = self.build_ai_tab()
        tabs.addTab(self.ai_tab, "AI đọc bản vẽ")
        tabs.addTab(self.build_inventor_tab(), "Inventor 2018")
        tabs.addTab(self.build_chat_tab(), "ChatGPT thủ công")
        self.command_tab = self.build_command_tab()
        tabs.addTab(self.command_tab, "Nhập lệnh CAD")
        self.tabs = tabs
        self.refresh_project_view()
        self.statusBar().showMessage("V0.6 · PDF Vision AI · Inventor 2018 COM")

    def build_project_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        top = QHBoxLayout()
        self.project_name = QLineEdit(self.project["project_name"])
        self.project_name.setPlaceholderText("Tên dự án")
        self.project_name.editingFinished.connect(self.update_project_name)
        btn_new = QPushButton("Dự án mới"); btn_new.clicked.connect(self.new_project)
        btn_open = QPushButton("Mở dự án"); btn_open.clicked.connect(self.open_project)
        btn_save = QPushButton("Lưu dự án"); btn_save.clicked.connect(self.save_project)
        top.addWidget(QLabel("Tên dự án:")); top.addWidget(self.project_name, 1)
        top.addWidget(btn_new); top.addWidget(btn_open); top.addWidget(btn_save)
        root.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        left = QGroupBox("Danh sách chi tiết")
        ll = QVBoxLayout(left)
        self.component_list = QListWidget()
        ll.addWidget(self.component_list)
        row = QHBoxLayout()
        add = QPushButton("Thêm chi tiết"); add.clicked.connect(self.add_component)
        edit = QPushButton("Sửa JSON chi tiết"); edit.clicked.connect(self.edit_component_json)
        row.addWidget(add); row.addWidget(edit); ll.addLayout(row)
        right = QGroupBox("Thông tin và tham số CAD")
        rl = QVBoxLayout(right)
        self.project_view = QTextEdit(); self.project_view.setReadOnly(True)
        rl.addWidget(self.project_view)
        split.addWidget(left); split.addWidget(right); split.setSizes([350, 850])
        root.addWidget(split, 1)
        note = QLabel("V0.5: cập nhật tham số và tạo Sketch chữ nhật + Extrude trên IPT đã liên kết sau khi người dùng xác nhận.")
        note.setStyleSheet("color:#b45309;")
        root.addWidget(note)
        return w

    def build_pdf_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        top = QHBoxLayout()
        openb = QPushButton("Mở PDF"); openb.clicked.connect(self.open_pdf)
        ai = QPushButton("Phân tích PDF bằng AI"); ai.clicked.connect(self.open_ai_analysis)
        self.pdf_label = QLabel("Chưa chọn PDF")
        top.addWidget(openb); top.addWidget(ai); top.addWidget(self.pdf_label, 1)
        root.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        self.page_list = QListWidget(); self.page_list.currentRowChanged.connect(self.show_page)
        self.preview = PdfPreviewLabel("Kéo thả file PDF vào đây hoặc nhấn Mở PDF")
        self.preview.fileDropped.connect(self.load_pdf)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(500, 400)
        self.preview.setStyleSheet("background:#e2e8f0;color:#475569;")
        split.addWidget(self.page_list); split.addWidget(self.preview)
        split.setSizes([180, 1000])
        root.addWidget(split, 1)
        self.pdf_info = QLabel("PDF được mở và xem tại máy. Nhấn Phân tích PDF bằng AI để đọc chữ, hình chiếu và kích thước.")
        root.addWidget(self.pdf_info)
        return w

    def build_ai_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        root.addWidget(QLabel(
            "Luồng tự động: nạp PDF → AI đọc toàn bộ bản vẽ → kiểm tra kích thước/độ tin cậy → tạo lệnh CAD → người dùng xác nhận → Inventor dựng hình."
        ))
        file_row = QHBoxLayout()
        self.ai_pdf_label = QLabel("PDF: chưa chọn")
        self.ai_pdf_label.setWordWrap(True)
        file_row.addWidget(self.ai_pdf_label, 1)
        choose_pdf = QPushButton("Chọn PDF")
        choose_pdf.clicked.connect(self.open_pdf)
        file_row.addWidget(choose_pdf)
        root.addLayout(file_row)

        settings = QGroupBox("Kết nối AI")
        settings_layout = QVBoxLayout(settings)
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("OpenAI API Key"))
        self.ai_key_input = QLineEdit()
        self.ai_key_input.setEchoMode(QLineEdit.Password)
        self.ai_key_input.setPlaceholderText("Dán API key tại đây (không phải mật khẩu ChatGPT)")
        key_row.addWidget(self.ai_key_input, 1)
        settings_layout.addLayout(key_row)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model"))
        self.ai_model_input = QLineEdit(DEFAULT_MODEL)
        self.ai_model_input.setPlaceholderText("Ví dụ: gpt-4.1")
        model_row.addWidget(self.ai_model_input, 1)
        model_row.addWidget(QLabel("Chi tiết PDF"))
        self.ai_detail_combo = QComboBox()
        self.ai_detail_combo.addItem("Cao · đọc kích thước nhỏ", "high")
        self.ai_detail_combo.addItem("Tự động", "auto")
        self.ai_detail_combo.addItem("Thấp · tiết kiệm hơn", "low")
        model_row.addWidget(self.ai_detail_combo)
        settings_layout.addLayout(model_row)
        key_actions = QHBoxLayout()
        save_key = QPushButton("Lưu cấu hình và khóa an toàn")
        save_key.clicked.connect(self.save_ai_settings)
        clear_key = QPushButton("Xóa khóa đã lưu")
        clear_key.clicked.connect(self.clear_ai_key)
        key_actions.addWidget(save_key); key_actions.addWidget(clear_key)
        settings_layout.addLayout(key_actions)
        self.ai_key_status = QLabel("Khóa API chưa được kiểm tra.")
        self.ai_key_status.setWordWrap(True)
        settings_layout.addWidget(self.ai_key_status)
        root.addWidget(settings)

        actions = QHBoxLayout()
        create_part = QPushButton("Tạo IPT mới")
        create_part.clicked.connect(self.create_new_ipt_for_ai)
        link_part = QPushButton("Gắn IPT đang mở")
        link_part.clicked.connect(self.link_active_ipt_for_ai)
        self.ai_analyze_button = QPushButton("ĐỌC PDF VÀ PHÂN TÍCH")
        self.ai_analyze_button.clicked.connect(self.start_pdf_ai_analysis)
        self.ai_to_command_button = QPushButton("Chuyển lệnh sang CAD")
        self.ai_to_command_button.clicked.connect(self.send_ai_command_to_cad)
        self.ai_to_command_button.setEnabled(False)
        actions.addWidget(create_part); actions.addWidget(link_part)
        actions.addWidget(self.ai_analyze_button); actions.addWidget(self.ai_to_command_button)
        root.addLayout(actions)
        self.ai_status_label = QLabel("Chưa chạy phân tích.")
        self.ai_status_label.setWordWrap(True)
        root.addWidget(self.ai_status_label)
        self.ai_report = QTextEdit()
        self.ai_report.setReadOnly(True)
        self.ai_report.setPlaceholderText("Báo cáo đọc bản vẽ, kích thước, hình chiếu, câu hỏi và lệnh CAD sẽ hiển thị tại đây.")
        root.addWidget(self.ai_report, 1)

        try:
            settings_data = load_settings()
            self.ai_model_input.setText(settings_data.get("model", DEFAULT_MODEL))
            detail = settings_data.get("detail", "high")
            index = self.ai_detail_combo.findData(detail)
            if index >= 0: self.ai_detail_combo.setCurrentIndex(index)
            if get_api_key():
                self.ai_key_status.setText("Đã có khóa API được lưu mã hóa theo tài khoản Windows này.")
            else:
                self.ai_key_status.setText("Chưa lưu khóa. Cần API key riêng; gói ChatGPT Free/Plus không tự bao gồm API credit.")
        except Exception as e:
            self.ai_key_status.setText("Lỗi cấu hình: " + str(e))
        return w

    def open_ai_analysis(self):
        if not self.pdf_path:
            self.open_pdf()
            if not self.pdf_path:
                return
        self.tabs.setCurrentWidget(self.ai_tab)

    def save_ai_settings(self):
        try:
            entered_key = self.ai_key_input.text().strip()
            save_settings(
                self.ai_model_input.text().strip(),
                str(self.ai_detail_combo.currentData()),
                api_key=entered_key if entered_key else None,
            )
            self.ai_key_input.clear()
            if get_api_key():
                self.ai_key_status.setText("Đã lưu cấu hình. Khóa API được mã hóa bằng Windows DPAPI theo tài khoản hiện tại.")
            else:
                self.ai_key_status.setText("Đã lưu model và mức chi tiết PDF. Chưa có khóa API.")
            QMessageBox.information(self, "Cấu hình AI", "Đã lưu cấu hình AI.")
        except Exception as e:
            QMessageBox.critical(self, "Không lưu được cấu hình AI", str(e))

    def clear_ai_key(self):
        if QMessageBox.question(self, "Xóa API Key", "Xóa khóa API đã mã hóa trên máy tính này?") != QMessageBox.Yes:
            return
        try:
            save_settings(
                self.ai_model_input.text().strip() or DEFAULT_MODEL,
                str(self.ai_detail_combo.currentData()),
                api_key="",
            )
            self.ai_key_input.clear()
            self.ai_key_status.setText("Đã xóa khóa API.")
        except Exception as e:
            QMessageBox.critical(self, "Không xóa được khóa", str(e))

    def create_new_ipt_for_ai(self):
        if self.inventor_app is None:
            try:
                self.inventor_app = connect_inventor()
            except Exception as e:
                QMessageBox.warning(self, "Kết nối Inventor", str(e))
                return
        default_name = "PDF2Inventor_NewPart.ipt"
        if self.pdf_path:
            default_name = Path(self.pdf_path).stem[:80] + ".ipt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu chi tiết IPT mới", default_name, "Inventor Part (*.ipt)"
        )
        if not path:
            return
        if not path.lower().endswith(".ipt"):
            path += ".ipt"
        if os.path.exists(path):
            QMessageBox.warning(self, "File đã tồn tại", "Không ghi đè IPT có sẵn. Hãy chọn tên file mới.")
            return
        doc = None
        try:
            template = self.inventor_app.FileManager.GetTemplateFile(12290)
            doc = self.inventor_app.Documents.Add(12290, template, True)
            doc.SaveAs(path, False)
            doc.Activate()
            self.component_list.setCurrentRow(-1)
            if not self.link_active_ipt_for_ai():
                try: doc.Close(True)
                except Exception: pass
                return
            self.inv_log.append("ĐÃ TẠO IPT MỚI TỪ TEMPLATE: " + path)
            self.ai_status_label.setText(
                "Đã tạo IPT mới và liên kết vào dự án. Tiếp theo nhấn ĐỌC PDF VÀ PHÂN TÍCH."
            )
            if not self.project_path:
                self.statusBar().showMessage("Đã tạo IPT. Hãy lưu hồ sơ dự án để giữ liên kết file.")
        except Exception as e:
            if doc is not None:
                try: doc.Close(True)
                except Exception: pass
            QMessageBox.critical(self, "Không tạo được IPT mới", str(e))

    def link_active_ipt_for_ai(self):
        doc, info, params = self.ui_read_inventor()
        if doc is None:
            return False
        path = info.get("full_path") or ""
        if info.get("extension") != ".ipt" or not path or not os.path.isfile(path):
            QMessageBox.warning(
                self, "File IPT chưa sẵn sàng",
                "Hãy mở một file Part (.ipt) trong Inventor 2018 và Save As trước. "
                "Nên dùng một IPT mới/trống để tạo chi tiết từ PDF."
            )
            return False

        row = self.component_list.currentRow()
        if row < 0:
            source_name = Path(self.pdf_path).stem if self.pdf_path else Path(info["display_name"]).stem
            safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in source_name.upper()).strip("_")
            if not safe or not safe[0].isalpha():
                safe = "PDF_" + safe
            component_id = safe[:32] or "PDF_PART"
            base = component_id
            suffix = 2
            existing_ids = {str(c.get("component_id")) for c in self.project.get("components", [])}
            while component_id in existing_ids:
                component_id = (base[:27] + "_" + str(suffix))[:32]
                suffix += 1
            comp = {
                "component_id": component_id,
                "name": Path(self.pdf_path).stem if self.pdf_path else Path(info["display_name"]).stem,
                "document_type": "part",
                "inventor_file": None,
                "parameters": {},
                "features": [],
                "description": "Chi tiết được tạo từ phân tích PDF bằng AI."
            }
            self.project["components"].append(comp)
            row = len(self.project["components"]) - 1
        comp = self.project["components"][row]
        comp["inventor_file"] = path
        comp["parameters"] = params
        self.refresh_project_view()
        self.component_list.setCurrentRow(row)
        if self.project_path:
            save_json(self.project_path, self.project)
        self.ai_status_label.setText(
            "Đã gắn chi tiết " + str(comp["component_id"]) + " với IPT: " + path
        )
        self.inv_log.append("AI TARGET IPT: " + path + " · COMPONENT: " + str(comp["component_id"]))
        return True

    def start_pdf_ai_analysis(self):
        if not self.pdf_path:
            QMessageBox.information(self, "Chưa có PDF", "Hãy kéo thả hoặc chọn một file PDF bản vẽ trước.")
            return
        if self.ai_worker is not None and self.ai_worker.isRunning():
            QMessageBox.information(self, "Đang phân tích", "AI đang đọc bản vẽ này.")
            return
        try:
            configured_api_key = get_api_key()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi API Key", str(e))
            return
        if not configured_api_key:
            QMessageBox.warning(
                self, "Thiếu API Key",
                "Hãy nhập OpenAI API Key ở phía trên và nhấn Lưu cấu hình. "
                "API tính phí riêng, không dùng chung hạn mức ChatGPT."
            )
            return
        row = self.component_list.currentRow()
        if row < 0:
            if not self.link_active_ipt_for_ai():
                return
            row = self.component_list.currentRow()
        comp = self.project["components"][row]
        path = comp.get("inventor_file") or ""
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Chưa gắn IPT", "Hãy gắn một file IPT đã lưu vào chi tiết đích trước.")
            return
        try:
            if self.inventor_app is None:
                self.inventor_app = connect_inventor()
            doc = get_document_by_path(self.inventor_app, path)
            if doc is None:
                raise InventorBridgeError("Hãy mở đúng file IPT đã liên kết trong Inventor 2018.")
            self.ai_target_component_id = comp["component_id"]
            args = {
                "pdf_path": self.pdf_path,
                "model": self.ai_model_input.text().strip() or DEFAULT_MODEL,
                "detail": str(self.ai_detail_combo.currentData()),
                "project_id": self.project["project_id"],
                "component_id": self.ai_target_component_id,
                "part_name": comp.get("name", self.ai_target_component_id),
                "document_path": path,
            }
            self.ai_analyze_button.setEnabled(False)
            self.ai_to_command_button.setEnabled(False)
            self.ai_status_label.setText(
                "Đang gửi PDF lên OpenAI API để đọc hình chiếu, kích thước, mặt cắt và đặc tính hình học. "
                "Hãy giữ ứng dụng mở."
            )
            self.ai_worker = PdfAnalysisWorker(args, self)
            self.ai_worker.analysis_ready.connect(self.on_pdf_ai_analysis_ready)
            self.ai_worker.analysis_failed.connect(self.on_pdf_ai_analysis_failed)
            self.ai_worker.start()
        except Exception as e:
            self.ai_analyze_button.setEnabled(True)
            QMessageBox.warning(self, "Không thể phân tích PDF", str(e))

    def on_pdf_ai_analysis_ready(self, analysis):
        self.ai_analyze_button.setEnabled(True)
        self.ai_analysis = analysis
        report = format_analysis_report(analysis)
        if analysis.get("cad_command"):
            try:
                document = build_command_document(
                    analysis, self.project["project_id"], self.ai_target_component_id
                )
                report += "\n\nJSON LỆNH DỰ KIẾN\n" + json.dumps(document, ensure_ascii=False, indent=2)
                has_questions = bool(document.get("questions"))
                self.ai_to_command_button.setEnabled(not has_questions)
                self.ai_status_label.setText(
                    "AI đã phân tích xong và tạo được một lệnh hình học cơ bản. "
                    "Bạn vẫn cần kiểm tra JSON rồi xác nhận trước khi sửa IPT."
                    if not has_questions else
                    "AI còn câu hỏi chưa được làm rõ; chưa cho phép chuyển lệnh sang Inventor."
                )
            except Exception as e:
                self.ai_to_command_button.setEnabled(False)
                report += "\n\nKhông tạo được lệnh CAD: " + str(e)
                self.ai_status_label.setText("Đã đọc PDF nhưng lệnh CAD không đạt điều kiện an toàn.")
        else:
            self.ai_to_command_button.setEnabled(False)
            self.ai_status_label.setText(
                "Đã đọc PDF. Bản vẽ chưa thể dựng trung thực bằng nhóm feature hiện tại; "
                "xem câu hỏi/cảnh báo trong báo cáo. Không tự tạo khối thay thế."
            )
        self.ai_report.setPlainText(report)
        self.statusBar().showMessage("AI đã hoàn thành phân tích PDF.")

    def on_pdf_ai_analysis_failed(self, message):
        self.ai_analyze_button.setEnabled(True)
        self.ai_to_command_button.setEnabled(False)
        self.ai_status_label.setText("Phân tích thất bại.")
        self.ai_report.setPlainText("KHÔNG PHÂN TÍCH ĐƯỢC PDF\n\n" + message)
        QMessageBox.warning(self, "Lỗi phân tích AI", message)

    def send_ai_command_to_cad(self):
        if not self.ai_analysis or not self.ai_analysis.get("cad_command"):
            QMessageBox.information(self, "Chưa có lệnh CAD", "AI chưa tạo được lệnh hình học hợp lệ.")
            return
        try:
            document = build_command_document(
                self.ai_analysis,
                self.project["project_id"],
                self.ai_target_component_id,
            )
            if document.get("questions"):
                raise PdfAIError("Bản vẽ vẫn còn câu hỏi chưa được giải quyết; chưa được phép áp dụng.")
            self.command_text.setPlainText(json.dumps(document, ensure_ascii=False, indent=2))
            self.tabs.setCurrentWidget(self.command_tab)
            self.validate_commands()
        except Exception as e:
            QMessageBox.warning(self, "Không chuyển được lệnh CAD", str(e))

    def build_chat_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        root.addWidget(QLabel("Quy trình FREE MODE: xuất ngữ cảnh → dán vào ChatGPT → nhận JSON → nhập lệnh ở tab kế tiếp."))
        self.chat_instructions = QTextEdit()
        self.chat_instructions.setReadOnly(True)
        self.chat_instructions.setPlainText(
            "1. Nhấn 'Tạo gói gửi ChatGPT'.\\n"
            "2. Mở ChatGPT trên trình duyệt, dán toàn bộ nội dung tệp TXT.\\n"
            "3. Viết yêu cầu sửa bằng tiếng Việt.\\n"
            "4. Yêu cầu ChatGPT chỉ trả về JSON theo schema trong gói.\\n"
            "5. Lưu phần JSON trả lời thành tệp .json rồi nhập ở tab 'Nhập lệnh CAD'.\\n\\n"
            "Không cần tải PDF lên ChatGPT nếu hồ sơ tham số đã mô tả đủ chi tiết."
        )
        root.addWidget(self.chat_instructions, 1)
        row = QHBoxLayout()
        export = QPushButton("Tạo gói gửi ChatGPT"); export.clicked.connect(self.export_chat_context)
        copy = QPushButton("Sao chép ngữ cảnh"); copy.clicked.connect(self.copy_context)
        row.addWidget(export); row.addWidget(copy)
        root.addLayout(row)
        self.context_preview = QTextEdit()
        self.context_preview.setPlaceholderText("Nội dung ngữ cảnh sẽ hiện ở đây.")
        root.addWidget(self.context_preview, 2)
        return w

    def build_command_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        root.addWidget(QLabel("Nhập JSON do ChatGPT tạo. Ứng dụng kiểm tra mã chi tiết, tham số, kích thước, đơn vị và loại thao tác trước khi sửa IPT."))
        row = QHBoxLayout()
        loadb = QPushButton("Chọn tệp JSON"); loadb.clicked.connect(self.import_commands)
        validate = QPushButton("Kiểm tra lệnh"); validate.clicked.connect(self.validate_commands)
        applyb = QPushButton("Áp dụng lệnh"); applyb.clicked.connect(self.apply_commands)
        row.addWidget(loadb); row.addWidget(validate); row.addWidget(applyb)
        root.addLayout(row)
        self.command_text = QTextEdit()
        self.command_text.setPlaceholderText('Dán JSON lệnh vào đây hoặc chọn tệp .json')
        root.addWidget(self.command_text, 2)
        self.command_result = QTextEdit(); self.command_result.setReadOnly(True)
        self.command_result.setPlaceholderText("Kết quả kiểm tra và lịch sử thay đổi.")
        root.addWidget(self.command_result, 1)
        warning = QLabel("V0.5 hỗ trợ set_parameter, Sketch chữ nhật/tròn, Extrude và Extrude Cut. Chưa hỗ trợ Fillet, Chamfer hoặc IAM.")
        warning.setStyleSheet("color:#b91c1c;font-weight:600;")
        root.addWidget(warning)
        return w


    def build_inventor_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        label = QLabel("Mở một file IPT đã lưu trong Inventor 2018, kết nối để đọc tham số và liên kết với chi tiết. V0.5 có thể dựng Sketch chữ nhật và Extrude trực tiếp trên IPT này.")
        label.setWordWrap(True); root.addWidget(label)
        self.inv_status = QLabel("Chưa kết nối Inventor.")
        root.addWidget(self.inv_status)
        self.inv_doc_label = QLabel("Tài liệu: chưa đọc")
        self.inv_doc_label.setWordWrap(True); root.addWidget(self.inv_doc_label)
        row = QHBoxLayout()
        for caption, handler in [
            ("Kết nối Inventor", self.ui_connect_inventor),
            ("Đọc tài liệu", self.ui_read_inventor),
            ("Gắn IPT vào chi tiết", self.ui_link_inventor),
            ("Đồng bộ tham số", self.ui_sync_inventor)
        ]:
            btn = QPushButton(caption); btn.clicked.connect(handler); row.addWidget(btn)
        root.addLayout(row)
        self.inv_log = QTextEdit(); self.inv_log.setReadOnly(True); root.addWidget(self.inv_log, 1)
        return w

    def ui_connect_inventor(self):
        try:
            self.inventor_app = connect_inventor()
            version = str(self.inventor_app.SoftwareVersion.DisplayVersion)
            self.inv_status.setText("Đã kết nối Autodesk Inventor " + version)
            self.inv_log.append("KẾT NỐI THÀNH CÔNG · " + version)
            self.ui_read_inventor()
        except Exception as e:
            QMessageBox.warning(self, "Kết nối Inventor", str(e))

    def ui_read_inventor(self):
        try:
            if self.inventor_app is None: self.inventor_app = connect_inventor()
            doc = get_active_document(self.inventor_app)
            info = get_document_info(doc, self.inventor_app)
            params = read_parameters(doc)
            self.inv_doc_label.setText("Tài liệu: " + info["display_name"] + " · " + (info["full_path"] or "Chưa lưu"))
            self.inv_log.append("TÀI LIỆU: " + info["display_name"] + "\nĐƯỜNG DẪN: " + info["full_path"] + "\n" + "\n".join([k + " = " + str(v.get("expression")) for k,v in params.items()]))
            self.active_inventor_doc = doc
            return doc, info, params
        except Exception as e:
            QMessageBox.warning(self, "Đọc Inventor", str(e))
            return None, None, None

    def ui_link_inventor(self):
        row = self.component_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Chọn chi tiết", "Hãy chọn một chi tiết trong tab Dự án CAD.")
            return
        doc, info, params = self.ui_read_inventor()
        if doc is None: return
        if info["extension"] != ".ipt" or not info["full_path"] or not os.path.isfile(info["full_path"]):
            QMessageBox.warning(self, "File không hợp lệ", "Hãy mở và lưu một file IPT trước.")
            return
        comp = self.project["components"][row]
        comp["inventor_file"] = info["full_path"]
        comp["parameters"] = params
        self.refresh_project_view()
        if self.project_path: save_json(self.project_path, self.project)
        self.inv_log.append("ĐÃ GẮN IPT VỚI " + str(comp.get("component_id")))

    def ui_sync_inventor(self):
        row = self.component_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Chọn chi tiết", "Hãy chọn một chi tiết trong tab Dự án CAD.")
            return
        comp = self.project["components"][row]
        path = comp.get("inventor_file")
        if not path:
            QMessageBox.information(self, "Chưa liên kết", "Hãy gắn IPT vào chi tiết trước.")
            return
        try:
            if self.inventor_app is None: self.inventor_app = connect_inventor()
            doc = get_document_by_path(self.inventor_app, path)
            if doc is None: raise InventorBridgeError("Hãy mở đúng file IPT đã liên kết trong Inventor.")
            comp["parameters"] = read_parameters(doc)
            self.refresh_project_view()
            if self.project_path: save_json(self.project_path, self.project)
            self.inv_log.append("ĐÃ ĐỒNG BỘ THAM SỐ TỪ " + path)
        except Exception as e:
            QMessageBox.warning(self, "Đồng bộ Inventor", str(e))

    def update_project_name(self):
        self.project["project_name"] = self.project_name.text().strip() or "New CAD Project"

    def new_project(self):
        if QMessageBox.question(self, "Dự án mới", "Tạo dự án mới? Hãy lưu dự án hiện tại trước nếu cần.") != QMessageBox.Yes:
            return
        name, ok = QInputDialog.getText(self, "Tên dự án", "Nhập tên dự án:")
        if not ok: return
        self.project = default_project()
        self.project["project_name"] = name.strip() or "New CAD Project"
        self.project["project_id"] = "PROJECT_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self.project_path = None
        self.project_name.setText(self.project["project_name"])
        self.refresh_project_view()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở dự án PDF2Inventor", "", "Project JSON (*.json)")
        if not path: return
        try:
            data = load_json(path)
            if "components" not in data or "project_id" not in data:
                raise ValueError("Tệp không đúng cấu trúc dự án PDF2Inventor.")
            self.project = data; self.project_path = path
            self.project_name.setText(self.project.get("project_name", ""))
            self.refresh_project_view()
            self.statusBar().showMessage("Đã mở dự án.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi mở dự án", str(e))

    def save_project(self):
        self.update_project_name()
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Lưu dự án", "PDF2Inventor_Project.json", "Project JSON (*.json)")
        if not path: return
        try:
            save_json(path, self.project); self.project_path = path
            self.statusBar().showMessage(f"Đã lưu dự án: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi lưu", str(e))

    def add_component(self):
        cid, ok = QInputDialog.getText(self, "Thêm chi tiết", "Mã chi tiết (ví dụ PART_001):")
        if not ok or not cid.strip(): return
        if any(c["component_id"] == cid.strip() for c in self.project["components"]):
            QMessageBox.warning(self, "Trùng mã", "Mã chi tiết đã tồn tại."); return
        name, ok = QInputDialog.getText(self, "Tên chi tiết", "Tên chi tiết:")
        if not ok: return
        comp = {"component_id": cid.strip(), "name": name.strip() or cid.strip(),
                "document_type": "part", "inventor_file": None, "parameters": {},
                "features": [], "description": "Bổ sung mô tả chi tiết và tham số trước khi yêu cầu ChatGPT chỉnh sửa."}
        self.project["components"].append(comp)
        self.refresh_project_view()

    def edit_component_json(self):
        row = self.component_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Chọn chi tiết", "Hãy chọn một chi tiết."); return
        comp = self.project["components"][row]
        dlg = JsonEditor(json.dumps(comp, ensure_ascii=False, indent=2), self)
        if dlg.exec():
            try:
                updated = json.loads(dlg.editor.toPlainText())
                if updated.get("component_id") != comp.get("component_id"):
                    raise ValueError("Không được tự đổi component_id trong cửa sổ này.")
                self.project["components"][row] = updated
                self.refresh_project_view()
            except Exception as e:
                QMessageBox.critical(self, "JSON không hợp lệ", str(e))

    def refresh_project_view(self):
        self.component_list.clear()
        for c in self.project.get("components", []):
            self.component_list.addItem(f'{c.get("component_id")} · {c.get("name")}')
        self.project_view.setPlainText(json.dumps(self.project, ensure_ascii=False, indent=2))

    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn bản vẽ PDF", "", "PDF (*.pdf)")
        if path:
            self.load_pdf(path)

    def load_pdf(self, path):
        try:
            d = fitz.open(path)
            if not d.is_pdf or d.page_count < 1:
                d.close()
                raise ValueError("Tệp không phải PDF hợp lệ hoặc không có trang.")
            if self.pdf: self.pdf.close()
            self.pdf = d; self.pdf_path = path
            self.project["source_pdf"] = os.path.basename(path)
            self.pdf_label.setText(os.path.basename(path))
            self.ai_pdf_label.setText("PDF: " + path)
            self.page_list.clear()
            for i, page in enumerate(d):
                self.page_list.addItem(f"Trang {i+1} · {page.rect.width:.0f}×{page.rect.height:.0f} pt")
            self.page_list.setCurrentRow(0)
            self.ai_analysis = None
            self.ai_to_command_button.setEnabled(False)
            self.ai_report.clear()
            self.ai_status_label.setText("Đã nạp PDF. Hãy gắn file IPT đích và nhấn ĐỌC PDF VÀ PHÂN TÍCH.")
            self.tabs.setCurrentWidget(self.tabs.widget(1))
            self.statusBar().showMessage("Đã nạp PDF: " + os.path.basename(path))
        except Exception as e:
            QMessageBox.critical(self, "Không mở được PDF", str(e))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for url in urls:
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.load_pdf(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def show_page(self, index):
        if not self.pdf or index < 0 or index >= self.pdf.page_count: return
        self.page_index = index
        page = self.pdf.load_page(index)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.4,1.4), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        txt = page.get_text("text").strip()
        self.pdf_info.setText(f"Trang {index+1}/{self.pdf.page_count} · {len(page.get_drawings())} vector paths · {len(page.get_images(full=True))} ảnh · {len(txt)} ký tự text")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pdf: self.show_page(self.page_index)

    def build_context_text(self):
        self.update_project_name()
        context = {
            "purpose": "Hiểu dự án CAD và tạo lệnh sửa tham số hoặc dựng hình học cơ bản trong Inventor 2018. Không tự giả định kích thước còn thiếu.",
            "project": self.project,
            "command_schema": {
                "project_id": self.project["project_id"],
                "commands": [{
                    "op": "set_parameter",
                    "component_id": "MÃ_CHI_TIẾT_CÓ_TRONG_HỒ_SƠ",
                    "parameter": "TÊN_THAM_SỐ_CÓ_TRONG_HỒ_SƠ",
                    "value": 550,
                    "unit": "mm",
                    "reason": "Lý do thay đổi ngắn gọn"
                }],
                "questions": [],
                "warnings": []
            },
            "geometry_command_schema": {
                "op": "create_rectangle_extrude",
                "component_id": "MÃ_CHI_TIẾT_CÓ_IPT_ĐÃ_GẮN",
                "length": 150,
                "width": 70,
                "thickness": 8,
                "origin_x": 0,
                "origin_y": 0,
                "unit": "mm",
                "operation": "auto",
                "direction": "positive",
                "reason": "Tạo khối chữ nhật kiểm thử"
            },
            "circle_command_schema": {
                "op": "create_circle_extrude",
                "component_id": "MÃ_CHI_TIẾT_CÓ_IPT_ĐÃ_GẮN",
                "diameter": 20,
                "thickness": 8,
                "center_x": 0,
                "center_y": 0,
                "unit": "mm",
                "operation": "cut",
                "direction": "positive",
                "reason": "Tạo lỗ tròn bằng Extrude Cut"
            }
        }
        instruction = (
            "Bạn là trợ lý thiết kế cơ khí cho PDF2Inventor AI V0.5, Autodesk Inventor 2018. "
            "Đọc hồ sơ JSON bên dưới và yêu cầu của người dùng. "
            "Với set_parameter, chỉ dùng component_id và parameter có sẵn trong hồ sơ. "
            "Với create_rectangle_extrude, tạo Sketch chữ nhật trên mặt phẳng XY và Extrude/Cut; bắt buộc có length, width, thickness và unit=mm. "
            "origin_x và origin_y là tọa độ góc đầu tiên từ gốc XY, mặc định 0 mm nếu người dùng không chỉ định. "
            "Với create_circle_extrude, tạo Sketch tròn có đường kính điều khiển và Extrude/Cut; bắt buộc có diameter, thickness và unit=mm. "
            "center_x và center_y là tọa độ tâm hình tròn, mặc định 0 mm nếu người dùng không chỉ định. "
            "operation chỉ được dùng auto, join, new_body hoặc cut; direction chỉ được dùng positive hoặc negative. "
            "Mỗi gói JSON chỉ dùng một chế độ: set_parameter (có thể nhiều lệnh) hoặc đúng một lệnh create_rectangle_extrude/create_circle_extrude. Không trộn hai loại lệnh. "
            "Không tự bịa kích thước, không tự đổi đơn vị ngầm định. Nếu thiếu hoặc mơ hồ, trả commands rỗng và ghi câu hỏi vào questions. "
            "Nếu thay đổi ảnh hưởng các chi tiết lắp ráp, ghi cảnh báo vào warnings. "
            "Chỉ trả về một JSON hợp lệ, không Markdown, không giải thích bên ngoài JSON. "
            "V0.5 chưa hỗ trợ native Hole, Fillet, Chamfer, Pattern hoặc xóa Feature; lỗ tròn đơn giản dùng create_circle_extrude với operation=cut."
        )
        return instruction + "\n\n--- CAD PROJECT CONTEXT ---\n" + json.dumps(context, ensure_ascii=False, indent=2)

    def export_chat_context(self):
        text = self.build_context_text()
        path, _ = QFileDialog.getSaveFileName(self, "Lưu gói ngữ cảnh ChatGPT", "ChatGPT_CAD_Context.txt", "Text (*.txt)")
        if path:
            Path(path).write_text(text, encoding="utf-8")
        self.context_preview.setPlainText(text)
        self.statusBar().showMessage("Đã tạo gói ngữ cảnh. Mở ChatGPT và dán nội dung tệp TXT.")

    def copy_context(self):
        text = self.build_context_text()
        QApplication.clipboard().setText(text)
        self.context_preview.setPlainText(text)
        self.statusBar().showMessage("Đã sao chép ngữ cảnh CAD vào clipboard.")

    def import_commands(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn JSON lệnh từ ChatGPT", "", "JSON (*.json)")
        if not path: return
        try:
            data = load_json(path)
            self.command_text.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.pending_commands = data
            self.validate_commands()
        except Exception as e:
            QMessageBox.critical(self, "Không đọc được JSON", str(e))

    def parse_commands(self):
        data = json.loads(self.command_text.toPlainText())
        if data.get("project_id") != self.project.get("project_id"):
            raise ValueError("project_id không khớp dự án đang mở.")
        if not isinstance(data.get("commands", []), list):
            raise ValueError("'commands' phải là danh sách.")
        return data

    def validate_commands(self):
        try:
            data = self.parse_commands()
            issues = []
            commands = data.get("commands", [])
            geometry_commands = [cmd for cmd in commands if isinstance(cmd, dict) and cmd.get("op") in {"create_rectangle_extrude", "create_circle_extrude"}]
            if geometry_commands and len(commands) != 1:
                issues.append("Lệnh create_rectangle_extrude phải đứng riêng trong một gói JSON; không trộn với set_parameter hoặc lệnh hình học khác.")
            for i, cmd in enumerate(commands, 1):
                if not isinstance(cmd, dict):
                    issues.append(f"Lệnh {i}: mỗi phần tử commands phải là một đối tượng JSON.")
                    continue
                op = cmd.get("op")
                comp = next((c for c in self.project["components"] if c.get("component_id") == cmd.get("component_id")), None)
                if not comp:
                    issues.append(f'Lệnh {i}: không tìm thấy chi tiết {cmd.get("component_id")}.')
                    continue
                if op == "set_parameter":
                    if cmd.get("parameter") not in comp.get("parameters", {}):
                        issues.append(f'Lệnh {i}: tham số "{cmd.get("parameter")}" không tồn tại trong chi tiết.')
                    if isinstance(cmd.get("value"), bool) or not isinstance(cmd.get("value"), (int, float)):
                        issues.append(f"Lệnh {i}: value phải là số.")
                    current = comp.get("parameters", {}).get(cmd.get("parameter"), {})
                    if isinstance(current, dict) and cmd.get("unit") != current.get("unit"):
                        issues.append(f'Lệnh {i}: đơn vị lệnh ({cmd.get("unit")}) khác đơn vị tham số ({current.get("unit")}).')
                elif op == "create_rectangle_extrude":
                    if not comp.get("inventor_file"):
                        issues.append(f'Lệnh {i}: chi tiết {cmd.get("component_id")} chưa được gắn với file IPT.')
                    try:
                        validate_rectangle_command(cmd)
                    except Exception as e:
                        issues.append(f"Lệnh {i}: {e}")
                elif op == "create_circle_extrude":
                    if not comp.get("inventor_file"):
                        issues.append(f'Lệnh {i}: chi tiết {cmd.get("component_id")} chưa được gắn với file IPT.')
                    try:
                        validate_circle_command(cmd)
                    except Exception as e:
                        issues.append(f"Lệnh {i}: {e}")
                else:
                    issues.append(f"Lệnh {i}: thao tác '{op}' chưa được hỗ trợ trong V0.5.")
            if not commands and not data.get("questions"):
                issues.append("Không có lệnh hoặc câu hỏi nào.")
            self.pending_commands = data
            msg = "KIỂM TRA HOÀN TẤT\n"
            msg += f"Số lệnh: {len(commands)}\n"
            msg += f"Câu hỏi cần làm rõ: {len(data.get('questions', []))}\n"
            msg += f"Cảnh báo: {len(data.get('warnings', []))}\n\n"
            msg += "\n".join(issues) if issues else "Không phát hiện lỗi cấu trúc cơ bản."
            if data.get("questions"): msg += "\n\nCÂU HỎI:\n" + "\n".join(map(str, data["questions"]))
            if data.get("warnings"): msg += "\n\nCẢNH BÁO:\n" + "\n".join(map(str, data["warnings"]))
            self.command_result.setPlainText(msg)
            return not issues
        except Exception as e:
            self.command_result.setPlainText("JSON / kiểm tra không hợp lệ:\n" + str(e))
            return False

    def apply_commands(self):
        if not self.validate_commands():
            QMessageBox.warning(self, "Chưa thể áp dụng", "Hãy sửa lỗi hoặc bổ sung thông tin trước."); return
        data = self.pending_commands
        if data.get("questions"):
            QMessageBox.warning(
                self, "Chưa đủ dữ liệu",
                "Bản vẽ còn câu hỏi cần làm rõ. Hãy giải quyết các câu hỏi trước khi cho phép Inventor thay đổi mô hình."
            )
            return
        if not data.get("commands"):
            QMessageBox.information(self, "Không có thay đổi", "AI/ChatGPT chưa đưa ra lệnh sửa nào."); return
        targets = []
        for cmd in data["commands"]:
            comp = next(c for c in self.project["components"] if c["component_id"] == cmd["component_id"])
            targets.append((comp, cmd))

        # Geometry operations are intentionally a single-command transaction in V0.5.
        if targets and targets[0][1].get("op") in {"create_rectangle_extrude", "create_circle_extrude"}:
            comp, cmd = targets[0]
            path = comp.get("inventor_file")
            try:
                if self.inventor_app is None: self.inventor_app = connect_inventor()
                doc = get_document_by_path(self.inventor_app, path)
                if doc is None:
                    raise InventorBridgeError("Hãy mở đúng file IPT đã liên kết trong Inventor.")
            except Exception as e:
                QMessageBox.warning(self, "Inventor", str(e)); return
            if cmd["op"] == "create_rectangle_extrude":
                dims = (
                    f'Dài X: {cmd["length"]} mm · Rộng Y: {cmd["width"]} mm · '
                    f'Đùn Z: {cmd["thickness"]} mm · Gốc: ({cmd.get("origin_x", 0)}, {cmd.get("origin_y", 0)}) mm'
                )
            else:
                dims = (
                    f'Đường kính: {cmd["diameter"]} mm · Đùn/Cắt Z: {cmd["thickness"]} mm · '
                    f'Tâm: ({cmd.get("center_x", 0)}, {cmd.get("center_y", 0)}) mm'
                )
            intro = (
                "Sẽ tạo hình học thật trong Inventor 2018: " + str(path) + "\n" +
                dims + "\nOperation: " + str(cmd.get("operation", "auto")) +
                "\nSẽ tạo file backup trước khi thay đổi."
            )
            if QMessageBox.question(self, "Xác nhận tạo Sketch/Extrude", intro + "\n\nTiếp tục?") != QMessageBox.Yes:
                return
            try:
                if cmd["op"] == "create_rectangle_extrude":
                    result = create_rectangle_extrude(doc, self.inventor_app, cmd)
                else:
                    result = create_circle_extrude(doc, self.inventor_app, cmd)
                comp["parameters"] = copy.deepcopy(result["parameters"])
                self.project["change_history"].append({
                    "timestamp": now(),
                    "component_id": cmd["component_id"],
                    "operation": cmd["op"],
                    "dimensions_mm": result["dimensions_mm"],
                    "parameter_names": result["parameter_names"],
                    "backup_file": result["backup_path"],
                    "inventor_file": result["document_path"],
                    "source": "ChatGPT manual",
                    "applied_to_inventor": True,
                    "reason": cmd.get("reason", "")
                })
                self.inv_log.append(
                    "ĐÃ TẠO SKETCH + FEATURE TRONG INVENTOR\n"
                    + "FILE: " + result["document_path"] + "\n"
                    + "BACKUP: " + result["backup_path"] + "\n"
                    + "THAM SỐ: " + json.dumps(result["parameter_names"], ensure_ascii=False)
                )
                self.refresh_project_view()
                if self.project_path: save_json(self.project_path, self.project)
                else: self.save_project()
                self.command_result.append(
                    "\nĐÃ TẠO SKETCH + FEATURE TRONG INVENTOR. Backup: " + result["backup_path"]
                )
                QMessageBox.information(
                    self, "Hoàn tất",
                    "Đã tạo Sketch và Extrude/Cut trong Inventor.\n"
                    "Backup: " + result["backup_path"]
                )
            except Exception as e:
                QMessageBox.critical(self, "Lỗi tạo hình học", str(e))
            return

        paths = {os.path.normcase(os.path.abspath(c.get("inventor_file", ""))) for c,cmd in targets if c.get("inventor_file")}
        if paths and (len(paths) != 1 or any(not c.get("inventor_file") for c,cmd in targets)):
            QMessageBox.warning(self, "Nhiều file IPT", "Hãy chia lệnh theo từng file IPT."); return
        use_inv = bool(paths)
        doc = None
        path = next(iter(paths)) if paths else None
        if use_inv:
            try:
                if self.inventor_app is None: self.inventor_app = connect_inventor()
                doc = get_document_by_path(self.inventor_app, path)
                if doc is None: raise InventorBridgeError("Hãy mở đúng file IPT đã liên kết trong Inventor.")
            except Exception as e:
                QMessageBox.warning(self, "Inventor", str(e)); return
        lines = []
        for comp,cmd in targets:
            p = comp["parameters"].get(cmd["parameter"], {})
            old = p.get("expression", p.get("value")) if isinstance(p,dict) else p
            lines.append(str(cmd["component_id"]) + " · " + cmd["parameter"] + ": " + str(old) + " → " + str(cmd["value"]) + " " + str(cmd["unit"]))
        intro = ("Sẽ sửa mô hình Inventor thật: " + str(path) + "\nSẽ tạo bản sao dự phòng trước khi sửa." if use_inv else "Chỉ cập nhật hồ sơ JSON; chưa liên kết IPT.")
        if QMessageBox.question(self, "Xác nhận áp dụng", intro + "\n\n" + "\n".join(lines) + "\n\nTiếp tục?") != QMessageBox.Yes: return
        backup = None
        if use_inv:
            changes = [{"parameter":cmd["parameter"],"value":cmd["value"],"unit":cmd["unit"]} for comp,cmd in targets]
            try:
                result = apply_parameter_changes(doc, changes)
                backup = result["backup_path"]
                self.inv_log.append("ĐÃ SỬA IPT: " + path + "\nBACKUP: " + backup)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi Inventor", str(e)); return
        for comp,cmd in targets:
            p = comp["parameters"].get(cmd["parameter"], {})
            old = p.get("expression", p.get("value")) if isinstance(p,dict) else p
            comp["parameters"][cmd["parameter"]] = {"value":cmd["value"],"unit":cmd["unit"],"expression":str(cmd["value"])+" "+str(cmd["unit"])}
            self.project["change_history"].append({"timestamp":now(),"component_id":cmd["component_id"],"parameter":cmd["parameter"],"old_value":old,"new_value":cmd["value"],"unit":cmd["unit"],"reason":cmd.get("reason",""),"source":"ChatGPT manual","applied_to_inventor":use_inv,"inventor_file":path,"backup_file":backup})
        if use_inv:
            try:
                verified = read_parameters(doc)
                for comp,cmd in targets: comp["parameters"] = copy.deepcopy(verified)
            except Exception: pass
        self.refresh_project_view()
        if self.project_path: save_json(self.project_path,self.project)
        else: self.save_project()
        if use_inv:
            self.command_result.append("\nĐÃ CẬP NHẬT INVENTOR THẬT. Backup: " + str(backup))
            QMessageBox.information(self,"Hoàn tất","Đã cập nhật Inventor và lưu IPT.\nBackup: "+str(backup))
        else:
            self.command_result.append("\nĐã cập nhật hồ sơ JSON; Inventor không thay đổi.")
            QMessageBox.information(self,"Hoàn tất","Đã cập nhật hồ sơ JSON. Chưa liên kết IPT.")

class JsonEditor(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa dữ liệu chi tiết (JSON)")
        self.resize(700, 600)
        layout = QVBoxLayout(self)
        self.editor = QTextEdit(); self.editor.setPlainText(text)
        layout.addWidget(self.editor)
        row = QHBoxLayout()
        ok = QPushButton("Lưu"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Hủy"); cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(ok); row.addWidget(cancel)
        layout.addLayout(row)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
