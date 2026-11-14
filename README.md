# PDF2Inventor AI V0.6 · PDF Vision → Inventor 2018

## Mục tiêu V0.6
Nạp PDF trực tiếp vào phần mềm. Ứng dụng trích vector CAD/text gốc, AI thị giác đọc hình chiếu/mặt cắt/kích thước, kiểm tra tỷ lệ và đề xuất lệnh CAD. Người dùng xác nhận để Inventor 2018 dựng hình.

Kích thước số ghi trên bản vẽ là chuẩn cuối cùng; tỷ lệ vector chỉ dùng để hiệu chuẩn tọa độ và kiểm tra chéo.

## Quy trình
1. Mở PDF2Inventor AI V0.6.
2. Kéo thả PDF vào cửa sổ hoặc nhấn Mở PDF.
3. Mở Inventor 2018 và kết nối ứng dụng với Inventor.
4. Trong tab AI đọc bản vẽ, nhấn Tạo IPT mới và chọn nơi lưu; ứng dụng tạo Part từ template Inventor mặc định, tự gắn vào dự án và tự lưu hồ sơ JSON cạnh file IPT. Nếu đã có một IPT trống đang mở, có thể dùng Gắn IPT đang mở.
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
- Sketch biên dạng vector kín + Extrude, hỗ trợ lỗ tròn, cửa sổ/rãnh kín đa giác.
- Đường cong Bezier trên biên dạng ngoài được xấp xỉ bằng các đoạn thẳng ngắn lấy từ vector PDF; không thay thế cung/fillet CAD native.
- Extrude Cut bằng lệnh hình tròn chỉ trong chế độ CAD thủ công và khi IPT đã có solid.
- Tạo backup và yêu cầu xác nhận trước khi sửa IPT.

## Giới hạn quan trọng của AI trong V0.6
- Bộ sinh lệnh tự động phát một feature cho một chi tiết đơn: lăng trụ chữ nhật, khối trụ, hoặc biên dạng vector phẳng có lỗ/cửa sổ xuyên suốt rồi Extrude.
- AI phải chỉ ra ít nhất một chuẩn vector theo X và một chuẩn theo Y trên cùng hình chiếu. Ứng dụng tự tính lại mm/point từ đoạn thẳng PDF và yêu cầu sai khác tỷ lệ không quá 2%.
- Kích thước bao lệnh CAD được đối chiếu với ba kích thước tổng thể Dài/Rộng/Cao; sai số tối đa 0.1% hoặc 0.05 mm, lấy giá trị lớn hơn.
- Đường bao vector có thể gồm cạnh thẳng và cung Bezier được lấy mẫu thành đoạn thẳng ngắn; lỗ tròn được tạo thành đường tròn Sketch thực, cửa sổ/rãnh kín được tạo từ vòng Sketch bên trong.
- Nếu bản vẽ có lỗ bậc, rãnh hở, bậc chiều sâu, ren, mặt nghiêng 3D, vát/bo cần feature riêng, nhiều feature độc lập hoặc bản lắp nhiều chi tiết, AI phải trả câu hỏi/cảnh báo và không phát lệnh hình học đơn giản dễ gây sai chi tiết.
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
