"""
Scenario Engine for Virtual RF Environment.

Loads and evaluates time-varying environment keyframes from JSON scenario configs.
"""

import json
import os
from typing import Any, Dict, List, Optional


KEYFRAME_TIME_TOLERANCE_S = 1e-9


class ScenarioEngine:
    """
    Manages time-varying environmental keyframes.
    """

    def __init__(self, scenario_config: Optional[Dict[str, Any]] = None):
        if scenario_config is None:
            # Default fallback single keyframe scenario
            self.name = "Default Scenario"
            self.duration_seconds = 5.0
            self.keyframes = [
                {
                    "time_s": 0.0,
                    "modulation": "QPSK",
                    "snr_db": 20.0,
                    "channel_type": "awgn",
                    "interference_type": "none",
                    "interference_power": 0.0,
                }
            ]
        else:
            self.name = scenario_config.get("name", "Unnamed Scenario")
            self.duration_seconds = scenario_config.get("duration_seconds", 5.0)
            self.keyframes = sorted(
                scenario_config.get("keyframes", []), key=lambda k: k["time_s"]
            )

    @classmethod
    def load_from_file(cls, filepath: str) -> "ScenarioEngine":
        """Loads scenario configuration from JSON file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Scenario configuration file '{filepath}' not found.")
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls(data)

    def get_keyframe_at(self, timestamp_s: float) -> Dict[str, Any]:
        """
        Returns active keyframe dict at timestamp_s (last keyframe with time_s <= timestamp_s).
        """
        if not self.keyframes:
            return {
                "time_s": 0.0,
                "modulation": "QPSK",
                "snr_db": 20.0,
                "channel_type": "awgn",
                "interference_type": "none",
                "interference_power": 0.0,
            }

        # The environment clock accumulates `current_time_s += dt`, so 10 x 0.1 s is
        # 0.9999999999999999 and a keyframe at 1.0 s used to apply one step late
        # (while the one at 2.0 s, reached as 2.0000000000000004, was on time).
        # A 1 ns tolerance makes keyframe timing independent of that drift.
        active = self.keyframes[0]
        for kf in self.keyframes:
            if kf["time_s"] <= timestamp_s + KEYFRAME_TIME_TOLERANCE_S:
                active = kf
            else:
                break
        return active
