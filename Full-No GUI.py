import os
import glob
import pandas as pd
from math import exp
import requests
import json
from datetime import datetime
import calendar
import csv
from io import BytesIO
from PIL import Image

# OpenWeather API Key (replace with your own if needed)
OPENWEATHER_API_KEY = ""

### API Fetching Functions
def fetch_api(url, params=None):
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {url} - {e}")
    except requests.exceptions.JSONDecodeError:
        print(f"⚠️ JSON parsing failed: {url}")
    return None

def get_alternative_precipitation(lat, lon, start_date, end_date):
    start_date_alt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    end_date_alt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date_alt,
        "end_date": end_date_alt,
        "daily": "precipitation_sum",
        "timezone": "auto"
    }
    response = fetch_api(url, params)
    if response and "daily" in response and "precipitation_sum" in response["daily"]:
        precip_values = response["daily"]["precipitation_sum"]
        if precip_values:
            return sum(precip_values)
    return "No data"

def get_climate_data(lat, lon, month, year, max_years_back=5):
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    adjusted_year = year
    while adjusted_year > current_year or (adjusted_year == current_year and month > current_month):
        print(f"Adjusting future date {month}/{year} to {month}/{adjusted_year - 1}.")
        adjusted_year -= 1
    attempts = 0
    while attempts < max_years_back:
        first_day = 1
        last_day = calendar.monthrange(adjusted_year, month)[1]
        start_date = datetime(adjusted_year, month, first_day).strftime("%Y%m%d")
        end_date = datetime(adjusted_year, month, last_day).strftime("%Y%m%d")
        print(f"Fetching NASA POWER data for {start_date} to {end_date}...")
        params = {
            "parameters": "T2M,PRECTOT",
            "community": "RE",
            "longitude": lon,
            "latitude": lat,
            "start": start_date,
            "end": end_date,
            "format": "JSON"
        }
        climate_response = fetch_api("https://power.larc.nasa.gov/api/temporal/daily/point", params)
        if (climate_response and "properties" in climate_response and 
            "parameter" in climate_response["properties"]):
            parameters = climate_response["properties"]["parameter"]
            t2m_data = parameters.get("T2M", {})
            prectot_data = parameters.get("PRECTOT", {})
            valid_t2m = [v for v in t2m_data.values() if v != -999.0]
            valid_prectot = [v for v in prectot_data.values() if v != -999.0]
            avg_t2m = sum(valid_t2m) / len(valid_t2m) if valid_t2m else "No data"
            if valid_prectot:
                total_prectot = sum(valid_prectot)
            else:
                print("NASA precipitation missing; trying Open-Meteo...")
                total_prectot = get_alternative_precipitation(lat, lon, start_date, end_date)
            if avg_t2m != "No data" or total_prectot != "No data":
                return {
                    "Date Range": f"{start_date} to {end_date}",
                    "Average Temperature (T2M)": avg_t2m,
                    "Total Precipitation (PRECTOT)": total_prectot
                }
        adjusted_year -= 1
        attempts += 1
    return {"Error": f"No climate data for month {month} in past {max_years_back} years from {year}."}

def get_weather_data(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }
    return fetch_api(url, params)

def get_soil_data(lat, lon, depth="0-5cm"):
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    properties = ["phh2o", "soc", "clay", "silt", "sand", "cec", "cfvo"]
    soil_data = {}
    for prop in properties:
        params = {
            "lat": lat,
            "lon": lon,
            "property": prop,
            "depth": depth,
            "value": "mean"
        }
        response = fetch_api(url, params)
        if response and "features" in response and len(response["features"]) > 0:
            soil_data[prop] = response["features"][0]["properties"].get(prop, {}).get(depth, {}).get("mean", None)
        else:
            soil_data[prop] = None
    return soil_data

def get_terrain_data(lat, lon):
    url = "https://api.opentopodata.org/v1/srtm90m"
    params = {"locations": f"{lat},{lon}"}
    return fetch_api(url, params)

