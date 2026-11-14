# PDF2Inventor Local Edition V0.6 · Offline vector-first PDF + Inventor 2018

## Chức năng hiện có
- Tạo, mở và lưu hồ sơ dự án JSON.
- Mở và xem PDF cục bộ bằng PyMuPDF.
- Phân tích PDF cục bộ: trích xuất text spans, vị trí chữ, ứng viên kích thước, vector paths và bounding box.
- Xuất báo cáo JSON chứa dữ liệu vector/text để kiểm tra và xử lý tiếp.
- Kết nối Autodesk Inventor đang chạy qua COM.
- Đọc tham số của file IPT đang mở và liên kết IPT với chi tiết trong hồ sơ.
- Nhận lệnh JSON set_parameter; ứng dụng xác nhận, tạo backup, cập nhật tham số, gọi Update và Save.
- Nhận lệnh create_rectangle_extrude để tạo Sketch chữ nhật trên XY và Extrude.
- Nhận lệnh create_circle_extrude để tạo Sketch tròn và Extrude/Cut.
- Phân tích PDF chạy tại máy; không gọi OpenAI API, không gửi PDF ra mạng, không cần GPU.

## V0.6 Local Edition · Cách phân tích PDF
1. Chạy EXE trên Windows 64-bit.
2. Mở tab PDF và chọn PDF bản vẽ.
3. Nhấn **Phân tích PDF vector tại máy**.
4. Kiểm tra số vector paths, text spans và các kích thước tìm được.
5. Nhấn **Xuất báo cáo JSON** để lưu toàn bộ dữ liệu trích xuất.

## Nguyên tắc tỷ lệ và kích thước
- Tọa độ PDF được trích xuất theo point (1/72 inch), không được tự coi là mm.
- Kích thước ghi bằng số trên bản vẽ là nguồn chuẩn để hiệu chuẩn tỷ lệ.
- V0.6 hiện chưa tự động ghép mọi đường bao thành biên dạng 2D và chưa tự suy ra chiều sâu 3D.
- Không được dựng hình khi kích thước hoặc hình chiếu còn mơ hồ. Không tự đoán tỷ lệ, độ dày, lỗ khuất, ren, bo/vát hoặc cấu tạo lắp ráp.
- Nếu PDF là ảnh scan, cần bổ sung OCR cục bộ; nhánh hiện tại ưu tiên PDF vector.

## Giới hạn dựng hình
- Hình học Inventor hiện hỗ trợ Sketch chữ nhật/tròn và Extrude/Cut cơ bản.
- Chưa hỗ trợ tự động dựng mọi biên dạng tự do, nhiều mặt phẳng, Fillet, Chamfer, Pattern, ren hoặc assembly IAM.
- Kiểm thử CI xác nhận logic Python và khả năng build; không thay thế kiểm thử COM geometry trên Autodesk Inventor 2018 thật.

## Build EXE
GitHub Actions workflow Build PDF2Inventor AI for Windows chạy trên nhánh feature/v0.6-local-edition. Khi build thành công, tải artifact PDF2Inventor_AI_Windows_x64 trong trang Actions.

Người dùng cuối không cần cài Python. Máy build GitHub Actions tự cài Python, PySide6, PyMuPDF, pywin32 và PyInstaller.

## An toàn
- Không sửa nhánh main; bản Local Edition phát triển trên nhánh feature/v0.6-local-edition.
- Trước thao tác hình học, ứng dụng yêu cầu xác nhận.
- Các thay đổi thật trên IPT tạo file backup bên cạnh file gốc.
- Nếu tạo hình học thất bại, ứng dụng cố gắng hủy transaction và báo lỗi.
