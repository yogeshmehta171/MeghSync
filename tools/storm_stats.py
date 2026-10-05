"""
storm_stats.py: describe the synthetic storms that the model was trained on.

Run from the folder that contains synthetic_storms_mm_hr.npy (and the dataset/ folder, if you want SWMM results too):

    python storm_stats.py
    python storm_stats.py --rain synthetic_storms_mm_hr.npy --data-dir dataset

It measures the rain curves that were saved. It cannot read the generator's own settings, so the
Gaussian numbers below are ESTIMATES from the finished curves (amplitude, centre, width of each pulse).
Time step is 5 minutes, as in ml/dataset.py.
"""
import argparse
import os
import numpy as np

STEP_MIN = 5
WET_MMHR = 0.1          # a step counts as "raining" above this


def pulses(r, min_height, min_gap=3):
    """Local maxima of a smoothed curve -> list of (index, height). No scipy needed."""
    k = np.ones(3) / 3
    s = np.convolve(r, k, mode="same")
    idx = [i for i in range(1, len(s) - 1) if s[i] >= s[i - 1] and s[i] > s[i + 1] and s[i] >= min_height]
    out = []
    for i in idx:                                   # drop peaks closer than min_gap steps (keep the higher one)
        if out and i - out[-1][0] < min_gap:
            if s[i] > out[-1][1]:
                out[-1] = (i, s[i])
        else:
            out.append((i, s[i]))
    return out


def sigma_steps(r, i):
    """Width of a pulse as a Gaussian sigma (in steps), from where it falls to half its height."""
    h = r[i] / 2.0
    lo = i
    while lo > 0 and r[lo] > h:
        lo -= 1
    hi = i
    while hi < len(r) - 1 and r[hi] > h:
        hi += 1
    return max(hi - lo, 1) / 2.355                  # FWHM / 2.355


def q(a):
    a = np.asarray(a, float)
    return "min %.1f | p10 %.1f | median %.1f | p90 %.1f | max %.1f" % (
        a.min(), np.percentile(a, 10), np.median(a), np.percentile(a, 90), a.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain", default="synthetic_storms_mm_hr.npy")
    ap.add_argument("--data-dir", default="dataset")
    a = ap.parse_args()

    rain = np.load(a.rain, allow_pickle=True)
    storms = [np.asarray(r, float).ravel() for r in rain]
    print(f"{a.rain}: {len(storms)} storms, array shape {getattr(rain, 'shape', None)}")

    n_steps, peak, peak_t, wet_h, total_mm, n_pulse, sig_min, centre_h = [], [], [], [], [], [], [], []
    for r in storms:
        n_steps.append(len(r))
        p = r.max()
        peak.append(p)
        peak_t.append(int(r.argmax()) * STEP_MIN / 60)
        wet_h.append((r > WET_MMHR).sum() * STEP_MIN / 60)
        total_mm.append(r.sum() * STEP_MIN / 60)
        pl = pulses(r, max(0.2 * p, 1.0))
        n_pulse.append(len(pl))
        sig_min.append(sigma_steps(r, int(r.argmax())) * STEP_MIN)

    print("\nLength of each storm record (hours):  ", q(np.array(n_steps) * STEP_MIN / 60))
    print("Peak intensity (mm/hr):               ", q(peak))
    print("Time of the main peak (hours in):     ", q(peak_t))
    print("Time with rain > %.1f mm/hr (hours):   %s" % (WET_MMHR, q(wet_h)))
    print("Total rain (mm):                      ", q(total_mm))
    print("Pulses per storm (>= 20% of the peak): ", q(n_pulse), "| storms with 2+ pulses:", int(np.sum(np.array(n_pulse) >= 2)))
    print("Main pulse width, Gaussian sigma (min):", q(sig_min))
    print("Storms with peak < 10 mm/hr:", int(np.sum(np.array(peak) < 10)), "| < 30 mm/hr:", int(np.sum(np.array(peak) < 30)),
          "| zero rain:", int(np.sum(np.array(peak) <= WET_MMHR)))

    # optional: what SWMM produced for these storms
    f0 = os.path.join(a.data_dir, "flood_storm_000.npy")
    if os.path.exists(f0):
        mx, wet = [], []
        for i in range(len(storms)):
            fp = os.path.join(a.data_dir, f"flood_storm_{i:03d}.npy")
            if os.path.exists(fp):
                f = np.load(fp)
                mx.append(float(f.max()))
                wet.append(int((f.max(axis=0) >= 0.15).sum()))
        print(f"\nSWMM flood files found for {len(mx)} storms; array shape of storm 0: {np.load(f0).shape} (time, nodes)")
        print("Deepest flood per storm (m):          ", q(mx))
        print("Nodes ever above 15 cm per storm:     ", q(wet))
        if os.path.exists(os.path.join(a.data_dir, "blockage_storm_000.npy")):
            nb = [int((np.load(os.path.join(a.data_dir, f"blockage_storm_{i:03d}.npy")) < 1).sum()) for i in range(len(mx))]
            print("Pipes with capacity < 1 per storm:    ", q(nb))


if __name__ == "__main__":
    main()
