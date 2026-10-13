# Stage 3 — Evaluation & Analysis

Pipeline `src/evaluate.py` dùng đúng PhoBERT trong `outputs/stage2/final_selection/selection.json`
và `outputs/stage2/baseline/baseline.joblib` đã fit trên Colab. Không train lại và không tìm
hyperparameter trên test. Kết quả là inference local, không gọi là một lần chạy Colab mới.

## Chạy

Từ root, dùng môi trường Stage 2 có PyTorch, Java và assets VnCoreNLP:

```text
python -m src.evaluate
python -m pytest -q
python scripts/build_stage3_notebook.py
python scripts/verify_stage3.py
```

Mở `notebooks/03_evaluation.ipynb` để đọc kết quả. Notebook mặc định không chạy lại inference.
Trên Colab, mount Drive và đặt `PROJECT` thành thư mục gốc đã upload. Không cần ZIP.
Baseline được serialize bằng scikit-learn 1.6.1; ưu tiên phiên bản đó để tái lập. Pipeline
kiểm tra lại C và validation Macro-F1 trước khi đánh giá test, kể cả khi môi trường khác phiên bản.

`--batch-size` chỉ điều chỉnh batch inference, không thay effective batch huấn luyện.
`--root` chọn root dự án; `--output` mặc định `outputs/stage3`.
Nếu đầu vào khác SHA-256 đã khóa, pipeline dừng. Khi đã có `metrics.json`, lần gọi tiếp theo
đọc kết quả đã lưu. Giữ nguyên artifact đầu tiên; không xóa lock để chọn lại model theo test.
Nếu lần chạy bị gián đoạn, chạy lại với đầu vào y hệt; inference được chạy lại từ đầu.

`python scripts/build_stage3_report.py` dựng lại báo cáo từ predictions đã lưu, không inference
và không thay điểm số. Các cột nhận xét trong review queue được giữ lại theo row ID.

## Artifact

| File | Nội dung |
|---|---|
| `lock.json` | Hash selection, checkpoint, baseline, config, dữ liệu và assets tách từ |
| `provenance.json` | Thời điểm, thiết bị, batch, phiên bản, source hash, segmentation cache |
| `metrics.json`, `comparison.csv` | Test metrics của hai model; metrics chỉ được ghi khi hoàn tất |
| `*_classification_report.csv` | Precision, recall, F1 và support |
| `*_confusion_matrix.png` | Số lượng và tỷ lệ chuẩn hóa theo nhãn thật |
| `test_predictions.csv` | Row ID, ground truth, dự đoán hai model, PhoBERT probabilities, độ dài |
| `errors.csv`, `error_review.csv` | Toàn bộ lỗi PhoBERT và mẫu để đọc ngữ cảnh |
| `slices.csv` | Độ dài token và overlap validation/test |
| `bootstrap.json` | Paired row bootstrap 2.000 lần, seed 42; CI percentile 95% Macro-F1 và delta |
| `summary.md` | Báo cáo tổng hợp |

Điểm chính dùng toàn bộ official test. Lát cắt bỏ overlap validation là phân tích độ nhạy,
không tạo split mới để chọn model. Token length tính trước truncation, bao gồm special tokens.
Macro-F1 trên mọi lát cắt luôn lấy trung bình cả ba lớp; lớp vắng có F1 bằng 0.

Bootstrap chỉ biểu diễn biến thiên lấy mẫu test có điều kiện theo hai model đã cố định,
không đo độ ổn định nhiều seed. Duplicate/ngữ cảnh chung có thể khiến CI theo dòng quá hẹp.
Confidence softmax chưa calibration; lỗi confidence cao không chứng minh annotation sai.
Các ô nhận xét trong review queue để trống có chủ đích cho người học, không phải thiếu dự đoán.
