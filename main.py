import sys, json, os, copy
from pathlib import Path
from datetime import datetime
import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QTextEdit, QFileDialog, QMessageBox, QSplitter,
    QGroupBox, QLineEdit, QTabWidget, QInputDialog, QDialog
)

APP_TITLE = "PDF2Inventor AI · V0.3 Portable"
SCHEMA_VERSION = "0.2"

def now():
    return datetime.now().isoformat(timespec="seconds")

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
            "Các thay đổi trong V0.2 mới cập nhật hồ sơ JSON, chưa điều khiển hình học Inventor."
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

        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self.build_project_tab(), "Dự án CAD")
        tabs.addTab(self.build_pdf_tab(), "PDF")
        tabs.addTab(self.build_chat_tab(), "ChatGPT thủ công")
        tabs.addTab(self.build_command_tab(), "Nhập lệnh CAD")
        self.tabs = tabs
        self.refresh_project_view()
        self.statusBar().showMessage("V0.3 PORTABLE · Không cần cài Python · FREE MODE · Dữ liệu lưu cục bộ")

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
        note = QLabel("V0.2 lưu hồ sơ tham số và lịch sử. Chưa thay đổi hình học trong Inventor.")
        note.setStyleSheet("color:#b45309;")
        root.addWidget(note)
        return w

    def build_pdf_tab(self):
        w = QWidget(); root = QVBoxLayout(w)
        top = QHBoxLayout()
        openb = QPushButton("Mở PDF"); openb.clicked.connect(self.open_pdf)
        self.pdf_label = QLabel("Chưa chọn PDF")
        top.addWidget(openb); top.addWidget(self.pdf_label, 1)
        root.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        self.page_list = QListWidget(); self.page_list.currentRowChanged.connect(self.show_page)
        self.preview = QLabel("Mở PDF để xem bản vẽ")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(500, 400)
        self.preview.setStyleSheet("background:#e2e8f0;color:#475569;")
        split.addWidget(self.page_list); split.addWidget(self.preview)
        split.setSizes([180, 1000])
        root.addWidget(split, 1)
        self.pdf_info = QLabel("PDF được xử lý tại máy tính, không tự động gửi lên ChatGPT.")
        root.addWidget(self.pdf_info)
        return w

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
        root.addWidget(QLabel("Nhập JSON do ChatGPT tạo. Ứng dụng sẽ kiểm tra mã chi tiết, tên tham số, đơn vị và giá trị trước khi ghi vào hồ sơ dự án."))
        row = QHBoxLayout()
        loadb = QPushButton("Chọn tệp JSON"); loadb.clicked.connect(self.import_commands)
        validate = QPushButton("Kiểm tra lệnh"); validate.clicked.connect(self.validate_commands)
        applyb = QPushButton("Áp dụng vào hồ sơ"); applyb.clicked.connect(self.apply_commands)
        row.addWidget(loadb); row.addWidget(validate); row.addWidget(applyb)
        root.addLayout(row)
        self.command_text = QTextEdit()
        self.command_text.setPlaceholderText('Dán JSON lệnh vào đây hoặc chọn tệp .json')
        root.addWidget(self.command_text, 2)
        self.command_result = QTextEdit(); self.command_result.setReadOnly(True)
        self.command_result.setPlaceholderText("Kết quả kiểm tra và lịch sử thay đổi.")
        root.addWidget(self.command_result, 1)
        warning = QLabel("CẢNH BÁO: V0.2 chỉ cập nhật dữ liệu tham số trong project.json. Chưa sửa file IPT/IAM trong Inventor.")
        warning.setStyleSheet("color:#b91c1c;font-weight:600;")
        root.addWidget(warning)
        return w

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
        if not path: return
        try:
            d = fitz.open(path)
            if self.pdf: self.pdf.close()
            self.pdf = d; self.pdf_path = path
            self.project["source_pdf"] = os.path.basename(path)
            self.pdf_label.setText(os.path.basename(path))
            self.page_list.clear()
            for i, p in enumerate(d):
                self.page_list.addItem(f"Trang {i+1} · {p.rect.width:.0f}×{p.rect.height:.0f} pt")
            self.page_list.setCurrentRow(0)
        except Exception as e:
            QMessageBox.critical(self, "Không mở được PDF", str(e))

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
            "purpose": "Hiểu dự án CAD và đề xuất lệnh sửa tham số. Không tự giả định kích thước còn thiếu.",
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
            }
        }
        instruction = (
            "Bạn là trợ lý thiết kế cơ khí cho PDF2Inventor AI, Inventor 2018. "
            "Đọc hồ sơ JSON bên dưới và yêu cầu sửa của người dùng. "
            "Chỉ tạo lệnh set_parameter nếu component_id và parameter tồn tại chính xác trong hồ sơ. "
            "Không tự bịa kích thước, không tự đổi đơn vị ngầm định. "
            "Nếu mơ hồ, trả commands rỗng và ghi câu hỏi vào questions. "
            "Nếu thay đổi ảnh hưởng các chi tiết lắp ráp, ghi cảnh báo vào warnings. "
            "Chỉ trả về một JSON hợp lệ, không Markdown, không giải thích bên ngoài JSON. "
            "Không tạo lệnh xóa feature hoặc thay đổi hình học topo ở chế độ này."
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
            for i, cmd in enumerate(data.get("commands", []), 1):
                if cmd.get("op") != "set_parameter":
                    issues.append(f"Lệnh {i}: chỉ hỗ trợ set_parameter trong V0.2."); continue
                comp = next((c for c in self.project["components"] if c["component_id"] == cmd.get("component_id")), None)
                if not comp:
                    issues.append(f'Lệnh {i}: không tìm thấy chi tiết {cmd.get("component_id")}.'); continue
                if cmd.get("parameter") not in comp.get("parameters", {}):
                    issues.append(f'Lệnh {i}: tham số "{cmd.get("parameter")}" không tồn tại trong chi tiết.')
                if not isinstance(cmd.get("value"), (int, float)):
                    issues.append(f"Lệnh {i}: value phải là số.")
                current = comp.get("parameters", {}).get(cmd.get("parameter"), {})
                if isinstance(current, dict) and cmd.get("unit") != current.get("unit"):
                    issues.append(f'Lệnh {i}: đơn vị lệnh ({cmd.get("unit")}) khác đơn vị tham số ({current.get("unit")}).')
            if not data.get("commands") and not data.get("questions"):
                issues.append("Không có lệnh hoặc câu hỏi nào.")
            self.pending_commands = data
            msg = "KIỂM TRA HOÀN TẤT\n"
            msg += f"Số lệnh: {len(data.get('commands', []))}\n"
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
        if not data.get("commands"):
            QMessageBox.information(self, "Không có thay đổi", "ChatGPT chưa đưa ra lệnh sửa nào."); return
        preview = []
        for cmd in data["commands"]:
            comp = next(c for c in self.project["components"] if c["component_id"] == cmd["component_id"])
            p = comp["parameters"][cmd["parameter"]]
            old = p["value"] if isinstance(p, dict) else p
            preview.append(f'{cmd["component_id"]} · {cmd["parameter"]}: {old} → {cmd["value"]} {cmd["unit"]}')
        if QMessageBox.question(self, "Xác nhận áp dụng", "Các thay đổi vào hồ sơ dự án (chưa sửa Inventor):\n\n" + "\n".join(preview) + "\n\nTiếp tục?") != QMessageBox.Yes:
            return
        for cmd in data["commands"]:
            comp = next(c for c in self.project["components"] if c["component_id"] == cmd["component_id"])
            param = comp["parameters"][cmd["parameter"]]
            if isinstance(param, dict):
                old = param.get("value")
                param["value"] = cmd["value"]
            else:
                old = param
                comp["parameters"][cmd["parameter"]] = {"value": cmd["value"], "unit": cmd["unit"]}
            self.project["change_history"].append({
                "timestamp": now(), "component_id": cmd["component_id"],
                "parameter": cmd["parameter"], "old_value": old,
                "new_value": cmd["value"], "unit": cmd["unit"],
                "reason": cmd.get("reason", ""), "source": "ChatGPT manual"
            })
        self.refresh_project_view()
        self.save_project()
        self.command_result.append("\n\nĐã cập nhật hồ sơ JSON. Chưa thay đổi hình học trong Inventor; cầu nối Inventor sẽ được triển khai ở phiên bản sau.")
        QMessageBox.information(self, "Đã cập nhật hồ sơ", "Đã lưu thông số và lịch sử thay đổi vào dự án.")

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
