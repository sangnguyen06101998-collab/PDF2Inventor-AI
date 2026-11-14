# Tạo PDF2Inventor_AI.exe mà không cài Python trên máy sử dụng

## Cách làm bằng GitHub Actions

1. Tạo một repository GitHub mới (có thể để Private).
2. Tải toàn bộ thư mục dự án này lên repository, giữ nguyên thư mục `.github/workflows`.
3. Mở tab **Actions** của repository.
4. Chọn workflow **Build PDF2Inventor AI for Windows**.
5. Nhấn **Run workflow** và chờ build hoàn tất.
6. Mở lần chạy vừa hoàn tất, kéo xuống **Artifacts**, tải `PDF2Inventor_AI_Windows_x64`.
7. Giải nén artifact và chạy `PDF2Inventor_AI.exe` trên Windows 10/11 64-bit.

Python chỉ được cài trong máy build Windows tạm thời của GitHub Actions. Máy tính sử dụng ứng dụng không cần Python, không cần pip, không cần virtual environment.

## Cách build trực tiếp trên máy Windows (tùy chọn)

Chạy `build_windows_exe.bat`. Cách này cần Python 3.12 64-bit trên máy build; không cần làm nếu dùng GitHub Actions.

## Giới hạn của phiên bản

- EXE chứa ứng dụng V0.3 Portable dựa trên mã nguồn V0.2 Manual Chat.
- PDF được đọc và xử lý cục bộ; chế độ ChatGPT vẫn là sao chép ngữ cảnh / nhập JSON thủ công, không dùng API.
- Phiên bản này CHƯA tạo hoặc chỉnh sửa hình học IPT/IAM thực tế trong Inventor. Bridge Inventor 2018 sẽ được phát triển riêng sau khi kiểm tra ứng dụng chạy ổn định.
- Để mở PDF, dữ liệu dự án và các file đã xuất, ứng dụng cần quyền đọc/ghi thư mục người dùng.
