"""Locked Stage 3 evaluation of the selected Colab models; no fitting or tuning."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile

import joblib
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer

from .experiment import load_processed, metrics, sha256, write_json
from .model import load_checkpoint_model
from .segmentation import ASSETS, Segmenter, segment_frame

NAMES = ['CLEAN', 'OFFENSIVE', 'HATE']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def paired_bootstrap(labels, baseline, phobert, repetitions=2000, seed=42):
    """Paired row bootstrap: conditional on fixed models, not training-seed uncertainty."""
    labels, baseline, phobert = map(np.asarray, (labels, baseline, phobert))
    if not len(labels) or not (labels.shape == baseline.shape == phobert.shape):
        raise ValueError('Expected nonempty aligned prediction arrays')
    rng = np.random.default_rng(seed)
    def score(y, p):
        cm = np.bincount(3 * y + p, minlength=9).reshape(3, 3)
        den = cm.sum(0) + cm.sum(1)
        return np.divide(2 * cm.diagonal(), den, out=np.zeros(3), where=den != 0).mean()
    samples = np.empty((repetitions, 3))
    for i in range(repetitions):
        ix = rng.integers(0, len(labels), size=len(labels))
        a, b = score(labels[ix], baseline[ix]), score(labels[ix], phobert[ix])
        samples[i] = a, b, b - a
    return {name: np.quantile(samples[:, i], [.025, .975]).tolist()
            for i, name in enumerate(['baseline', 'phobert', 'difference'])}


def error_tables(frame, prediction, probabilities, lengths, validation_texts):
    result = frame[['row_id', 'text_clean', 'label_id']].copy()
    result['prediction'] = prediction
    result['confidence'] = probabilities.max(axis=1)
    for i, name in enumerate(NAMES):
        result['prob_' + name.lower()] = probabilities[:, i]
    result['token_length'] = lengths
    result['validation_overlap'] = result.text_clean.isin(validation_texts)
    result['correct'] = result.label_id == result.prediction
    return result


def render_reports(output, results, predictions, intervals, selected):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = []
    for model, result in results.items():
        rows.append({'model': model, **{k: result[k] for k in ['macro_f1', 'weighted_f1', 'accuracy']}})
        pd.DataFrame(result['per_class']).T.to_csv(output / f'{model}_classification_report.csv')
        cm = np.array(result['confusion_matrix'])
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        normalized = np.divide(cm, cm.sum(1, keepdims=True), out=np.zeros_like(cm, dtype=float), where=cm.sum(1, keepdims=True) != 0)
        for ax, values, title in zip(axes, [cm, normalized], ['Counts', 'Row normalized']):
            ax.imshow(values, cmap='Blues')
            ax.set(xticks=range(3), yticks=range(3), xticklabels=NAMES, yticklabels=NAMES,
                   xlabel='Predicted', ylabel='True', title=f'{model}: {title}')
            for i in range(3):
                for j in range(3):
                    ax.text(j, i, str(cm[i, j]) if title == 'Counts' else f'{values[i,j]:.1%}',
                            ha='center', va='center', color='white' if values[i,j] > values.max()/2 else 'black')
        fig.tight_layout()
        fig.savefig(output / f'{model}_confusion_matrix.png', dpi=160)
        plt.close(fig)
    pd.DataFrame(rows).to_csv(output / 'comparison.csv', index=False)
    errors = predictions.loc[~predictions.correct].sort_values('confidence', ascending=False)
    errors.to_csv(output / 'errors.csv', index=False)
    # A reproducible review queue, not invented human annotations.
    examples = errors.groupby(['label_id', 'prediction'], sort=True).head(10).copy()
    examples['review_category'] = ''
    examples['review_notes'] = ''
    examples.to_csv(output / 'error_review.csv', index=False)
    slices = []
    masks = {'all': np.ones(len(predictions), dtype=bool),
             'validation_overlap': predictions.validation_overlap,
             'no_validation_overlap': ~predictions.validation_overlap,
             'tokens_0_32': predictions.token_length <= 32,
             'tokens_33_128': predictions.token_length.between(33, 128),
             'tokens_over_128': predictions.token_length > 128}
    for name, mask in masks.items():
        subset = predictions.loc[mask]
        if len(subset):
            slices.append({'slice': name, 'rows': len(subset), 'errors': int((~subset.correct).sum()),
                           **{k: v for k, v in metrics(subset.label_id, subset.prediction).items()
                              if k in ['accuracy', 'macro_f1', 'weighted_f1']}})
    pd.DataFrame(slices).to_csv(output / 'slices.csv', index=False)
    lines = ['# Stage 3 — Đánh giá test và phân tích lỗi', '',
             f'Model khóa từ validation: `{selected}`. Test: {len(predictions):,} mẫu, seed huấn luyện 42.',
             'Inference thực hiện local bằng checkpoint và baseline đã huấn luyện trên Colab; không fit lại.', '',
             '| Model | Test Macro-F1 | Weighted-F1 | Accuracy |', '|---|---:|---:|---:|']
    lines += [f"| {r['model']} | {r['macro_f1']:.6f} | {r['weighted_f1']:.6f} | {r['accuracy']:.6f} |" for r in rows]
    lines += ['', '## Precision / recall / F1 theo lớp (PhoBERT)', '',
              '| Lớp | Precision | Recall | F1 | Support |', '|---|---:|---:|---:|---:|']
    for name in NAMES:
        r = results['phobert']['per_class'][name]
        lines.append(f"| {name} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1-score']:.4f} | {int(r['support'])} |")
    lines += ['', '## Phân tích lỗi', '', f'Tổng {len(errors)} dự đoán sai. Các hướng nhầm (nhãn thật → dự đoán):']
    for (a, b), count in errors.groupby(['label_id', 'prediction']).size().sort_values(ascending=False).items():
        lines.append(f'- {NAMES[a]} → {NAMES[b]}: {count} mẫu.')
    lines += ['', 'Các lát cắt chẩn đoán (Macro-F1 luôn tính đủ ba lớp; lát cắt nhỏ cần thận trọng):', '',
              '| Lát cắt | Số mẫu | Số sai | Macro-F1 |', '|---|---:|---:|---:|']
    lines += [f"| {r['slice']} | {r['rows']} | {r['errors']} | {r['macro_f1']:.4f} |" for r in slices]
    lines += ['', '## Độ bất định và giới hạn', '',
              f"Paired bootstrap 2.000 lần, seed 42: CI 95% Macro-F1 PhoBERT {intervals['phobert']}; chênh lệch PhoBERT − baseline {intervals['difference']}.",
              'Bootstrap theo dòng giả định mẫu độc lập; duplicate/ngữ cảnh chung có thể làm CI quá hẹp. Không đo biến thiên qua seed huấn luyện.',
              'Test chính thức giữ nguyên; lát cắt bỏ overlap validation chỉ là phân tích độ nhạy, không thay điểm test chính.',
              'Softmax confidence chưa được hiệu chuẩn. Không suy luận nguyên nhân ngôn ngữ hay nhãn sai chỉ từ confusion matrix.',
              '`error_review.csv` chứa tối đa 10 lỗi confidence cao mỗi hướng nhầm, để người học xem ngữ cảnh và ghi nhận xét; không đại diện ngẫu nhiên cho toàn bộ lỗi.',
              'Không sửa nhãn test, không chọn lại checkpoint/threshold/hyperparameters từ kết quả này. Chưa chứng minh chất lượng production.', '',
              '![PhoBERT confusion matrix](phobert_confusion_matrix.png)', '']
    (output / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')


def run(root='.', output='outputs/stage3', batch_size=16):
    root = Path(root).resolve()
    output = root / output
    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    stage2 = root / 'outputs/stage2'
    selection_path = stage2 / 'final_selection/selection.json'
    selection = read(selection_path)
    if selection['selection_split'] != 'validation' or selection['selection_metric'] != 'macro_f1':
        raise ValueError('Model must be selected on validation Macro-F1')
    selected = selection['selected']['run']
    if Path(selected).name != selected:
        raise ValueError('Invalid selected run name')
    directory = stage2 / 'runs' / selected
    manifest = read(directory / 'manifest.json')
    for split, filename in [('train', 'train_decontaminated.csv'), ('validation', 'validation.csv')]:
        digest = sha256(root / 'data/processed' / filename)
        if digest != selection['data_hashes'][split] or digest != manifest['data_hashes'][split]:
            raise ValueError(f'{split} provenance mismatch')
    baseline_dir = stage2 / 'baseline'
    baseline_info = read(baseline_dir / 'results.json')
    for split in ['train', 'validation']:
        if baseline_info[split + '_sha256'] != selection['data_hashes'][split]:
            raise ValueError('Baseline data mismatch')
    frozen = {'selection': sha256(selection_path), 'checkpoint': sha256(directory / 'best_model.pt'),
              'baseline': sha256(baseline_dir / 'baseline.joblib'),
              'config': sha256(directory / 'config.json'),
              'test': sha256(root / 'data/processed/test.csv'),
              'data_hashes': selection['data_hashes'], 'selected_run': selected,
              'evaluation_split': 'test', 'segmenter': manifest['segmenter']}
    if (output / 'lock.json').exists():
        if read(output / 'lock.json') != frozen:
            raise ValueError('Evaluation inputs changed; preserve the existing evaluation')
        if (output / 'metrics.json').exists():
            print(f'Completed evaluation already exists: {output}', flush=True)
            return read(output / 'metrics.json')
    elif output.exists() and any(output.iterdir()):
        raise FileExistsError('Output is nonempty without an evaluation lock')
    write_json(output / 'lock.json', frozen)
    baseline = joblib.load(baseline_dir / 'baseline.joblib')
    best = max(baseline_info['trials'], key=lambda row: row['macro_f1'])
    validation = load_processed(root / 'data/processed/validation.csv', 'validation')
    if baseline.named_steps['classifier'].C != best['C'] or not np.isclose(
            metrics(validation.label_id, baseline.predict(validation.text_clean))['macro_f1'], best['macro_f1'], atol=1e-10, rtol=0):
        raise ValueError('Saved baseline does not reproduce selected validation score')
    test = load_processed(root / 'data/processed/test.csv', 'test')
    assets = root / 'resources/vncorenlp'
    # Java classpaths containing Vietnamese characters fail on some Windows JVMs.
    if os.name == 'nt' and not str(assets).isascii():
        assets = Path(tempfile.gettempdir()) / 'vitoxic-stage3-vncorenlp'
        for name in ASSETS:
            target = assets / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or sha256(target) != manifest['segmenter'][name]:
                shutil.copy2(root / 'resources/vncorenlp' / name, target)
    segmenter = Segmenter(assets)
    if segmenter.identity != manifest['segmenter']:
        raise ValueError('Segmenter differs from training')
    texts, cache_key = segment_frame(test, segmenter, root / 'data/cache/segmented')
    torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model, config = load_checkpoint_model(directory, device)
    tokenizer = AutoTokenizer.from_pretrained(directory / 'tokenizer', local_files_only=True, use_fast=False)
    lengths = [len(tokenizer.encode(t, truncation=False)) for t in texts]
    probabilities = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            inputs = tokenizer(texts[start:start + batch_size], padding=True, truncation=True,
                               max_length=config.max_length, return_token_type_ids=False, return_tensors='pt')
            logits = model(**{k: v.to(device) for k, v in inputs.items()})
            if not torch.isfinite(logits).all():
                raise ValueError('Nonfinite test logits')
            probabilities.append(logits.softmax(-1).cpu().numpy())
            if start % (batch_size * 16) == 0:
                print(f'Test inference: {min(start + batch_size, len(texts))}/{len(texts)} ({device})', flush=True)
    probabilities = np.concatenate(probabilities)
    prediction = probabilities.argmax(1)
    baseline_prediction = baseline.predict(test.text_clean)
    predictions = error_tables(test, prediction, probabilities, lengths, set(validation.text_clean))
    predictions['baseline_prediction'] = baseline_prediction
    predictions.to_csv(output / 'test_predictions.csv', index=False)
    results = {'baseline': metrics(test.label_id, baseline_prediction), 'phobert': metrics(test.label_id, prediction)}
    intervals = paired_bootstrap(test.label_id, baseline_prediction, prediction)
    write_json(output / 'bootstrap.json', {'repetitions': 2000, 'seed': 42, 'confidence': .95, 'intervals': intervals})
    render_reports(output, results, predictions, intervals, selected)
    write_json(output / 'provenance.json', {'created_at': datetime.now(timezone.utc).isoformat(),
               'device': device, 'batch_size': batch_size, 'test_rows': len(test),
               'segmentation_cache_key': cache_key, 'max_length': config.max_length,
               'evaluation_source_sha256': sha256(Path(__file__)), 'torch': torch.__version__,
               'numpy': np.__version__, 'baseline_validation_reproduced': True})
    # Written last: only a complete report is considered finished.
    write_json(output / 'metrics.json', results)
    print(json.dumps({k: v['macro_f1'] for k, v in results.items()}), flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', default='outputs/stage3')
    parser.add_argument('--batch-size', type=int, default=16)
    args = parser.parse_args()
    run(args.root, args.output, args.batch_size)
