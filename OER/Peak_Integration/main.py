# mypy: ignore-errors
# pylint: skip-file

"""
Filename: main.py
Author: Patryk Nowak
Date: 13-03-2026
Description: Entry point for OER peak integration analysis.
"""

import json
import os
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from tqdm import tqdm

from oer_file import OERFile
from oer_trial import OERTrial


# ------------------------------------------------------------------ #
# Bounds persistence                                                   #
# ------------------------------------------------------------------ #

def bounds_path(file_path: str) -> str:
    """Returns path to the JSON sidecar file storing saved bounds."""
    base = os.path.splitext(file_path)[0]
    return base + "_bounds.json"


def load_saved_bounds(file_path: str) -> dict:
    """Loads previously saved bounds from the sidecar JSON file."""
    path = bounds_path(file_path)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_bounds(file_path: str, bounds_store: dict):
    """Saves bounds for all trials to the sidecar JSON file."""
    with open(bounds_path(file_path), "w") as f:
        json.dump(bounds_store, f, indent=2)

# ------------------------------------------------------------------ #
# Bound computation                                                    #
# ------------------------------------------------------------------ #


def compute_bounds(trial: OERTrial, saved: dict = None):
    """Returns (lower_f, upper_f, lower_r, upper_r). Uses saved bounds if available."""
    if saved is None:
        saved = {}
    if trial.label in saved:
        b = saved[trial.label]
        return b.get("lower_f"), b.get("upper_f"), b.get("lower_r"), b.get("upper_r")

    lower_f, upper_f = trial._forward_peak_bounds()
    lower_r, upper_r = trial._reverse_peak_bounds()

    return lower_f, upper_f, lower_r, upper_r


# ------------------------------------------------------------------ #
# Plotting                                                             #
# ------------------------------------------------------------------ #

def draw_trial(trial: OERTrial, lower_f, upper_f, lower_r, upper_r):
    """Plots the full CV with integration bounds, baselines, and shading."""
    fig, ax = plt.subplots(figsize=(8, 6))
    full = np.concatenate([trial.forward, trial.reverse])
    ax.plot(full[:, 0], full[:, 1])

    if lower_f is not None and upper_f is not None:
        ax.axvline(lower_f, color='g', linestyle='--', label='fl')
        ax.axvline(upper_f, color='g', linestyle='--', label='fu')
        bl = trial.get_baseline(trial.forward, lower_f, upper_f)
        if bl is not None:
            ax.plot(bl[:, 0], bl[:, 1], color='g', linewidth=1, linestyle=':')
            mask = (trial.forward[:, 0] >= lower_f) & (
                trial.forward[:, 0] <= upper_f)
            x, y = trial.forward[mask, 0], trial.forward[mask, 1]
            ax.fill_between(x, y, np.interp(
                x, bl[:, 0], bl[:, 1]), alpha=0.3, color='g')

    if lower_r is not None and upper_r is not None:
        ax.axvline(lower_r, color='r', linestyle='--', label='rl')
        ax.axvline(upper_r, color='r', linestyle='--', label='ru')
        bl = trial.get_baseline(trial.reverse, lower_r, upper_r)
        if bl is not None:
            ax.plot(bl[:, 0], bl[:, 1], color='r', linewidth=1, linestyle=':')
            mask = (trial.reverse[:, 0] >= lower_r) & (
                trial.reverse[:, 0] <= upper_r)
            x, y = trial.reverse[mask, 0], trial.reverse[mask, 1]
            ax.fill_between(x, y, np.interp(
                x, bl[:, 0], bl[:, 1]), alpha=0.3, color='r')

    ax.set_xlabel("t (s)")
    ax.set_ylabel("j_ECSA (mA cm⁻²)")
    ax.set_title(trial.label)
    ax.grid()
    if ax.get_legend_handles_labels()[0]:
        ax.legend()

    plt.tight_layout()
    return fig


# ------------------------------------------------------------------ #
# Integral recalculation                                               #
# ------------------------------------------------------------------ #

