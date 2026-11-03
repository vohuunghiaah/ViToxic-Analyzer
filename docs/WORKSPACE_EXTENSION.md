# Workspace và extension — cập nhật 03/11/2026

## Chạy và sử dụng

```powershell
docker compose up --build -d
```

Đợi container healthy. Mở **http://127.0.0.1:8001/workspace**.
Trang phân tích nhanh vẫn ở `/`. Có nút “Kiểm duyệt” để chuyển sang workspace.

1. **Nhập dữ liệu:** CSV UTF-8, có hàng tiêu đề; chọn dấu phân cách và cột nội dung.
   Hỗ trợ ngoặc kép, dấu phẩy trong nội dung, xuống dòng trong ô, BOM, dấu `;` và tab.
   Tối đa 2 MB, 1.000 dòng, 5.000 ký tự/câu. Excel cần lưu thành CSV UTF-8 trước.
   Hàng thiếu nội dung bị báo lỗi, không tự âm thầm bỏ qua.
2. **Phân tích:** tối đa 16 câu và 20.000 ký tự mỗi lượt. Lưu sau từng lượt.
   “Dừng sau lượt này” chờ kết quả hiện tại rồi lưu. Mở lại phiên và chọn “Phân tích phần còn lại”.
   Nếu một câu bị API từ chối sau chuẩn hóa, tách lượt để xác định câu lỗi; vẫn giữ kết quả câu hợp lệ.
   Không phân tích lại những câu đã có kết quả. Không trộn checkpoint khác vào cùng phiên.
3. **Kiểm duyệt:** tìm nội dung, lọc nhãn mô hình/trạng thái/điểm dự đoán, phân trang 20 câu.
   Mở chi tiết để xác nhận hoặc sửa nhãn, ghi chú, đánh dấu cần xem xét.
   Nhãn người duyệt luôn tách biệt nhãn mô hình. Không có hành động tự xóa/chặn bình luận.
4. **Dashboard:** phân bố nhãn mô hình và tiến độ trên các phiên được lưu trong trình duyệt.
5. **Xuất:** CSV chứa toàn bộ phiên, nhãn dự đoán, xác suất, nhãn duyệt và ghi chú.
   CSV vô hiệu hóa các ô có thể bị Excel diễn giải thành công thức. JSON giữ cấu trúc để khôi phục (tối đa 64 MiB, vẫn tối đa 1.000 hàng và giới hạn từng trường).
   Xuất không phụ thuộc bộ lọc đang chọn. Khôi phục JSON tạo phiên mới, không ghi đè phiên cũ.

## Dữ liệu và phạm vi local

Workspace lưu bình luận, dự đoán và quyết định duyệt trong **IndexedDB** của trình duyệt.
API chỉ nhận nội dung để phân tích; không lưu lịch sử trên server. Dùng cố định một URL:
`localhost:8001` và `127.0.0.1:8001` có bộ nhớ riêng. Đổi port hoặc profile cũng không dùng chung lịch sử.
Xóa dữ liệu trình duyệt có thể mất lịch sử; sao lưu JSON trước. Không chia sẻ giữa thành viên nhóm.

Web Locks ngăn nhiều tab cùng chạy phân tích; revision kiểm tra nguyên tử khi lưu và xóa ngăn ghi đè hoặc xóa bản mới từ tab cũ
ở tab khác. Khi báo lỗi lưu/xung đột, sao lưu JSON rồi tải lại trang để đọc phiên mới nhất.
Chưa có tài khoản, phân quyền hoặc audit trail nhiều người. Muốn làm việc nhóm cần lưu trên server
(SQLite/Postgres), xác thực và đồng bộ; đây là bước tiếp theo, không phải chức năng của bản này.

## Extension Chrome / Edge 0.2.0 (Manifest V3)

Không cần đóng gói model vào extension. Extension gọi API local đã chạy bằng Docker.

