# AI_TRACKER — ViToxic-Analyzer

Cập nhật: **2026-10-13**. Theo dõi công việc, bằng chứng kiểm chứng và phần còn lại của đồ án. Đây không phải bảng tự đánh giá năng lực của người học; không tự đánh dấu checkbox tự đánh giá.

## Trạng thái tổng thể

| Phạm vi | Trạng thái | Bằng chứng / giới hạn |
|---|---|---|
| Stage 1 — Data Engineering & EDA | Hoàn thành | Pipeline chạy trên dữ liệu thật, notebook có outputs, báo cáo audit và tests |
| Stage 2 — Dataset, model, training | Hoàn thành | Run Colab, logs/checkpoint và kiểm chứng artifact của run ban đầu |
| Stage 2 — Tuning tuần tự | Kết quả 8 cấu hình đã kiểm chứng local | Đã thay length 256 bằng rerun có best checkpoint hợp lệ; last checkpoint rerun còn ở epoch 4 |
| Stage 2 — Chọn model và reload | Kiểm chứng độc lập local hoàn tất | Reload CPU: 2.672/2.672 dự đoán khớp Colab; Macro-F1 0.684326 |
| Stage 3 — Evaluation & Analysis | Hoàn thành | 6.680 mẫu test; PhoBERT Macro-F1 0.654565, baseline 0.632496; báo cáo, notebook và verifier đạt |
| Stage 4 — API local | Hoàn thành và kiểm chứng | 38 tests đạt; API thật khớp 12/12 validation, benchmark CPU và bundle offline |
| Stage 4 — Docker / public deployment | Đã chuẩn bị cấu hình, chưa triển khai | Máy không có Docker; chưa có build/run container hoặc hosting public |

**Quy ước bằng chứng:** “kiểm chứng local” nghĩa là trợ lý đã chạy công cụ trên workspace; “người dùng gửi” nghĩa là kết quả Colab được cung cấp trong chat/file đính kèm, chưa đồng nghĩa artifact mới nhất đã có trong workspace.

## Quyết định đã thống nhất

- Huấn luyện bằng Google Colab; upload cả thư mục dự án lên Drive, không dùng ZIP làm workflow chính.
- Chỉ dùng baseline và kết quả Colab để báo cáo. Baseline local trước đây do trợ lý tự chạy, không phải người dùng; đã ngừng sử dụng.
- Stage 3 dùng đúng model/baseline đã huấn luyện trên Colab để inference test local CPU theo yêu cầu hoàn thiện; không fit lại baseline local cũ.
- Tuning tuần tự với **seed 42**, không chạy thêm nhiều seeds theo lựa chọn của người dùng.
- Dùng validation Macro-F1 chọn cấu hình và checkpoint; test dành cho Stage 3, không dùng để tiếp tục tuning.
- Giữ train decontaminated 21.292 mẫu và validation 2.672 mẫu; không nhập lại ba split để chia mới.
- Có thể hoàn tất quy trình Stage 2 dù chưa đạt các mục tiêu F1 trong roadmap. Không gọi validation score là test score hoặc chất lượng production.
- Bảo toàn config, manifest và source snapshot của run cũ. Đổi source/hyperparameters thì tạo run mới; không bỏ cơ chế kiểm tra resume.

## Lịch sử thay đổi

### 2026-10-02 — Stage 1

