# PDF2Inventor AI V0.4 · Inventor COM

## Chức năng
- Giữ chế độ ChatGPT thủ công, không dùng API.
- Tạo/mở/lưu hồ sơ dự án JSON.
- Mở và xem PDF cục bộ bằng PyMuPDF.
- Kết nối Autodesk Inventor đang chạy qua COM.
- Đọc tham số của file IPT đang mở.
- Liên kết file IPT với một chi tiết trong hồ sơ dự án.
- Đồng bộ tham số Inventor vào hồ sơ.
- Nhận lệnh JSON `set_parameter`; nếu chi tiết đã liên kết với IPT đang mở, ứng dụng xác nhận trước, tạo bản sao dự phòng, cập nhật tham số Inventor, gọi Update và Save.
- Ghi lịch sử thay đổi và đường dẫn backup.

## Giới hạn V0.4
- Chỉ hỗ trợ cập nhật tham số của một file chi tiết `.ipt` trong một lần áp dụng.
- Không tự tạo Sketch/Extrude/Hole mới trong V0.4.
- Không hỗ trợ sửa IAM, BOM hay các lệnh hình học topo.
- Cầu nối cần Autodesk Inventor cài trên Windows và đang chạy. EXE không mang Inventor theo.
- Khi chưa liên kết IPT, lệnh vẫn chỉ cập nhật hồ sơ JSON.
- PDF hiện mới xem/trích xuất thông tin cơ bản; OCR và nhận dạng bản vẽ nâng cao chưa có.

## Cách sử dụng
1. Mở Autodesk Inventor 2018 và mở file IPT cần điều khiển.
2. Mở PDF2Inventor AI.
3. Vào tab Inventor 2018 → Kết nối Inventor.
4. Vào tab Dự án CAD, chọn chi tiết cần liên kết.
5. Quay lại tab Inventor 2018 → Gắn IPT vào chi tiết đã chọn.
6. Nhấn Đọc tham số vào hồ sơ.
7. Tạo gói ngữ cảnh, gửi ChatGPT thủ công và nhập JSON lệnh.
8. Kiểm tra lệnh; nhấn Áp dụng và xác nhận. Ứng dụng sẽ tạo backup trước khi sửa IPT.

## Build EXE
Chạy GitHub Actions workflow `Build PDF2Inventor AI for Windows` trên nhánh `feature/v0.4-inventor-com`. Tải artifact `PDF2Inventor_AI_Windows_x64` khi build thành công.

Người dùng cuối không cần cài Python. Máy build GitHub Actions cài Python, PySide6, PyMuPDF, pywin32 và PyInstaller.

## An toàn
- Không ghi đè nhánh `main`; V0.4 được phát triển trên nhánh riêng `feature/v0.4-inventor-com`.
- Mỗi lần cập nhật tham số IPT đều tạo file backup bên cạnh file gốc.
- Nếu cập nhật thất bại, cầu nối cố gắng khôi phục biểu thức tham số cũ và báo vị trí backup.
