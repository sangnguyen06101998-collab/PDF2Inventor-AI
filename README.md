# PDF2Inventor AI V0.5 · Inventor 2018 Sketch + Extrude

## Chức năng đã có trong mã nguồn
- Chế độ ChatGPT thủ công, không dùng API trả phí.
- Tạo, mở và lưu hồ sơ dự án JSON.
- Mở và xem PDF cục bộ bằng PyMuPDF.
- Kết nối Autodesk Inventor đang chạy qua COM.
- Đọc tham số của file IPT đang mở.
- Liên kết một file IPT với một chi tiết trong hồ sơ dự án.
- Đồng bộ tham số Inventor vào hồ sơ.
- Nhận lệnh JSON set_parameter; ứng dụng xác nhận, tạo backup, cập nhật tham số, gọi Update và Save.
- Nhận lệnh JSON create_rectangle_extrude để tạo Sketch hình chữ nhật trên mặt phẳng XY và Extrude thành khối 3D.
- Nhận lệnh JSON create_circle_extrude để tạo Sketch hình tròn có đường kính điều khiển và Extrude thành trụ hoặc Extrude Cut để khoét lỗ/hốc tròn.
- Sketch chữ nhật được ràng buộc ngang/dọc, cố định góc đầu tiên và có hai kích thước điều khiển bằng tham số người dùng.
- Chiều sâu Extrude tham chiếu tham số người dùng riêng.
- operation auto tự chọn Join nếu vùng hình học mới giao với solid hiện có theo bounding box; nếu không giao thì chọn New Body. operation=cut tạo hốc/khoét bằng Extrude Cut và yêu cầu có solid hiện hữu.
- Mỗi thao tác hình học tạo backup IPT trước khi thực thi; có transaction để hủy thao tác khi phát sinh lỗi.
- Đọc lại tham số sau khi dựng hình và lưu lịch sử vào hồ sơ dự án.

## JSON mẫu: dựng hình chữ nhật 150 × 70 × 8 mm

Thay PROJECT_ID_THỰC_TẾ và COMPONENT_ID_THỰC_TẾ bằng đúng mã trong dự án đang mở.

    {
      "project_id": "PROJECT_ID_THỰC_TẾ",
      "commands": [
        {
          "op": "create_rectangle_extrude",
          "component_id": "COMPONENT_ID_THỰC_TẾ",
          "length": 150,
          "width": 70,
          "thickness": 8,
          "origin_x": 200,
          "origin_y": 0,
          "unit": "mm",
          "operation": "auto",
          "direction": "positive",
          "reason": "Tạo khối chữ nhật kiểm thử"
        }
      ],
      "questions": [],
      "warnings": []
    }

origin_x và origin_y là vị trí góc đầu tiên tính từ gốc tọa độ XY, đơn vị mm. Trong ví dụ trên, hình được đặt tại X=200 mm để tránh chồng lên khối thử đang có tại gốc. Có thể dùng 0 nếu vùng đó còn trống hoặc muốn Join vào khối hiện tại.

operation nhận auto, join hoặc new_body. direction nhận positive hoặc negative. Ba kích thước bắt buộc là số dương và unit bắt buộc là mm.


## JSON mẫu: khoét lỗ tròn đường kính 20 mm

    {
      "project_id": "PROJECT_ID_THỰC_TẾ",
      "commands": [
        {
          "op": "create_circle_extrude",
          "component_id": "COMPONENT_ID_THỰC_TẾ",
          "diameter": 20,
          "thickness": 8,
          "center_x": 75,
          "center_y": 35,
          "unit": "mm",
          "operation": "cut",
          "direction": "positive",
          "reason": "Khoét lỗ tròn kiểm thử"
        }
      ],
      "questions": [],
      "warnings": []
    }

Tâm hình tròn được xác định bởi center_x và center_y trong hệ tọa độ XY. Với operation=cut, Inventor dùng biên dạng tròn để cắt vào solid hiện có; chiều sâu cắt là thickness. Hãy kiểm tra vị trí và hướng cắt trước khi xác nhận.

## Giới hạn V0.5
- Tạo hình học hiện hỗ trợ một lệnh create_rectangle_extrude hoặc create_circle_extrude trong mỗi gói JSON; không trộn lệnh dựng hình với set_parameter trong cùng gói.
- Hình chữ nhật dựng trên mặt phẳng XY gốc; chưa có chọn mặt phẳng hoặc mặt nghiêng.
- Chưa hỗ trợ biên dạng tự do, native Hole Feature, Fillet, Chamfer, Pattern hoặc chỉnh sửa IAM. Lỗ tròn hiện tại được tạo bằng Sketch tròn + Extrude Cut, không phải native Hole Feature.
- Không tự động nhận dạng kích thước PDF. Người dùng và ChatGPT cần xác định kích thước trước khi phát lệnh.
- Join trong chế độ auto được ước lượng theo bounding box; nếu hình học thực không giao nhau, Inventor có thể từ chối Join và thông báo lỗi.
- V0.5 cần được thử nghiệm trên Inventor 2018 thực tế. Kiểm thử CI xác nhận cấu trúc, validation và khả năng build; không thay thế kiểm thử CAD COM trên máy người dùng.
- Bridge hiện làm việc với một file IPT đã liên kết và đang mở trong Inventor.

## Cách sử dụng
1. Mở Inventor 2018 và mở file IPT đã lưu.
2. Mở PDF2Inventor AI V0.5.
3. Trong tab Inventor 2018, nhấn Kết nối Inventor.
4. Trong tab Dự án CAD, chọn chi tiết cần điều khiển.
5. Trong tab Inventor 2018, nhấn Gắn IPT vào chi tiết.
6. Nhấn Đồng bộ tham số để lấy dữ liệu mới nhất.
7. Vào ChatGPT thủ công và tạo gói ngữ cảnh.
8. Gửi ngữ cảnh cùng yêu cầu cho ChatGPT; nhập JSON trả về vào tab Nhập lệnh CAD.
9. Nhấn Kiểm tra lệnh. Đọc kích thước và vị trí trước khi nhấn Áp dụng lệnh.
10. Xác nhận thao tác trong hộp thoại. Sau khi hoàn tất, kiểm tra mô hình và nhật ký Inventor.

## Build EXE
GitHub Actions workflow Build PDF2Inventor AI for Windows tự chạy khi có commit trên nhánh feature/v0.5-sketch-extrude. Khi build thành công, tải artifact PDF2Inventor_AI_Windows_x64 trong trang Actions của GitHub.

Người dùng cuối không cần cài Python. Máy build GitHub Actions cài Python, PySide6, PyMuPDF, pywin32 và PyInstaller.

## An toàn và phát triển
- Không sửa nhánh main; V0.5 phát triển riêng trên feature/v0.5-sketch-extrude, dựa trên nhánh V0.4 đã kiểm chứng kết nối Inventor.
- Trước thao tác tham số/hình học, ứng dụng yêu cầu xác nhận.
- Các thay đổi thật trên IPT tạo file backup bên cạnh file gốc.
- Nếu tạo hình học thất bại, ứng dụng cố gắng hủy transaction và báo đường dẫn backup.
- Chỉ phát hành EXE V0.5 sau khi kiểm thử tự động/build thành công và kiểm tra thực tế trên Inventor 2018.
