"""Rebuild and execute the Stage 1 notebook using the invoking Python kernel."""
import json
from pathlib import Path
import sys
import tempfile

import nbformat as nbf
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]
nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
nb.cells = [
    md("""# ViToxic-Analyzer — Stage 1: Data Engineering & EDA

**Câu hỏi nghiên cứu:** Dữ liệu có mất cân bằng, trùng lặp hoặc xung đột nhãn đến mức nào? Chuẩn hóa thế nào để giữ tín hiệu hữu ích cho phân loại?

Notebook tái tạo kết quả từ CSV thật. Chỉ khám phá nội dung **train**; validation/test chỉ được audit cấu trúc, phân bố nhãn và overlap. Chưa huấn luyện model. Một số biểu đồ chứa ngôn ngữ xúc phạm từ dữ liệu nghiên cứu.

Nguồn: [ViHSD](https://github.com/sonlam1102/vihsd), [PhoBERT](https://github.com/VinAIResearch/PhoBERT)."""),
    code("""from pathlib import Path
import sys
ROOT = Path.cwd()
if not (ROOT / 'src').exists():
    ROOT = ROOT.parent
assert (ROOT / 'src').exists(), 'Mở notebook từ project hoặc notebooks/'
sys.path.insert(0, str(ROOT))
import pandas as pd
from IPython.display import display, Image, Markdown
from src.stage1 import run
from src.data_loader import LABELS
from src.preprocessing import preprocess_text, PreprocessingConfig
report = run(ROOT / 'data', ROOT / 'reports/stage1', ROOT / 'data/processed')
train = pd.read_csv(ROOT / 'data/processed/train.csv', keep_default_na=False)
print('Đã tái tạo audit, processed data và figures.')"""),
    md("## 1. Schema, missing values và phân bố nhãn\n\nLoader kiểm tra cột và miền nhãn. Ô trống được đếm riêng; chuỗi literal `NA` không bị chuyển thành missing. `duplicate_excess` là số dòng dư sau lần xuất hiện đầu tiên, không phải số nhóm."),
    code("""rows = []
for split, values in report['splits'].items():
    rows.append({'split': split, 'rows': values['rows'],
                 **{LABELS[int(k)]: v for k, v in values['label_counts'].items()},
                 'empty_raw': values['empty_raw'], 'empty_clean': values['empty_clean'],
                 'raw_duplicate_excess': values['raw_duplicate_excess'],
                 'normalized_duplicate_excess': values['normalized_duplicate_excess'],
                 'conflicting_groups': values['conflicting_normalized_groups']})
display(pd.DataFrame(rows).set_index('split'))
display(Image(filename=str(ROOT / 'reports/stage1/figures/label_distribution.png')))"""),
    md("## 2. Độ dài văn bản\n\nĐếm đơn vị phân cách bởi khoảng trắng, **không phải số từ tiếng Việt hoặc PhoBERT subword**. Histogram dùng log ở trục số lượng; box plot dùng symlog để vẫn thấy đuôi dài. Không chốt max_length=256 chỉ từ biểu đồ này."),
    code("""display(train.assign(whitespace_units=train.free_text.str.split().str.len())
        .groupby('label_id').whitespace_units.describe(percentiles=[.5, .9, .95, .99]))
display(Image(filename=str(ROOT / 'reports/stage1/figures/text_lengths.png')))"""),
    md("## 3. Word clouds và top n-grams theo lớp — train only\n\nChưa tách từ: các term là đơn vị chữ. Không bỏ stopwords để tránh quyết định ngôn ngữ tùy ý; vì vậy từ chức năng có thể đứng đầu. Tần suất cao không đồng nghĩa feature có tính phân biệt hay quan hệ nhân quả."),
    code("""display(Image(filename=str(ROOT / 'reports/stage1/figures/wordclouds.png')))
grams = pd.read_csv(ROOT / 'reports/stage1/train_ngrams.csv')
for n in (1, 2, 3):
    display(Markdown(f'### Top {n}-grams'))
    display(grams[grams.n.eq(n)].groupby('label', sort=False).head(10).reset_index(drop=True))"""),
    md("## 4. Leakage và xung đột nhãn\n\nKhóa duplicate = preprocessing + casefold + gộp khoảng trắng. Mask URL/mention có thể tạo collision; chưa phát hiện near-duplicate. Bản train bổ sung bỏ overlap với holdout và quarantine nhóm nhãn xung đột, không tự sửa nhãn. Giữ nguyên validation/test, kể cả overlap giữa hai tập này."),
    code("""display(pd.DataFrame(report['cross_split_overlap']).T.fillna('—'))
display(pd.Series(report['decontaminated_train']))"""),
    md("## 5. Tiền xử lý và ablation dự kiến\n\nGiữ emoji/emoticon, số, dấu câu và hoa/thường mặc định. Lowercase/teen code chỉ là tùy chọn, cần kiểm chứng bằng validation. Các ví dụ bên dưới là tự tạo, không lấy từ test. `text_clean` cần word segmentation trước khi tokenization PhoBERT."),
    code("""examples = ['KO dc nói vậy!!! 😡 :)))', 'Xem https://example.org @ban #học_tập', 'Tiếng Việt 123 ❤️']
ablation = PreprocessingConfig(lowercase=True, normalize_teencode=True)
display(pd.DataFrame({'raw': examples,
                      'default': [preprocess_text(t) for t in examples],
                      'lowercase_teencode': [preprocess_text(t, ablation) for t in examples]}))
display(pd.Series(report['preprocessing'], name='Default config'))"""),
    md("## 6. Imbalanced data\n\nClass weights = N / (3 × số mẫu lớp), tính lại theo đúng bản train dùng để học. Weighted CrossEntropy và WeightedRandomSampler là hai thí nghiệm riêng. Không oversampling holdout; giữ split sẵn có nên không chia stratified lại."),
    code("""display(pd.DataFrame(report['class_weights']).rename(index=LABELS))
majority_fraction = train.label_id.value_counts(normalize=True).max()
print(f'Accuracy nếu luôn đoán majority trên train: {majority_fraction:.2%}')
print('Đây chỉ là mốc mô tả train, không phải kết quả đánh giá model.')"""),
    md("## 7. Kết luận và bàn giao Stage 2\n\nDùng Macro-F1 làm chỉ số chính, kèm F1/recall từng lớp. Làm baseline TF-IDF + Logistic Regression trước PhoBERT. So sánh official/decontaminated theo giao thức công bố rõ; cân nhắc tác động collision của preprocessing. Chọn tách từ, đo subword/truncation trên train/validation; không dùng test để tuning. Chưa có kết quả model để đưa lên CV."),
    code("display(Markdown((ROOT / 'reports/stage1/summary.md').read_text(encoding='utf-8')))"),
    md("## 8. Provenance và tái lập\n\nSHA-256 ghi nhận đúng đầu vào của lần chạy, không chứng minh nguồn gốc phát hành. Xem requirements-lock.txt cho toàn bộ phiên bản môi trường."),
    code("display(report['provenance'])"),
]
nb.metadata.kernelspec = {"display_name": "Python (ViToxic .venv)", "language": "python", "name": "python3"}
nb.metadata.language_info = {"name": "python", "version": sys.version.split()[0]}
destination = ROOT / 'notebooks/01_eda.ipynb'
destination.parent.mkdir(exist_ok=True)
# Temporary kernel spec avoids changing the user's global Jupyter configuration.
with tempfile.TemporaryDirectory() as temp:
    kernel = Path(temp) / 'vitoxic'
    kernel.mkdir()
    (kernel / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'ViToxic execution', 'language': 'python'}), encoding='utf-8')
    from jupyter_client import KernelManager
    manager = KernelManager(kernel_name='vitoxic', kernel_spec_manager=KernelSpecManager(kernel_dirs=[temp]))
    NotebookClient(nb, km=manager, timeout=180, resources={'metadata': {'path': str(ROOT)}}).execute()
nbf.validate(nb)
nbf.write(nb, destination)
print(f'Executed and saved {destination.name}: {len(nb.cells)} cells')
