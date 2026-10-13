# ViToxic-Analyzer

Đồ án Machine Learning phân loại bình luận tiếng Việt: **CLEAN / OFFENSIVE / HATE** trên ViHSD, sử dụng baseline TF-IDF và PhoBERT.

## Trạng thái hiện tại

- **Stage 1:** đã audit, preprocessing và tạo train decontaminated (21.292 mẫu).
- **Stage 2:** đã fine-tune PhoBERT trên Colab Tesla T4; model được chọn có best checkpoint epoch 5.
- **Tuning:** hoàn thành 8 cấu hình tuần tự, seed 42, thử learning rate, max length, dropout và effective batch size. Đây không phải full grid.
- **Length 256 rerun:** best checkpoint epoch 5 đã reload trên toàn bộ validation và khớp 2.672/2.672 dự đoán; thay run cũ trong bảng tuning. Last checkpoint rerun còn ở epoch 4, xem báo cáo review.
- **Stage 3:** đã đánh giá đủ 6.680 mẫu test local bằng model và baseline Colab đã khóa. Bảng đầu dưới đây là **validation**, một seed.
- **Stage 4:** API local đã triển khai và kiểm chứng HTTP với model thật; đã chuẩn bị Docker, chưa build container hoặc deploy public. Xem [hướng dẫn API](docs/STAGE4_API.md).

| Model — cùng dữ liệu Colab | Macro-F1 | Weighted-F1 | Accuracy |
|---|---:|---:|---:|
| Character TF-IDF + Logistic Regression (C=2) | 0.6173 | 0.8380 | 0.8335 |
| PhoBERT — best epoch 5, effective batch 16 | **0.6843** | **0.8691** | **0.8679** |

Đọc [báo cáo kiểm tra Stage 2](outputs/stage2/review/summary.md) để xem F1 từng lớp, dấu hiệu overfitting và phạm vi xác minh.

### Kết quả test — Stage 3

| Model | Test Macro-F1 | Weighted-F1 | Accuracy |
|---|---:|---:|---:|
| Baseline Colab TF-IDF + Logistic Regression | 0.6325 | 0.8494 | 0.8436 |
| PhoBERT — model chọn bằng validation | **0.6546** | **0.8665** | **0.8647** |

Đã xuất classification reports, confusion matrices, 904 lỗi PhoBERT, phân tích ngữ cảnh và bootstrap.
OFFENSIVE F1 **0.4162**, HATE recall **0.5770**; chưa đạt mục tiêu ban đầu.
95 dòng test overlap validation; lát cắt không overlap có Macro-F1 **0.6536**.
Đọc [báo cáo Stage 3](outputs/stage3/summary.md), [phân tích lỗi](outputs/stage3/qualitative_analysis.md)
hoặc mở [notebook 03](notebooks/03_evaluation.ipynb). [Hướng dẫn chạy](docs/STAGE3_EVALUATION.md).

## Cấu trúc thư mục

```text
ViToxic-Analyzer/
├── configs/                 # Cấu hình mẫu cho run mới
├── data/
│   ├── raw/                 # CSV gốc, không chỉnh sửa
│   ├── processed/           # Các split sau Stage 1
│   └── cache/segmented/     # Cache tách từ, có thể tái tạo
├── docs/                    # Hướng dẫn và giải thích cấu trúc
├── notebooks/               # 01_eda, 02_training, 03_evaluation
├── outputs/
│   ├── stage1/              # Audit, EDA, biểu đồ
│   ├── stage2/              # Baseline, runs, search và review
│   ├── stage3/              # Test metrics, predictions, biểu đồ và phân tích lỗi
│   ├── stage4/              # Bundle inference và kiểm chứng API/benchmark
│   └── archive/             # Kết quả local/tài nguyên cũ để đối chiếu
├── requirements/
│   ├── stage1.txt           # Dependencies EDA
│   ├── stage2.txt           # Dependencies training
│   └── locks/               # Phiên bản thực tế Windows/Colab
├── resources/vncorenlp/     # JAR và model tách từ
├── scripts/                 # Tạo notebook, kiểm tra, migration
├── src/                     # Pipeline dữ liệu và huấn luyện
└── tests/                   # Kiểm thử Stage 1–4
```

