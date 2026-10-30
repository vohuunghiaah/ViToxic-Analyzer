# Trạng thái web và triển khai — 24/10/2026

**Kết luận:** web và API đã chạy cùng model thật trên Windows CPU và container Linux qua Docker Desktop.
Sẵn sàng demo local/Docker; chưa triển khai public, chưa có URL hosting/domain.

Đã bổ sung workspace tại `/workspace` (CSV, duyệt, thống kê, lịch sử IndexedDB và báo cáo)
và extension Manifest V3 thử nghiệm. Xem `WORKSPACE_EXTENSION.md` và bằng chứng mới
`outputs/stage4/workspace-verification.json`; các báo cáo web/Docker cũ giữ nguyên để đối chiếu lịch sử.

Cập nhật 31/10/2026: extension 0.2 tự gắn nhãn comment YouTube đang hiển thị sau khi bật cho website,
tách comment/reply và bỏ tên tác giả, thêm màu nhãn Light/Dark. Hướng dẫn cài/cập nhật ở
`WORKSPACE_EXTENSION.md`; bằng chứng cho bản này ở `outputs/stage4/extension-auto-verification.json`.

Docker đang phục vụ tại <http://127.0.0.1:8001/>. Cổng 8000 bị container `whybi-api-1`
của dự án khác chiếm; Compose đã đổi sang `127.0.0.1:${VITOXIC_PORT:-8001}:8000`.
Container ViToxic healthy và smoke test tại 8001 PASS. Không dừng dịch vụ ở 8000.
Có thể đặt `VITOXIC_PORT=8002` trong `.env` cạnh Compose nếu cần đổi cổng host.

## Phần đã hoàn thành

- Web tiếng Việt tại `/`, giao diện trắng/đen và nút đổi Light/Dark. Mặc định theo hệ điều hành,
  ghi nhớ lựa chọn trong localStorage; không lưu bình luận hoặc lịch sử dự đoán vào storage.
- Phân tích một bình luận hoặc nhiều dòng; hiển thị CLEAN/OFFENSIVE/HATE, điểm từng nhãn,
  token trước rút gọn, cảnh báo rút gọn và tải JSON. Kết quả đến từ API, không phải dữ liệu giả.
- Kiểm tra đầu vào: 5.000 ký tự/câu, 32 câu/batch, tổng 20.000 ký tự. Đếm ký tự Unicode
  thống nhất với Python, bỏ dòng trống trong batch. Có trạng thái đang xử lý và lỗi kết nối/503.
- Giao diện responsive; có label, focus bàn phím, vùng thông báo kết quả và reduced motion.
- FastAPI phục vụ web/assets cùng origin. Dockerfile, `.dockerignore` và script đóng gói đã
  bổ sung `web/`; model vẫn mount read-only, giữ nguyên checkpoint và preprocessing.

## Kiểm chứng lần này

| Hạng mục | Kết quả |
|---|---|
| Gói bàn giao trước khi chỉnh sửa | 44/44 checksum khớp |
| `python -m pytest tests/test_stage4.py -q` | 22 test PASS |
| `python scripts/smoke_deploy.py` | PASS qua HTTP thật: web, 4 assets, readiness, metadata, single/batch |
| `python -m pip check` | Không có dependency bị thiếu/xung đột |
| `node --check web/app.js`, `web/theme.js` | PASS |
| Trình duyệt với model thật | Single và batch trả kết quả, dịch vụ ready, không có lỗi JavaScript |
| Giao diện | Đã xem ảnh desktop Light và mobile Dark; kiểm tra 320px/390px không tràn ngang |
| Light/Dark | Đổi chế độ và tải lại vẫn giữ lựa chọn |
| Ca biên trên trình duyệt | Input rỗng, >5.000 ký tự, >32 câu bị chặn; bỏ dòng trống; download JSON |
| Phản hồi mô phỏng riêng để kiểm thử UI | Cảnh báo rút gọn, xử lý 503, bật lại nút sau lỗi; chuỗi HTML được hiển thị dạng text |
| `docker compose config --quiet` | PASS cú pháp/config |
| Docker build/run | PASS: image đã build, container Linux healthy, smoke test model thật tại 8001 PASS |

Python thực tế: 3.14.7; Torch 2.14.1; Transformers 4.57.6; FastAPI 0.162.0.
Môi trường kiểm chứng được ghi tại `requirements/locks/windows-web-2026-10-24.txt`;
không dùng lock này để kết luận Linux tương thích. Dockerfile vẫn dùng Python 3.11.
Pytest có một cảnh báo deprecation từ Starlette/httpx, không gây lỗi test.

`outputs/stage4/web-verification.json` là bằng chứng cho lần bổ sung web.
`outputs/stage4/docker-verification.json` cập nhật kiểm chứng Docker sau khi xử lý xung đột cổng.
Gói ZIP `ViToxic-Analyzer-web-2026-10-24.zip` tạo trước lần sửa cổng vẫn dùng 8000;
khi dùng gói đó cần áp dụng mapping Compose mới hoặc đóng gói lại từ checkout hiện tại.
`outputs/stage4/verification.json` và `summary.md` là bằng chứng lịch sử của model/API trước
khi bổ sung web; không phải kết quả chạy lại benchmark hoặc container hiện tại.

## Mở web trên máy hiện tại

Trong PowerShell tại `D:\MachineLearning`, chạy và giữ terminal mở:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Đợi `Application startup complete`, mở <http://127.0.0.1:8000/>. Swagger tại `/docs`.
Nhấn Ctrl+C để dừng. Server Python dùng trong kiểm chứng đã được dừng sau khi hoàn tất;
container Docker hiện vẫn chạy ở 8001. Dừng container bằng `docker compose down`.
Môi trường `.venv` chỉ có trên máy này, không đi kèm gói deploy. Máy khác làm theo README.

## Điều kiện trước khi public

1. Chọn VPS/server có thể chạy Python, Java và model; upload cả `outputs/stage4/bundle/`.
   Chỉ đưa thư mục web lên hosting tĩnh sẽ không có khả năng phân tích.
2. Khởi động Docker Engine, chạy `docker compose up --build -d`, đợi healthcheck healthy,
   chạy `python scripts/smoke_deploy.py --url http://127.0.0.1:8001`. Ghi lại image digest và dependencies Linux thực tế.
3. Cấu hình domain/HTTPS, cơ chế truy cập và giới hạn tải ở reverse proxy. Compose hiện
   chỉ mở `127.0.0.1:8001`; không đổi thành public khi chưa cấu hình lớp truy cập.
4. Đo RAM/CPU, độ trễ, tải đồng thời và khả năng restart trên máy đích. Một worker giữ một
   bản model trong RAM; inference bận trả 503. Chưa kiểm thử tải production.

Chất lượng model vẫn là mức demo nghiên cứu (Macro-F1 0,6546 trên test đã báo cáo).
Điểm dự đoán chưa calibration; không dùng kết quả này để tự động xóa/chặn bình luận.
