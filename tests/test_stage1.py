import unicodedata

import pandas as pd
import pytest

from src.data_loader import class_weights, load_split
from src.preprocessing import PreprocessingConfig, preprocess_text
from src.stage1 import audit, fingerprint, run


def test_unicode_signals_and_idempotence():
    text = unicodedata.normalize("NFD", "Đồ tệ!!! 👩‍💻 ❤️ :))) 123 #bạo_lực")
    cleaned = preprocess_text(text)
    assert cleaned == "Đồ tệ!!! 👩‍💻 ❤️ :))) 123 bạo_lực"
    assert preprocess_text(cleaned) == cleaned


def test_opt_in_teencode_respects_word_boundaries():
    config = PreprocessingConfig(lowercase=True, normalize_teencode=True)
    assert preprocess_text("KO dc token abc http://abc.vn @abc #vui", config) == "không được token abc urltoken usertoken vui"
    assert preprocess_text("ko dc") == "ko dc"


def test_missing_not_stringified():
    with pytest.raises(TypeError):
        preprocess_text(None)


def test_loader_preserves_literal_na_and_empty(tmp_path):
    (tmp_path / "ViHSD_train.csv").write_text("free_text,label_id\nNA,0\n,1\nnull,2\n", encoding="utf-8")
    frame = load_split(tmp_path, "train")
    assert frame.free_text.tolist() == ["NA", "", "null"]
    (tmp_path / "ViHSD_test.csv").write_text("free_text,label_id\nx,1.5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_split(tmp_path, "test")


def test_weights_and_missing_class():
    assert class_weights([0, 0, 0, 1, 2]) == pytest.approx({0: 5 / 9, 1: 5 / 3, 2: 5 / 3})
    with pytest.raises(ValueError):
        class_weights([0, 1])


def test_audit_detects_conflicting_cross_split_duplicates():
    frames = {}
    for split, texts, labels in [("train", ["ABC", "abc", "different"], [0, 1, 2]),
                                  ("validation", ["abc"], [2]), ("test", ["unique"], [0])]:
        frame = pd.DataFrame({"free_text": texts, "text_clean": texts, "label_id": labels})
        frame["text_key"] = frame.text_clean.map(fingerprint)
        frames[split] = frame
    report = audit(frames)
    assert report["splits"]["train"]["conflicting_normalized_groups"] == 1
    assert report["cross_split_overlap"]["train__validation"]["unique_normalized_texts"] == 1
    assert report["cross_split_overlap"]["train__validation"]["train_rows"] == 2


def test_pipeline_exclusions_and_holdout_integrity(tmp_path, monkeypatch):
    import src.stage1 as pipeline
    monkeypatch.setattr(pipeline, "make_figures", lambda *args: None)
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame({"free_text": ["clean", "offensive", "hate", "clean", "overlap", "conflict", "conflict", ""],
                  "label_id": [0, 1, 2, 0, 1, 0, 2, 0]}).to_csv(raw / "ViHSD_train.csv", index=False)
    for split in ("validation", "test"):
        pd.DataFrame({"free_text": ["overlap"], "label_id": [2]}).to_csv(raw / f"ViHSD_{split}.csv", index=False)
    original = {p.name: p.read_bytes() for p in raw.iterdir()}
    out, processed = tmp_path / "report", tmp_path / "processed"
    report = run(raw, out, processed)
    assert report["decontaminated_train"]["rows"] == 3
    assert report["class_weights"]["decontaminated_train"] == {0: 1., 1: 1., 2: 1.}
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == original
    assert pd.read_csv(processed / "test.csv").free_text.tolist() == ["overlap"]
    assert set(pd.read_csv(processed / "train_exclusions.csv").reason) == {
        "duplicate_train", "holdout_overlap", "conflicting_train_labels", "empty_text"}