- Đọc roadmap, kiểm tra ba CSV ViHSD: train 24.048, validation 2.672, test 6.680 mẫu.
- Tạo `src/preprocessing.py`: NFC, khoảng trắng, URL/mention placeholders, hashtag; giữ emoji, dấu câu và số. Lowercase/teen code là tùy chọn.
- Tạo `src/data_loader.py`: kiểm tra schema/labels, class weights từ train và wrapper sampler/DataLoader.
- Tạo `src/stage1.py`: phân bố nhãn, độ dài, n-grams, word clouds, missing/duplicate/conflict/overlap audit và provenance hashes.
- Giữ nguyên official splits; xuất thêm train decontaminated và danh sách lý do loại. Train sau lọc còn **21.292** mẫu.
- Phát hiện 792 nhóm text chuẩn hóa chung train/test, trong đó 80 nhóm khác nhãn; 92 nhóm chung validation/test. Đây là exact normalized matching, không phải kiểm tra semantic duplicates.
- Tạo `notebooks/01_eda.ipynb`, script tạo notebook, README, requirements và tests. Notebook chạy đủ 9 code cells; 7 tests Stage 1 đạt tại thời điểm kiểm chứng.

### 2026-10-10 — Xây dựng Stage 2 và chuyển sang Colab

- Tạo `src/config.py`, `dataset.py`, `model.py`, `experiment.py`, `segmentation.py`, `train.py`, `baseline.py`, `tune.py`.
- Triển khai VnCoreNLP/RDRSegmenter, cache theo text/row IDs/assets, PhoBERT tokenizer và dynamic padding/truncation.
- Model gồm PhoBERT encoder và classification head ba lớp; hỗ trợ freeze/unfreeze.
- Training gồm weighted CrossEntropy hoặc sampler riêng biệt, AdamW, warmup/cosine, FP16, gradient accumulation, clipping, gradient checkpointing và early stopping.
- Lưu best model, last checkpoint, optimizer/scheduler/scaler/RNG, config, manifest, history và validation predictions. Resume tại cuối epoch đã hoàn tất.
- Tạo baseline character TF-IDF 3–5 grams + Logistic Regression; fit vectorizer trên train, chọn C trên validation.
- Tạo notebook Colab `02_training.ipynb`, config mẫu, hướng dẫn, môi trường Stage 2 riêng và tests.
- Theo yêu cầu người dùng, chuyển từ upload ZIP sang mount Drive và đọc trực tiếp thư mục dự án.
- Kiểm thử weighted accumulation tương đương large batch, cache invalidation, split guard, checkpoint reload và resume CPU fixture. Tổng cộng **13 tests đạt** tại các lần kiểm chứng đã ghi nhận.
- Chạy thử VnCoreNLP và tokenizer thật trên câu tổng hợp. Đây không phải huấn luyện PhoBERT local.

### 2026-10-11 — Kiểm tra run Colab đầu tiên và tổ chức lại dự án

- Người dùng cung cấp run PhoBERT đầu: Tesla T4, 5 epochs, best epoch 3, validation Macro-F1 **0.658707**.
- Tính lại metrics từ đủ 2.672 predictions; đối chiếu row IDs/labels/hashes. Reload checkpoint offline, đối chiếu 12 mẫu (4/lớp): trùng predictions lưu.
- Kiểm tra last checkpoint ở epoch 5; source snapshot khớp 12 hashes của manifest.
- Xác định baseline Colab C=2 đạt **0.617302**; tách biệt với lần kiểm chứng local của trợ lý.
- Chuyển raw data vào `data/raw/`, báo cáo/run vào `outputs/`, dependencies vào `requirements/`, VnCoreNLP vào `resources/`, cache vào `data/cache/`.
- Cập nhật source, config mẫu, notebook, README và tài liệu; giữ nguyên artifact lịch sử và source snapshot. Raw CSV vẫn khớp hashes; **13/13 tests đạt sau refactor**.
- Tạo `scripts/verify_stage2.py`, báo cáo `outputs/stage2/review/`, tài liệu `docs/PROJECT_STRUCTURE.md` và nhật ký migration.
- Yêu cầu xóa baseline local bị công cụ chặn bằng “blocked by policy”, kể cả sau khi người dùng cho phép lại. Không được ghi nhận là đã xóa.

### 2026-10-12 — Search learning rate trên Colab

