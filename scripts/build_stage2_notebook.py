"""Generate a Colab-first notebook. Training cells deliberately have no fake outputs."""
from pathlib import Path
import ast
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
nb = nbf.v4.new_notebook()
nb.cells = [
md('''# ViToxic-Analyzer — Stage 2 trên Google Colab

**Cách dùng:** chọn Runtime → Change runtime type → GPU, rồi chạy lần lượt từ trên xuống.
Upload toàn bộ thư mục `ViToxic-Analyzer` lên Google Drive, rồi mở `notebooks/02_training.ipynb` bằng Colab. Không cần ZIP hoặc push GitHub.

Notebook dùng train decontaminated **21.292 dòng** và validation **2.672 dòng** trong thư mục dự án; Stage 2 không đọc test. Đã hoàn thành tuning tuần tự 8 cấu hình, seed 42. Model được chọn: `phobert_lr3e-5_len128_drop01_batch16_seed42`, validation Macro-F1 0.684326, best epoch 5. Baseline Colab đạt 0.617302. Xem `outputs/stage2/final_selection/selection.json` và `outputs/stage2/review/summary.md`. Các cell bên dưới vẫn là mẫu cho run ban đầu; không cần train/search lại để hoàn tất Stage 2. Notebook không huấn luyện lại nếu run đã có kết quả.

Tách từ bằng VnCoreNLP → PhoBERT tokenizer → dynamic padding → weighted CrossEntropy → AdamW + warmup/cosine → chọn checkpoint theo validation Macro-F1.

[PhoBERT](https://github.com/VinAIResearch/PhoBERT) · [VnCoreNLP](https://github.com/vncorenlp/VnCoreNLP) · [Colab FAQ](https://research.google.com/colaboratory/faq.html)'''),
md('''## 1. Mount Drive và chọn thư mục dự án

Colab sẽ hỏi quyền mount Drive. Sửa `PROJECT` bên dưới nếu thư mục được upload ở vị trí khác.
Mặc định: `MyDrive/ViToxic-Analyzer`. Thư mục này cần chứa `src/`, `configs/`, `tests/`, `requirements/stage2.txt` và `data/processed/`.
Notebook đọc trực tiếp thư mục dự án trên Drive; kết quả và checkpoint lưu tại `outputs/stage2/`, cache tại `data/cache/`, tài nguyên tại `resources/`. Khi nối lại phiên, mount Drive và dùng lại cùng đường dẫn.'''),
code('''from pathlib import Path
import os, sys, json, shutil, subprocess
from google.colab import drive
drive.mount('/content/drive')
PROJECT = Path('/content/drive/MyDrive/ViToxic-Analyzer')  # sửa nếu upload ở vị trí khác
required = ['src/train.py', 'configs/phobert_colab.json', 'tests/test_stage2.py',
            'requirements/stage2.txt', 'data/processed/train_decontaminated.csv',
            'data/processed/validation.csv']
missing = [name for name in required if not (PROJECT / name).is_file()]
if missing:
    raise FileNotFoundError(f'Kiểm tra PROJECT và upload đủ thư mục. Còn thiếu: {missing}')
DRIVE_ROOT = PROJECT / 'outputs/stage2'
DRIVE_ROOT.mkdir(parents=True, exist_ok=True)
os.chdir(PROJECT)
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
print('Project:', PROJECT)
print('Kết quả sẽ lưu tại:', DRIVE_ROOT)'''),
md('''## 2. Dependencies và GPU

Giữ bản PyTorch CUDA có sẵn của Colab. Cài dependencies trước khi import Transformers.
Nếu Colab yêu cầu restart sau cài đặt, restart runtime rồi chạy lại từ ô 1.
Không cần API key hoặc token Hugging Face để tải model public.'''),
code('''subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r', 'requirements/stage2.txt'], check=True)
if shutil.which('java') is None:
    subprocess.run(['apt-get', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'default-jre-headless'], check=True)
import torch
if not torch.cuda.is_available():
    raise RuntimeError('Chọn GPU trong Runtime → Change runtime type rồi chạy lại.')
print('PyTorch:', torch.__version__, '| GPU:', torch.cuda.get_device_name(0))
print('VRAM GB:', round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1))
(PROJECT / 'requirements/locks').mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=(PROJECT / 'requirements/locks/colab-stage2-current.txt').open('w'), check=True)'''),
md('''## 3. Kiểm tra dữ liệu, mã nguồn và segmenter

Test sử dụng encoder nhỏ ngẫu nhiên, không thay thế việc kiểm chứng huấn luyện PhoBERT thật.
VnCoreNLP tải assets lần đầu; các lần sau dùng lại từ Drive. Stage 2 không đọc test.'''),
code('''from src.experiment import load_processed
train = load_processed('data/processed/train_decontaminated.csv', 'train')
validation = load_processed('data/processed/validation.csv', 'validation')
print('Train:', len(train), '| Validation:', len(validation))
display(train.label_id.value_counts().sort_index().rename('train_count'))
subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_stage2.py'], check=True)
SEGMENTER_DIR = PROJECT / 'resources/vncorenlp'
subprocess.run([sys.executable, '-m', 'src.segmentation', '--directory', str(SEGMENTER_DIR), '--download'], check=True)'''),
md('''## 4. Cấu hình thí nghiệm

Mặc định: batch 8 × accumulation 4 = effective batch **32**, 5 epochs tối đa, FP16, gradient checkpointing, early stopping patience 2 theo Macro-F1.
`max_length=128` là cấu hình khởi đầu; số liệu truncation sẽ được lưu. Search có cả 128/256. Không tuyên bố 128 tối ưu trước khi so sánh.

Nếu hết VRAM: đặt batch=4, accumulation=8 và eval_batch=8 **trước khi bắt đầu run mới**. Đổi cấu hình phải đổi RUN_NAME. Resume yêu cầu giữ nguyên hyperparameters và dữ liệu. Chỉ bật `freeze_epochs=1` khi muốn thí nghiệm head-only epoch đầu.

Drive cần dung lượng trống cho model tốt nhất (~0,5 GB), checkpoint để resume (~1,6 GB) và file tạm khi lưu. Dự trù khoảng 5 GB/run. Search nhiều runs cần nhiều dung lượng hơn.'''),
code('''from src.config import TrainConfig
from src.experiment import write_json
RUN_NAME = 'phobert_lr2e-5_len128_seed42'  # đổi tên khi thử cấu hình khác
config = TrainConfig.from_json('configs/phobert_colab.json')
config.output_dir = str(DRIVE_ROOT / 'runs' / RUN_NAME)
config.segmenter_dir = str(SEGMENTER_DIR)
config.cache_dir = str(PROJECT / 'data/cache/segmented')
config.validate()
CONFIG_PATH = DRIVE_ROOT / 'active_configs' / f'{RUN_NAME}.json'
write_json(CONFIG_PATH, config.to_dict())
display(config.to_dict())'''),
md('''## 5. Baseline TF-IDF + Logistic Regression

Character 3–5 grams; vectorizer fit trên train, chọn C bằng validation Macro-F1. Chạy baseline là độc lập với PhoBERT; không dùng test.
Ô này chạy baseline một lần và giữ kết quả trên Drive. Nếu muốn đổi dữ liệu/cấu hình, dùng thư mục output mới.'''),
code('''BASELINE_DIR = DRIVE_ROOT / 'baseline'
if not (BASELINE_DIR / 'results.json').exists():
    subprocess.run([sys.executable, '-m', 'src.baseline', '--output', str(BASELINE_DIR)], check=True)
import pandas as pd
display(pd.read_csv(BASELINE_DIR / 'comparison.csv'))'''),
md('''## 6. Train / resume PhoBERT

Chạy bằng subprocess để tách JVM của VnCoreNLP khỏi notebook. Checkpoint lưu sau **mỗi epoch hoàn tất**; mất kết nối giữa epoch thì epoch đó chạy lại. Không có cam kết resume giữa mini-batch.

Best model và early stopping dùng **cùng một metric**. Loss validation sử dụng class weights tính từ train; không tính lại weights từ validation. Epoch freeze dùng encoder eval, sau đó unfreeze để fine-tune toàn bộ.
Không đóng phiên chủ động khi lệnh đang chạy; thời gian/GPU phụ thuộc hạn mức Colab.'''),
code('''RUN_DIR = Path(config.output_dir)
if (RUN_DIR / 'validation_metrics.json').exists():
    print('Run đã hoàn tất. Đổi RUN_NAME để bắt đầu thí nghiệm khác.')
else:
    command = [sys.executable, '-m', 'src.train', '--config', str(CONFIG_PATH)]
    if (RUN_DIR / 'last_checkpoint.pt').exists():
        command.append('--resume')
        print('Resume từ cuối epoch đã lưu.')
    subprocess.run(command, check=True)'''),
md('''## 7. Kết quả, learning curves và truncation

Đây là **validation metrics để lựa chọn mô hình**, không phải test metrics. Điểm baseline và PhoBERT chỉ so sánh khi train/validation hashes trùng nhau. Không kết luận hơn baseline nếu chưa chạy model.
Biểu đồ giúp nhận biết overfitting; n-grams/độ dài Stage 1 không thay thế số subword ở đây.'''),
code('''import matplotlib.pyplot as plt
history = pd.read_json(RUN_DIR / 'history.json')
display(history)
result = json.loads((RUN_DIR / 'validation_metrics.json').read_text())
display(result)
display(json.loads((RUN_DIR / 'token_lengths.json').read_text()))
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
history.plot(x='epoch', y=['train_loss', 'validation_loss'], ax=axes[0], marker='o')
history.plot(x='epoch', y='validation_macro_f1', ax=axes[1], marker='o')
axes[0].set_ylabel('Weighted cross-entropy')
axes[1].set_ylabel('Macro-F1')
fig.tight_layout()
fig.savefig(RUN_DIR / 'learning_curves.png', dpi=150)
plt.show()
baseline_result = json.loads((BASELINE_DIR / 'results.json').read_text())
manifest = json.loads((RUN_DIR / 'manifest.json').read_text())
assert baseline_result['train_sha256'] == manifest['data_hashes']['train']
assert baseline_result['validation_sha256'] == manifest['data_hashes']['validation']
best_baseline = max(baseline_result['trials'], key=lambda row: row['macro_f1'])
comparison = pd.DataFrame([
    {'model': 'TF-IDF + LR', **{k: best_baseline[k] for k in ['macro_f1', 'weighted_f1', 'accuracy']}},
    {'model': RUN_NAME, **{k: result[k] for k in ['macro_f1', 'weighted_f1', 'accuracy']}}
])
comparison.to_csv(RUN_DIR / 'baseline_comparison.csv', index=False)
display(comparison)'''),
md('''## 8. Hyperparameter search — tùy chọn, có giới hạn số runs

Mặc định **không chạy** để bạn kiểm tra run đầu trước. `MAX_TRIALS=4` so sánh learning rates 1e-5, 2e-5, 3e-5, 5e-5. Ngân sách lớn hơn mở rộng grid effective batch 16/32, max_length 128/256, dropout 0.1/0.2/0.3.
Mỗi trial huấn luyện từ pretrained, không dùng checkpoint trial trước. Search dùng cùng data/seed; bảng ghi rõ planned/completed. Chưa thay cho đánh giá nhiều seeds hoặc test cuối.
Có thể nối lại search đã ngắt bằng cùng tên thư mục/cấu hình/ngân sách.'''),
code('''RUN_SEARCH = False
MAX_TRIALS = 4
SEARCH_DIR = DRIVE_ROOT / 'search_v2'  # search_v1 giữ nguyên kế hoạch lịch sử
command = [sys.executable, '-m', 'src.tune', '--config', str(CONFIG_PATH),
           '--output', str(SEARCH_DIR), '--max-trials', str(MAX_TRIALS)]
if RUN_SEARCH:
    command.append('--execute')
SEARCH_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = SEARCH_DIR / 'search.log'
with LOG_PATH.open('a', encoding='utf-8') as log:
    with subprocess.Popen(command, cwd=PROJECT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                          errors='replace', bufsize=1,
                          env={**os.environ, 'PYTHONUNBUFFERED': '1'}) as process:
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
            log.flush()
        returncode = process.wait()
if returncode:
    raise RuntimeError(f'Search thất bại (exit {returncode}). Xem lỗi gốc phía trên hoặc {LOG_PATH}')
display(pd.read_csv(SEARCH_DIR / 'comparison.csv'))'''),
md('''## 9. Kiểm tra checkpoint dùng được offline

Reload kiến trúc và trọng số đã lưu, chạy lại một ví dụ **đã tách từ**. Ví dụ chỉ kiểm tra serialization, không dùng để kết luận model tốt. Bộ inference Stage 3/4 phải dùng đúng preprocessing + VnCoreNLP như train.'''),
code('''from src.model import load_checkpoint_model
from transformers import AutoTokenizer
restored, saved_config = load_checkpoint_model(RUN_DIR)
tokenizer = AutoTokenizer.from_pretrained(RUN_DIR / 'tokenizer', use_fast=False, local_files_only=True)
batch = tokenizer('Tôi đang học machine learning .', return_tensors='pt', return_token_type_ids=False,
                  truncation=True, max_length=saved_config.max_length)
with torch.no_grad():
    probabilities = restored(**batch).softmax(-1)[0].tolist()
display(dict(zip(['CLEAN', 'OFFENSIVE', 'HATE'], probabilities)))
del restored'''),
md('''## 10. Bàn giao Stage 3

Giữ toàn bộ thư mục run đã chọn: `best_model.pt`, `config.json`, `encoder_config/`, `tokenizer/`, `manifest.json`, `token_lengths.json`, `history.json`, `validation_metrics.json` và `validation_predictions.csv`. `last_checkpoint.pt` dùng để resume, không bắt buộc khi inference.

Chốt cấu hình bằng validation trước khi mở test. Báo cáo riêng kết quả official/decontaminated, baseline, F1 từng lớp, sai số qua seeds và hạn chế overlap validation/test. Chưa gọi validation F1 là kết quả test hoặc hiệu quả triển khai thực tế.

**Tiêu chí hoàn thành thực nghiệm Stage 2:** run thật kết thúc, checkpoint reload được, logs/manifest đầy đủ; nếu tuyên bố tuning hoàn tất thì phải có nhiều trial completed và bảng chọn cấu hình.'''),
]
nb.metadata = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
               'language_info': {'name': 'python'}, 'colab': {'name': '02_training.ipynb'}, 'accelerator': 'GPU'}
for cell in nb.cells:
    if cell.cell_type == 'code':
        ast.parse(cell.source)
nbf.validate(nb)
nbf.write(nb, ROOT / 'notebooks/02_training.ipynb')
print('Generated Colab notebook; syntax and notebook schema validated (training not executed).')
