"""
Filename: file_reader.py
Author: Patryk Nowak
Date: 18-6-2026
Description: Loads an Excel file and owns all SheetReader objects
"""

import pandas as pd
from sheet_reader import SheetReader


class FileReader:
    """Top-level object for one Excel file."""

    def __init__(self, file_path: str, is_lsv: bool = False):
        self.file_path = file_path
        self.is_lsv = is_lsv
        self.sheets: list[SheetReader] = []
        self._load()

    def _load(self):
        try:
            xl = pd.ExcelFile(self.file_path)
        except Exception as e:
            raise IOError(f"Could not open '{self.file_path}': {e}")
        for name in xl.sheet_names:
            df = pd.read_excel(self.file_path, sheet_name=name, header=0)
            self.sheets.append(SheetReader(
                name=str(name), raw_df=df, is_lsv=self.is_lsv))

    def summary(self):
        print(f"File: {self.file_path}")
        for sheet in self.sheets:
            print(f"  {sheet.name!r}  ({len(sheet.trials)} trial(s))")

    def __repr__(self):
        return f"FileReader(path={self.file_path!r}, n_sheets={len(self.sheets)})"