- Kiểm tra 4 trials của `outputs/stage2/search_v1/`: tất cả đã completed.
- Đối chiếu predictions, data hashes và sự hiện diện checkpoint của cả 4 trial. Không chạy lại full inference cho cả 4 model.
- Chọn LR **3e-5** theo validation Macro-F1 **0.678846**, giữ length 128, dropout 0.1, effective batch 32.

### 2026-10-13 — Hoàn thành chuỗi tuning và chọn model

- Người dùng gửi kết quả length 256: Macro-F1 **0.665775**; giữ length 128 cho bước tiếp theo.
- Người dùng gửi dropout 0.2: **0.673834**; dropout 0.3: **0.672896**. Giữ dropout 0.1 theo Macro-F1.
- Người dùng gửi effective batch 16: **0.684326**, cao nhất trong tám cấu hình đã so sánh. Best epoch 5.
- Hướng dẫn tạo bảng `tuning_comparison.csv`, `selection.json` và reload checkpoint offline trên Colab.
- Người dùng gửi bảng đủ tám cấu hình và `PASS: checkpoint tải lại được và inference hợp lệ.` Xác nhận Stage 2 hoàn tất theo quy trình một seed đã thống nhất.
- Tạo `AGENTS.md` đúng nội dung người dùng yêu cầu và tracker này để bàn giao toàn bộ lịch sử, trạng thái, giới hạn và phần còn lại.
- Chưa chạy Stage 3 hoặc triển khai API; chưa chỉnh config mặc định thành model cuối trong lần tạo tracker.

### 2026-10-13 — Audit toàn bộ kết quả vừa tải về

- Đọc lại roadmap; kiểm tra chín thư mục run (run ban đầu và tám cấu hình tuning), final_selection và baseline Colab.
- Tính lại metrics/per-class/confusion matrix từ 2.672 predictions của từng run; kiểm tra row IDs, labels và hashes train/validation: khớp.
- Đối chiếu config và bảng tuning, kiểm tra chọn model đúng Macro-F1 cao nhất. Best weights mọi run đọc được và hữu hạn; source 12 hashes/run tìm được bản khớp.
- Phát hiện CKPT-01: best/last checkpoint length 256 chỉ tới epoch 3/2, không khớp báo cáo epoch 5. Bảo toàn artifact, ghi cách khắc phục trong review.
- Xác minh hash ba raw CSV với audit Stage 1 (không đánh giá model trên test), assets VnCoreNLP và input identity của cache train/validation.
- Tạo scripts/audit_downloaded_stage2.py, cập nhật timestamp/phạm vi script verifier cũ, cập nhật README/docs/review và sinh lại notebook Stage 2. Không đổi source training, config hay manifest lịch sử.
- 13/13 tests passed; kiểm tra cú pháp hai notebook, generator validate schema. Reload model cuối offline, inference CPU đủ 2.672 mẫu validation: 0 dự đoán khác Colab, Macro-F1 0.684326. Kết quả chi tiết lưu tại outputs/stage2/review/full_audit.json.

### 2026-10-13 — Kiểm chứng length 256 rerun

- Tạo và chạy scripts/verify_len256_rerun.py: config, metrics từ predictions, best metadata/weights, data/source/assets hashes đạt. Reload offline CPU toàn bộ 2.672 mẫu: 0 mismatch; Macro-F1 0.6657751681, best epoch 5.
- Last checkpoint mới đến epoch 4; ghi CKPT-02, không tuyên bố resume hoàn chỉnh. Verifier trả exit 1 để phản ánh bất nhất này dù best inference đạt.
- Cập nhật bảng tám cấu hình bằng rerun thay length 256 cũ; lưu bảng/selection trước đó, giữ nguyên các run lịch sử. Model cuối vẫn batch 16, Macro-F1 0.684326.
- Cập nhật báo cáo review, README và tracker. Không train, không đọc test để đánh giá; không thay source training. Verifier đã kiểm tra cú pháp và thực thi trên artifact thật.

### 2026-10-13 — Hoàn thành Stage 3

