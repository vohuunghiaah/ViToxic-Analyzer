# Kiểm tra PR #1 — 03/11/2026

## Phạm vi và đồng bộ

- Workspace ban đầu: `main` tại `ac0a6c240a9fc3ebca4e35bcebe7a927773b59ea`, 14 tệp đã sửa và 5 tệp chưa theo dõi. Không đưa các thay đổi Colab đang dở vào PR.
- Fetch nhánh `feat/web-workspace-youtube-extension`, tạo worktree riêng, pull `--ff-only`: đã đồng bộ tại `5c721b804c1d682a73c202dc3a9c4f70247597a5` (46 tệp khác `origin/main`).
- Rà mã API/serving, web/data/workspace, extension/background/page/auto/popup, manifest, Docker/Compose, scripts đóng gói và tests. Không thay nhãn, checkpoint, pipeline preprocessing, predictions hoặc kết quả nghiên cứu.

## Phát hiện và xử lý

| Mức | Phát hiện / bằng chứng | Xử lý |
|---|---|---|
| Cao | Xóa phiên không kiểm tra revision: tái hiện code gốc xóa bản revision 2 dù tab giữ bản cũ | Transaction IndexedDB kiểm tra revision nguyên tử cho cả lưu và xóa; test stale delete, stale save, cạnh tranh tạo/sửa |
| Cao | Model thật không khởi động từ `My Drive`: Java báo không tìm thấy `My%20Drive/.../wordsegmenter.rdr` | Mở rộng nhận diện đường dẫn cần sao chép assets; kiểm checksum trước/sau; test real bundle đã đạt |
| Vừa | Lưu quyết định thất bại chỉ giữ chỉnh sửa trong form; JSON backup lấy bản active cũ | Giữ bản vừa sửa trong active khi lưu lỗi, chặn sửa tiếp, yêu cầu sao lưu; chặn submit trùng và refresh khi đang import/lưu |
| Vừa | JSON backup hợp lệ 1.000 hàng Unicode có thể vượt giới hạn khôi phục 10 MiB | Tăng giới hạn file lên 64 MiB, giữ giới hạn 1.000 hàng/5.000 code point và 2.000 ký tự ghi chú; test round-trip >10 MiB |
| Thấp | JSON có hàng null gây TypeError kỹ thuật | Kiểm tra hàng và trả thông báo dữ liệu không hợp lệ |
| Cải thiện | API extension cố định 8001 | Cấu hình chỉ từ popup; host literal `127.0.0.1`, HTTP, port 1–65535; kiểm quyền và cấm redirect. Không tăng host permissions/CORS |
| Cải thiện | Theo dõi DOM sau tắt, kết quả còn chờ khi chuyển trang SPA | Disconnect observer/xóa cache khi tắt; invalidation khi YouTube chuyển video và đối chiếu URL trước gắn nhãn |

**CSV:** không tái hiện thất bại được mô tả: baseline chạy 11/11 JavaScript tests đạt. Không sửa/xóa bảo vệ công thức. Thay assertion chuỗi bằng `csv-parse`, thêm `=`, `+`, `-`, `@`, whitespace/control characters, nháy kép, Unicode và nhiều dòng. Kiểm tra `<br>` trên code gốc cũng đạt, không coi đó là lỗi đã sửa.

## Kiểm thử

| Lệnh / kịch bản | Kết quả |
|---|---|
| Python ban đầu với interpreter hệ thống | Không collect được: thiếu FastAPI; đã tạo venv Python 3.11 riêng |
| `python -m pytest -m "not integration" -q` | 44 passed, 1 deselected; không tải checkpoint |
| `python -m pytest tests/test_stage4.py -q` | 27 passed, 0 failed (bao gồm 5 ca đường dẫn Java) |
| `npm test` | 18 passed, 0 failed |
| `npm run test:browser` | 3 passed, 0 failed; Chromium + IndexedDB thật, native extension/API giả và adapter YouTube DOM giả lập |
| `node scripts/check-js.cjs`, Python compileall, `git diff --check` | Đạt |
| `uv pip check`, `npm audit` | Dependencies tương thích; 0 npm vulnerabilities |
| `VITOXIC_TEST_BUNDLE=... python -m pytest tests/test_bundle_integration.py -q` | 1 passed sau sửa đường dẫn; trước sửa 1 failed |

Windows/Python 3.11.9 có Starlette/httpx deprecation warning. Khi khởi tạo/chạy JVM, pytest faulthandler in `Windows fatal exception: access violation`, nhưng test tiếp tục, trả 1 passed/exit 0. Ghi nhận diagnostic này, không coi log sạch; cần kiểm tra riêng tương tác PyJNIus/JVM/faulthandler. Không ẩn cảnh báo bằng cấu hình test.

## Docker và model thật

- Docker Desktop daemon được khởi động; `docker compose config --quiet` và build đạt.
- Không đọc được mount ổ Google Drive: `/bundle/bundle.json` không hiện trong container. Đã sao chép manifest cùng đúng 12 asset sang thư mục local bị Git ignore, giữ nguyên bundle nguồn; phục vụ với mount read-only.
- Container chạy user `app`, healthy, bind `127.0.0.1:18081` trong kiểm thử. Compose mặc định vẫn `127.0.0.1:8001`; không mở public.
- Smoke HTTP thật đạt `/`, `/workspace`, 8 static assets, `/ready`, `/model`, `/predict`, `/predict/batch`.
- Image: `sha256:eacfc2a7218830414e9eba38d92c8b7819c9bc0235d042a2c3f481eb1bc7271a`.
- Checkpoint: `f8a6a9a785c4f7fefcaba2e228944e6fe29d0ac673eb96864937e9ffb8ea9156`, run `phobert_lr3e-5_len128_drop01_batch16_seed42`.
- Smoke gọi trước readiness từng lỗi kết nối; kết quả đạt chỉ ghi sau khi startup hoàn tất và healthcheck healthy.

## CI và giới hạn

Thêm GitHub Actions: Python syntax/unit/API fake, JavaScript syntax/unit, Chromium fixture, diff whitespace và Docker build. Test checkpoint thật mang marker `integration`; nếu không cung cấp bundle thì SKIP, không ghi PASS. Không ghi model weights hoặc dữ liệu riêng vào Git.

Chưa chạy YouTube công khai trong đợt này, chưa kiểm chứng hộp cấp quyền/toolbar bằng thao tác người dùng, chưa đo tải production/CUDA/public HTTPS/auth. Native extension dùng host fixture loopback nếu Chromium không cấp quyền YouTube ngoài user gesture; adapter YouTube được kiểm riêng bằng DOM giả lập trên URL YouTube. Các báo cáo/ảnh 24–31/10 là lịch sử, không thay thế kiểm chứng mới.

Giới hạn: browser storage theo origin/profile; thay port cần backup JSON; selector phụ thuộc DOM website; không đồng bộ đa người dùng. Dependencies Python còn ranges, chưa có Linux lock theo image digest. Không tuyên bố production-ready.
