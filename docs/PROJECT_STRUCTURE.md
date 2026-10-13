# Cấu trúc dự án

## Bốn nhóm chính

1. **Code/cấu hình:** `src/`, `configs/`, `tests/`, `scripts/`.
2. **Dữ liệu/tài nguyên:** `data/raw/`, `data/processed/`, `data/cache/`, `resources/`.
3. **Kết quả:** `outputs/stage1/`, `outputs/stage2/`, `outputs/stage3/`, `outputs/stage4/`.
4. **Hướng dẫn/môi trường:** `README.md`, `docs/`, `notebooks/`, `requirements/`.

Chạy CLI từ root. Không đặt checkpoint vào source; không sửa config lịch sử để dùng làm cấu hình mẫu.

## Module

| Module | Trách nhiệm |
|---|---|
| `src/stage1.py` | Audit, EDA, xuất processed data |
| `src/preprocessing.py` | Chuẩn hóa văn bản |
| `src/data_loader.py` | CSV loader, weights/sampler |
| `src/segmentation.py` | VnCoreNLP và cache |
| `src/dataset.py` | Dataset, tokenizer, padding |
| `src/model.py` | PhoBERT, head, reload checkpoint |
| `src/train.py` | Training, validation, resume |
| `src/baseline.py` | TF-IDF + Logistic Regression |
| `src/tune.py` | Search tuần tự và bảng so sánh |
| `src/evaluate.py` | Khóa model, đánh giá test, bootstrap và phân tích lỗi Stage 3 |
| `src/serving.py` | Kiểm tra bundle, preprocessing → segmentation → tokenizer → inference |
| `src/api.py` | HTTP API, schema/limits, lifespan và điều phối inference |
| `src/config.py`, `src/experiment.py` | Config, metrics, provenance |

Giữ package `src` và lệnh `python -m src.train` ổn định; chưa cần chia thành nhiều package con.

## Kết quả Stage 3

`outputs/stage3/` giữ lock/provenance, test predictions, metrics của PhoBERT và baseline,
classification reports, confusion matrices, bootstrap, các lát cắt và error review queue.
Đọc `docs/STAGE3_EVALUATION.md`; mở `notebooks/03_evaluation.ipynb` để xem báo cáo.
`scripts/verify_stage3.py` đối chiếu dữ liệu gốc và tính lại metrics, không chạy lại inference.

## Triển khai Stage 4

`scripts/package_stage4.py` tạo `outputs/stage4/bundle/` chỉ gồm model và assets inference,
không có dữ liệu train/test. `scripts/verify_stage4.py` kiểm chứng HTTP và ghi benchmark.
`Dockerfile`, `compose.yaml`, `.dockerignore` chuẩn bị container CPU; xem `docs/STAGE4_API.md`.
Bundle bị Git ignore, phải chuyển riêng khi deploy. Hiện đã kiểm chứng local, chưa build Docker.

## Kết quả Stage 2

```text
outputs/stage2/
├── baseline/                          # Baseline thật trên Colab
├── runs/phobert_lr2e-5_len128_seed42/
│   ├── best_model.pt                  # Best model epoch 3
│   ├── last_checkpoint.pt             # Resume state cuối epoch
│   ├── tokenizer/, encoder_config/    # Reload offline
│   ├── config.json, manifest.json     # Hồ sơ gốc, không sửa
│   ├── history.json, learning_curves.png
│   ├── validation_metrics.json, validation_predictions.csv
│   ├── token_lengths.json, baseline_comparison.csv
│   └── source_snapshot/src/           # Source cũ, khớp manifest
├── submitted_configs/                 # Config đã gửi lên Colab
├── active_configs/                    # Notebook tạo khi chạy lần tới
├── search_v1/                         # 4 learning-rate trials completed
├── final_selection/                   # Bảng 8 cấu hình và selection.json từ Colab
├── search_v2/                         # Chỉ tạo khi dùng notebook search mới
└── review/                            # Báo cáo kiểm chứng
```

Kết quả chính thức duy nhất của Stage 2 nằm tại `outputs/stage2/` (Colab). `outputs/archive/stage2_pretraining/` là dữ liệu cũ đã ngừng sử dụng, đang chờ xóa vì thao tác xóa bị hệ thống chặn. `outputs/archive/local_resources/` giữ tài nguyên local cũ; tài nguyên đang dùng tại `resources/vncorenlp/`.

`runs/` hiện có thêm bốn run length 256, dropout 0.2, dropout 0.3 và effective batch 16. Model cuối nằm tại `runs/phobert_lr3e-5_len128_drop01_batch16_seed42/`. `review/full_audit.json` kiểm tra toàn bộ chín thư mục run (gồm run ban đầu), tám cấu hình tuning và reload model cuối. Đọc `review/summary.md` trước khi dùng các checkpoint khác vì có artifact không khớp báo cáo.

## Đường dẫn cũ → mới

| Cũ | Mới |
|---|---|
| `data/ViHSD_*.csv` | `data/raw/ViHSD_*.csv` |
| `reports/stage1/` | `outputs/stage1/` |
| `stage2/runs/` | `outputs/stage2/runs/` |
| `stage2/baseline/` | `outputs/stage2/baseline/` |
| `stage2/search_v1/` | `outputs/stage2/search_v1/` |
| `stage2/segmentation_cache/` | `data/cache/segmented/` |
| `stage2/vncorenlp/` | `resources/vncorenlp/` |
| `reports/stage2/` | `outputs/archive/stage2_pretraining/` |
| `requirements*.txt` | `requirements/` và `requirements/locks/` |
| `scripts/package_colab.py` | `scripts/legacy/package_colab.py` (ngừng dùng) |

Migration ghi tại `outputs/migration-2026-10-11.json`. Raw CSV, checkpoint, lịch sử và config gốc giữ nguyên nội dung. Notebook EDA giữ outputs đã chạy, chỉ đổi đường dẫn cell source. Script ZIP là bản lịch sử, không dùng cho workflow Drive.

## Google Drive và checkpoint cũ

Upload thư mục mới sau refactor; thay notebook và source đồng thời. `PROJECT` vẫn như cũ; kết quả mới là `PROJECT / 'outputs/stage2'`. Không chỉ upload notebook mới trong khi dữ liệu vẫn ở đường dẫn cũ.

Checkpoint reload bằng `load_checkpoint_model(run_directory)` vẫn hoạt động. Resume kiểm tra source hashes: code thay đổi thì tạo run mới. Run đầu đã hoàn tất 5 epochs; không cần resume để xem kết quả hoặc dùng Stage 3. Hồ sơ gốc giữ đường dẫn Colab cũ làm provenance, không dùng các đường dẫn đó làm chỉ dẫn chạy mới.