### Data Collection and CSV Handling
def get_location_info(lat, lon, month, year):
    report = {}
    report["Climate Data"] = get_climate_data(lat, lon, month, year)
    weather_response = get_weather_data(lat, lon)
    if weather_response and "main" in weather_response:
        main = weather_response["main"]
        report["Weather Data"] = {
            "Location": weather_response.get("name", "Unknown"),
            "Temperature": main.get("temp", "No data"),
            "Humidity": main.get("humidity", "No data"),
            "Pressure": main.get("pressure", "No data")
        }
    else:
        report["Weather Data"] = "No weather data retrieved."
    soil_response = get_soil_data(lat, lon)
    report["Soil Data (Depth 0-5cm)"] = soil_response if soil_response else "No soil data retrieved."
    terrain_response = get_terrain_data(lat, lon)
    if terrain_response and "results" in terrain_response and len(terrain_response["results"]) > 0:
        elevation = terrain_response["results"][0].get("elevation", "No data")
        report["Elevation Data"] = {"Elevation (meters)": elevation}
    else:
        report["Elevation Data"] = "No elevation data retrieved."
    return report

def export_report_to_csv(report, filepath='/Users/michael_z/Downloads/location_data_report.csv'):
    try:
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Section', 'Key', 'Value'])
            for section, data in report.items():
                if isinstance(data, dict):
                    for key, value in data.items():
                        value = '' if value is None else str(value)
                        writer.writerow([section, key, value])
                else:
                    writer.writerow([section, '', str(data)])
        print(f"Successfully exported report to {filepath}")
    except Exception as e:
        print(f"Error exporting report: {e}")

