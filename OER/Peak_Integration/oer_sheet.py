# mypy: ignore-errors
# pylint: skip-file

import pandas as pd
from oer_trial import OERTrial


class OERSheet:
    """One sheet from the Excel file — one sheet per sample, multiple trials per sheet."""

    def __init__(self, name: str, raw_df: pd.DataFrame, scan_rate: int = 100):
        self.name = name
        self.raw_df = raw_df
        self.scan_rate = scan_rate
        self.trials: list[OERTrial] = []
        self._parse_trials()

    def _parse_trials(self):
        """Parses column pairs [E, j] into OERTrial objects."""
        df = self.raw_df
        n_cols = df.shape[1]

        if n_cols % 2 != 0:
            print(
                f"[OERSheet '{self.name}'] odd column count ({n_cols}), last column ignored.")

        for i in range(n_cols // 2):
            col_E, col_j = df.columns[i * 2], df.columns[i * 2 + 1]
            try:
                arr = df[[col_E, col_j]].dropna().to_numpy(dtype=float)
            except ValueError:
                continue
            try:
                self.trials.append(
                    OERTrial(data=arr, trial_index=i, label=f"{self.name} - Trial {i+1}", scan_rate=self.scan_rate))
            except ValueError as e:
                print(f"[OERSheet '{self.name}'] skipping trial {i+1}: {e}")

    def __repr__(self):
        return f"OERSheet(name={self.name!r}, n_trials={len(self.trials)})"
