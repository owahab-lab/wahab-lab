"""
Filename: main.py
Author: Patryk Nowak
Date: 22-9-2026
Description: Entry point — looks up j/E values across trials and writes a Results sheet
"""

import os
import re
import openpyxl
from file_reader import FileReader


def parse_sheet_name(name: str) -> tuple[float | None, float | None]:
    """Extract n and orbital filling from a sheet name like 'CALZ702-z (2-1-3)'.

    Given (la-ni-o): n = ni,orbital_filling = 10 - q.
    Returns (None, None) if the pattern is missing or ni == 0.
    """
    m = re.search(r'\((\d+)-(\d+)-(\d+)\)', name)
    if not m:
        return None, None
    la, ni, o = float(m.group(1)), float(m.group(2)), float(m.group(3))
    if ni == 0:
        return None, None
    orbital_filling = 28-(2*o - 3*la)/ni
    return ni, orbital_filling


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
    headers = ["Sample", "n=", "Orbital Filling"]
    for E in voltages:
        headers += [f"Avg j at {E} V (mA/cm²)", f"Std j at {E} V"]
    for j in currents:
        headers += [f"Avg E at {j} mA/cm² (V)", f"Std E at {j} mA/cm²"]

    data_rows = []
    for sheet in f.sheets:
        n, orbital_filling = parse_sheet_name(sheet.name)
        row = [sheet.name, n, orbital_filling]
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


def ask_is_lsv() -> bool:
    while True:
        raw = input(
            "Is this LSV data [y/n]: ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please answer 'y' or 'n'.")


if __name__ == "__main__":
    os.system('clear' if os.name == 'posix' else 'cls')
    file_path = os.path.abspath(
        input("Drag in the Excel file: ").strip().strip("'\""))
    is_lsv = ask_is_lsv()

    f = FileReader(file_path, is_lsv=is_lsv)
    f.summary()

    voltages = parse_floats("\nVoltages to look up (e.g. 1.5 1.55 1.6): ")
    currents = parse_floats("Currents to look up (e.g. 10 50 100):      ")

    if not voltages and not currents:
        print("Nothing to look up.")
    else:
        write_results_sheet(file_path, f, voltages, currents)