def recalculate(trial: OERTrial, lower_f, upper_f, lower_r, upper_r):
    """Recalculates forward and reverse integrals from explicit bounds."""
    fwd = trial.integrate(trial.forward, bounds=(lower_f, upper_f))
    _rev = trial.integrate(trial.reverse, bounds=(lower_r, upper_r))
    rev = -_rev if _rev is not None else None
    return fwd, rev


# ------------------------------------------------------------------ #
# Excel output                                                         #
# ------------------------------------------------------------------ #

def write_results(results: list, file_path: str):
    """Writes results to a new 'Integrals' sheet in the Excel file."""
    try:
        wb = openpyxl.load_workbook(file_path)
    except Exception as e:
        print(f"[ERROR] Could not open workbook for writing: {e}")
        print(f"  Path used: {file_path!r}")
        return

    if "Integrals" in wb.sheetnames:
        del wb["Integrals"]
    ws = wb.create_sheet("Integrals")

    ws.cell(row=1, column=1, value="Trial")
    ws.cell(row=1, column=2, value="Forward Integral (mC cm⁻²)")
    ws.cell(row=1, column=3, value="Reverse Integral (mC cm⁻²)")
    ws.cell(row=1, column=4, value="Forward Peak E (V)")
    ws.cell(row=1, column=5, value="Forward Peak j (mA cm⁻²)")
    ws.cell(row=1, column=6, value="Reverse Peak E (V)")
    ws.cell(row=1, column=7, value="Reverse Peak j (mA cm⁻²)")

    for i, (label, fwd, rev, fwd_E, fwd_j, rev_E, rev_j) in enumerate(results):
        ws.cell(row=i + 2, column=1, value=label)
        ws.cell(row=i + 2, column=2, value=fwd)
        ws.cell(row=i + 2, column=3, value=rev)
        ws.cell(row=i + 2, column=4, value=fwd_E)
        ws.cell(row=i + 2, column=5, value=fwd_j)
        ws.cell(row=i + 2, column=6, value=rev_E)
        ws.cell(row=i + 2, column=7, value=rev_j)

    try:
        wb.save(file_path)
        print(f"Results written to {file_path}")
    except Exception as e:
        print(f"[ERROR] Could not save workbook: {e}")
        print("  The file may be open in Excel. Close it and try again.")


def prompt_scan_rate() -> int:
    """Asks for scan rate once before loading the file."""
    while True:
        raw = input("Scan rate (mV/s) [100]: ").strip()
        if not raw:
            return 100
        try:
            return int(raw)
        except ValueError:
            print("  Please enter a number.")


# ------------------------------------------------------------------ #
# Modes                                                                #
# ------------------------------------------------------------------ #

def run_all(oer_file: OERFile, file_path: str):
    """Integrates all trials silently with a progress bar, then writes to Excel."""
    # clear old plots and saved bounds
    plots_dir = os.path.join(os.path.dirname(
        file_path), os.path.splitext(os.path.basename(file_path))[0])
    if os.path.exists(plots_dir):
        for f in os.listdir(plots_dir):
            os.remove(os.path.join(plots_dir, f))
    bp = bounds_path(file_path)
    if os.path.exists(bp):
        os.remove(bp)

    results = []
    for trial in tqdm(oer_file.all_trials(), desc="Integrating"):
        results.append(
            (trial.label, trial.forward_integral, trial.reverse_integral,
             trial.forward_peak_E, trial.forward_peak_j,
             trial.reverse_peak_E, trial.reverse_peak_j))
    write_results(results, file_path)
    save_plots(oer_file, file_path)


