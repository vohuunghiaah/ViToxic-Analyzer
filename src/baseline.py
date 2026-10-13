"""TF-IDF + LogisticRegression tuning on validation only; never open test."""
import argparse
from pathlib import Path
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from .experiment import load_processed, metrics, sha256, write_json


def run(train_path='data/processed/train_decontaminated.csv',
        validation_path='data/processed/validation.csv', output='outputs/stage2/baseline'):
    train = load_processed(train_path, 'train')
    validation = load_processed(validation_path, 'validation')
    output = Path(output)
    if (output / 'results.json').exists():
        raise FileExistsError(f'{output}: use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    rows, best, best_score = [], None, -1
    for c in [0.5, 1.0, 2.0]:
        model = Pipeline([
            ('tfidf', TfidfVectorizer(analyzer='char', ngram_range=(3, 5), min_df=2,
                                     max_features=100000, sublinear_tf=True)),
            ('classifier', LogisticRegression(C=c, class_weight='balanced', max_iter=1000, random_state=42)),
        ])
        model.fit(train.text_clean, train.label_id)
        result = metrics(validation.label_id, model.predict(validation.text_clean))
        rows.append({'C': c, **result})
        print(f'C={c}: validation macro_f1={result["macro_f1"]:.4f}', flush=True)
        if result['macro_f1'] > best_score:
            best, best_score = model, result['macro_f1']
    joblib.dump(best, output / 'baseline.joblib')
    write_json(output / 'results.json', {'evaluation_split': 'validation', 'seed': 42,
        'train_sha256': sha256(train_path), 'validation_sha256': sha256(validation_path),
        'train_rows': len(train), 'validation_rows': len(validation),
        'feature_type': 'character 3-5 grams; fitted on train only', 'trials': rows})
    pd.DataFrame([{k: row[k] for k in ['C', 'accuracy', 'macro_f1', 'weighted_f1']} for row in rows]).to_csv(output / 'comparison.csv', index=False)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-path', default='data/processed/train_decontaminated.csv')
    parser.add_argument('--validation-path', default='data/processed/validation.csv')
    parser.add_argument('--output', default='outputs/stage2/baseline')
    args = parser.parse_args()
    run(args.train_path, args.validation_path, args.output)
