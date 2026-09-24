# F1 Telemetry Analysis Project

This project reads Formula 1 telemetry data and calculates two main outputs:

1. Session-level vehicle values such as drag area (CdA), max speed, air density, gear ratios, and torque.
2. A detailed engine-power model based on the vehicle and environment conditions.

The project is designed to be simple to run, even for someone who is comfortable with telemetry data but not necessarily with Python programming.

Special thanks to RedKakusu on Discord for providing the initial project requirements and helping shape the direction of this analysis.

---

## What this project does

The script combines telemetry, weather, and location data to estimate:

- maximum speed of the session
- air density from pressure and temperature
- drag area (CdA)
- overall gear ratios
- engine torque at max speed
- wheel torque at max speed
- a detailed engine-power model under full-throttle conditions

This is based on the two handover specifications stored in the sources folder:

- CdA and vehicle parameters
- Engine power logic

---

## Project structure

The repository currently contains the following important items:

- [calculate_f1_telemetry.py](calculate_f1_telemetry.py)
  Main Python script that runs the analysis
- [inputs](inputs)
  Folder containing the CSV input files
- [outputs](outputs)
  Folder where result CSV files are written
- [sources](sources)
  Handover notes and engineering specification files
- [requirements.txt](requirements.txt)
  Python dependencies needed for the project

---

## Input files

The script expects the following files inside the [inputs](inputs) folder:

- [inputs/car_data.csv](inputs/car_data.csv)
- [inputs/weather.csv](inputs/weather.csv)
- [inputs/location.csv](inputs/location.csv)

### car_data.csv
This file contains the vehicle telemetry rows. It should include columns such as:

- date
- speed
- rpm
- n_gear
- throttle
- brake
- meeting_key
- session_key

### weather.csv
This file contains the weather conditions for the relevant session. It should include columns such as:

- date
- air_temperature
- pressure
- wind_speed
- wind_direction
- meeting_key
- session_key

### location.csv
This file contains the vehicle position data for calculating heading and wind-normalized direction. It should include:

- date
- x
- y

---

## Output files

When the script runs, it writes output files into the [outputs](outputs) folder.

### 1) Summary output
File:
- [outputs/cda_and_vehicle_parameters_results.csv](outputs/cda_and_vehicle_parameters_results.csv)

This file contains the session-level summary values, such as:

- CdA (m²)
- Max Speed (kph)
- Max Speed (m/s)
- Max RPM
- Max Gear
- Engine Torque at Max Speed (Nm)
- Wheel Torque at Max Speed (Nm)
- Overall Ratio at Max Speed
- Air Density (kg/m³)
- Gear 2 to Gear 8 overall ratios

This is the first requirement result.

### 2) Detailed engine-power output
File:
- [outputs/engine_power_model_results.csv](outputs/engine_power_model_results.csv)

This file contains the row-by-row engine power model output. It includes columns such as:

- date
- speed
- rpm
- n_gear
- throttle
- brake
- omega_e
- accel
- P_w
- T_total
- P_MGU
- T_MGU
- T_ICE_capped
- EF_max
- net_energy

This is the second requirement result.

The detailed file is useful for looking at how the model behaves over time rather than only at the maximum-speed point.

---

## How to run the project

Before running the analysis, create a Python virtual environment and install the project dependencies.

### 1) Create a virtual environment

```bash
cd /home/vishwa/my_files/f1_telemetry
python3 -m venv .venv
```

### 2) Activate the virtual environment

On Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3) Install the required Python packages

```bash
pip install -r requirements.txt
```

### 4) Run the project

After the environment is ready, run the script from the project folder:

```bash
python calculate_f1_telemetry.py
```

This runs the default mode, which executes both requirements:

- the first requirement: CdA and vehicle parameter calculation
- the second requirement: detailed engine-power model calculation

### Run only the first requirement

```bash
python calculate_f1_telemetry.py --mode requirement1
```

This creates only the summary output CSV.

> If you already have the virtual environment created, you can use:
>
> ```bash
> cd /home/vishwa/my_files/f1_telemetry
> source .venv/bin/activate
> python calculate_f1_telemetry.py
> ```

---

## Understanding the script flow

The script is organized in a simple workflow:

1. Load the CSV files from the [inputs](inputs) folder
2. Find the highest-speed row in the car telemetry
3. Match the relevant weather and location records by time
4. Compute the weather-corrected air density and drag area
5. Calculate gear ratios and max-speed vehicle values
6. Filter rows that are valid for the full-power engine model
7. Calculate the engine-power metrics row by row
8. Save the results into the [outputs](outputs) folder

---

## Why the inputs matter

The analysis depends on having clean, time-aligned data. If the data is missing or the timestamps are not aligned properly, the results may be wrong.

Important things to check:

- dates are in a valid format
- speed values are numeric
- rpm values are numeric
- location data exists for the same session window
- weather data is matched to the same meeting/session

---

## Simple interpretation of the results

### Summary values
These are the headline values for the session:

- CdA: how much aerodynamic drag the car experiences
- Max speed: the peak speed reached in the telemetry
- Air density: how dense the air is for that session
- Gear ratios: how the drivetrain is arranged at different gears

### Detailed engine-power values
These are more technical values for each full-power telemetry row:

- omega_e: engine rotational speed in rad/s
- accel: acceleration estimate
- P_w: wheel tractive power
- T_total: total crankshaft torque
- P_MGU: electrical power available from the MGU-K
- T_MGU: torque delivered by the MGU-K
- T_ICE_capped: final ICE torque after regulation limits are applied
- EF_max: maximum fuel energy flow for the RPM point
- net_energy: cumulative energy balance over the lap

---

## Important notes

- The project uses sample telemetry data by default, so it works even before real race data is added.
- Real F1 data may have more columns and more detailed timings.
- The code is intentionally simple and readable so it can be extended later.
- The output is saved as CSV for easy viewing in Excel, Google Sheets, or Python/pandas tools.

---

## Common contributor checklist

Before running the script, check:

- the CSV files are in [inputs](inputs)
- the CSV columns match the expected names
- the script is being run from the project root
- the outputs folder exists or gets created automatically

---

## Quick start summary

```bash
cd /home/vishwa/my_files/f1_telemetry
.venv/bin/python calculate_f1_telemetry.py
```

Then open the generated result files in [outputs](outputs).

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Final note

This project is meant to be an engineering workflow for telemetry analysis, not a complicated software package. The goal is to make the data process clear, repeatable, and easy to inspect.
