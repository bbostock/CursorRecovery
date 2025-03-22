# Step 4
# # extract_ai_requests.py v2.3
# Extracts AI requests from the full_composer_blob.json file into text format
# timeline file. Search through the file for Date/Time Stamps and use these to
# find the equivalent file changes in /History.
# Usage: python3 step_4.py

import json
from datetime import datetime
import os

input_path = os.path.expanduser("~/CursorRecovery/Extracted/full_composer_blob_decoded.json")
output_path = os.path.expanduser("~/CursorRecovery/ai_request_timeline.txt")

print("🚀 Running extract_ai_requests.py v2.3")

if not os.path.exists(input_path):
    print(f"❌ File not found: {input_path}")
    exit(1)

try:
    with open(input_path, "r") as f:
        data = json.load(f)

    requests = []

    if "conversation" in data and isinstance(data["conversation"], list):
        for entry in data["conversation"]:
            if not isinstance(entry, dict):
                continue

            text = entry.get("text", "").strip()
            ts = None

            # Look for timestamp
            if "timingInfo" in entry:
                ts = entry["timingInfo"].get("clientStartTime")
            elif "timestamp" in entry:
                ts = entry.get("timestamp")

            # Convert timestamp
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(str(ts)[:13]) / 1000)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = "(invalid timestamp)"
            else:
                time_str = "(no timestamp)"

            if text:
                requests.append(f"[{time_str}] {text}")

    if requests:
        with open(output_path, "w") as out:
            out.write("\n\n".join(requests))
        print(f"✅ Extracted {len(requests)} AI request(s) → {output_path}")
    else:
        print("⚠️ No AI requests found.")

except Exception as e:
    print(f"❌ Error parsing JSON: {e}")