# Stage 2 — Hướng dẫn chạy trên Google Colab

Đã hoàn tất tuning tuần tự 8 cấu hình trên Colab, seed 42. Run được chọn là `phobert_lr3e-5_len128_drop01_batch16_seed42`, best epoch 5, validation Macro-F1 0.684326. Bốn trials trong `search_v1` đều completed. Xem `outputs/stage2/review/summary.md` để biết kết quả kiểm tra artifact tải về và các bất nhất còn tồn đọng.

## Bắt đầu

1. Upload thư mục `ViToxic-Analyzer` lên Google Drive (mặc định đặt ngay trong My Drive), rồi mở `notebooks/02_training.ipynb` bằng Google Colab.
2. Chọn Runtime → Change runtime type → GPU.
3. Chạy các ô theo thứ tự. Ô đầu mount Google Drive; đặt `PROJECT = Path('/content/drive/MyDrive/ViToxic-Analyzer')` trỏ đúng thư mục vừa upload. Notebook kiểm tra các file cần thiết và đọc trực tiếp trên Drive, không yêu cầu ZIP.
4. Kiểm tra cấu hình ở ô 4. Mặc định batch 8, accumulation 4, max_length 128, LR 2e-5, tối đa 5 epochs và patience 2 theo Macro-F1. Đây là cấu hình bắt đầu, chưa được chứng minh tối ưu.
5. Chạy baseline và PhoBERT. Kết quả lưu ở `MyDrive/ViToxic-Analyzer/outputs/stage2/runs/<RUN_NAME>`.
6. Xem loss/F1, phân bố token lengths và bảng so sánh. Để tuning, bật `RUN_SEARCH=True`; mặc định 4 trials learning rate. Mở rộng ngân sách để thử effective batch 16/32, max_length 128/256, dropout 0.1/0.2/0.3.

Thư mục upload cần có `src/`, `configs/`, `tests/`, `notebooks/`, `requirements/stage2.txt` và `data/processed/` với `train_decontaminated.csv` (21.292 mẫu), `validation.csv` (2.672 mẫu). Stage 2 không đọc test dù file test có trong thư mục. Không cần công khai dataset/GitHub để chạy Colab. Các thư mục môi trường local `.venv/`, `.venv-stage2/` không cần thiết trên Colab.

Khi source thay đổi, cập nhật file tương ứng trong thư mục Drive. Nếu sửa script tạo notebook, chạy `python scripts/build_stage2_notebook.py` rồi upload lại notebook. Khi thay code/data/config, dùng tên run/search mới và restart runtime để nạp lại module. Đường dẫn kết quả là `PROJECT / 'outputs/stage2'`, nên tự thay đổi theo vị trí dự án.

## Tính tái lập và resume

- Seed cho Python, NumPy, PyTorch, DataLoader và sampler; lưu config, resolved model revision, file hashes, segmenter asset hashes, source hashes và phiên bản môi trường.
- VnCoreNLP assets được tải từ commit cố định của nguồn chính thức; cache theo text, row IDs và asset hashes, tránh dùng nhầm preprocessing cache.
- Tokenizer được lưu cùng checkpoint và cố định theo revision encoder. Có hàm reload offline `load_checkpoint_model()`.
- `best_model.pt` chứa model tốt nhất theo metric đã chọn. `last_checkpoint.pt` chứa model cuối epoch, optimizer, scheduler, GradScaler, RNG và early-stopping state.
- Resume từ **cuối epoch hoàn tất gần nhất**, không resume giữa batch. Epoch đang chạy sẽ phải chạy lại. Chạy lại ô train sẽ tự thêm `--resume` nếu có checkpoint.
- Nếu lỗi xảy ra trước checkpoint đầu tiên, chọn RUN_NAME mới để chạy lại. Không tự xóa thư mục kết quả cũ.
- Không đổi epochs/LR/batch/precision/seed khi resume; lịch learning rate phụ thuộc tổng số bước ban đầu. Dùng run mới khi đổi hyperparameters.
- Kết quả GPU có thể khác nhẹ giữa phần cứng/phiên bản runtime; resume trên CPU đã được test bit-for-bit với fixture nhỏ, không có cam kết GPU giống tuyệt đối giữa mọi môi trường.
- Lưu file tạm rồi replace để hạn chế checkpoint dở dang. Google Drive/quota vẫn có thể gây lỗi I/O; kiểm tra dung lượng trước khi search. Dự trù khoảng 5 GB/run gồm file tạm.

## Thiết kế ML

`preprocess_text` Stage 1 → VnCoreNLP/RDRSegmenter → PhoBERT tokenizer → dynamic padding/truncation → encoder → Dropout/Linear/Tanh/Dropout/Linear (3 logits).

