# ViToxic-Analyzer

Đồ án Machine Learning: phân loại bình luận tiếng Việt thành **CLEAN (0), OFFENSIVE (1), HATE (2)** trên ViHSD.

**Hiện tại: Stage 1 — Data Engineering & EDA.** Chưa huấn luyện PhoBERT và chưa có kết quả đánh giá model. Mục tiêu là một thí nghiệm có thể tái lập, giải thích được các lựa chọn và kiểm soát rò rỉ dữ liệu.

## Chạy trên Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m src.stage1
.\.venv\Scripts\python -m pytest -q
```

Đầu vào tại `data/ViHSD_train.csv`, `data/ViHSD_validation.csv`, `data/ViHSD_test.csv`, cột `free_text,label_id`. Không tải dữ liệu tự động. Môi trường Stage 1 đã chạy bằng Python 3.14; khi sang Stage 2 cần kiểm tra tương thích phiên bản PyTorch/Transformers riêng. `requirements-lock.txt` ghi lại môi trường Windows thực tế, còn `requirements.txt` chứa khoảng phiên bản.

Mở `notebooks/01_eda.ipynb` bằng VS Code/Jupyter và chọn `.venv` làm kernel. Notebook có outputs đã chạy; chạy lại từ đầu sẽ tái tạo báo cáo. Không cần GPU cho Stage 1.

## Đọc kết quả

- `reports/stage1/summary.md`: số liệu thực, leakage và giới hạn.
- `reports/stage1/audit.json`: thống kê chi tiết, class weights, cấu hình, SHA-256 dữ liệu và phiên bản thư viện.
- `reports/stage1/figures/`: phân bố nhãn, độ dài, word clouds chỉ trên train.
- `reports/stage1/train_ngrams.csv`: top 20 unigram/bigram/trigram mỗi lớp; đếm theo đơn vị chữ, chưa tách từ tiếng Việt.
- `data/processed/{train,validation,test}.csv`: dữ liệu đã chuẩn hóa, giữ nguyên số dòng/nhãn/split và cột gốc.
- `data/processed/train_decontaminated.csv`: train thay thế đã bỏ overlap với holdout, nhóm xung đột nhãn, dòng rỗng và bản sao.
- `data/processed/train_exclusions.csv`: row ID và lý do loại, ưu tiên empty → overlap → conflict → duplicate.

## Quyết định phương pháp

1. **Giữ split chính thức.** Không chia stratified lại từ ba tập có sẵn. Validation chọn cấu hình; test chỉ đánh giá cuối. Audit nhãn/overlap holdout là kiểm tra chất lượng, không dùng để quyết định mô hình. EDA nội dung chỉ đọc train.
2. **Hai giao thức tách biệt.** Bản official giữ mọi dòng để đối chiếu benchmark, nhưng vẫn có nguy cơ trùng lặp. Bản decontaminated dùng khóa từ text đã chuẩn hóa + casefold + khoảng trắng; việc mask URL/mention có thể gộp nội dung khác nhau. Chỉ dùng holdout text để lọc overlap; không dùng holdout labels để chỉnh train. Công bố chính sách và số dòng của mỗi thí nghiệm. Chưa kiểm tra near-duplicates.
3. **Preprocessing thận trọng.** Mặc định NFC, xử lý khoảng trắng/ký tự vô hình, mask URL/mention, giữ nội dung hashtag. Giữ hoa/thường, emoji, emoticon, dấu câu, số và từ tục để tránh mất tín hiệu. Lowercase và map teen code là tùy chọn để ablation bằng validation; từ điển nhỏ cố định, không học từ test. Không sửa nhãn bằng phỏng đoán.
4. **Imbalance chỉ từ train đang dùng.** Class weights `N/(3*n_c)`, thứ tự `[CLEAN, OFFENSIVE, HATE]`. Thử weighted loss và sampling như các thí nghiệm riêng; không mặc định kết hợp cả hai. Không oversample validation/test; chưa augmentation để tránh đổi nghĩa/nhãn.
5. **Macro-F1 là metric chính dự kiến.** Báo cáo thêm F1/recall từng lớp, confusion matrix, Weighted-F1 và accuracy. Chưa cam kết các target trong roadmap khi chưa có baseline. TF-IDF + Logistic Regression nên là baseline trước khi fine-tune PhoBERT.
6. **PhoBERT cần word segmentation.** `text_clean` chưa phải đầu vào hoàn chỉnh cho PhoBERT. Stage 2 phải nối bộ tách từ tương thích (theo hướng dẫn VinAI), rồi tokenizer; đo tỷ lệ truncation bằng tokenizer trên train/validation trước khi chốt `max_length`. Histogram hiện tại không phải số subword tokens. Giữ thống nhất pipeline train/inference.

`src/data_loader.py` cung cấp CSV loader, class weights và wrapper PyTorch tùy chọn. Torch chưa nằm trong dependencies Stage 1; các wrapper Torch chưa được kiểm chứng trong môi trường này. Tokenized Dataset, collator và training thuộc Stage 2.

## Những gì cần hiểu để bảo vệ đồ án

- Vì sao accuracy cao có thể che giấu lỗi ở lớp OFFENSIVE/HATE?
- Vì sao không xóa mọi emoji, từ tục và dấu câu?
- Duplicate giữa train/test làm lệch đánh giá thế nào? Exact matching bỏ sót điều gì?
- Vì sao cần tính lại weights sau khi lọc train?
- Từ tiếng Việt, đơn vị phân cách bằng khoảng trắng và subword khác nhau thế nào?

## Phạm vi CV

Có thể mô tả sau khi tự chạy và giải thích được kết quả: “Built a reproducible data auditing and preprocessing pipeline for Vietnamese hate-speech classification, including split-overlap analysis, configurable Unicode normalization and train-only class balancing.”

Chưa ghi “trained/deployed PhoBERT”, F1 hay khả năng moderation thực tế. Khi hoàn thành các stage sau, bổ sung baseline, kết quả trên test, giao thức chống leakage và phân tích lỗi. Ba nhãn là các lớp phân loại; không mặc định xác suất model là thang điểm mức độ độc hại đã được hiệu chuẩn.

## Nguồn và giới hạn

- [ViHSD — tác giả và nguồn dữ liệu](https://github.com/sonlam1102/vihsd)
- [Bài báo ViHSD](https://arxiv.org/abs/2103.11528)
- [PhoBERT — hướng dẫn word segmentation](https://github.com/VinAIResearch/PhoBERT)

CSV hiện có do người dùng cung cấp; hash phục vụ truy vết, chưa chứng minh trùng bản phát hành gốc. Trước khi chia sẻ lại dữ liệu cần xác minh điều kiện sử dụng từ nguồn. `.gitignore` loại dữ liệu CSV/processed khỏi commit mới, nhưng không untrack file đã có trong Git. Word clouds và n-grams có thể chứa ngôn từ xúc phạm; cần xem trước khi đưa lên portfolio. Nhãn phản ánh bộ dữ liệu và có thể có thiên lệch hoặc thiếu ngữ cảnh.
