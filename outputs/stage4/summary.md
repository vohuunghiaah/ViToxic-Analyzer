# Stage 4 — API local và bộ triển khai

Kiểm chứng ngày 2026-10-13. Dùng nguyên checkpoint
`phobert_lr3e-5_len128_drop01_batch16_seed42`, SHA-256
`f8a6a9a785c4f7fefcaba2e228944e6fe29d0ac673eb96864937e9ffb8ea9156`.
Không train lại hoặc đánh giá lại toàn bộ test.

## Đã hoàn tất

- FastAPI: `/predict`, `/predict/batch`, `/health`, `/ready`, `/model`, `/docs` và OpenAPI.
- Bundle offline 14 files với SHA-256, không chứa CSV hoặc optimizer state.
- Preprocessing và VnCoreNLP thật; model tải một lần, warmup trước khi ready.
- Giới hạn input/body, xử lý Unicode/truncation; một inference tại một thời điểm,
  trả 503 khi bận, không nhả slot sớm khi client hủy yêu cầu.
- **38 tests đạt** (Stage 1–4). Unit tests API dùng fixture; kiểm chứng HTTP riêng dùng model thật.
- **12/12 dự đoán validation khớp Colab** qua API, 0 mismatch. Unicode NFC/NFD và single/batch khớp.
- Dockerfile CPU, Compose, hướng dẫn chạy và lockfile môi trường Windows đã tạo.

## Benchmark local CPU

| Batch | Số request | Latency p50 | Latency p95 | Throughput |
|---|---:|---:|---:|---:|
| 1 | 20 | 111,2 ms | 145,2 ms | 9,07 câu/s |
| 8 | 5 | 365,7 ms | 435,9 ms | 23,63 câu/s |

Startup gồm nạp model và warmup: **23,6 giây**. RSS cây tiến trình lớn nhất quan sát sau request:
**1.008,2 MiB**. Đã sửa phép đo Windows để tính cả interpreter con của venv launcher.

Đây là benchmark HTTP sau warmup, dùng một câu tổng hợp ngắn lặp lại. Không phải load test,
không kiểm soát mọi hoạt động nền của máy, chỉ 5 mẫu ở batch 8; p95 chưa phải ước lượng ổn định.
Tổng RSS có thể đếm trùng shared pages, không đo peak allocation. Chi tiết máy/phần mềm và scope
ở `verification.json`; log server thử nghiệm ở `verification_server.log`.

## Chưa được xác minh

- Docker build/run chưa thực hiện vì máy hiện tại không có Docker.
- Chưa deploy public, cấu hình HTTPS/authentication hoặc kiểm thử tải trên máy chủ.
- CUDA chưa được kiểm chứng trong API; lần này chỉ CPU.
- TestClient hiện có deprecation warning với httpx; tests vẫn pass, cần theo dõi dependency khi nâng cấp.

Chất lượng model giữ nguyên Stage 3: test Macro-F1 0,6546, OFFENSIVE F1 0,4162,
HATE recall 0,5770. Softmax chưa calibration; API chạy đúng không chứng minh chất lượng moderation
production. Không tuyên bố Stage 4 đã hoàn tất phần triển khai public.

Hướng dẫn: [STAGE4_API.md](../../docs/STAGE4_API.md).
