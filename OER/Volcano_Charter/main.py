"""
Filename: main.py
Author: Patryk Nowak
Date: 18-6-2026
Description: Entry point — looks up j/E values across trials and writes a Results sheet
"""

import os
import openpyxl
from file_reader import FileReader


def parse_floats(prompt: str) -> list[float]:
    raw = input(prompt).strip()
    if not raw:
        return []
    values = []
    for t in raw.replace(",", " ").split():
        try:
            values.append(float(t))
        except ValueError:
            print(f"  Skipping '{t}' — not a number.")
    return values


def write_results_sheet(file_path: str, f: FileReader,
                        voltages: list[float], currents: list[float]):
    # Build headers and per-sheet rows together so keys are never duplicated
    headers = ["Sample"]
    for E in voltages:
        headers += [f"Avg j at {E} V (mA/cm²)", f"Std j at {E} V"]
    for j in currents:
        headers += [f"Avg E at {j} mA/cm² (V)", f"Std E at {j} mA/cm²"]

    data_rows = []
    for sheet in f.sheets:
        row = [sheet.name]
        for E in voltages:
            mean, std = sheet.lookup_j_at_E(E)
            row += [mean, std]
        for j in currents:
            mean, std = sheet.lookup_E_at_j(j)
            row += [mean, std]
        data_rows.append(row)

    wb = openpyxl.load_workbook(file_path)
    if "Results" in wb.sheetnames:
        del wb["Results"]
    ws = wb.create_sheet("Results")

    for col, h in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=h)
    for r, row in enumerate(data_rows, start=2):
        for col, v in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=v)

    wb.save(file_path)
    print(f"Results written to 'Results' sheet in {file_path}")


if __name__ == "__main__":
    os.system('clear' if os.name == 'posix' else 'cls')
    file_path = os.path.abspath(
        input("Drag in the Excel file: ").strip().strip("'\""))

    f = FileReader(file_path)
    f.summary()

    voltages = parse_floats("\nVoltages to look up (e.g. 1.5 1.55 1.6): ")
    currents = parse_floats("Currents to look up (e.g. 10 50 100):      ")

    if not voltages and not currents:
        print("Nothing to look up.")
    else:
        write_results_sheet(file_path, f, voltages, currents)
