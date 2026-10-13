"""Regenerate Stage 3 analysis from saved predictions, without model inference."""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluate import read, render_reports, error_tables
from src.experiment import metrics, sha256, write_json


def main():
    out = ROOT / 'outputs/stage3'
    lock = read(out / 'lock.json')
    path = out / 'test_predictions.csv'
    pred = pd.read_csv(path, keep_default_na=False)
    test_path = ROOT / 'data/processed/test.csv'
    validation_path = ROOT / 'data/processed/validation.csv'
    if sha256(test_path) != lock['test'] or sha256(validation_path) != lock['data_hashes']['validation']:
        raise ValueError('Changed evaluation data')
    test = pd.read_csv(test_path, keep_default_na=False)
    validation = pd.read_csv(validation_path, keep_default_na=False)
    if pred.row_id.tolist() != test.row_id.tolist() or pred.label_id.tolist() != test.label_id.tolist():
        raise ValueError('Predictions are not aligned with test')
    result = error_tables(test, pred.prediction.to_numpy(),
                          pred[['prob_clean', 'prob_offensive', 'prob_hate']].to_numpy(),
                          pred.token_length.to_numpy(), set(validation.text_clean))
    result['baseline_prediction'] = pred.baseline_prediction
    result.to_csv(path, index=False)
    scores = read(out / 'metrics.json')
    for model, column in [('baseline', 'baseline_prediction'), ('phobert', 'prediction')]:
        if metrics(result.label_id, result[column]) != scores[model]:
            raise ValueError('Stored metrics mismatch')
    review_path = out / 'error_review.csv'
    existing_review = pd.read_csv(review_path, keep_default_na=False) if review_path.exists() else None
    render_reports(out, scores, result, read(out / 'bootstrap.json')['intervals'], lock['selected_run'])
    if existing_review is not None:
        review = pd.read_csv(review_path, keep_default_na=False).set_index('row_id')
        previous = existing_review.set_index('row_id')
        for column in ['review_category', 'review_notes']:
            review[column] = previous[column].reindex(review.index).fillna('')
        review.reset_index().to_csv(review_path, index=False)
    run = ROOT / 'outputs/stage2/runs' / lock['selected_run']
    history = read(run / 'history.json')
    validation_score = read(run / 'validation_metrics.json')['macro_f1']
    summary = out / 'summary.md'
    with summary.open('a', encoding='utf-8') as stream:
        stream.write('\n## Đối chiếu quá trình học\n\n')
        epoch = read(run / 'validation_metrics.json')['best_epoch']
        stream.write(f"Best epoch theo validation: {epoch}; validation Macro-F1 {validation_score:.6f}, test Macro-F1 {scores['phobert']['macro_f1']:.6f}.\n")
        stream.write(f"Train loss giảm từ {history[0]['train_loss']:.4f} xuống {history[-1]['train_loss']:.4f}; validation loss thấp nhất {min(r['validation_loss'] for r in history):.4f}, cuối cùng {history[-1]['validation_loss']:.4f}.\n")
        stream.write('Loss validation tăng trong khi train loss giảm là dấu hiệu overfitting; Macro-F1 vẫn tăng nên checkpoint epoch 5 đúng tiêu chí chọn đã khóa. Không đổi checkpoint sau khi xem test.\n\n')
        stream.write(f'![Learning curves](../stage2/runs/{run.name}/learning_curves.png)\n\n')
        stream.write('## Môi trường baseline\n\nBaseline được serialize bằng scikit-learn 1.6.1 trên Colab; lần inference local dùng 1.9.1 và có cảnh báo khác phiên bản. C và validation Macro-F1 đã được kiểm tra lại trước test; không fit lại baseline. Nên dùng 1.6.1 khi tái lập môi trường gốc.\n')
    write_json(out / 'analysis_provenance.json', {'report_source_sha256': sha256(Path(__file__)),
               'analysis_module_sha256': sha256(ROOT / 'src/evaluate.py'),
               'prediction_sha256': sha256(path),
               'note': 'Analysis regenerated from saved probabilities; predictions and metrics unchanged.'})
    print('Regenerated Stage 3 analysis without inference')


if __name__ == '__main__':
    main()
