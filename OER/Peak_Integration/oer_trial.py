# mypy: ignore-errors
# pylint: skip-file

import numpy as np
from scipy.signal import savgol_filter
from scipy.integrate import trapezoid


class OERTrial:
    """One CV sweep cycle. Forward = anodic (t: 0→T), reverse = cathodic (t: T→2T)."""

    def __init__(self, data: np.ndarray, trial_index: int, label: str = "", scan_rate: int = 100):
        self.data = data.copy()
        self.scan_rate = scan_rate
        self.trial_index = trial_index
        self.label = label or f"Trial {trial_index}"

        if len(self.data) < 4:
            raise ValueError(
                f"Trial '{self.label}' has too few points ({len(self.data)}) to process.")

        self.data[:, 0] = self.data[:, 0] * (1000 / self.scan_rate)
        # save before zeroing, in ms units
        self._t_offset = float(self.data[0, 0])
        self.data[:, 0] -= self._t_offset  # shift so t starts at 0

        # Split at the turnaround (max t = max E)
        self.split_idx = np.argmax(self.data[:, 0])
        t_max = self.data[self.split_idx, 0]

        self.forward = self.data[:self.split_idx +
                                 1].copy()  # include turnaround point

        # Reflect reverse t past turnaround: t_reverse = 2*t_max - t_raw
        # so reverse continues forward in time (T → 2T) instead of folding back
        raw_reverse = self.data[self.split_idx:].copy()
        raw_reverse[:, 0] = 2 * t_max - raw_reverse[:, 0]
        self.reverse = raw_reverse[np.argsort(raw_reverse[:, 0])].copy()

        self._prep_forward()
        self._prep_reverse()

        self._fwd_bounds = self._forward_peak_bounds()
        self._rev_bounds = self._reverse_peak_bounds()

        self.forward_integral = self.integrate(
            self.forward, bounds=self._fwd_bounds)
        _rev = self.integrate(self.reverse, bounds=self._rev_bounds)
        self.reverse_integral = -_rev if _rev is not None else None

        self.forward_peak_E, self.forward_peak_j = self._peak_coords(
            self.forward, self._fwd_bounds, mode="max")
        self.reverse_peak_E, self.reverse_peak_j = self._peak_coords(
            self.reverse, self._rev_bounds, mode="min", reflected=True)

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    def _deriv(self, x, y):
        """Centered finite difference derivative using roll."""
        return (np.roll(y, -1) - np.roll(y, 1)) / (np.roll(x, -1) - np.roll(x, 1))

    def _smooth(self, arr: np.ndarray) -> np.ndarray:
        """Savitzky-Golay smoothing on j column."""
        window = max(2, len(arr) // 25)
        window = min(window, 25)
        window = window if window % 2 != 0 else window - 1
        polyorder = min(5, window - 1)
        out = arr.copy()
        out[:, 1] = savgol_filter(
            arr[:, 1], window_length=window, polyorder=polyorder)
        return out

    def _prep_reverse(self):
        self.reverse = self.reverse[np.argsort(self.reverse[:, 0])].copy()
        self.reverse_clean = self._smooth(self.reverse)
        x, y = self.reverse_clean[:, 0], self.reverse_clean[:, 1]
        dy = self._deriv(x, y)
        self.reverse_d2 = np.column_stack((x, self._deriv(x, dy)))

    def _prep_forward(self):
        self.forward_clean = self._smooth(self.forward)

    # ------------------------------------------------------------------ #
    # Peak bounds                                                          #
    # ------------------------------------------------------------------ #

    def _forward_peak_bounds(self):
        """Forward peak bounds.
        Right bound: local minimum to the right of the first local peak.
        Left bound: tangent chord from right bound to the left wall (on clean data)."""
        x, y = self.forward_clean[:, 0], self.forward_clean[:, 1]

        # first local maximum
        peak_idx = None
        for i in range(1, len(y) - 1):
            if y[i] > y[i - 1] and y[i] > y[i + 1]:
                peak_idx = i
                break
        if peak_idx is None:
            return None, None

        # right bound: first local minimum to the right of the peak
        t_end = None
        for i in range(peak_idx + 1, len(y) - 1):
            if y[i] < y[i - 1] and y[i] < y[i + 1]:
                t_end = float(x[i])
                break
        if t_end is None:
            t_end = float(x[-1])

        # left bound: chord from right bound to left wall, steepest positive slope (on clean data)
        t_start = None
        candidates = self.forward_clean[x < x[peak_idx]]
        if len(candidates) >= 2:
            j_end = np.interp(t_end, x, y)
            slopes = (j_end - candidates[:, 1]) / (t_end - candidates[:, 0])
            t_start = float(candidates[np.argmax(slopes), 0])

        return t_start, t_end

    def _reverse_peak_bounds(self):
        """Reverse peak bounds.
        Left bound: inflection point to the left of the trough (d2: + -> -).
        Right bound: tangent chord from trough minimum to the right wall (on clean data)."""
        x, y = self.reverse_clean[:, 0], self.reverse_clean[:, 1]
        d2 = self.reverse_d2

        trough_idx = np.argmin(y)

        # left bound: rightmost inflection point to the left of the trough (d2: + -> -)
        t_start = None
        for i in range(trough_idx, 0, -1):
            if d2[i, 1] < 0 and d2[i - 1, 1] > 0:
                x0, y0 = d2[i - 1, 0], d2[i - 1, 1]
                x1, y1 = d2[i, 0], d2[i, 1]
                # linear interpolation to zero crossing
                t_start = x0 - y0 * (x1 - x0) / (y1 - y0)
                break

        # right bound: tangent line at each point to the right of trough that passes through left bound
        t_end = None
        if t_start is not None:
            j_start = np.interp(t_start, x, y)
            candidates = self.reverse_clean[x > x[trough_idx]]
            if len(candidates) >= 1:
                # j_trough = float(y[trough_idx])
                # t_trough = float(x[trough_idx])
                closest_idx = None
                min_error = np.inf
                for ci in range(len(candidates)):
                    t_c, j_c = float(candidates[ci, 0]), float(
                        candidates[ci, 1])
                    # slope of tangent at this point
                    tangent_slope = np.interp(
                        t_c, self.reverse_d2[:, 0], self.reverse_d2[:, 1])
                    # check if tangent line at (t_c, j_c) passes through (t_start, j_start)
                    j_at_start = j_c + tangent_slope * (t_start - t_c)
                    error = np.abs(j_at_start - j_start)
                    if np.isclose(j_at_start, j_start, rtol=1e-3):
                        t_end = float(t_c)
                        break
                    if error < min_error:
                        min_error = error
                        closest_idx = ci
                if t_end is None and closest_idx is not None:
                    t_end = float(candidates[closest_idx, 0])

        return t_start, t_end

    # ------------------------------------------------------------------ #
    # Baseline + integration                                               #
    # ------------------------------------------------------------------ #

    def _peak_coords(self, sweep: np.ndarray, bounds: tuple, mode: str, reflected: bool = False):
        """Returns (E_V, j) of the max or min j within bounds, from raw data.
        reflected=True for the reverse sweep, whose t-axis was mirrored past t_max."""
        lower, upper = bounds
        if lower is None or upper is None:
            return None, None
        x, y = sweep[:, 0], sweep[:, 1]
        mask = (x >= lower) & (x <= upper)
        if not np.any(mask):
            return None, None
        x_reg, y_reg = x[mask], y[mask]
        idx = np.argmax(y_reg) if mode == "max" else np.argmin(y_reg)
        t_peak = float(x_reg[idx])
        j_peak = float(y_reg[idx])
        if reflected:
            t_max = float(self.data[self.split_idx, 0])
            t_original = 2 * t_max - t_peak  # un-reflect back to original t
            E_peak = (t_original + self._t_offset) * self.scan_rate / 1000.0
        else:
            E_peak = (t_peak + self._t_offset) * self.scan_rate / 1000.0
        return E_peak, j_peak

    def get_baseline(self, sweep: np.ndarray, t_lower: float, t_upper: float):
        """Straight-line baseline from j(t_lower) to j(t_upper)."""
        s = sweep[np.argsort(sweep[:, 0])]
        region = s[(s[:, 0] >= t_lower) & (s[:, 0] <= t_upper)]
        if len(region) < 2:
            return None
        j_lo = np.interp(t_lower, s[:, 0], s[:, 1])
        j_hi = np.interp(t_upper, s[:, 0], s[:, 1])
        x = np.concatenate(([t_lower], region[:, 0], [t_upper]))
        y = j_lo + (j_hi - j_lo) * (x - t_lower) / (t_upper - t_lower)
        return np.column_stack((x, y))

    def integrate(self, sweep: np.ndarray, bounds: tuple):
        """Trapezoidal integration of (data - baseline) between bounds. Returns mC/cm² or None."""
        lower, upper = bounds
        if lower is None or upper is None:
            return None
        x, y = sweep[:, 0], sweep[:, 1]
        mask = (x >= lower) & (x <= upper)
        x_reg, y_reg = x[mask], y[mask]
        baseline = self.get_baseline(sweep, lower, upper)
        if baseline is None:
            return None
        bl_y = np.interp(x_reg, baseline[:, 0], baseline[:, 1])
        return float(trapezoid(y_reg - bl_y, x_reg))

    def __repr__(self):
        return f"OERTrial(label={self.label!r}, n_points={len(self.data)})"