- Tạo `src/evaluate.py`: khóa selection/checkpoint/baseline/config/data hashes, xác minh baseline validation trước khi inference test; không fit hoặc tuning thêm.
- Tạo báo cáo hai model, per-class metrics, confusion matrices, paired bootstrap NumPy, lát cắt độ dài/overlap và error review queue. Tạo notebook 03 và hướng dẫn Stage 3.
- Inference CPU hoàn tất 6.680/6.680 test: PhoBERT Macro-F1 **0.654565**, Weighted-F1 **0.866463**, accuracy **0.864671**; baseline Colab Macro-F1 **0.632496**. Không train/tuning lại.
- PhoBERT có 904 lỗi; OFFENSIVE F1 **0.416244**, HATE recall **0.577035**. CI bootstrap 95% Macro-F1 PhoBERT [0.635964, 0.672837], delta so baseline [0.002596, 0.041801]. Bootstrap theo dòng, không đo biến thiên qua training seeds.
- Verifier đối chiếu raw test hash, tái tạo preprocessing, row IDs/nhãn/probabilities và tính lại metrics: đạt. Checkpoint khớp bản Stage 2 đã reload toàn bộ validation. Train decontaminated/test không có overlap chuẩn hóa; validation/test có 95 dòng. Lát cắt không overlap đạt Macro-F1 0.6536.
- Sửa thống kê overlap dùng cùng fingerprint casefold/khoảng trắng như Stage 1; dựng lại báo cáo từ probabilities đã lưu, không inference hoặc đổi predictions. Bảo toàn source snapshot inference đầu và ghi source hash của analysis mới.
- Thêm phân tích định lượng và tám ví dụ ngữ cảnh trong `outputs/stage3/qualitative_analysis.md`; không coi giả thuyết nguyên nhân là nhãn chuyên gia hoặc sửa ground truth.
- **17/17 tests passed** sau thay đổi; notebook 03 thực thi đủ **8 code cells** và lưu outputs; kiểm tra trực quan hai confusion matrices. Cập nhật README, cấu trúc và hướng dẫn Stage 3.
- Chạy lại CLI trên artifact hoàn tất: chỉ đọc kết quả đã khóa, không inference lại. Làm mới outputs notebook sau khi bổ sung nhận xét HATE recall so với baseline.
- Baseline Colab được lưu bằng scikit-learn 1.6.1, local dùng 1.9.1: có cảnh báo deserialize khác phiên bản, validation Macro-F1 tái tạo đúng. Cần công bố môi trường và giới hạn tái lập.

### 2026-10-13 — Triển khai Stage 4 local

- Tạo `src/serving.py`, `src/api.py`, exporter bundle và verifier HTTP. Dùng đúng checkpoint khóa Stage 3, không train hoặc fit lại, không đánh giá lại toàn bộ test.
- API single/batch, health/readiness/model metadata, Swagger/OpenAPI. Nạp model/JVM một lần; worker thread đơn, giới hạn input/body, bảo vệ slot cả khi client hủy, lỗi không echo nội dung input.
- Export 14 file model/tokenizer/config/VnCoreNLP/preprocessing với SHA-256; bundle không chứa CSV hoặc optimizer. Khắc phục classpath Windows có dấu trong serving bằng bản assets ASCII được kiểm tra hashes.
- **38/38 tests pass**; real HTTP CPU khớp **12/12 validation predictions** Colab. Kiểm tra Unicode NFC/NFD, single/batch, câu dài/truncation, lỗi 422 và body 413 đạt.
- Benchmark sau warmup: batch 1 p50 111,2 ms / p95 145,2 ms; batch 8 p50 365,7 ms, throughput 23,63 câu/s. Startup 23,6 s; RSS cây tiến trình lớn nhất quan sát 1.008,2 MiB. Câu tổng hợp ngắn, mẫu nhỏ, không phải load test hoặc peak allocation.
- Sửa benchmark đo nhầm RAM venv launcher trên Windows; đo cây tiến trình và dừng toàn bộ cây server thử nghiệm. Xác minh tiến trình server thử nghiệm đã kết thúc.
- Thêm `requirements/stage4.txt`, lock môi trường Windows, Dockerfile/Compose/.dockerignore, hướng dẫn API và báo cáo. Chưa build/run Docker vì máy không có Docker; chưa deploy public hoặc kiểm chứng CUDA.
- Đã khởi động server local `127.0.0.1:8000`, kiểm tra `/ready`, `/predict` và `/docs` thành công; lưu OpenAPI schema vào `outputs/stage4/openapi.json`. Server local được giữ chạy để người dùng thử.

