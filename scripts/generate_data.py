
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START = "2025-01-01 00:00"
END = "2026-10-31 23:00"
TZ = "Asia/Jakarta"

# jumlah mesin per tipe (total 40 mesin)
MACHINE_MIX = {"CNC Lathe": 10, "Press": 8, "Conveyor": 8, "Packaging": 7, "Injection Molding": 7}

BASE_FAILURES_PER_YEAR = 3.2     
PREVENTIVE_INTERVAL_DAYS = 45    
PROTECT_DAYS = 90                
PROTECT_PROB = 0.6               
BACKGROUND_ERRORS_PER_MACHINE = 25   
MISSING_RATE = 0.005             
GLITCH_RATE = 0.001              

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(SEED)

COMPONENTS = {
 
    "bearing":        ("bearing wear",     "E101", "Vibration above normal limit",   (800_000, 2_000_000),   (4, 12)),
    "motor":          ("motor overheating", "E201", "Motor temperature too high",     (2_000_000, 6_000_000), (6, 24)),
    "hydraulic_pump": ("pressure loss",    "E301", "Hydraulic pressure below limit", (1_500_000, 4_000_000), (3, 10)),
    "control_board":  ("electrical fault", "E401", "Voltage unstable",               (1_000_000, 3_000_000), (2, 8)),
}
COMP_NAMES = list(COMPONENTS)
NOISE_ERROR = ("E001", "Communication timeout")

BASE = {"voltage": 170.0, "rotation_rpm": 446.0, "pressure": 101.0, "vibration": 40.0, "temperature": 70.0}
SD = {"voltage": 8.0, "rotation_rpm": 30.0, "pressure": 6.0, "vibration": 4.0, "temperature": 2.5}
MODEL_OFFSETS = {1: (0, 0, 0, 0, 0), 2: (3, 10, 2, 1, 2), 3: (-3, -8, -2, -1, -2), 4: (5, 15, 4, 2, 4)}
MODEL_FAIL_FACTOR = {1: 0.9, 2: 1.0, 3: 1.15, 4: 1.35}
SENSOR_COLS = ["voltage", "rotation_rpm", "pressure", "vibration", "temperature"]

WARMUP_HOURS = 120               

def make_machines() -> pd.DataFrame:
    rows, mid = [], 1
    for mtype, count in MACHINE_MIX.items():
        for i in range(1, count + 1):
            install = pd.Timestamp("2016-01-01") + pd.Timedelta(days=int(rng.integers(0, 2900)))
            rows.append({
                "machine_id": mid,
                "machine_name": f"{mtype} {i:02d}",
                "machine_type": mtype,
                "machine_model": f"model{int(rng.integers(1, 5))}",
                "production_line": f"Line {'ABCD'[int(rng.integers(0, 4))]}",
                "install_date": install.date(),
                "status": "active",
            })
            mid += 1
    return pd.DataFrame(rows)


def round_half(x: float) -> float:
    return round(x * 2) / 2


def round_cost(x: float) -> int:
    return int(round(x / 50_000) * 50_000)


def severity_from_downtime(hours: float) -> str:
    return "low" if hours < 5 else ("medium" if hours < 12 else "high")


