"""
Filename: trial_reader.py
Author: Patryk Nowak
Date: 18-6-2026
Description: One CV trial — forward/reverse sweep with interpolated lookups
"""

import numpy as np


class TrialReader:
    """One CV sweep. Forward = anodic (first half), reverse = cathodic (second half)."""

    def __init__(self, data: np.ndarray, trial_index: int, label: str = ""):
        self.data = data.copy()
        self.trial_index = trial_index
        self.label = label or f"Trial {trial_index}"

    @property
    def forward(self) -> np.ndarray:
        return self.data[: len(self.data) // 2]

    def _fwd_columns(self):
        fwd = self.forward
        return fwd[:, 0], fwd[:, 1]  # E, j

    def lookup_j(self, E_target: float) -> float:
        """Interpolate j at E_target on the forward sweep."""
        E, j = self._fwd_columns()
        if not E.min() <= E_target <= E.max():
            raise ValueError(
                f"E={E_target} outside [{E.min():.4f}, {E.max():.4f}] in {self.label!r}")
        return float(np.interp(E_target, E, j))

    def lookup_E(self, j_target: float) -> float:
        """Interpolate E at j_target on the forward sweep (assumes j is monotone)."""
        E, j = self._fwd_columns()
        if not j.min() <= j_target <= j.max():
            raise ValueError(
                f"j={j_target} outside [{j.min():.4e}, {j.max():.4e}] in {self.label!r}")
        return float(np.interp(j_target, j, E))

    def __repr__(self):
        return f"TrialReader(label={self.label!r}, n_points={len(self.data)})"