## Tổng hợp tuning Colab

Tất cả dùng seed 42. Đã kiểm chứng local config, metrics và predictions của đủ tám cấu hình. Bảng hiện dùng rerun length 256: best checkpoint đã đạt kiểm chứng reload đầy đủ; trạng thái resume còn hạn chế CKPT-02. Số hiển thị làm tròn sáu chữ số.

| Thí nghiệm | LR | Length | Dropout | Effective batch | Best epoch | Validation Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|
| trial_00 | 1e-5 | 128 | 0.1 | 32 | 5 | 0.638557 |
| trial_01 | 2e-5 | 128 | 0.1 | 32 | 3 | 0.658707 |
| trial_02 | 3e-5 | 128 | 0.1 | 32 | 5 | 0.678846 |
| trial_03 | 5e-5 | 128 | 0.1 | 32 | 5 | 0.677662 |
| Thử length 256 | 3e-5 | 256 | 0.1 | 32 | 5 | 0.665775 |
| Thử dropout 0.2 | 3e-5 | 128 | 0.2 | 32 | 5 | 0.673834 |
| Thử dropout 0.3 | 3e-5 | 128 | 0.3 | 32 | 5 | 0.672896 |
| **Chọn: batch 16** | **3e-5** | **128** | **0.1** | **16** | **5** | **0.684326** |

### Cấu hình được chọn

- Run: `phobert_lr3e-5_len128_drop01_batch16_seed42`.
- Microbatch 8 × gradient accumulation 2 = effective batch 16.
- Validation: Macro-F1 **0.684326**, Weighted-F1 **0.869080**, accuracy **0.867889**.
- OFFENSIVE F1 **0.509804**; HATE recall **0.577778**.
- Macro-F1 tăng khoảng **0.0670** tuyệt đối so với baseline Colab **0.617302**.
- Đường dẫn người dùng gửi: `/content/drive/MyDrive/ViToxic-Analyzer/stage2/runs/phobert_lr3e-5_len128_drop01_batch16_seed42`.
- Đã có artifact local tại `outputs/stage2/runs/<run_name>/`; manifest giữ đường dẫn Drive lịch sử, script audit giải quyết đường dẫn theo workspace root.
- Kết quả inference minh họa người dùng gửi xác nhận tensor hợp lệ/reload thành công, không phải bài đánh giá chất lượng model.

## Lỗi còn tồn đọng

Các checkbox dưới đây theo dõi lỗi kỹ thuật, không phải self-assessment của người học.

