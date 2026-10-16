# BÀN GIAO TRIỂN KHAI — ViToxic Analyzer

Gói bàn giao ngày 2026-10-16. Người nhận chỉ cần giải nén gói này; không cần thư mục dự án
của người gửi, Drive, CSV train/test hoặc tải lại PhoBERT. Model và VnCoreNLP assets đã có sẵn.
Đây là API backend kèm Swagger để thử API, chưa có frontend cho người dùng cuối.

## 1. Kiểm tra gói

Giải nén ZIP, mở terminal tại thư mục có `compose.yaml`, chạy:

```text
python scripts/verify_handoff.py
```

Lệnh dùng Python standard library, không cần pip. Phải hiện PASS. Manifest kiểm tra SHA-256
của source/config/model; file ZIP cũng có checksum `.sha256` riêng do người gửi cung cấp.

## 2. Triển khai Docker CPU

Cài Docker Engine/Desktop và Docker Compose trên máy đích. Chạy từ root vừa giải nén:

```text
docker compose up --build -d
docker compose logs -f api
```

Đợi `Application startup complete`, rồi mở `http://127.0.0.1:8000/docs` trên máy chạy Docker.
Model nằm tại `outputs/stage4/bundle`, được mount read-only vào `/bundle`.
**Không chạy `package_stage4.py`**: bundle đã xuất sẵn, gói bàn giao không cần artifact training.
Build lần đầu cần internet để tải base image/packages; inference sau đó dùng assets local.

Kiểm tra bằng Python trên host hoặc trong container:

```text
python scripts/smoke_deploy.py
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
docker compose ps
```

Dừng: `docker compose down`. Chạy lại: `docker compose up -d`.
Nếu port 8000 đã được dùng, đổi mapping bên trái thành `127.0.0.1:8001:8000`, rồi thử
`python scripts/smoke_deploy.py --url http://127.0.0.1:8001`.

**Phạm vi kiểm chứng:** source và model đã chạy thật trên Windows CPU; Dockerfile và Compose
đã chuẩn bị nhưng máy người gửi không có Docker nên chưa build/run trên Linux. Người nhận phụ trách
xác nhận container và ghi lại phiên bản/image digest thực tế. Dependencies runtime dùng ranges;
lock Windows trong `requirements/locks/` là bằng chứng môi trường đã chạy, không phải lock Linux.

## 3. Chạy không dùng Docker

Cần Python 3.11, Java trên PATH. Tạo virtualenv, kích hoạt rồi chạy:

```text
python -m pip install -r requirements/stage4.txt
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Giữ terminal chạy. Mở Swagger không tự khởi động API. Nếu `Failed to fetch`, kiểm tra `/ready`
và tiến trình Uvicorn trước; tab còn mở không đảm bảo server còn sống.

## 4. Người deploy cần hoàn thành

1. Chọn máy chủ và build/run container, xác nhận healthcheck và smoke test PASS.
2. Ghi lại CPU/RAM, phiên bản dependencies, image digest và URL triển khai.
3. Nếu public: cấu hình domain/HTTPS, cơ chế truy cập và giới hạn tải ở reverse proxy.
   Compose hiện chỉ bind localhost; `127.0.0.1` trên laptop người nhận không trỏ tới VPS.
   Dùng proxy trên host hoặc SSH port forwarding để truy cập VPS; không mở cổng model tùy tiện.
4. Kiểm tra restart sau reboot, log, tài nguyên và tải đồng thời trên máy đích.
5. Bàn giao lại URL `/docs`, kết quả smoke test, cấu hình triển khai và cách dừng/khởi động.

Khởi đầu nên dành khoảng 4 GB RAM và vài GB đĩa trống, rồi đo lại trên máy đích; đây là dự trù,
không phải cấu hình tối thiểu đã chứng nhận. Local từng quan sát khoảng 1 GB RSS sau warmup;
build/startup có thể cần nhiều hơn. Dùng một Uvicorn worker để tránh nhân bản model trong RAM.
Request inference thứ hai khi model đang bận nhận 503/Retry-After, không xếp hàng vô hạn.

## 5. API và giới hạn model

`POST /predict`: `{"text":"Xin chào!"}`.
`POST /predict/batch`: `{"texts":["Xin chào!","Cảm ơn bạn."]}`.
Chi tiết giới hạn/input/output: `docs/STAGE4_API.md`; schema: `outputs/stage4/openapi.json`.

Model giữ nguyên `phobert_lr3e-5_len128_drop01_batch16_seed42`, checkpoint epoch 5, max length 128.
Test Macro-F1 0,6546; OFFENSIVE F1 0,4162; HATE recall 0,5770. Confidence chưa calibration.
Không train lại, chỉnh threshold hoặc đổi preprocessing trong bước deploy. API chạy đúng không
đồng nghĩa chất lượng moderation production; chưa tự động chặn/xóa bình luận.

## 6. Nội dung gói

- `src/`: mã nguồn dự án; serving không đọc dữ liệu training.
- `outputs/stage4/bundle/`: checkpoint + tokenizer + VnCoreNLP + config + manifest.
- `Dockerfile`, `compose.yaml`, `.dockerignore`, `requirements/`: môi trường chạy.
- `scripts/verify_handoff.py`, `scripts/smoke_deploy.py`: kiểm tra gói và API độc lập.
- `tests/test_stage4.py`: unit tests; cài thêm pytest nếu muốn chạy.
- `outputs/stage4/verification.json`, `summary.md`, `openapi.json`: bằng chứng local trước bàn giao.
- `AI_TRACKER.md`, `AGENTS.md`: lịch sử và quy tắc tiếp tục dự án.

Không kèm `.venv`, `.git`, CSV dữ liệu, cache, model tuning khác, baseline hoặc optimizer state.
Các link tới artifact training trong tài liệu lịch sử có thể không có trong gói deployment này.
Không có mật khẩu/tài khoản hosting được tạo hoặc gửi kèm. Tài nguyên bên thứ ba giữ nội dung gốc;
khi phân phối rộng hơn cần kiểm tra điều khoản của nguồn PhoBERT và VnCoreNLP.