- Weighted loss = weighted CrossEntropy với weights từ train đang dùng. Sampler là một lựa chọn khác, không đồng thời nhân đôi cân bằng lớp.
- Gradient accumulation chuẩn hóa theo tổng trọng số của **những mẫu thật trong nhóm**, kể cả nhóm cuối thiếu batch.
- AdamW tách bias/LayerNorm khỏi weight decay; linear warmup rồi cosine decay. Scheduler chỉ tăng khi optimizer thực hiện bước (không tăng khi AMP overflow).
- FP16 dùng GradScaler; BF16 chỉ khi GPU hỗ trợ; CPU test dùng FP32.
- Gradient checkpointing giảm VRAM. Freeze encoder theo `freeze_epochs`, mặc định 0 để fine-tune toàn bộ ngay từ đầu.
- `selection_metric=macro_f1` mặc định; đổi sang `loss` nếu cần bám roadmap gốc. Checkpoint và early stopping dùng cùng metric. Validation loss dùng weights train.
- `max_length=128` là cấu hình đầu; `token_lengths.json` báo truncation ở 128/256 cho train và validation. Search mới quyết định độ dài tốt hơn, không chọn theo test.
- Baseline dùng character TF-IDF 3–5 grams + Logistic Regression balanced, C trong {0.5, 1, 2}. Character n-grams thích hợp làm baseline không phụ thuộc word segmentation, nhưng hiệu quả phải kiểm chứng bằng dữ liệu.
- Search tuần tự bằng subprocess, mỗi trial khởi tạo lại từ pretrained và không kế thừa model đã fine-tune. `comparison.csv` phân biệt rõ planned/completed; selected_run chỉ xuất khi có kết quả.

## Lệnh tương đương

Sau khi đã cài dependencies, chuẩn bị processed data và Java:

```text
python -m src.segmentation --download
python -m src.baseline --output outputs/stage2/baseline_new
python -m src.train --config configs/phobert_colab.json
python -m src.train --config configs/phobert_colab.json --resume
python -m src.tune --config configs/phobert_colab.json --max-trials 4
python -m src.tune --config configs/phobert_colab.json --max-trials 4 --execute
python -m pytest -q
```

CLI mặc định lưu local. Notebook đổi output/cache/segmenter sang Drive để giữ qua phiên Colab. Cài `requirements/stage2.txt`; GPU Torch có sẵn của Colab được giữ nếu thỏa phiên bản.

## Khi gặp lỗi

- **CUDA unavailable:** bật GPU runtime; không tự chuyển sang CPU huấn luyện nhiều giờ.
- **CUDA out of memory:** run mới với batch 4, accumulation 8, eval_batch 8; nếu cần batch 2, accumulation 16. Giữ gradient checkpointing.
- **Java/JVM lỗi:** kiểm tra `java -version`; chạy segmentation/training bằng subprocess như notebook. Không khởi tạo nhiều JVM trong một kernel.
- **Windows có đường dẫn tiếng Việt:** JVM/pyjnius có thể không đọc được classpath có dấu. Dùng thư mục assets không dấu nếu kiểm thử cục bộ; đường dẫn Colab mặc định trong notebook không gặp trường hợp này.
- **Network download lỗi:** chạy lại cell tải assets; file chưa hoàn tất dùng đuôi `.download`, không coi là model hoàn chỉnh.
- **Run directory exists:** dùng RUN_NAME mới, hoặc resume khi có `last_checkpoint.pt`. Không ghi đè checkpoint cũ.
- **Search bị ngắt:** dùng lại cùng config, output và max_trials; các trial xong được bỏ qua, trial có checkpoint tiếp tục chạy.
- **Restart sau pip install:** chạy lại các cell từ đầu và mount Drive; không cần upload lại thư mục.

## Hoàn thành Stage 2 và ghi CV

Đã thử đủ các giá trị LR/length/dropout/effective batch trong roadmap bằng 8 cấu hình tuần tự, không phải full grid. Model cuối dùng LR 3e-5, length 128, dropout 0.1, microbatch 8 × accumulation 2 = effective batch 16. Không cần train thêm chỉ để chạy full grid. Stage 3 dành cho test, error analysis và so sánh cuối cùng. Kiểm tra tình trạng artifact ở báo cáo review trước khi sử dụng checkpoint của các run khác.

Baseline Colab đạt validation Macro-F1 0.6173 (C=2); PhoBERT được chọn đạt 0.6843. Đây là validation score, không phải test score. Chỉ sử dụng kết quả Colab để báo cáo và so sánh. Giao thức dùng train decontaminated khác benchmark official; còn overlap giữa validation/test được ghi nhận ở Stage 1.

## Nguồn

- [PhoBERT và yêu cầu word segmentation](https://github.com/VinAIResearch/PhoBERT)
- [VnCoreNLP](https://github.com/vncorenlp/VnCoreNLP)
- [PyTorch AMP](https://docs.pytorch.org/docs/stable/notes/amp_examples.html)
- [Giới hạn và lưu trữ Colab](https://research.google.com/colaboratory/faq.html)

## Run cũ sau khi sắp xếp thư mục

Run hoàn tất nằm tại `outputs/stage2/runs/phobert_lr2e-5_len128_seed42/`. Config/manifest gốc giữ đường dẫn Colab cũ để bảo toàn provenance; reload model dùng đường dẫn run mới, không cần sửa config gốc. Source snapshot khớp toàn bộ 12 hashes trong manifest. Không resume run này bằng code đã đổi đường dẫn: cơ chế source-hash guard sẽ từ chối. Run đã hoàn tất nên chỉ cần đọc kết quả/reload; dùng RUN_NAME và thư mục search mới cho thí nghiệm tiếp theo.
