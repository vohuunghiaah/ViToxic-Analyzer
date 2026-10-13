"""Explicit-budget sequential search; each trial gets a fresh process/JVM."""
import argparse
from dataclasses import replace
import itertools
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd
from .config import TrainConfig
from .experiment import write_json


def run(base_path, output, max_trials=4, execute=False):
    if max_trials < 1:
        raise ValueError('max_trials must be positive')
    base = TrainConfig.from_json(base_path)
    output = Path(output)
    # Controlled first comparison: learning rate. Larger budgets explore the full grid.
    candidates = [dict(learning_rate=lr, batch_size=base.batch_size,
                       gradient_accumulation_steps=base.gradient_accumulation_steps,
                       max_length=base.max_length, dropout=base.dropout) for lr in [1e-5, 2e-5, 3e-5, 5e-5]]
    for lr, effective_batch, length, dropout in itertools.product([1e-5, 2e-5, 3e-5, 5e-5], [16, 32], [128, 256], [.1, .2, .3]):
        microbatch = max(n for n in range(1, min(base.batch_size, effective_batch) + 1) if effective_batch % n == 0)
        candidate = dict(learning_rate=lr, batch_size=microbatch,
                         gradient_accumulation_steps=effective_batch // microbatch,
                         max_length=length, dropout=dropout)
        if candidate not in candidates:
            candidates.append(candidate)
    chosen = candidates[:max_trials]
    if (output / 'search_plan.json').exists():
        existing = json.loads((output / 'search_plan.json').read_text(encoding='utf-8'))
        if existing != {'base': base.to_dict(), 'trials': chosen}:
            raise ValueError('Search plan changed; choose a new output directory')
    write_json(output / 'search_plan.json', {'base': base.to_dict(), 'trials': chosen})
    rows = []
    for index, parameters in enumerate(chosen):
        directory = output / f'trial_{index:02d}'
        config = replace(base, **parameters, output_dir=str(directory)).validate()
        config_path = output / f'trial_{index:02d}.json'
        write_json(config_path, config.to_dict())
        if execute and not (directory / 'validation_metrics.json').exists():
            command = [sys.executable, '-m', 'src.train', '--config', str(config_path)]
            if (directory / 'last_checkpoint.pt').exists():
                command.append('--resume')
            subprocess.run(command, check=True)
        result = directory / 'validation_metrics.json'
        row = {'trial': index, **parameters, 'effective_batch_size': config.batch_size * config.gradient_accumulation_steps,
               'status': 'completed' if result.exists() else 'planned', 'output_dir': str(directory)}
        if result.exists():
            score = json.loads(result.read_text(encoding='utf-8'))
            row.update({k: score[k] for k in ['macro_f1', 'weighted_f1', 'accuracy', 'best_epoch', 'loss']})
        rows.append(row)
        pd.DataFrame(rows).to_csv(output / 'comparison.csv', index=False)
    complete = [row for row in rows if row['status'] == 'completed']
    if complete:
        best = min(complete, key=lambda r: r['loss']) if base.selection_metric == 'loss' else max(complete, key=lambda r: r['macro_f1'])
        write_json(output / 'selected_run.json', {'selection_split': 'validation', 'metric': base.selection_metric, **best})
    print(f'{len(chosen)} trials; execute={execute}; results: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', default='outputs/stage2/search_v1')
    parser.add_argument('--max-trials', type=int, default=4)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    run(args.config, args.output, args.max_trials, args.execute)
