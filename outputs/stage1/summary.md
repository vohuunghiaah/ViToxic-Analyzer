# Stage 1 — Kết quả trên dữ liệu thực

Tạo lại bằng `python -m src.stage1`.

| Split | Rows | CLEAN | OFFENSIVE | HATE | Empty | Duplicate excess (normalized) |
|---|---:|---:|---:|---:|---:|---:|
| train | 24048 | 19886 | 1606 | 2556 | 2 | 1535 |
| validation | 2672 | 2190 | 212 | 270 | 0 | 22 |
| test | 6680 | 5548 | 444 | 688 | 0 | 107 |

## Trùng lặp giữa các tập

Khóa so sánh: preprocessing mặc định + casefold + chuẩn hóa khoảng trắng. Không phải kiểm tra tương đồng ngữ nghĩa.

- train__validation: 322 nội dung chung; 28 nhóm khác nhãn.
- train__test: 792 nội dung chung; 80 nhóm khác nhãn.
- validation__test: 92 nội dung chung; 13 nhóm khác nhãn.

Train loại overlap / duplicate / conflict / empty: **21292** dòng (gốc 24048).

## Class weights: N / (3 × count)

Theo thứ tự CLEAN, OFFENSIVE, HATE:

- official_train: CLEAN=0.4031, OFFENSIVE=4.9913, HATE=3.1362
- decontaminated_train: CLEAN=0.4049, OFFENSIVE=5.0158, HATE=3.0201

## Diễn giải và giới hạn

- Chỉ dự đoán lớp đông nhất đã đạt accuracy 82.69% trên train; đây không phải kết quả model trên test.
- Ưu tiên Macro-F1, kèm F1/recall từng lớp; Weighted-F1 và accuracy là chỉ số bổ sung.
- EDA nội dung, n-grams, word clouds chỉ dùng train. Audit holdout chỉ phục vụ kiểm tra chất lượng, không chọn hyperparameter.
- N-grams/độ dài tính theo đơn vị chữ phân cách bởi khoảng trắng, chưa phải từ tiếng Việt hoặc subword PhoBERT.
- Bản decontaminated là thí nghiệm bổ sung; phải công bố số dòng và không so trực tiếp như cùng giao thức benchmark.
- Validation/test có overlap vẫn được giữ nguyên; ghi rõ giới hạn này khi báo cáo kết quả cuối.
- Placeholder URL/mention có thể gộp hai nội dung khác nhau; cần review chính sách trước khi chốt giao thức huấn luyện.
- Chưa huấn luyện model, chưa chọn độ dài tokenizer và chưa thực hiện word segmentation.