Chức năng từng module, vị trí checkpoint và đường dẫn cũ → mới: [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Chạy trên Google Colab

Upload thư mục đã sắp xếp lên Drive, mở `notebooks/02_training.ipynb`, chọn GPU và chạy từng ô. Ô đầu mặc định:

```python
PROJECT = Path('/content/drive/MyDrive/ViToxic-Analyzer')
```

Notebook đọc trực tiếp Drive, không cần ZIP. Kết quả nằm trong `outputs/stage2/`. Run đã hoàn tất sẽ được đọc lại thay vì train lại. Muốn chạy cấu hình mới, đổi `RUN_NAME`; search mới dùng `search_v2` để giữ nguyên kế hoạch lịch sử. Xem [STAGE2_COLAB.md](docs/STAGE2_COLAB.md).

Không cần upload `.git/`, `.venv/`, `.venv-stage2/`, `.pytest_cache/` hoặc `outputs/archive/`. Giữ run đã huấn luyện, processed data, source, config, requirements và notebook. Bản Drive cũ chưa được tự động thay đổi: hãy upload bản cấu trúc mới này.

## Chạy và kiểm tra cục bộ

Chạy từ root sau khi kích hoạt môi trường tương ứng:

```text
python -m pip install -r requirements/stage1.txt
python -m src.stage1
python -m pytest -q tests/test_stage1.py
```

Với môi trường Stage 2 đã có PyTorch:

```text
python -m pip install -r requirements/stage2.txt
python -m pytest -q
python scripts/verify_stage2.py
python scripts/audit_downloaded_stage2.py
```

`verify_stage2.py` kiểm tra run ban đầu trên 12 mẫu. `audit_downloaded_stage2.py` kiểm tra các artifact Colab đã tải về, bảng chọn model và chạy lại toàn bộ 2.672 mẫu validation bằng checkpoint cuối trên CPU. Báo cáo ở `outputs/stage2/review/full_audit.json`. Không huấn luyện hoặc đánh giá test.

Stage 3: `python -m src.evaluate` (đọc lại kết quả nếu đã hoàn tất);
`python scripts/verify_stage3.py` kiểm tra artifact mà không inference lại.
Không fit lại baseline hoặc dùng test để đổi cấu hình. Baseline lưu bằng scikit-learn 1.6.1,
local dùng 1.9.1 có cảnh báo phiên bản; đã tái tạo đúng validation Macro-F1 trước test.

## API local — Stage 4

```text
python -m pip install -r requirements/stage4.txt
python scripts/package_stage4.py
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Mở [Swagger UI](http://127.0.0.1:8000/docs). Hỗ trợ `POST /predict`, `POST /predict/batch`,
`GET /health`, `GET /ready`, `GET /model`. Model được nạp một lần, dùng đúng preprocessing và
checkpoint đã đánh giá; confidence chưa calibration. Kiểm chứng: `python scripts/verify_stage4.py`.
Gói model chưa gồm cơ chế moderation tự động hoặc chất lượng production.

## Nguyên tắc thí nghiệm

- Giữ nguyên raw data và split chính thức. Train decontaminated lọc overlap/conflict/duplicate; công bố giao thức này khi so benchmark.
- EDA nội dung chỉ trên train. Validation chọn model; test đánh giá cuối.
- Preprocessing giữ emoji, dấu câu, số và tín hiệu ngôn ngữ; VnCoreNLP tách từ trước PhoBERT tokenizer.
- Class weights chỉ từ train; không oversample holdout. Macro-F1 chọn checkpoint/early stopping.
- Mỗi run giữ model, tokenizer, config, manifest, hashes, history và predictions cùng nhau. Config/manifest cũ bất biến, dù chứa đường dẫn Colab trước migration.
- Source snapshot của run cũ được bảo toàn. Đổi code thì không resume checkpoint bằng source mới; dùng run mới.

## Nguồn và giới hạn

[ViHSD](https://github.com/sonlam1102/vihsd) · [Bài báo ViHSD](https://arxiv.org/abs/2103.11528) · [PhoBERT](https://github.com/VinAIResearch/PhoBERT) · [VnCoreNLP](https://github.com/vncorenlp/VnCoreNLP).

CSV do người dùng cung cấp; hashes truy vết đầu vào, không chứng minh nguồn phát hành. Có overlap validation/test được ghi ở Stage 1. Đã có test score một seed, chưa đánh giá moderation thực tế. Gọi đúng **0.6843 là validation Macro-F1**, **0.6546 là test Macro-F1**. Không suy rộng kết quả thành chất lượng production; không tuning tiếp trên test đã xem.