1. Mở `chrome://extensions` hoặc `edge://extensions`.
2. Bật **Developer mode** → **Load unpacked** → chọn thư mục `extension` trong checkout dự án.
3. Nếu đã cài bản cũ: bấm **Reload** trên thẻ ViToxic, sau đó **tải lại tab YouTube**.
4. Mở video YouTube và cuộn xuống bình luận. Mở popup ViToxic, để trống các ô selector
   để dùng bộ nhận diện YouTube có sẵn.
5. Bấm **Bật tự động trên website này** và chấp nhận quyền truy cập website khi Chrome hỏi.
   Từ đó, bình luận trong màn hình ở tab đang xem được gửi đến API local để phân tích.
   Có thể đóng popup: extension tiếp tục khi cuộn, tải thêm bình luận, đổi video và tải lại trang.
6. Nhãn **Bình thường — xanh lá**, **Xúc phạm — vàng/cam**, **Thù ghét — đỏ/hồng**,
   có chữ, ký hiệu và điểm dự đoán. Màu thích ứng với chế độ sáng/tối của hệ thống.
   Bấm **Tắt tự động và gỡ nhãn** để dừng trên website này, kể cả lần tải trang tiếp theo.

Bộ đọc YouTube lấy riêng `#content-text` trong `ytd-comment-view-model` hoặc
`ytd-comment-renderer`: không lấy tên tác giả, thời gian, lượt thích hay nút trả lời.
Reply được tính là bình luận riêng. Tên hoặc `@mention` nằm trong chính câu bình luận vẫn được giữ
để không làm mất ngữ cảnh. Không đoán tên người dùng bằng cách xóa từ trong câu.

Nếu muốn thao tác thủ công: **Xem comment trong màn hình** hoặc **Tách vùng bôi đen** →
kiểm tra danh sách → **Phân tích danh sách xem trước**. Khi bôi đen nhiều comment, mỗi comment
được tách riêng; comment nhiều dòng vẫn là một mục. Bôi đen một phần sẽ lấy trọn nội dung
của comment đó. Trang chưa có bộ nhận diện cần cấu hình selector; extension không tự gộp
toàn bộ vùng chọn thành một câu. Giữ popup mở khi chạy phân tích thủ công.

Trang thử: **http://127.0.0.1:8001/static/comments-demo.html**, tự nhận diện `.demo-comment`.

Quyền gồm `activeTab`, `scripting`, `storage` và host `http://127.0.0.1/*`.
Quyền HTTP/HTTPS khác là tùy chọn, chỉ yêu cầu cho website khi bạn bật tự động.
Cấu hình được lưu theo origin; content script được đăng ký cho các website đã bật.
Quyền host của Chrome không
giới hạn theo port; code chỉ gửi tới `http://127.0.0.1` với cổng đã cấu hình, không nhận URL tùy ý từ trang web và không theo redirect.
Nội dung được gửi từ service worker, không từ JavaScript của website; không cần mở CORS toàn cục.
Không chạy tự động trên website chưa bật; không lưu lịch sử extension, không sửa/xóa bình luận gốc.
Chỉ lưu cấu hình website và địa chỉ API trong `chrome.storage.local`; bộ nhớ đệm kết quả nằm trong tab.

### Đổi cổng API

Mở popup → **Kết nối API local**, nhập `http://127.0.0.1:8002` → **Lưu địa chỉ API**.
Đặt `VITOXIC_PORT=8002` trong `.env` của Compose và chạy `docker compose up -d` tương ứng.
Mặc định vẫn là 8001. Chỉ chấp nhận host literal `127.0.0.1`, HTTP và cổng 1–65535;
không nhận hostname ngoài, localhost, URL có tài khoản, đường dẫn, query hoặc fragment.
Không cần cấp quyền host mới. Chỉ popup có thể đổi cấu hình; lượt đang chạy giữ địa chỉ ban đầu.
Link workspace trong popup theo địa chỉ đã lưu. Xuất JSON trước khi đổi origin/port của workspace.

