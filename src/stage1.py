"""Run with python -m src.stage1. Raw data and official splits are immutable."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import re
from importlib.metadata import version

import pandas as pd

from .data_loader import LABELS, SPLITS, class_weights, load_split
from .preprocessing import PreprocessingConfig, preprocess_text


def fingerprint(text):
    # Exact normalized duplicates, not fuzzy/semantic duplicates.
    return " ".join(text.casefold().split())


def audit(frames):
    summaries = {}
    for split, frame in frames.items():
        valid = frame[frame.text_clean.ne("")]
        lengths = frame.free_text.str.split().str.len()
        summaries[split] = {
            "rows": len(frame), "empty_raw": int(frame.free_text.str.strip().eq("").sum()),
            "empty_clean": int(frame.text_clean.eq("").sum()),
            "label_counts": {str(k): int(frame.label_id.eq(k).sum()) for k in LABELS},
            "raw_duplicate_excess": int(frame.free_text.duplicated().sum()),
            "normalized_duplicate_excess": int(valid.text_key.duplicated().sum()),
            "conflicting_normalized_groups": int((valid.groupby("text_key").label_id.nunique() > 1).sum()),
            "changed_rows": int(frame.free_text.ne(frame.text_clean).sum()),
            "whitespace_length": {str(k): float(v) for k, v in lengths.describe(percentiles=[.5, .9, .95, .99]).items()},
        }
    overlaps = {}
    for i, left in enumerate(SPLITS):
        for right in SPLITS[i + 1:]:
            a, b = frames[left], frames[right]
            keys = (set(a.text_key) & set(b.text_key)) - {""}
            combined = pd.concat([a[a.text_key.isin(keys)], b[b.text_key.isin(keys)]])
            overlaps[f"{left}__{right}"] = {
                "unique_normalized_texts": len(keys),
                f"{left}_rows": int(a.text_key.isin(keys).sum()),
                f"{right}_rows": int(b.text_key.isin(keys).sum()),
                "conflicting_label_groups": int((combined.groupby("text_key").label_id.nunique() > 1).sum()),
            }
    return {"splits": summaries, "cross_split_overlap": overlaps}


def top_ngrams(frame, n=1, limit=20):
    records = []
    for label, name in LABELS.items():
        counter = Counter()
        for text in frame.loc[frame.label_id.eq(label), "text_clean"]:
            tokens = re.findall(r"(?u)\b[^\W\d_]+\b", text.casefold())
            counter.update(" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1))
        for term, count in counter.most_common(limit):
            records.append({"label": name, "n": n, "term": term, "count": count})
    return pd.DataFrame(records, columns=["label", "n", "term", "count"])


def make_figures(train, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import seaborn as sns
    from wordcloud import WordCloud
    sns.set_theme(style="whitegrid", font="DejaVu Sans")
    out.mkdir(parents=True, exist_ok=True)
    counts = train.label_id.value_counts().reindex(LABELS, fill_value=0)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].bar(list(LABELS.values()), counts, color=["#439a86", "#edb458", "#c85c5c"])
    axes[0].set(title="Training class distribution", ylabel="Rows")
    axes[1].pie(counts, labels=list(LABELS.values()), autopct="%.1f%%",
                colors=["#439a86", "#edb458", "#c85c5c"])
    fig.tight_layout(); fig.savefig(out / "label_distribution.png", dpi=150); plt.close(fig)
    plot = train.assign(length=train.free_text.str.split().str.len(), label=train.label_id.map(LABELS))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    sns.histplot(data=plot, x="length", hue="label", bins=60, element="step", ax=axes[0],
                 hue_order=list(LABELS.values()),
                 palette={"CLEAN": "#439a86", "OFFENSIVE": "#edb458", "HATE": "#c85c5c"})
    axes[0].set(xlabel="Whitespace-separated units (not PhoBERT tokens)", yscale="log")
    sns.boxplot(data=plot, x="label", y="length", ax=axes[1], order=list(LABELS.values()))
    axes[1].set(yscale="symlog", ylabel="Whitespace units (symlog scale)")
    axes[1].set_ylim(bottom=0)
    fig.tight_layout(); fig.savefig(out / "text_lengths.png", dpi=150); plt.close(fig)
    font = font_manager.findfont("DejaVu Sans")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    grams = top_ngrams(train, limit=150)
    for ax, name in zip(axes, LABELS.values()):
        subset = grams[grams.label.eq(name)]
        if len(subset):
            cloud = WordCloud(width=650, height=400, background_color="white", font_path=font,
                              random_state=42, collocations=False).generate_from_frequencies(dict(zip(subset.term, subset["count"])))
            ax.imshow(cloud, interpolation="bilinear")
        ax.set_title(name); ax.axis("off")
    fig.suptitle("Train only: syllable frequencies (may contain offensive language)")
    fig.tight_layout(); fig.savefig(out / "wordclouds.png", dpi=150); plt.close(fig)


def run(data_dir=Path("data"), output=Path("reports/stage1"), processed=Path("data/processed")):
    data_dir, output, processed = map(Path, (data_dir, output, processed))
    config = PreprocessingConfig()
    frames = {}
    for split in SPLITS:
        frame = load_split(data_dir, split)
        frame["text_clean"] = frame.free_text.map(lambda text: preprocess_text(text, config))
        frame["text_key"] = frame.text_clean.map(fingerprint)
        frames[split] = frame
    report = audit(frames)
    output.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    # Benchmark version: preserve EVERY row, flag empties; never silently relabel/drop.
    for split, frame in frames.items():
        frame.drop(columns="text_key").to_csv(processed / f"{split}.csv", index=False)
    # Alternative leakage-controlled train; holdouts stay intact. Conflicts are
    # quarantined, not resolved by guessing. Overlap matching is label-independent.
    train = frames["train"].copy()
    holdout_keys = (set(frames["validation"].text_key) | set(frames["test"].text_key)) - {""}
    conflicts = train.groupby("text_key").label_id.nunique()
    conflict_keys = set(conflicts[conflicts.gt(1)].index)
    reason = pd.Series("", index=train.index)
    reason.loc[train.text_key.duplicated()] = "duplicate_train"
    reason.loc[train.text_key.isin(conflict_keys)] = "conflicting_train_labels"
    reason.loc[train.text_key.isin(holdout_keys)] = "holdout_overlap"
    reason.loc[train.text_clean.eq("")] = "empty_text"
    clean = train[reason.eq("")]
    clean.drop(columns="text_key").to_csv(processed / "train_decontaminated.csv", index=False)
    # Row IDs and reason only: avoid publishing raw social comments in reports.
    pd.DataFrame({"row_id": train.row_id, "reason": reason}).loc[reason.ne("")].to_csv(processed / "train_exclusions.csv", index=False)
    report["decontaminated_train"] = {"rows": len(clean), "excluded_by_primary_reason": reason[reason.ne("")].value_counts().to_dict()}
    report["class_weights"] = {"official_train": class_weights(train.label_id), "decontaminated_train": class_weights(clean.label_id)}
    report["preprocessing"] = asdict(config)
    report["provenance"] = {
        "source": "https://github.com/sonlam1102/vihsd",
        "note": "Local CSVs supplied by user; hashes identify files, not verified original release membership.",
        "files": {split: {"sha256": hashlib.sha256((data_dir / f"ViHSD_{split}.csv").read_bytes()).hexdigest()} for split in SPLITS},
        "python": platform.python_version(),
        "packages": {p: version(p) for p in ["pandas", "numpy", "matplotlib", "seaborn", "wordcloud"]},
        "seed": 42,
    }
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.concat([top_ngrams(train, n=n) for n in (1, 2, 3)]).to_csv(output / "train_ngrams.csv", index=False)
    make_figures(train, output / "figures")
    lines = ["# Stage 1 — Kết quả trên dữ liệu thực", "", "Tạo lại bằng `python -m src.stage1`.", "",
             "| Split | Rows | CLEAN | OFFENSIVE | HATE | Empty | Duplicate excess (normalized) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for split, item in report["splits"].items():
        counts = item["label_counts"]
        lines.append(f"| {split} | {item['rows']} | {counts['0']} | {counts['1']} | {counts['2']} | {item['empty_clean']} | {item['normalized_duplicate_excess']} |")
    lines += ["", "## Trùng lặp giữa các tập", "", "Khóa so sánh: preprocessing mặc định + casefold + chuẩn hóa khoảng trắng. Không phải kiểm tra tương đồng ngữ nghĩa.", ""]
    for pair, item in report["cross_split_overlap"].items():
        lines.append(f"- {pair}: {item['unique_normalized_texts']} nội dung chung; {item['conflicting_label_groups']} nhóm khác nhãn.")
    lines += ["", f"Train loại overlap / duplicate / conflict / empty: **{len(clean)}** dòng (gốc {len(train)}).",
              "", "## Class weights: N / (3 × count)", "", "Theo thứ tự CLEAN, OFFENSIVE, HATE:", ""]
    for name, weights in report["class_weights"].items():
        lines.append(f"- {name}: " + ", ".join(f"{LABELS[k]}={v:.4f}" for k, v in weights.items()))
    majority = train.label_id.value_counts().max() / len(train)
    lines += ["", "## Diễn giải và giới hạn", "",
              f"- Chỉ dự đoán lớp đông nhất đã đạt accuracy {majority:.2%} trên train; đây không phải kết quả model trên test.",
              "- Ưu tiên Macro-F1, kèm F1/recall từng lớp; Weighted-F1 và accuracy là chỉ số bổ sung.",
              "- EDA nội dung, n-grams, word clouds chỉ dùng train. Audit holdout chỉ phục vụ kiểm tra chất lượng, không chọn hyperparameter.",
              "- N-grams/độ dài tính theo đơn vị chữ phân cách bởi khoảng trắng, chưa phải từ tiếng Việt hoặc subword PhoBERT.",
              "- Bản decontaminated là thí nghiệm bổ sung; phải công bố số dòng và không so trực tiếp như cùng giao thức benchmark.",
              "- Validation/test có overlap vẫn được giữ nguyên; ghi rõ giới hạn này khi báo cáo kết quả cuối.",
              "- Placeholder URL/mention có thể gộp hai nội dung khác nhau; cần review chính sách trước khi chốt giao thức huấn luyện.",
              "- Chưa huấn luyện model, chưa chọn độ dài tokenizer và chưa thực hiện word segmentation."]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("reports/stage1"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    result = run(args.data_dir, args.output, args.processed)
    print(json.dumps({"rows": {k: v["rows"] for k, v in result["splits"].items()}, "output": str(args.output)}, indent=2))
