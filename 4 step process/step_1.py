# STEP 1
# # organize_cursor_history.py v1.7
# Copies the Cursor history files into a more organized structure based on the date/time of the history file.
# Usage: python3 step_1.py
import os
import shutil
import json
import time
from datetime import datetime, timezone

VERSION = "1.7"

# Path to the Cursor history directory
import os

HISTORY_ROOT = os.path.expanduser("~/Library/Application Support/Cursor/User/History/")
OUTPUT_ROOT = os.path.expanduser("~/CursorRecovery")
OUTPUT_ROOT_ORGANIZED = os.path.join(OUTPUT_ROOT, "Organized")

print(f"\n🚀 Running organize_cursor_history.py v{VERSION}\n")
print(f"🔍 Checking history folder: {HISTORY_ROOT}")

# Ensure output directories exists
os.makedirs(OUTPUT_ROOT, exist_ok=True)
os.makedirs(OUTPUT_ROOT_ORGANIZED, exist_ok=True)

# Iterate over each history folder
for folder_name in os.listdir(HISTORY_ROOT):
    folder_path = os.path.join(HISTORY_ROOT, folder_name)

    if not os.path.isdir(folder_path):
        continue  # Skip non-directory items

    json_file = os.path.join(folder_path, "entries.json")

    if not os.path.exists(json_file):
        continue  # Skip folders without entries.json

    print(f"\n📄 Found entries.json in: {folder_path}")

    # Load JSON data
    with open(json_file, "r") as f:
        data = json.load(f)

    if "resource" not in data or "entries" not in data or not data["entries"]:
        print(f"⚠️ Skipping {folder_name} (No valid entries)")
        continue

    # Extract correct filename from `resource`
    resource_path = data["resource"]
    correct_filename = os.path.basename(resource_path)  # Extract filename only

    # Process each file version separately
    for entry in data["entries"]:
        original_filename = entry.get("id")  # e.g., "merm.swift"
        timestamp = entry.get("timestamp")

        if not original_filename or not timestamp:
            continue  # Skip invalid entries

        original_path = os.path.join(folder_path, original_filename)

        if not os.path.exists(original_path):
            print(f"❌ Missing expected file: {original_path}")
            continue

        # Generate unique timestamp for each file
        timestamp_str = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Target folder for this file's specific timestamp
        target_folder = os.path.join(OUTPUT_ROOT_ORGANIZED, timestamp_str)
        os.makedirs(target_folder, exist_ok=True)

        # Final destination path
        new_path = os.path.join(target_folder, correct_filename)

        # Prevent duplicate filenames in the same timestamp folder
        counter = 1
        while os.path.exists(new_path):
            name_part, ext = os.path.splitext(correct_filename)
            new_path = os.path.join(target_folder, f"{name_part}.{counter}{ext}")
            counter += 1

        # Copy the file while preserving timestamps
        shutil.copy2(original_path, new_path)

        print(f"✅ Copied {original_filename} → {os.path.basename(new_path)} in {target_folder}")

print("\n✅ Done! Organized history saved in:", OUTPUT_ROOT_ORGANIZED)
print("\n📂 Start with the folder whose date/time matches your last known good code.")
print("🔍 Compare each file with your current version.")
print("📋 Copy any recovered code you need into your working files.")
print("🔁 Work backwards through earlier folders to find the last good version of each file.")
print("🧩 Only copy the most recent good version of each file.")
print("💾 If you're unsure when your last good save was, run step_2.py to begin extracting and reviewing version history.")