def simulate_machine(m, hours: pd.DatetimeIndex):
    n = len(hours)
    mid = int(m.machine_id)
    model = int(m.machine_model[-1])
    off = MODEL_OFFSETS[model]
    hod = hours.hour.to_numpy()
    daily = np.sin((hod - 8) / 24 * 2 * np.pi)          
    sig = {
        "voltage":      BASE["voltage"] + off[0] + rng.normal(0, SD["voltage"], n),
        "rotation_rpm": BASE["rotation_rpm"] + off[1] + rng.normal(0, SD["rotation_rpm"], n),
        "pressure":     BASE["pressure"] + off[2] + rng.normal(0, SD["pressure"], n),
        "vibration":    BASE["vibration"] + off[3] + rng.normal(0, SD["vibration"], n),
        "temperature":  BASE["temperature"] + off[4] + 2.5 * daily + rng.normal(0, SD["temperature"], n),
    }
    valid = np.ones(n, dtype=bool)

    maint_rows, failure_rows, error_rows = [], [], []


    prev = []                                            
    pos = int(rng.integers(0, PREVENTIVE_INTERVAL_DAYS * 24))
    cycle0, k = int(rng.integers(0, 4)), 0
    while pos < n - 48:
        comp = COMP_NAMES[(cycle0 + k) % 4]
        p = min(max(pos + int(rng.integers(-5 * 24, 5 * 24)), 0), n - 48)
        p = (p // 24) * 24 + 7                           
        prev.append((p, comp))
        pos += PREVENTIVE_INTERVAL_DAYS * 24
        k += 1
    for p, comp in prev:
        lo, hi = COMPONENTS[comp][3]
        dt = round_half(rng.uniform(1.5, 4.0))
        valid[p:p + int(np.ceil(dt))] = False
        maint_rows.append({
            "machine_id": mid, "maintenance_date": hours[p], "component": comp,
            "maintenance_type": "preventive", "cost_idr": round_cost(rng.uniform(lo, hi)),
            "downtime_hours": dt,
        })


    age_years = (hours[0].date() - m.install_date).days / 365.25
    rate = BASE_FAILURES_PER_YEAR * (1 + 0.12 * age_years) * MODEL_FAIL_FACTOR[model]
    k_fail = rng.poisson(rate * n / 8766)
    cands = np.sort(rng.integers(WARMUP_HOURS, n - 48, size=k_fail)) if k_fail else np.array([], dtype=int)
    comp_w = rng.dirichlet(np.array([3.5, 3.0, 2.0, 1.5]))

    last = -10_000
    for fi in cands:
        if fi - last < 240:                              
            continue
        comp = COMP_NAMES[int(rng.choice(4, p=comp_w))]
        protected = any(pc == comp and 0 <= fi - pi <= PROTECT_DAYS * 24 for pi, pc in prev)
        if protected and rng.random() < PROTECT_PROB:
            continue
        last = fi

        ftype, ecode, edesc, (clo, chi), (dlo, dhi) = COMPONENTS[comp]
        L = int(rng.uniform(48, 120))
        s = max(0, fi - L)
        w = np.arange(s, fi)
        ramp = ((w - s) / max(fi - s, 1)) ** 2
        if comp == "bearing":
            sig["vibration"][w] += 14 * ramp
            sig["temperature"][w] += 4 * ramp
        elif comp == "motor":
            sig["temperature"][w] += 18 * ramp
            sig["rotation_rpm"][w] -= 30 * ramp
            sig["vibration"][w] += 3 * ramp
        elif comp == "hydraulic_pump":
            sig["pressure"][w] -= 28 * ramp
            sig["vibration"][w] += 5 * ramp
            sig["temperature"][w] += 3 * ramp
        else:  # control_board
            sig["voltage"][w] += rng.normal(0, 25, len(w)) * ramp
            sig["rotation_rpm"][w] += rng.normal(0, 40, len(w)) * ramp
            sig["temperature"][w] += 2 * ramp

        counts = rng.poisson(0.02 + 0.35 * ramp)
        for j in np.nonzero(counts)[0]:
            for _ in range(counts[j]):
                r = ramp[j]
                error_rows.append({
                    "machine_id": mid,
                    "error_time": hours[w[j]] + pd.Timedelta(minutes=int(rng.integers(0, 60))),
                    "error_code": ecode, "error_description": edesc,
                    "severity": "low" if r < 0.4 else ("medium" if r < 0.75 else "high"),
                })

        # ---- kerusakan + perawatan korektif ----
        downtime = round_half(rng.uniform(dlo, dhi))
        valid[fi:fi + int(np.ceil(downtime))] = False
        ftime = hours[fi] + pd.Timedelta(minutes=int(rng.integers(0, 60)))
        failure_rows.append({
            "machine_id": mid, "failure_time": ftime, "component": comp, "failure_type": ftype,
            "severity": severity_from_downtime(downtime), "downtime_hours": downtime,
        })
        maint_rows.append({
            "machine_id": mid, "maintenance_date": ftime + pd.Timedelta(minutes=30), "component": comp,
            "maintenance_type": "corrective", "cost_idr": round_cost(rng.uniform(clo, chi) * rng.uniform(2.0, 4.0)),
            "downtime_hours": downtime,
        })

    all_errors = [(c[1], c[2]) for c in COMPONENTS.values()] + [NOISE_ERROR]
    for idx in rng.integers(0, n, size=rng.poisson(BACKGROUND_ERRORS_PER_MACHINE)):
        code, desc = all_errors[int(rng.integers(0, len(all_errors)))]
        error_rows.append({
            "machine_id": mid,
            "error_time": hours[idx] + pd.Timedelta(minutes=int(rng.integers(0, 60))),
            "error_code": code, "error_description": desc,
            "severity": "low" if rng.random() < 0.9 else "medium",
        })

    df = pd.DataFrame(sig)
    glitch = np.nonzero(rng.random(n) < GLITCH_RATE)[0]
    for g in glitch:
        col = SENSOR_COLS[int(rng.integers(0, 5))]
        df.loc[g, col] *= rng.uniform(2.0, 3.0)
    for col in SENSOR_COLS:
        df.loc[rng.random(n) < MISSING_RATE, col] = np.nan

    df.insert(0, "reading_time", hours)
    df.insert(0, "machine_id", mid)
    df[SENSOR_COLS] = df[SENSOR_COLS].round(2)
    df = df[valid]                                       
    return df, maint_rows, failure_rows, error_rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    hours = pd.date_range(START, END, freq="h", tz=TZ)
    machines = make_machines()

    sensors, maint, fails, errs = [], [], [], []
    for m in machines.itertuples():
        s, mt, f, e = simulate_machine(m, hours)
        sensors.append(s); maint += mt; fails += f; errs += e

    sensor_df = pd.concat(sensors, ignore_index=True)
    maint_df = pd.DataFrame(maint).sort_values(["maintenance_date", "machine_id"])
    fail_df = pd.DataFrame(fails).sort_values(["failure_time", "machine_id"])
    err_df = pd.DataFrame(errs).sort_values(["error_time", "machine_id"])

    machines.to_csv(OUTPUT_DIR / "machines.csv", index=False)
    sensor_df.to_csv(OUTPUT_DIR / "sensor_readings.csv", index=False)
    maint_df.to_csv(OUTPUT_DIR / "maintenance_logs.csv", index=False)
    fail_df.to_csv(OUTPUT_DIR / "failures.csv", index=False)
    err_df.to_csv(OUTPUT_DIR / "error_logs.csv", index=False)

    print(f"Selesai! File tersimpan di: {OUTPUT_DIR.resolve()}")
    print(f"  machines.csv          : {len(machines):>8,} baris")
    print(f"  sensor_readings.csv   : {len(sensor_df):>8,} baris")
    print(f"  maintenance_logs.csv  : {len(maint_df):>8,} baris")
    print(f"  failures.csv          : {len(fail_df):>8,} baris")
    print(f"  error_logs.csv        : {len(err_df):>8,} baris")
    print(f"  Rentang waktu         : {hours[0].date()} s/d {hours[-1].date()}")


if __name__ == "__main__":
    main()
