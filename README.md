# PDF2Inventor AI V0.6 · PDF Vision → Inventor 2018

## Mục tiêu V0.6
Nạp bản vẽ PDF trực tiếp vào phần mềm, để AI thị giác đọc hình chiếu/mặt cắt/kích thước, tạo báo cáo và đề xuất lệnh CAD có cấu trúc. Người dùng kiểm tra lệnh rồi xác nhận để Inventor 2018 dựng hình.

## Quy trình
1. Mở PDF2Inventor AI V0.6.
2. Kéo thả PDF vào cửa sổ hoặc nhấn Mở PDF.
3. Mở Inventor 2018, mở một file Part (.ipt) đã lưu. Nên dùng IPT mới/trống khi dựng chi tiết mới từ PDF.
4. Trong tab AI đọc bản vẽ, nhấn Gắn IPT Inventor đang mở. Nếu chưa chọn chi tiết trong dự án, ứng dụng tạo một hồ sơ component và gắn với IPT đang mở.
5. Nhập OpenAI API Key và nhấn Lưu cấu hình và khóa an toàn. Cấu hình model mặc định là gpt-4.1; có thể đổi tên model nếu tài khoản API được cấp quyền khác.
6. Chọn mức chi tiết PDF (Cao cho bản vẽ cơ khí có kích thước nhỏ).
7. Nhấn ĐỌC PDF VÀ PHÂN TÍCH. Ứng dụng gửi PDF tới OpenAI Responses API để AI đọc nội dung chữ và ảnh các trang.
8. Đọc báo cáo: loại bản vẽ, hình chiếu, mặt cắt, kích thước đọc được, feature, độ tin cậy, câu hỏi và cảnh báo.
9. Chỉ khi AI xác định được một hình dạng cơ bản phù hợp và không còn câu hỏi chưa giải quyết, nhấn Chuyển lệnh sang CAD.
10. Trong tab Nhập lệnh CAD, nhấn Kiểm tra lệnh, đọc kích thước, sau đó nhấn Áp dụng lệnh và xác nhận. Inventor tạo backup trước khi thay đổi.

## Cấu hình API, chi phí và bảo mật
- Phân tích tự động cần OpenAI API Key riêng. API được tính phí theo mức sử dụng, không dùng chung hạn mức ChatGPT Free/Plus.
- Khóa được lưu mã hóa bằng Windows DPAPI theo tài khoản Windows hiện tại; khóa không được ghi thành văn bản thuần vào settings.json.
- PDF được gửi qua HTTPS tới OpenAI API. Ứng dụng đặt store:false cho Responses API. Dù vậy, file vẫn được gửi ra ngoài máy để xử lý bởi dịch vụ API; không dùng chế độ AI tự động cho tài liệu mật nếu chưa được phép.
- PDF đầu vào hiện giới hạn 50 MB cho mỗi file.
- Có thể để trống khóa và tiếp tục dùng tab ChatGPT thủ công / nhập JSON như các bản trước.
- Có thể dùng biến môi trường OPENAI_API_KEY thay cho lưu khóa trong ứng dụng.

## Phạm vi CAD tự động hiện có
- Sửa tham số IPT.
- Sketch chữ nhật + Extrude thành lăng trụ chữ nhật, kích thước có tham số.
- Sketch tròn + Extrude thành khối trụ, đường kính có tham số.
- Sketch biên dạng đa giác kín + Extrude, hỗ trợ lỗ tròn xuyên suốt có đường kính điều khiển.
- Extrude Cut bằng lệnh hình tròn chỉ trong chế độ CAD thủ công và khi IPT đã có solid.
- Tạo backup và yêu cầu xác nhận trước khi sửa IPT.

## Giới hạn quan trọng của AI trong V0.6
- Bộ sinh lệnh tự động phát một feature cho một chi tiết đơn: lăng trụ chữ nhật, khối trụ, hoặc biên dạng đa giác phẳng có lỗ tròn xuyên suốt rồi Extrude.
- Các biên dạng đa giác chỉ dùng cạnh thẳng; lỗ tròn phải có đường kính/tọa độ tâm đọc được rõ ràng.
- Nếu bản vẽ có lỗ bậc, rãnh không tròn, bậc chiều sâu, ren, mặt nghiêng 3D, vát, bo, nhiều feature hoặc bản lắp nhiều chi tiết, AI phải trả câu hỏi/cảnh báo và không phát lệnh hình học đơn giản dễ gây sai chi tiết.
- Chưa tự dựng một bản lắp hoàn chỉnh, chưa tạo native Hole, Fillet, Chamfer, Pattern, Thread hoặc bản vẽ 2D từ 3D.
- Không suy kích thước từ tỷ lệ hình nếu không có kích thước tham chiếu; không tự giả định vật liệu, chiều dày, dung sai hoặc kích thước thiếu.
- Mô hình AI có thể đọc sai nét/ký hiệu. Người dùng phải kiểm tra báo cáo và xem trước JSON trước khi xác nhận.
- Việc build và kiểm thử tự động không thay thế kiểm thử hình học thực tế trên Inventor 2018. Cần thử trên IPT bản sao/trống trước.

## Kiểm thử CI
- Compile tất cả module Python.
- Import giao diện chính, module PDF AI và module Inventor geometry.
- Unit tests cho Inventor COM bridge, validate lệnh hình học, schema AI và việc đóng gói lệnh.
- GitHub Actions tự build EXE trên nhánh feature/v0.6-pdf-vision-auto.

## Bản phát hành
Khi workflow build thành công, tải artifact PDF2Inventor_AI_Windows_x64 ở trang Actions của repository.

Nhánh V0.6 được phát triển tách riêng. Nhánh V0.4/V0.5 và main không bị ghi đè.
