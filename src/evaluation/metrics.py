"""
Evaluation Metrics Module.

Provides functions to compute reconstruction error, MSE, and Pearson correlation coefficient
for signal evaluation.
"""

import numpy as np


def mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Computes Mean Squared Error (MSE) between original and recovered signals.

    Args:
        y_true: Ground truth 1D signal.
        y_pred: Reconstructed / estimated 1D signal.

    Returns:
        MSE value as a float.
    """
    true_arr = np.asarray(y_true, dtype=np.float64)
    pred_arr = np.asarray(y_pred, dtype=np.float64)
    if len(true_arr) != len(pred_arr):
        raise ValueError(f"Length mismatch: y_true ({len(true_arr)}) vs y_pred ({len(pred_arr)})")

    return float(np.mean((true_arr - pred_arr) ** 2))


def normalized_reconstruction_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Computes Normalized Reconstruction Error (NRE): ||y_true - y_pred|| / ||y_true||.

    Args:
        y_true: Ground truth 1D signal.
        y_pred: Reconstructed 1D signal.

    Returns:
        NRE ratio as a float.
    """
    true_arr = np.asarray(y_true, dtype=np.float64)
    pred_arr = np.asarray(y_pred, dtype=np.float64)
    norm_true = np.linalg.norm(true_arr)
    if norm_true == 0:
        return 0.0
    return float(np.linalg.norm(true_arr - pred_arr) / norm_true)


def pearson_correlation(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Computes Pearson Correlation Coefficient between original and recovered signals.

    Args:
        y_true: Ground truth 1D signal.
        y_pred: Reconstructed 1D signal.

    Returns:
        Pearson correlation r in range [-1.0, 1.0].
    """
    true_arr = np.asarray(y_true, dtype=np.float64)
    pred_arr = np.asarray(y_pred, dtype=np.float64)

    if len(true_arr) != len(pred_arr):
        raise ValueError(f"Length mismatch: y_true ({len(true_arr)}) vs y_pred ({len(pred_arr)})")

    std_true = np.std(true_arr)
    std_pred = np.std(pred_arr)

    if std_true == 0 or std_pred == 0:
        return 0.0

    cov = np.mean((true_arr - np.mean(true_arr)) * (pred_arr - np.mean(pred_arr)))
    r = cov / (std_true * std_pred)
    return float(np.clip(r, -1.0, 1.0))
