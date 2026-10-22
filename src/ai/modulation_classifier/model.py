"""
Classifier Model Module.

Implements Random Forest classifier training, serialization via joblib, and loading.
"""

import os
import warnings
from typing import Dict, Optional, Tuple
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier


def train_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_estimators: int = 100,
    random_state: int = 42,
) -> RandomForestClassifier:
    """
    Trains a Random Forest classifier on feature matrix X_train and target labels y_train.

    Args:
        X_train: Feature matrix of shape (n_samples, n_features).
        y_train: Target label array of shape (n_samples,).
        n_estimators: Number of decision trees.
        random_state: Random state for reproducibility.

    Returns:
        Trained RandomForestClassifier instance.
    """
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=random_state,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    return clf


def save_model(
    model: RandomForestClassifier,
    save_path: str = "results/ai/modulation_classifier/rf_model.joblib",
) -> str:
    """
    Saves trained scikit-learn model to disk using joblib.

    Args:
        model: Trained classifier model.
        save_path: Destination file path.

    Returns:
        Absolute path to saved model file.
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(model, save_path)
    return os.path.abspath(save_path)


# Task-5 model: trained only on windows that tile a short symbol pattern. On
# non-repeating windows it labels BPSK and QPSK as OFDM-QPSK (0 % correct).
ORIGINAL_MODEL_PATH = "results/ai/modulation_classifier/rf_model.joblib"
# Same features / SNR grid, trained on tiled + non-repeating windows by
# experiments/retrain_modulation_classifier.py (evaluation in retrain_eval/).
DEFAULT_MODEL_PATH = "results/ai/modulation_classifier/rf_model_mixed.joblib"

_MODEL_CACHE: Dict[Tuple[str, float], RandomForestClassifier] = {}


def load_model(
    model_path: str = DEFAULT_MODEL_PATH,
) -> Optional[RandomForestClassifier]:
    """
    Loads trained model from disk via joblib (cached per file and mtime).

    Args:
        model_path: Path to model file. Pass ORIGINAL_MODEL_PATH for the Task-5 model.

    Returns:
        Loaded RandomForestClassifier instance or None if file not found (a
        warning is emitted, because every prediction then becomes 'UNKNOWN').
    """
    path = resolve_model_path(model_path)
    if path is None:
        warnings.warn(
            f"modulation classifier model not found at '{model_path}' (cwd={os.getcwd()}); "
            f"predictions will be 'UNKNOWN'",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    key = (os.path.abspath(path), os.path.getmtime(path))
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = joblib.load(path)
    return _MODEL_CACHE[key]


# Repository root: src/ai/modulation_classifier/model.py -> three levels up.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def resolve_model_path(model_path: str) -> Optional[str]:
    """
    Locate a model file. A relative path is tried from the current directory
    first (the original behaviour), then from the repository root, so running a
    script from another folder no longer silently drops the classifier (which
    made every prediction 'UNKNOWN').
    """
    if os.path.exists(model_path):
        return model_path
    if not os.path.isabs(model_path):
        alt = os.path.join(_REPO_ROOT, model_path)
        if os.path.exists(alt):
            return alt
    return None
