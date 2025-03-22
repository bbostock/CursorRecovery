# STEP 3
# decode_bob.py v2.1
# Decodes the full_composer_blob.bin file into a JSON file.
# Usage: python3 step_3.py
#

import os
import json

blob_path = os.path.expanduser("~/CursorRecovery/Extracted/full_composer_blob.bin")
output_path = os.path.expanduser("~/CursorRecovery/Extracted/full_composer_blob_decoded.json")

print("🚀 Running decode_blob.py v1.0")

with open(blob_path, "rb") as f:
    raw_data = f.read()

try:
    # Decode UTF-8 bytes to string
    text = raw_data.decode("utf-8")

    # Optional: parse it to confirm it's valid JSON
    json_obj = json.loads(text)

    # Save it as pretty JSON
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(json_obj, out, indent=2, ensure_ascii=False)

    print(f"✅ Decoded JSON written to: {output_path}")

except Exception as e:
    print(f"❌ Error decoding JSON: {e}")