def review_all(oer_file: OERFile, file_path: str):
    """Steps through every trial, shows the plot, and lets the user correct bounds.
    Saves approved bounds to a JSON sidecar so future runs start from the same values."""
    def fmt(v):
        return f"{v:.4f}" if v is not None else "N/A"

    bounds_store = load_saved_bounds(file_path)
    results = []
    for trial in oer_file.all_trials():
        lower_f, upper_f, lower_r, upper_r = compute_bounds(
            trial, bounds_store)

        while True:
            plt.close('all')
            draw_trial(trial, lower_f, upper_f, lower_r, upper_r)
            plt.show()

            ok = input(f"{trial.label} — ok? (Enter/n): ").strip().lower()
            if ok in ("", "y", "yes"):
                fwd, rev = recalculate(
                    trial, lower_f, upper_f, lower_r, upper_r)
                fwd_E, fwd_j = trial._peak_coords(
                    trial.forward, (lower_f, upper_f), mode="max")
                rev_E, rev_j = trial._peak_coords(
                    trial.reverse, (lower_r, upper_r), mode="min", reflected=True)
                results.append(
                    (trial.label, fwd, rev, fwd_E, fwd_j, rev_E, rev_j))
                bounds_store[trial.label] = {
                    "lower_f": lower_f, "upper_f": upper_f,
                    "lower_r": lower_r, "upper_r": upper_r
                }
                save_bounds(file_path, bounds_store)
                break

            for name, current in [("fl", lower_f), ("fu", upper_f), ("rl", lower_r), ("ru", upper_r)]:
                val = input(f"  {name} [{fmt(current)}]: ").strip()
                if not val:
                    continue
                try:
                    v = float(val)
                    if name == "fl":
                        lower_f = v
                    elif name == "fu":
                        upper_f = v
                    elif name == "rl":
                        lower_r = v
                    elif name == "ru":
                        upper_r = v
                except ValueError:
                    pass

    write_results(results, file_path)
    save_plots(oer_file, file_path)


def inspect_one(oer_file: OERFile):
    """Plots and prints integrals for a single user-selected trial."""
    sheet = input("Sheet name: ").strip()
    idx = int(input("Trial index: ").strip())
    trial = oer_file.get_sheet(sheet).trials[idx]
    lower_f, upper_f, lower_r, upper_r = compute_bounds(trial)
    draw_trial(trial, lower_f, upper_f, lower_r, upper_r)
    plt.show()
    print(
        f"Forward: {trial.forward_integral}  Reverse: {trial.reverse_integral}")


def save_plots(oer_file: OERFile, file_path: str):
    """Saves a PNG of each trial to a 'plots' folder next to the Excel file.
    Uses saved bounds if available, otherwise auto-detects."""
    plots_dir = os.path.join(os.path.dirname(
        file_path), os.path.splitext(os.path.basename(file_path))[0])
    os.makedirs(plots_dir, exist_ok=True)
    bounds_store = load_saved_bounds(file_path)

    for trial in tqdm(oer_file.all_trials(), desc="Saving plots"):
        lower_f, upper_f, lower_r, upper_r = compute_bounds(
            trial, bounds_store)
        fig = draw_trial(trial, lower_f, upper_f, lower_r, upper_r)
        safe_label = trial.label.replace("/", "-").replace("\\", "-")
        fig.savefig(os.path.join(plots_dir, f"{safe_label}.png"), dpi=150)
        plt.close(fig)


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        file_path = os.path.abspath(
            input("Drag in the OER file: ").strip().strip("'\""))

        scan_rate = prompt_scan_rate()
        f = OERFile(file_path, scan_rate=scan_rate)
        f.summary()

        while True:
            # os.system('clear' if os.name == 'posix' else 'cls')

            mode = input(
                "(a) run all  (r) review  (i) inspect one: ").strip().lower()
            if mode == "a":
                run_all(f, file_path)
            elif mode == "r":
                review_all(f, file_path)
            else:
                inspect_one(f)

            more_work = input(
                "Do you want to do more with this file? (y/n): ").strip().lower()
            if more_work not in ("y", "yes"):
                break

        new_file = input("Analyze another file? (y/n): ").strip().lower()
        if new_file not in ("y", "yes"):
            print("Goodbye!")
            break
