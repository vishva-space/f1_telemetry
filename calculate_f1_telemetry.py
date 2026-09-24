#!/usr/bin/env python3
"""F1 telemetry workflow combining the CdA summary and engine power model.

The script is structured into separate functions so the session-level CdA
calculations and the row-by-row engine power logic remain connected but clearly
separated.
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

P_ENGINE = 750_000.0
ETA_DRIVETRAIN = 0.95
ETA_THERMAL = 0.46
R_WHEEL = 0.355
R_GAS = 287.05
MASS_ASSUMED_KG = 860.0
CAR_MASS_KG = 860.0
ROLLING_RESISTANCE_COEFF = 0.015
P_WHEELS = P_ENGINE * ETA_DRIVETRAIN
GEAR_NAMES = [2, 3, 4, 5, 6, 7, 8]


def parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "nan", "NaN", "null", "NULL", "None"}:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def find_csv_file(search_dirs: Iterable[Path], filename: str) -> Optional[Path]:
    for base_dir in search_dirs:
        candidate = base_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def find_nearest_weather(weather_rows: List[Dict[str, str]], target_dt: datetime, meeting_key: Any = None, session_key: Any = None) -> Optional[Dict[str, str]]:
    best_row = None
    best_delta = None
    for row in weather_rows:
        row_dt = parse_date(row.get("date"))
        if row_dt is None:
            continue
        if meeting_key is not None and row.get("meeting_key") not in (None, ""):
            if str(row.get("meeting_key")) != str(meeting_key):
                continue
        if session_key is not None and row.get("session_key") not in (None, ""):
            if str(row.get("session_key")) != str(session_key):
                continue
        delta = abs((row_dt - target_dt).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_row = row
    return best_row


def find_bracketing_location(location_rows: List[Dict[str, str]], target_dt: datetime) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, str]]]:
    valid = []
    for row in location_rows:
        dt = parse_date(row.get("date"))
        if dt is None:
            continue
        valid.append((dt, row))
    if not valid:
        return None, None
    valid.sort(key=lambda item: item[0])
    prev_row = None
    next_row = None
    for dt, row in valid:
        if dt <= target_dt:
            prev_row = row
        if dt >= target_dt and next_row is None:
            next_row = row
            break
    if prev_row is None and next_row is not None:
        return next_row, next_row
    if next_row is None and prev_row is not None:
        return prev_row, prev_row
    return prev_row, next_row


def heading_from_location(prev_row: Optional[Dict[str, str]], next_row: Optional[Dict[str, str]]) -> float:
    if prev_row is None or next_row is None:
        return 0.0
    x1 = to_float(prev_row.get("x"))
    y1 = to_float(prev_row.get("y"))
    x2 = to_float(next_row.get("x"))
    y2 = to_float(next_row.get("y"))
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return 0.0
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return math.atan2(dy, dx)


def overall_ratio(rpm: float, speed_mps: float) -> float:
    if speed_mps <= 0 or rpm <= 0:
        return float("nan")
    return (rpm * 2.0 * math.pi * R_WHEEL) / (speed_mps * 60.0)


def compute_gear_ratios(car_rows: List[Dict[str, str]]) -> Dict[int, float]:
    gear_map: Dict[int, List[float]] = {gear: [] for gear in GEAR_NAMES}
    for row in car_rows:
        rpm = to_float(row.get("rpm"))
        speed_kph = to_float(row.get("speed"))
        gear_raw = row.get("n_gear")
        if rpm is None or speed_kph is None:
            continue
        if speed_kph <= 0:
            continue
        if gear_raw in (None, "", "0"):
            continue
        try:
            gear = int(float(gear_raw))
        except (TypeError, ValueError):
            continue
        if gear not in gear_map:
            continue
        speed_mps = speed_kph / 3.6
        ratio = overall_ratio(rpm, speed_mps)
        if math.isfinite(ratio):
            gear_map[gear].append(ratio)
    output: Dict[int, float] = {}
    for gear in GEAR_NAMES:
        values = gear_map[gear]
        output[gear] = (sum(values) / len(values)) if values else float("nan")
    return output


def load_inputs(data_dir: str = "inputs", car_filename: str = "car_data.csv", weather_filename: str = "weather.csv", location_filename: str = "location.csv") -> Dict[str, List[Dict[str, str]]]:
    base_dir = Path(data_dir)
    car_path = base_dir / car_filename
    weather_path = base_dir / weather_filename
    location_path = base_dir / location_filename

    for path in (car_path, weather_path, location_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing required CSV file: {path}")

    return {
        "car_data": read_csv(car_path),
        "weather": read_csv(weather_path),
        "location": read_csv(location_path),
    }


def compute_session_constants(input_data: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    car_rows = input_data["car_data"]
    weather_rows = input_data["weather"]
    location_rows = input_data["location"]

    if not car_rows:
        raise ValueError("No rows found in car_data.csv")

    max_speed_row = None
    max_speed_kph = float("-inf")
    for row in car_rows:
        speed_kph = to_float(row.get("speed"))
        if speed_kph is None:
            continue
        if speed_kph > max_speed_kph:
            max_speed_kph = speed_kph
            max_speed_row = row

    if max_speed_row is None:
        raise ValueError("No valid speed values found in car_data.csv")

    max_speed_mps = max_speed_kph / 3.6
    max_rpm = to_float(max_speed_row.get("rpm"))
    max_gear = max_speed_row.get("n_gear")
    try:
        max_gear_int = int(float(max_gear)) if max_gear not in (None, "") else None
    except (TypeError, ValueError):
        max_gear_int = None

    meeting_key = max_speed_row.get("meeting_key")
    session_key = max_speed_row.get("session_key")
    target_dt = parse_date(max_speed_row.get("date"))
    weather_row = find_nearest_weather(weather_rows, target_dt, meeting_key=meeting_key, session_key=session_key)
    if weather_row is None:
        weather_row = find_nearest_weather(weather_rows, target_dt)

    prev_loc, next_loc = find_bracketing_location(location_rows, target_dt)
    heading_rad = heading_from_location(prev_loc, next_loc)

    wind_speed = to_float(weather_row.get("wind_speed")) if weather_row else None
    wind_direction = to_float(weather_row.get("wind_direction")) if weather_row else None
    air_temp_c = to_float(weather_row.get("air_temperature")) if weather_row else None
    pressure_hpa = to_float(weather_row.get("pressure")) if weather_row else None

    if wind_speed is None or wind_direction is None:
        v_wind_head = 0.0
    else:
        theta_wind = math.radians((wind_direction + 180.0) % 360.0)
        delta_theta = theta_wind - heading_rad
        v_wind_head = wind_speed * math.cos(delta_theta)

    if air_temp_c is None or pressure_hpa is None:
        rho = float("nan")
    else:
        rho = (pressure_hpa * 100.0) / (R_GAS * (air_temp_c + 273.15))

    v_rel = max_speed_mps + v_wind_head
    if rho is None or math.isnan(rho) or v_rel <= 0:
        cda = float("nan")
    else:
        cda = (2.0 * P_WHEELS) / (rho * (v_rel ** 3))

    gear_averages = compute_gear_ratios(car_rows)

    return {
        "max_speed_row": max_speed_row,
        "max_speed_kph": max_speed_kph,
        "max_speed_mps": max_speed_mps,
        "max_rpm": max_rpm,
        "max_gear": max_gear_int,
        "weather_row": weather_row,
        "heading_rad": heading_rad,
        "v_wind_head": v_wind_head,
        "rho": rho,
        "v_rel": v_rel,
        "cda": cda,
        "gear_ratios": gear_averages,
        "weather_density": rho,
    }


def mass_validation_check(cda: float, max_speed_mps: float, rho: float, mass_assumed_kg: float = MASS_ASSUMED_KG) -> Dict[str, float]:
    g = 9.81
    f_trac = P_WHEELS / max_speed_mps
    f_drag = 0.5 * rho * cda * (max_speed_mps ** 2)
    c_rr_calculated = (f_trac - f_drag) / (mass_assumed_kg * g)
    return {
        "F_trac": f_trac,
        "F_drag": f_drag,
        "C_rr_calculated": c_rr_calculated,
    }


def compute_cda_summary(session_constants: Dict[str, Any]) -> Dict[str, Any]:
    max_speed_mps = session_constants["max_speed_mps"]
    max_speed_kph = session_constants["max_speed_kph"]
    max_rpm = session_constants["max_rpm"]
    max_gear = session_constants["max_gear"]
    rho = session_constants["rho"]
    cda = session_constants["cda"]
    gear_ratios = session_constants["gear_ratios"]

    omega_engine = (max_rpm * 2.0 * math.pi) / 60.0 if max_rpm is not None else float("nan")
    engine_torque = P_ENGINE / omega_engine if omega_engine not in (None, 0.0) and math.isfinite(omega_engine) else float("nan")
    overall_ratio_at_max = overall_ratio(max_rpm, max_speed_mps) if max_rpm is not None else float("nan")
    wheel_torque = engine_torque * overall_ratio_at_max * ETA_DRIVETRAIN if math.isfinite(engine_torque) and math.isfinite(overall_ratio_at_max) else float("nan")

    outputs: Dict[str, float | int | str] = {
        "CdA (m²)": cda,
        "Max Speed (kph)": max_speed_kph,
        "Max Speed (m/s)": max_speed_mps,
        "Max RPM": int(max_rpm) if max_rpm is not None and math.isfinite(max_rpm) else "N/A",
        "Max Gear": max_gear if max_gear is not None else "N/A",
        "Engine Torque at Max Speed (Nm)": engine_torque,
        "Wheel Torque at Max Speed (Nm)": wheel_torque,
        "Overall Ratio at Max Speed": overall_ratio_at_max,
        "Air Density (kg/m³)": rho,
    }
    for gear in GEAR_NAMES:
        outputs[f"Gear {gear} Overall Ratio"] = gear_ratios.get(gear, float("nan"))

    mass_check = mass_validation_check(cda, max_speed_mps, rho, MASS_ASSUMED_KG)

    return {
        "outputs": outputs,
        "mass_check": mass_check,
    }


def filter_valid_rows(car_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    valid_rows: List[Dict[str, str]] = []
    for i, row in enumerate(car_rows):
        speed_kph = to_float(row.get("speed"))
        rpm = to_float(row.get("rpm"))
        throttle = to_float(row.get("throttle")) if "throttle" in row and row.get("throttle") not in (None, "") else 100.0
        brake = to_float(row.get("brake")) if "brake" in row and row.get("brake") not in (None, "") else 0.0
        gear_raw = row.get("n_gear")
        if speed_kph is None or rpm is None:
            continue
        if speed_kph <= 0 or rpm <= 0:
            continue
        if throttle != 100.0 or brake != 0.0:
            continue
        if gear_raw in (None, "", "0"):
            continue
        try:
            gear = int(float(gear_raw))
        except (TypeError, ValueError):
            continue
        if gear == 0:
            continue

        if i > 0:
            prev_row = car_rows[i - 1]
            prev_rpm = to_float(prev_row.get("rpm"))
            prev_dt = parse_date(prev_row.get("date"))
            current_dt = parse_date(row.get("date"))
            if prev_rpm is not None and prev_dt is not None and current_dt is not None:
                dt_delta = (current_dt - prev_dt).total_seconds()
                if 0 < dt_delta <= 0.2 and (prev_rpm - rpm) > 500:
                    continue

        if i < len(car_rows) - 1:
            next_row = car_rows[i + 1]
            next_rpm = to_float(next_row.get("rpm"))
            next_dt = parse_date(next_row.get("date"))
            current_dt = parse_date(row.get("date"))
            if next_rpm is not None and next_dt is not None and current_dt is not None:
                dt_delta = (next_dt - current_dt).total_seconds()
                if 0 < dt_delta <= 0.2 and (next_rpm - rpm) < -500:
                    continue

        valid_rows.append(row)
    return valid_rows


def compute_engine_power_model(filtered_rows: List[Dict[str, str]], session_constants: Dict[str, Any]) -> List[Dict[str, Any]]:
    rho = session_constants.get("rho")
    model_rows: List[Dict[str, Any]] = []
    net_energy_mj = 0.0

    for idx, row in enumerate(filtered_rows):
        speed_kph = to_float(row.get("speed"))
        rpm = to_float(row.get("rpm"))
        if speed_kph is None or rpm is None:
            continue
        v_mps = speed_kph / 3.6
        omega_w = v_mps / R_WHEEL
        omega_e = (rpm * 2.0 * math.pi) / 60.0

        current_dt = parse_date(row.get("date"))
        prev_speed = None
        next_speed = None
        if idx > 0:
            prev_row = filtered_rows[idx - 1]
            prev_speed = to_float(prev_row.get("speed"))
        if idx < len(filtered_rows) - 1:
            next_row = filtered_rows[idx + 1]
            next_speed = to_float(next_row.get("speed"))

        if prev_speed is not None and next_speed is not None and idx > 0 and idx < len(filtered_rows) - 1:
            a = (next_speed / 3.6 - prev_speed / 3.6) / (2.0)
        elif prev_speed is not None:
            a = (speed_kph / 3.6 - prev_speed / 3.6) / 1.0
        elif next_speed is not None:
            a = (next_speed / 3.6 - speed_kph / 3.6) / 1.0
        else:
            a = 0.0

        f_drag = 0.5 * rho * session_constants["cda"] * (v_mps ** 2)
        f_rr = ROLLING_RESISTANCE_COEFF * CAR_MASS_KG * 9.81
        f_inert = CAR_MASS_KG * a
        p_w = (f_drag + f_rr + f_inert) * v_mps
        t_total = p_w / (omega_e * ETA_DRIVETRAIN)

        p_mgu_max = 7100.0 - 20.0 * speed_kph
        if speed_kph > 355.0:
            p_mgu_max = 0.0
        p_mgu_max = min(max(p_mgu_max, 0.0), 350.0)
        t_mgu = (p_mgu_max * 1000.0) / omega_e
        t_mgu = max(-500.0, min(500.0, t_mgu))
        t_ice = t_total - t_mgu

        ef_max = min(3000.0, 0.27 * rpm + 165.0)
        p_ice_max_kw = (ef_max / 3.6) * ETA_THERMAL
        t_ice_max = (p_ice_max_kw * 1000.0) / omega_e
        if t_ice > t_ice_max:
            t_ice = t_ice_max

        if idx > 0:
            prev_dt = parse_date(filtered_rows[idx - 1].get("date"))
            if prev_dt is not None and current_dt is not None:
                dt_seconds = (current_dt - prev_dt).total_seconds()
                if dt_seconds > 0:
                    net_energy_mj += (max(p_mgu_max, 0.0) * 1000.0 * dt_seconds) / 3_600_000_000.0

        row_result = {
            "date": row.get("date"),
            "speed": speed_kph,
            "rpm": rpm,
            "n_gear": row.get("n_gear"),
            "throttle": row.get("throttle"),
            "brake": row.get("brake"),
            "omega_e": omega_e,
            "accel": a,
            "P_w": p_w,
            "T_total": t_total,
            "P_MGU": p_mgu_max * 1000.0,
            "T_MGU": t_mgu,
            "T_ICE_capped": t_ice,
            "EF_max": ef_max,
            "net_energy": net_energy_mj,
        }
        model_rows.append(row_result)

    return model_rows


def save_summary_csv(summary_outputs: Dict[str, Any], output_dir: str = "outputs", filename: str = "cda_and_vehicle_parameters_results.csv") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / filename

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Parameter Name", "Value"])
        for label, value in summary_outputs.items():
            if isinstance(value, float):
                if math.isnan(value):
                    writer.writerow([label, "N/A"])
                else:
                    writer.writerow([label, format(value, ".12g")])
            else:
                writer.writerow([label, value])
    return out_path


def save_detailed_csv(model_rows: List[Dict[str, Any]], output_dir: str = "outputs", filename: str = "engine_power_model_results.csv") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / filename

    fieldnames = [
        "date",
        "speed",
        "rpm",
        "n_gear",
        "throttle",
        "brake",
        "omega_e",
        "accel",
        "P_w",
        "T_total",
        "P_MGU",
        "T_MGU",
        "T_ICE_capped",
        "EF_max",
        "net_energy",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in model_rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return out_path


def print_table(results: Dict[str, Any]) -> None:
    max_label_width = max(len(label) for label in results)
    for label, value in results.items():
        if isinstance(value, float):
            if math.isnan(value):
                display = "N/A"
            else:
                display = f"{value:.6f}"
        else:
            display = str(value)
        print(f"{label:<{max_label_width}} | {display}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute F1 CdA summary and engine power model.")
    parser.add_argument("--data-dir", type=str, default="inputs", help="Directory containing the input CSV files")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["requirement1", "both"],
        default="both",
        help="Select 'requirement1' to run only the CdA/session requirement, or 'both' to run both requirements (default).",
    )
    args = parser.parse_args()

    input_data = load_inputs(data_dir=args.data_dir)
    session_constants = compute_session_constants(input_data)

    if args.mode == "requirement1":
        cda_summary = compute_cda_summary(session_constants)
        summary_outputs = cda_summary["outputs"]
        mass_check = cda_summary["mass_check"]

        print("F1 CdA & Vehicle Parameters")
        print("=" * 30)
        print_table(summary_outputs)

        print("\nMass Validation Check")
        print("-" * 30)
        print(f"F_trac = {mass_check['F_trac']:.6f} N")
        print(f"F_drag = {mass_check['F_drag']:.6f} N")
        print(f"C_rr_calculated = {mass_check['C_rr_calculated']:.6f}")

        save_summary_csv(summary_outputs)
        print(f"\nCSV summary written to: outputs/cda_and_vehicle_parameters_results.csv")
        return

    cda_summary = compute_cda_summary(session_constants)
    summary_outputs = cda_summary["outputs"]
    mass_check = cda_summary["mass_check"]

    print("F1 CdA & Vehicle Parameters")
    print("=" * 30)
    print_table(summary_outputs)

    print("\nMass Validation Check")
    print("-" * 30)
    print(f"F_trac = {mass_check['F_trac']:.6f} N")
    print(f"F_drag = {mass_check['F_drag']:.6f} N")
    print(f"C_rr_calculated = {mass_check['C_rr_calculated']:.6f}")

    save_summary_csv(summary_outputs)
    print(f"\nCSV summary written to: outputs/cda_and_vehicle_parameters_results.csv")

    filtered_rows = filter_valid_rows(input_data["car_data"])
    detailed_rows = compute_engine_power_model(filtered_rows, session_constants)
    detail_path = save_detailed_csv(detailed_rows)
    print(f"Detailed power model CSV written to: {detail_path}")


if __name__ == "__main__":
    main()
