# Stage 4 — API và triển khai

API FastAPI dùng checkpoint PhoBERT đã khóa ở Stage 3. Không huấn luyện lại, không đổi
threshold, không dùng baseline TF-IDF để phục vụ. Model hiện là demo nghiên cứu:
test Macro-F1 0,6546, OFFENSIVE F1 0,4162, HATE recall 0,5770.

## Chạy local trên Windows

Tại root dự án, dùng môi trường `.venv-stage2` hiện có (hoặc Python 3.11 với Java 8+):

```powershell
.\.venv-stage2\Scripts\python.exe -m pip install -r requirements/stage4.txt
.\.venv-stage2\Scripts\python.exe scripts/package_stage4.py
.\.venv-stage2\Scripts\python.exe -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Mở [Swagger UI](http://127.0.0.1:8000/docs), chọn `/predict`, **Try it out**, nhập JSON rồi **Execute**.
Swagger UI cần tải JS/CSS từ CDN; inference và OpenAPI JSON không cần mạng.
Ctrl+C trong terminal chạy server để dừng. Không dùng `--reload` khi đo hiệu năng.

Nếu Swagger báo **Failed to fetch**, kiểm tra `http://127.0.0.1:8000/ready` trước.
Tab Swagger còn mở không có nghĩa API vẫn chạy. Sau khi server dừng hoặc khởi động lại máy,
chạy lại lệnh `uvicorn` ở trên, giữ terminal đó mở, đợi `Application startup complete`, rồi
tải lại trang `/docs`. Không cần cài dependencies hoặc export bundle lại mỗi lần khởi động.
Thông báo CORS của Swagger là gợi ý chung; kết nối bị từ chối cũng gây thông báo này.

```powershell
$payload = @{text = 'Chúc bạn một ngày vui vẻ!'} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/predict -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
```

Gói `outputs/stage4/bundle/` gồm checkpoint, tokenizer, encoder config, preprocessing config,
VnCoreNLP assets và SHA-256 manifest. Không chứa CSV train/test, optimizer hoặc checkpoint các run khác.
Không đưa bundle vào Git; sao chép riêng khi triển khai. Exporter kiểm tra model/config/selection với
lock Stage 3. API kiểm tra tất cả hashes của bundle trước khi nhận yêu cầu.
Không thay nội dung model trong bundle đang chạy; tạo phiên bản triển khai mới cho model mới.

## Hợp đồng API

| Endpoint | Chức năng |
|---|---|
| `GET /health` | Liveness của ứng dụng |
| `GET /ready` | Model đã nạp/warmup; `busy` cho biết đang xử lý |
| `GET /model` | Run, checkpoint hash, labels, device, giới hạn và trạng thái calibration |
| `POST /predict` | Một câu: `{"text":"Xin chào!"}` |
| `POST /predict/batch` | Danh sách: `{"texts":["Xin chào!","Cảm ơn bạn"]}` |
| `GET /docs`, `/openapi.json` | Giao diện thử API và schema |

Mỗi prediction trả `label_id` (0/1/2), `label` (CLEAN/OFFENSIVE/HATE), `confidence`,
`probabilities` đủ ba lớp, `token_count` trước truncation (gồm special tokens), và `truncated`.
Batch giữ nguyên thứ tự và trả `predictions`, `count`. API không trả lại hoặc ghi log nội dung câu.
Confidence là softmax **chưa hiệu chuẩn**, không phải xác suất quyết định chắc chắn đúng.

Giới hạn: 1–5.000 ký tự/câu, 1–32 câu/batch, tối đa 20.000 ký tự/batch, body tối đa 128 KiB.
Chuẩn hóa NFC và whitespace/URL/mention theo Stage 1, VnCoreNLP tách từ, tokenizer truncate 128 token,
rồi model argmax. Giữ emoji và cách viết gốc theo preprocessing đã dùng trong training.

| HTTP status | Ý nghĩa |
|---|---|
| 200 | Thành công |
| 422 | Sai schema/kiểu, rỗng sau chuẩn hóa, Unicode surrogate lỗi hoặc vượt giới hạn văn bản |
| 413 | Body quá 128 KiB, kể cả request chunked |
| 503 | Chưa ready hoặc đang bận; khi bận có `Retry-After: 1` |
| 500 | Inference lỗi; client không nhận traceback |

Model nạp một lần trong lifespan, warmup trước khi ready. Khởi tạo JVM và inference trên cùng
một worker thread; một request inference tại một thời điểm. Health vẫn có thể được xử lý khi
model bận. Client bị hủy không giải phóng slot khi model vẫn đang chạy. Một process/Uvicorn worker
để tránh nhân bản model trong RAM; throughput đo được không phải số người dùng đồng thời hỗ trợ.

## Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `VITOXIC_BUNDLE` | `<project>/outputs/stage4/bundle` | Thư mục artifact inference |
| `VITOXIC_DEVICE` | `cpu` | `cpu` hoặc `cuda` khi PyTorch/CUDA phù hợp |
| `VITOXIC_THREADS` | `4` | Số PyTorch CPU threads, số nguyên dương |

Không đọc đường dẫn Drive lịch sử trong config để tìm model. Trên Windows có đường dẫn tiếng Việt,
assets VnCoreNLP được sao chép vào thư mục ASCII trong TEMP và kiểm tra lại hashes trước khởi tạo JVM.

## Kiểm chứng và benchmark

```powershell
.\.venv-stage2\Scripts\python.exe -m pytest -q
.\.venv-stage2\Scripts\python.exe scripts/verify_stage4.py
```

Verifier tự khởi động một server local trên cổng trống, đợi ready, kiểm tra HTTP và dừng toàn bộ
cây tiến trình khi hoàn tất. So sánh 12 mẫu validation (4/nhãn thật) với predictions Colab đã lưu;
không đánh giá lại test. Kiểm tra NFC/NFD, single/batch, input lỗi, truncation và body limit.
Đo 20 request batch 1 và 5 request batch 8 sau warmup bằng một câu tổng hợp ngắn lặp lại.
RSS là tổng RSS cây tiến trình được lấy mẫu sau request, có thể đếm trùng shared pages và không phải peak allocation.
Kết quả thực tế và phiên bản môi trường ở `outputs/stage4/verification.json`.
Unit tests dùng model giả để kiểm tra API/concurrency; verifier HTTP dùng checkpoint và VnCoreNLP thật.

## Docker (cấu hình đã chuẩn bị, chưa chạy trên máy hiện tại)

Cần Docker Engine/Desktop. Export bundle trước, sau đó:

```text
docker compose up --build -d
docker compose logs -f api
docker compose down
```

Dockerfile cài Java và PyTorch CPU, chạy user không phải root. Compose mount bundle read-only,
chỉ bind `127.0.0.1:8000`. Build context loại dữ liệu, virtualenv và checkpoint. Image không chứa
weights; cần mang bundle riêng lên máy đích. Build cần internet, runtime inference không cần download.
Máy hiện tại không có lệnh Docker: chưa xác nhận build image, healthcheck container hoặc hành vi Linux.

Chưa có deploy public, HTTPS hay authentication. Khi có máy chủ/hosting đích, cần bổ sung cơ chế
truy cập và proxy phù hợp rồi đo tải trên máy đó; không dùng số benchmark local như cam kết production.
Không tự động xóa/chặn bình luận dựa trên kết quả demo này.

## Tài liệu tham khảo triển khai

- [FastAPI lifespan: nạp tài nguyên/model khi startup](https://fastapi.tiangolo.com/advanced/events/).
- [FastAPI trong container](https://fastapi.tiangolo.com/deployment/docker/).
