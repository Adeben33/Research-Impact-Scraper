import json
import shutil
import os

# File path
file_path = '/Users/adeben/Desktop/researchImpact/AI4PEP/zahra_movahedi_nia/impact_metrics.json'
backup_path = file_path.replace('.json', '_backup.json')

# Step 1: Backup
if os.path.abspath(file_path) != os.path.abspath(backup_path):
    shutil.copy(file_path, backup_path)
    print(f"Backup created at '{backup_path}'")
else:
    print("Backup skipped: source and destination are the same.")

# Step 2: Load JSON
with open(file_path, 'r') as f:
    data = json.load(f)

# Step 3: Safe year conversion
def safe_year(entry):
    try:
        return int(entry.get("Year", 0))
    except (ValueError, TypeError):
        return 0

# Step 4: Filter entries
filtered_data = [entry for entry in data if safe_year(entry) >= 2024]

# Step 5: Save filtered data
with open(file_path, 'w') as f:
    json.dump(filtered_data, f, indent=2)

print(f"Filtered {len(filtered_data)} entries with Year >= 2024 in '{file_path}'.")