- [x] **API-01 — Đo RAM Windows venv launcher:** verifier dùng tổng RSS cây tiến trình; bản kiểm chứng mới đo 1.008,2 MiB thay vì chỉ khoảng 4 MiB ở launcher.
- [x] **API-02 — Windows classpath có dấu trong serving:** sao chép assets sang TEMP ASCII và đối chiếu hashes; API thật khớp 12/12 validation qua segmentation mới.
- [ ] **DEPLOY-01 — Container/public chưa xác minh:** đã có Dockerfile và Compose nhưng máy không có Docker; chưa triển khai hosting, HTTPS/auth hoặc load test.
- [x] **EVAL-01 — Overlap Stage 3 cần nhất quán Stage 1:** dùng fingerprint casefold/khoảng trắng, có regression test khác chữ hoa/thường; verifier xác nhận 95 dòng test overlap validation.
- [ ] **ENV-01 — Phiên bản deserialize baseline khác Colab:** baseline được lưu bằng scikit-learn 1.6.1, local dùng 1.9.1. C và validation Macro-F1 đã tái tạo đúng; chưa đối chiếu toàn bộ test probabilities với môi trường 1.6.1. Đã công bố giới hạn trong báo cáo, không tuyên bố môi trường giống hệt.
- [x] **SYNC-01 — Artifact cuối đã có ở local:** đủ chín thư mục run, bảng tám cấu hình và selection.json. Kiểm chứng phát hiện bất nhất checkpoint length 256, theo dõi riêng tại CKPT-01.
- [x] **DOC-01 — Cập nhật tài liệu:** README, review, hướng dẫn Colab, cấu trúc thư mục và phần giới thiệu notebook phản ánh tám cấu hình và model cuối 0.684326; công bố rõ CKPT-01.
- [x] **CKPT-01 — Best checkpoint length 256 được thay thế bằng rerun hợp lệ:** best epoch 5; full validation 2.672/2.672 dự đoán khớp, Macro-F1 0.665775. Run cũ vẫn bất nhất, giữ lịch sử và loại khỏi bảng chọn model hiện hành; không sửa artifact cũ.
- [ ] **CKPT-02 — Last checkpoint rerun chưa đầy đủ:** file tải về ở epoch 4, history/best model đến epoch 5. Bốn dòng history đầu khớp hoàn toàn. Cần kiểm tra last checkpoint trực tiếp trên Drive; chưa có bằng chứng nguyên nhân. Không cần train lại best model đã xác minh.
- [ ] **CLEANUP-01 — Archive local chưa được xóa:** `outputs/archive/stage2_pretraining/baseline/results.json` vẫn tồn tại. Công cụ xóa đã bị chặn; không dùng archive này làm kết quả báo cáo. Quyền xóa đã được người dùng cấp, không hỏi lại chỉ vì thiếu xác nhận.
- [ ] **PATH-01 — Drive/local khác layout:** output mới người dùng gửi vẫn dưới `stage2/`; local đã dùng `outputs/stage2/`. Một số bản cache/resource được tải về lại xuất hiện trong `outputs/stage2/`. Cần thống nhất mapping khi đồng bộ, không sửa provenance gốc của các run.

### Lỗi đã xử lý

- [x] Chuẩn bị assets VnCoreNLP phụ thuộc `wget` gây lỗi Windows: đổi sang tải bằng Python, ghi file tạm và cố định revision nguồn.
- [x] Không tìm thấy JAVA_HOME khi đã có Java: bổ sung nhận diện từ `java -XshowSettings:properties`.
- [x] Migration bị gián đoạn bởi thuộc tính read-only của thư mục OneDrive: hoàn tất bằng di chuyển file có kiểm tra phạm vi, giữ nguyên dữ liệu/kết quả.
- [x] Workflow Colab yêu cầu ZIP không phù hợp mong muốn người dùng: chuyển sang đọc thư mục Drive.
- [x] Nhầm nguồn baseline trong cách diễn đạt: làm rõ baseline local do trợ lý chạy; báo cáo chính thức chỉ dùng Colab.
- [x] Vướng `Search plan changed` khi dùng config length 256 với `search_v1`: hướng dẫn chạy single-run mục 4 → 6 → 7, giữ nguyên search cũ. Đây là guard bảo vệ kết quả, không phải lỗi cần bỏ khỏi code.

### Giới hạn nghiên cứu, không phải lỗi triển khai đã xác nhận

