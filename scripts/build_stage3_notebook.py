"""Build a portable Stage 3 notebook. Viewing existing reports does not rerun test."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
nb = nbf.v4.new_notebook()
nb.metadata.kernelspec = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
nb.cells = [
    nbf.v4.new_markdown_cell('''# Stage 3 — Evaluation & Analysis

Đánh giá test bằng PhoBERT và baseline **đã chọn từ validation**. Không train hoặc tuning thêm.
Kết quả local có sẵn trong `outputs/stage3/`; chạy các ô đọc báo cáo để xem.
Nếu dùng Colab, upload bản dự án mới cùng artifact; mount Drive trước khi đặt `PROJECT`.
Không dùng test để chọn lại cấu hình. Softmax chưa được hiệu chuẩn.'''),
    nbf.v4.new_code_cell('''from pathlib import Path
import json
import pandas as pd
from IPython.display import display, Markdown, Image
PROJECT = Path.cwd()
if PROJECT.name == 'notebooks':
    PROJECT = PROJECT.parent
# Colab: mount Drive rồi dùng Path('/content/drive/MyDrive/ViToxic-Analyzer')
OUTPUT = PROJECT / 'outputs/stage3'
assert (PROJECT / 'src/evaluate.py').is_file(), 'Đặt PROJECT thành thư mục gốc dự án'
'''),
    nbf.v4.new_markdown_cell('''## Thực thi (chỉ khi chưa có kết quả)

Cài `requirements/stage2.txt` và Java trước khi chạy lần đầu. Baseline Colab được lưu bằng
scikit-learn 1.6.1; nên dùng phiên bản này khi tái lập. Pipeline kiểm tra lại điểm validation
của baseline, khóa model/data hashes, rồi mới inference test. CPU có thể mất vài phút.
Ô dưới mặc định chỉ đọc báo cáo đã có; đặt `RUN_EVALUATION = True` để thực thi nếu cần.'''),
    nbf.v4.new_code_cell('''RUN_EVALUATION = False
if RUN_EVALUATION:
    import subprocess, sys
    subprocess.run([sys.executable, '-m', 'src.evaluate'], cwd=PROJECT, check=True)
assert (OUTPUT / 'metrics.json').is_file(), 'Chưa có kết quả: chạy pipeline trước'
'''),
    nbf.v4.new_code_cell("display(pd.read_csv(OUTPUT / 'comparison.csv'))\ndisplay(pd.read_csv(OUTPUT / 'phobert_classification_report.csv', index_col=0))"),
    nbf.v4.new_code_cell("display(Image(filename=str(OUTPUT / 'phobert_confusion_matrix.png')))\ndisplay(Image(filename=str(OUTPUT / 'baseline_confusion_matrix.png')))"),
    nbf.v4.new_code_cell("display(pd.read_csv(OUTPUT / 'slices.csv'))\ndisplay(json.loads((OUTPUT / 'bootstrap.json').read_text(encoding='utf-8')))"),
    nbf.v4.new_markdown_cell('''## Đọc lỗi theo ngữ cảnh

`errors.csv` giữ toàn bộ lỗi; `error_review.csv` chọn tối đa 10 lỗi confidence cao mỗi hướng nhầm.
Đây là mẫu chẩn đoán có thiên lệch chọn mẫu. Đọc văn bản và ghi nhận xét vào bản sao;
không tự sửa ground truth. Có thể ghi thiếu ngữ cảnh, cách viết/teencode, mỉa mai hoặc
ranh giới OFFENSIVE/HATE nếu có bằng chứng; không khẳng định nguyên nhân chỉ từ model.
Không có checkbox tự đánh giá nào được đánh dấu tự động.'''),
    nbf.v4.new_code_cell("display(pd.read_csv(OUTPUT / 'error_review.csv').head(20))"),
    nbf.v4.new_code_cell("analysis = OUTPUT / 'qualitative_analysis.md'\nif analysis.exists():\n    display(Markdown(analysis.read_text(encoding='utf-8')))"),
    nbf.v4.new_code_cell("report = (OUTPUT / 'summary.md').read_text(encoding='utf-8')\ndisplay(Markdown('\\n'.join(line for line in report.splitlines() if not line.startswith('!['))))\nselected = json.loads((OUTPUT / 'lock.json').read_text(encoding='utf-8'))['selected_run']\ndisplay(Image(filename=str(PROJECT / 'outputs/stage2/runs' / selected / 'learning_curves.png')))"),
]
nbf.validate(nb)
nbf.write(nb, ROOT / 'notebooks/03_evaluation.ipynb')
print('Wrote notebooks/03_evaluation.ipynb')
