# PDF2Inventor AI V0.3 Portable

Bản đóng gói hướng tới ứng dụng Windows EXE độc lập. Người dùng cuối không cần cài Python.

## Lấy file EXE (không cài Python trên máy của bạn)

Xem `BUILD_EXE_ON_GITHUB.md`. GitHub Actions sử dụng máy Windows tạm thời để đóng gói ứng dụng và cung cấp file EXE tải về dưới dạng Artifact.

## Chức năng hiện có

- Tạo/mở/lưu hồ sơ dự án JSON.
- Quản lý danh sách chi tiết và tham số CAD.
- Mở PDF cục bộ để xem trang.
- Xuất ngữ cảnh dự án để dán vào ChatGPT.
- Nhập JSON lệnh do ChatGPT trả về.
- Kiểm tra project ID, component ID, tham số, kiểu số và đơn vị.
- Xác nhận trước khi cập nhật hồ sơ và ghi lịch sử thay đổi.
- FREE MODE: không cần API key.

## Giới hạn

V0.3 Portable hiện vẫn là ứng dụng quản lý ngữ cảnh và tham số JSON. Chưa điều khiển Inventor 2018 để sửa hình học IPT/IAM. Không được coi việc cập nhật JSON là đã sửa mô hình CAD.

## Build

- Người dùng cuối: tải EXE từ GitHub Actions Artifact, không cần Python.
- Máy build riêng: chạy `build_windows_exe.bat` (cần Python 3.12 64-bit).