def read_report_from_csv(filepath='/Users/michael_z/Downloads/location_data_report.csv'):
    report = {}
    try:
        with open(filepath, 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header
            for row in reader:
                section, key, value = row
                if section not in report:
                    report[section] = {}
                if key:
                    report[section][key] = value if value else None
                else:
                    report[section] = value if value else None
    except Exception as e:
        print(f"Error reading CSV: {e}")
    return report

### Crop Recommendation Logic
def load_local_crop_datasets(folder_path):
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    if not csv_files:
        print(f"No CSV files found in {folder_path}")
        return None
    dfs = [pd.read_csv(file) for file in csv_files if not pd.read_csv(file).empty]
    if not dfs:
        return None
    df_combined = pd.concat(dfs, ignore_index=True)
    print(f"Combined DataFrame shape: {df_combined.shape}")
    return df_combined

def export_plant_counts(df, folder_path):
    total_plants = len(df)
    group_col = next((col for col in ['label', 'crop', 'common_name', 'plant_name'] if col in df.columns), None)
    if not group_col:
        raise KeyError(f"No suitable column found in {list(df.columns)}")
    counts = df[group_col].value_counts().to_dict()
    output_file = os.path.join(folder_path, "plant_count.txt")
    with open(output_file, "w") as f:
        f.write(f"Total number of plant rows: {total_plants}\n")
        f.write("Counts per crop:\n")
        for crop, count in counts.items():
            f.write(f"{crop}: {count}\n")
    print(f"Plant counts exported to {output_file}")

def compute_optimal_conditions(df):
    group_col = next((col for col in ['label', 'crop', 'common_name', 'plant_name'] if col in df.columns), None)
    if not group_col:
        raise KeyError(f"No suitable column found in {list(df.columns)}")
    groups = df.groupby(group_col)
    optimal = {
        crop: {
            'T_opt': group['Temperature'].mean(),
            'H_opt': group['Humidity'].mean(),
            'pH_opt': group['pH'].mean(),
            'AP_opt': group['Rainfall'].mean()
        }
        for crop, group in groups
    }
    return optimal

def plant_fitness(sensor, optimal, sigmas, weights):
    T_opt = optimal['T_opt']
    H_opt = optimal['H_opt']
    pH_opt = optimal['pH_opt']
    AP_opt = optimal['AP_opt']
    P_opt = 1013
    T_avg_opt = T_opt
    diff_T = (sensor['T'] - T_opt)**2 / (2 * sigmas['sigma_T']**2)
    diff_H = (sensor['H'] - H_opt)**2 / (2 * sigmas['sigma_H']**2)
    diff_P = (sensor['P'] - P_opt)**2 / (2 * sigmas['sigma_P']**2)
    diff_Tavg = (sensor['T_avg'] - T_avg_opt)**2 / (2 * sigmas['sigma_Tavg']**2)
    diff_AP = (sensor['AP'] - AP_opt)**2 / (2 * sigmas['sigma_AP']**2)
    diff_pH = (sensor['pH'] - pH_opt)**2 / (2 * sigmas['sigma_pH']**2)
    exponent = (weights['w_T'] * diff_T +
                weights['w_H'] * diff_H +
                weights['w_P'] * diff_P +
                weights['w_Tavg'] * diff_Tavg +
                weights['w_AP'] * diff_AP +
                weights['w_pH'] * diff_pH)
    return exp(-exponent)

def get_sensor_data_from_report(report):
    sensor_data = {}
    keys = {
        'T': ('Weather Data', 'Temperature'),
        'H': ('Weather Data', 'Humidity'),
        'P': ('Weather Data', 'Pressure'),
        'T_avg': ('Climate Data', 'Average Temperature (T2M)'),
        'AP': ('Climate Data', 'Total Precipitation (PRECTOT)'),
        'pH': ('Soil Data (Depth 0-5cm)', 'phh2o')
    }
    for key, (section, subkey) in keys.items():
        try:
            value = report.get(section, {}).get(subkey, None)
            sensor_data[key] = float(value) if value and value.strip() else None
        except (ValueError, TypeError):
            sensor_data[key] = None
    return sensor_data

def prompt_for_missing_data(sensor_data, prompts, valid_ranges):
    for key in sensor_data:
        if sensor_data[key] is None:
            while True:
                try:
                    answer = input(prompts[key])
                    val = float(answer)
                    min_val, max_val = valid_ranges[key]
                    if not (min_val <= val <= max_val):
                        print(f"Value {val} outside range ({min_val}, {max_val}). Please try again.")
                        continue
                    sensor_data[key] = val
                    break
                except (ValueError, TypeError):
                    print("Invalid input. Please enter a number.")
    return sensor_data

def recommend_crop(sensor_data, optimal_conditions, sigmas, weights):
    crop_fitness = {crop: plant_fitness(sensor_data, optimal, sigmas, weights)
                    for crop, optimal in optimal_conditions.items()}
    best_crop = max(crop_fitness, key=crop_fitness.get)
    return best_crop, crop_fitness[best_crop], crop_fitness

def look_at_image(optimal_crop):
    try:
        df_numbers = pd.read_csv('/Users/michael_z/Downloads/Plant Database/numbers_updated.csv')
    except Exception as e:
        print(f"Error: Failed to open CSV file: {e}")
        return
    row = df_numbers[df_numbers['plant_name'] == optimal_crop]
    if row.empty:
        print(f"Error: Plant '{optimal_crop}' not found in CSV.")
        return
    image_url = row.iloc[0].get('image_url')
    if pd.isnull(image_url) or not image_url:
        print(f"Error: No image URL for {optimal_crop}.")
        return
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        image_data = BytesIO(response.content)
        pil_image = Image.open(image_data)
    except Exception as e:
        print(f"Error: Failed to load image: {e}")
        return
    pil_image.show()

### Selection Process for Selective Mode
def select_plants():
    print("\n--- Selective Mode: Plant Selection ---")
    folder_path = '/Users/michael_z/Downloads/Plant Database'
    df = load_local_crop_datasets(folder_path)
    if df is None:
        print("Error: No crop data found for selection.")
        return []
    group_col = next((col for col in ['label', 'crop', 'common_name', 'plant_name'] if col in df.columns), None)
    all_plants = sorted(df[group_col].unique())
    selected = set()
    while True:
        query = input("Enter search query (or press ENTER to finish selection): ").strip().lower()
        if query == "":
            break
        matches = [plant for plant in all_plants if query in str(plant).lower()]
        if not matches:
            print("No matches found.")
            continue
        print("Matches:")
        for idx, plant in enumerate(matches):
            print(f"{idx}: {plant}")
        indices = input("Enter indices (comma separated) of plants to add: ").split(",")
        for idx in indices:
            try:
                idx = int(idx.strip())
                if 0 <= idx < len(matches):
                    selected.add(matches[idx])
                else:
                    print(f"Index {idx} out of range.")
            except ValueError:
                print(f"Invalid index: {idx}")
        print("Current selection:", ", ".join(selected))
        more = input("Do you want to perform another search? (y/n): ").strip().lower()
        if more != "y":
            break
    return list(selected)

### Main Command-Line Workflow
def main():
    print("=== Crop Recommendation System ===")
    # Mode selection
    mode = ""
    while mode not in ["1", "2"]:
        mode = input("Select mode: (1) Optimal Solution, (2) Selective Solution: ").strip()
    if mode == "1":
        solution_mode = "optimal"
        selected_plants = None
    else:
        solution_mode = "selective"
        selected_plants = select_plants()
        if not selected_plants:
            print("No plants selected; defaulting to optimal (all plants).")
            solution_mode = "optimal"
            selected_plants = None

    # Get location inputs
    try:
        lat = float(input("Enter latitude: "))
        lon = float(input("Enter longitude: "))
        month = int(input("Enter month (1-12): "))
        year = int(input("Enter year: "))
    except ValueError:
        print("Error: Please enter valid numeric values.")
        return

    # Fetch location data
    report = get_location_info(lat, lon, month, year)
    csv_path = '/Users/michael_z/Downloads/location_data_report.csv'
    export_report_to_csv(report, csv_path)
    report_from_csv = read_report_from_csv(csv_path)

    # Prompt for missing sensor data
    prompts = {
        'T': "Enter instantaneous temperature (°C): ",
        'H': "Enter ambient humidity (%): ",
        'P': "Enter atmospheric pressure (hPa): ",
        'T_avg': "Enter monthly average temperature (°C): ",
        'AP': "Enter total precipitation (mm): ",
        'pH': "Enter soil pH: "
    }
    valid_ranges = {
        'T': (-50, 60),
        'H': (0, 100),
        'P': (900, 1100),
        'T_avg': (-50, 60),
        'AP': (0, 1000),
        'pH': (0, 14)
    }
    sensor_data = get_sensor_data_from_report(report_from_csv)
    sensor_data = prompt_for_missing_data(sensor_data, prompts, valid_ranges)

    # Load crop dataset
    folder_path = '/Users/michael_z/Downloads/Plant Database'
    df = load_local_crop_datasets(folder_path)
    if df is None:
        print("Error: No crop data found.")
        return
    export_plant_counts(df, folder_path)
    # If selective mode, filter dataset based on selected plants
    if solution_mode == "selective" and selected_plants:
        group_col = next((col for col in ['label', 'crop', 'common_name', 'plant_name'] if col in df.columns), None)
        df = df[df[group_col].isin(selected_plants)]
        if df.empty:
            print("Error: No matching crop data found for the selected plants.")
            return

    # Compute optimal conditions and recommend crop
    optimal_conditions = compute_optimal_conditions(df)
    sigmas = {
        'sigma_T': 2.0,
        'sigma_H': 10.0,
        'sigma_P': 10.0,
        'sigma_Tavg': 2.0,
        'sigma_AP': 20.0,
        'sigma_pH': 0.5
    }
    weights = {
        'w_T': 0.35,
        'w_H': 0.30,
        'w_P': 0.05,
        'w_Tavg': 0.15,
        'w_AP': 0.10,
        'w_pH': 0.05
    }
    best_crop, best_fitness, _ = recommend_crop(sensor_data, optimal_conditions, sigmas, weights)
    print("\n=== Optimal Crop Recommendation ===")
    print(f"Recommended Crop: {best_crop} (Fitness Score: {best_fitness:.4f})")

    # Ask if user wants to view the image
    view = input("\nDo you want to view an image of the recommended plant? (y/n): ").strip().lower()
    if view == 'y':
        look_at_image(best_crop)
    else:
        print("Image viewing skipped.")

if __name__ == "__main__":
    main()