### Giới hạn

- Bản thử nghiệm, chưa phát hành Chrome Web Store/Edge Add-ons; không cam kết hỗ trợ mọi website.
- Xem trước thủ công tối đa 50 bình luận. Tự động gửi từng nhóm tối đa 8 bình luận,
  nối hàng đợi giữa các tab, tránh gửi lại nội dung không đổi. Không tự cuộn hoặc bấm “xem thêm”.
- Selector tùy cấu trúc website. Không đọc iframe khác miền, shadow DOM, vùng nhập liệu,
  trang nội bộ trình duyệt hoặc những trang chặn extension.
- Chế độ tự động không cần mở popup; chế độ thủ công cần giữ popup tới khi hoàn tất.
- Model đang bận sẽ retry có giới hạn rồi báo lỗi. Không tự chặn nội dung.
- Nhãn extension chưa nhập vào lịch sử workspace. Có adapter YouTube desktop, Reddit và cấu trúc
  comment phổ biến; không cam kết nhận diện Facebook, YouTube mobile hay mọi biến thể giao diện.
  Website đổi cấu trúc có thể cần cập nhật adapter hoặc cấu hình selector trong popup.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_stage4.py -q
npm ci
npm test
npx playwright install chromium
npm run test:browser
.\.venv\Scripts\python.exe scripts/smoke_deploy.py --url http://127.0.0.1:8001
```

Trình duyệt: CSV qua model thật, sửa nhãn mà giữ nhãn model, tải lại lịch sử, JSON round-trip,
dừng/tiếp tục, phân trang, giao diện mobile và Dark. Các ca lỗi dùng phản hồi giả chỉ trong kiểm thử.
Extension: Chromium riêng với extension nạp thật, popup → service worker → API Docker thật →
gắn/gỡ nhãn trên trang fixture. Tab mục tiêu được chọn bằng test harness vì popup mở như tab kiểm thử;
chưa kiểm thử hộp cấp quyền và thao tác trên thanh công cụ Chrome/Edge của người dùng.

Kiểm thử bổ sung 0.2: `tests/extension-auto.browser.js` chạy extension thật với API local;
`tests/extension-youtube.browser.js` kiểm tra cấu trúc YouTube giả lập (bình luận, reply,
metadata, nhiều dòng, vùng chọn, đổi video kiểu SPA). Các file này là hàm dùng với Playwright
`browser_run_code_unsafe`, cần sửa đường dẫn Chromium/profile nếu chạy trên máy khác.
Kết quả cập nhật nằm trong `outputs/stage4/extension-auto-verification.json`.
Đã kiểm tra thêm bộ đọc trên một trang YouTube công khai: lấy đúng phần nội dung của 5 comment
đang hiển thị và gắn 5 nhãn thử nghiệm có kích thước hiển thị hợp lệ. Nhãn trong phép kiểm tra
YouTube trực tiếp là dữ liệu giả để thử hiển thị, không phải kết quả model; kiểm thử model thật
được thực hiện riêng qua extension trên trang fixture local.

Tài liệu nền tảng:
- https://developer.chrome.com/docs/extensions/develop/concepts/activeTab
- https://developer.chrome.com/docs/extensions/develop/concepts/network-requests
- https://developer.chrome.com/docs/extensions/reference/api/scripting
- https://developer.chrome.com/docs/extensions/reference/api/permissions

Kiểm thử tự động mới: `tests/browser.integration.cjs` dùng Chromium/profile tạm, IndexedDB thật,
extension native và API giả. DOM YouTube là fixture; không phải YouTube trực tiếp. Host fixture
loopback được dùng nếu không có quyền YouTube; không coi hộp cấp quyền/toolbar là đã kiểm thử.
Bộ kiểm thử cũ có đường dẫn máy lịch sử vẫn được giữ làm tài liệu, không nằm trong CI.
Xem `docs/PR1_REVIEW.md` để biết kết quả kiểm chứng ngày 03/11/2026.
