"""
Filename: sheet_reader.py
Author: Patryk Nowak
Date: 18-6-2026
Description: One Excel sheet — parses column pairs into trials, aggregates lookups
"""

import numpy as np
import pandas as pd
from trial_reader import TrialReader


class SheetReader:
    """One sheet per sample, multiple [E, j] column pairs per sheet."""

    def __init__(self, name: str, raw_df: pd.DataFrame):
        self.name = name
        self.raw_df = raw_df
        self.trials: list[TrialReader] = []
        self._parse_trials()

    def _parse_trials(self):
        df = self.raw_df
        n_cols = df.shape[1]
        if n_cols % 2 != 0:
            print(f"[{self.name}] odd column count ({n_cols}), last column ignored.")
        for i in range(n_cols // 2):
            col_E, col_j = df.columns[i * 2], df.columns[i * 2 + 1]
            try:
                arr = df[[col_E, col_j]].dropna().to_numpy(dtype=float)
                self.trials.append(TrialReader(
                    arr, trial_index=i, label=f"{self.name} - Trial {i+1}"))
            except ValueError as e:
                print(f"[{self.name}] skipping trial {i+1}: {e}")

    def _aggregate(self, values: list[float]) -> tuple[float | None, float]:
        if not values:
            return None, 0.0
        return float(np.mean(values)), float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

    def lookup_j_at_E(self, E_target: float) -> tuple[float | None, float]:
        """Return (mean, std) of j across all trials at E_target."""
        values = []
        for trial in self.trials:
            try:
                values.append(trial.lookup_j(E_target))
            except ValueError as e:
                print(f"  [skip] {e}")
        return self._aggregate(values)

    def lookup_E_at_j(self, j_target: float) -> tuple[float | None, float]:
        """Return (mean, std) of E across all trials at j_target."""
        values = []
        for trial in self.trials:
            try:
                values.append(trial.lookup_E(j_target))
            except ValueError as e:
                print(f"  [skip] {e}")
        return self._aggregate(values)

    def __repr__(self):
        return f"SheetReader(name={self.name!r}, n_trials={len(self.trials)})"
