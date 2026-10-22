"""
Unit tests for AI Modulation Classifier module.
"""

import os
import numpy as np
import pytest

from src.ai.modulation_classifier.features import extract_features, FEATURE_NAMES
from src.ai.modulation_classifier.dataset import generate_dataset, get_train_val_test_splits, generate_single_signal
from src.ai.modulation_classifier.model import train_classifier, save_model, load_model
from src.ai.modulation_classifier.inference import analyze_iq


def test_feature_extraction_properties():
    """
    Verifies feature vector dimensions and non-NaN properties.
    """
    sig = np.random.randn(512) + 1j * np.random.randn(512)
    feats = extract_features(sig, sample_rate=100000.0)

    assert len(feats) == len(FEATURE_NAMES), "Feature vector length does not match FEATURE_NAMES."
    assert not np.isnan(feats).any(), "Feature vector contains NaN values."
    assert not np.isinf(feats).any(), "Feature vector contains Inf values."


def test_dataset_generation_and_splits():
    """
    Verifies dataset generation shapes and 70/15/15 split proportions.
    """
    X, y, snrs, meta = generate_dataset(samples_per_class_per_snr=5, snr_levels=[10.0], seed=42)

    assert X.shape[0] == len(y)
    assert X.shape[1] == len(FEATURE_NAMES)
    assert len(meta["classes"]) == 8

    (X_tr, y_tr, _), (X_v, y_v, _), (X_te, y_te, _) = get_train_val_test_splits(X, y, snrs, seed=42)

    total = len(y)
    assert len(y_tr) == int(round(total * 0.70))
    assert len(y_v) + len(y_te) == total - len(y_tr)


def test_model_training_and_serialization(tmp_path):
    """
    Verifies Random Forest training and joblib persistence.
    """
    X, y, snrs, _ = generate_dataset(samples_per_class_per_snr=5, snr_levels=[10.0, 20.0], seed=42)
    (X_tr, y_tr, _), _, (X_te, y_te, _) = get_train_val_test_splits(X, y, snrs, seed=42)

    clf = train_classifier(X_tr, y_tr, n_estimators=10, random_state=42)
    save_file = os.path.join(tmp_path, "test_rf.joblib")
    save_model(clf, save_file)

    loaded_clf = load_model(save_file)
    assert loaded_clf is not None

    preds = loaded_clf.predict(X_te)
    assert len(preds) == len(y_te)


def test_inference_confidence_threshold():
    """
    Verifies that analyze_iq returns 'UNKNOWN' when prediction confidence is < 0.60.
    """
    # 1. Pure noise signal (random numbers) should yield low confidence / UNKNOWN
    noise_sig = np.random.randn(512) + 1j * np.random.randn(512)

    # Mock low-confidence model response
    class MockModel:
        classes_ = np.array(["BPSK", "QPSK", "FM"])

        def predict_proba(self, X):
            # Uniform probabilities (0.33 each < 0.60 threshold)
            return np.array([[0.333, 0.333, 0.334]])

    mock_clf = MockModel()
    res = analyze_iq(noise_sig, sample_rate=100000.0, model=mock_clf, confidence_threshold=0.60)

    assert res["predicted_modulation"] == "UNKNOWN", "Should return UNKNOWN when confidence < 0.60."
    assert res["confidence"] < 0.60