- Macro-F1 chưa đạt 0.70, OFFENSIVE F1 chưa đạt 0.60, HATE recall chưa đạt 0.75 trên validation.
- Test cũng chưa đạt các mục tiêu này: Macro-F1 0.654565, OFFENSIVE F1 0.416244, HATE recall 0.577035; không tuning tiếp theo test đã xem.
- Batch 16 tăng Macro-F1 nhưng HATE recall thấp hơn batch 32. Ghi rõ đánh đổi; chưa coi model đạt yêu cầu moderation/API thực tế.
- Train loss giảm trong khi validation loss tăng ở các epoch sau: dấu hiệu overfitting. Chọn checkpoint theo Macro-F1 vẫn đúng với giao thức đã định.
- Tuning tuần tự một seed không kiểm tra mọi tương tác hyperparameter, không chứng minh nghiệm tối ưu hay độ ổn định qua seeds.
- Split validation/test còn overlap đã biết; preprocessing placeholders có thể tạo collision. Chưa audit near-duplicates.
- Windows JVM từng lỗi với classpath có dấu; smoke test đã chạy thành công bằng đường dẫn ASCII. Chưa có fix tổng quát cho mọi đường dẫn Windows; Colab là môi trường training chính.

## Đề xuất cải thiện

1. **Ưu tiên bàn giao:** kiểm tra last checkpoint của rerun trên Drive và đối chiếu SHA-256 với bản tải về. Nên xuất manifest checksum sau khi training kết thúc để phát hiện lệch phiên bản. Best checkpoint rerun đã xác minh; không cần chạy lại training.
2. **Stage 3 đã hoàn tất:** bảo toàn lock, predictions và báo cáo; không điều chỉnh hyperparameters dựa trên test. Có thể bổ sung cluster bootstrap theo nhóm duplicate nếu cần đánh giá độ bất định chặt chẽ hơn.
3. **Phân tích OFFENSIVE/HATE:** đã phân tích số lượng lỗi, độ dài và tám ví dụ ngữ cảnh; bước nghiên cứu tiếp theo là review độc lập theo hướng dẫn nhãn trên train/validation, không tự sửa nhãn test hoặc fit theo các lỗi vừa xem.
4. **API local đã kiểm chứng:** bước tiếp theo là build/run Docker ở môi trường có Docker, rồi đo tải trên máy triển khai và chọn cơ chế truy cập/HTTPS phù hợp. Benchmark local chưa đủ để quyết định capacity production.
5. **Độ tin cậy dự đoán:** nếu API cần confidence/threshold, đánh giá calibration bằng dữ liệu validation hoặc tập calibration phù hợp; không xem softmax là xác suất đúng đã được hiệu chuẩn.
6. **Trải nghiệm thí nghiệm:** bổ sung tiện ích tổng hợp tất cả run và nêu rõ sự khác nhau giữa single-run với search, tránh tái dùng thư mục search với config khác.
7. **Môi trường/đường dẫn:** dùng một root cấu hình cho Drive và local, giữ lockfile theo môi trường; không trộn path lịch sử với path dùng để chạy mới.
8. **Tái lập baseline:** khi kiểm chứng môi trường, dùng scikit-learn 1.6.1 trong môi trường riêng và so sánh với predictions đã khóa; không fit lại hoặc chọn lại C bằng test.

Không tự bổ sung multi-seed vào yêu cầu hoàn tất hiện tại vì người dùng đã chọn một seed. Các đề xuất trên chưa được thực hiện chỉ bởi việc ghi vào tracker.

## Quy tắc cập nhật tracker

- Sau mỗi lần viết/sửa/debug code: mở lại file này, thêm lịch sử thay đổi và ghi kiểm chứng thực tế trước phản hồi cuối.
- Chỉ đánh `[x]` cho lỗi đã xử lý có bằng chứng; không tự đánh checkbox tự đánh giá của người học.
- Phân biệt code đã viết, test đã chạy, training đã chạy và artifact đã đồng bộ; không suy ra bước này từ bước kia.
- Không ghi “đã xóa”, “đã deploy”, “đã đánh giá test” khi chỉ hướng dẫn hoặc công cụ thất bại.
