# mypy: ignore-errors
# pylint: skip-file

import pandas as pd
from oer_sheet import OERSheet
from oer_trial import OERTrial


class OERFile:
    """Top-level object for one Excel file. Owns all sheets and trials."""

    def __init__(self, file_path: str, scan_rate: int = 100):
        self.file_path = file_path
        self.scan_rate = scan_rate
        self.sheets: list[OERSheet] = []
        self._load()

    def _load(self):
        try:
            xl = pd.ExcelFile(self.file_path)
        except Exception as e:
            raise IOError(f"Could not open '{self.file_path}': {e}")

        for name in xl.sheet_names:
            if name == "Integrals":
                continue
            df = pd.read_excel(self.file_path, sheet_name=name, header=0)
            self.sheets.append(
                OERSheet(name=str(name), raw_df=df, scan_rate=self.scan_rate))

    def get_sheet(self, name: str) -> OERSheet:
        for sheet in self.sheets:
            if sheet.name == name:
                return sheet
        raise KeyError(f"No sheet '{name}' in '{self.file_path}'")

    def all_trials(self) -> list[OERTrial]:
        return [t for sheet in self.sheets for t in sheet.trials]

    def summary(self):
        print(f"File: {self.file_path}  (scan rate: {self.scan_rate} mV/s)")
        for sheet in self.sheets:
            print(f"  {sheet.name!r}  ({len(sheet.trials)} trial(s))")
            for trial in sheet.trials:
                print(f"    {trial}")

    def __repr__(self):
        return f"OERFile(path={self.file_path!r}, n_sheets={len(self.sheets)})"
