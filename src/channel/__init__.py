"""
Channel modeling package for CogniTwin-SDR.
"""

from .awgn import AWGNChannel, apply_awgn

__all__ = ["AWGNChannel", "apply_awgn"]
