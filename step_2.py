# STEP 2
# extract_full_composer_blob.py v1.3
# Copies the largest composerData blob from the Cursor database to a binary file.
# Usage: python3 step_2.py
# Extracts all large composerData blobs (>2KB) from the Cursor database

import os
import sqlite3
from pathlib import Path

print("🚀 Running extract_large_composer_blobs.py v2.1")

# Correct and original path (unchanged!)
db_path = os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
output_dir = os.path.expanduser("~/CursorRecovery/Extracted")
min_size = 2048  # Minimum blob size in bytes

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

try:
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.text_factory = bytes
    cursor = conn.cursor()

    cursor.execute("""
        SELECT key, value
        FROM cursorDiskKV
        WHERE key LIKE 'composerData:%'
    """)

    count = 0

    for key, value in cursor.fetchall():
        if isinstance(key, bytes):
            key = key.decode("utf-8")

        if isinstance(value, bytes) and len(value) >= min_size:
            safe_key = key.replace(":", "_")
            output_path = os.path.join(output_dir, f"{safe_key}.bin")
            with open(output_path, "wb") as f:
                f.write(value)

            print(f"✅ Saved {safe_key} ({len(value)} bytes) → {output_path}")
            count += 1

    if count == 0:
        print(f"⚠️ No composerData blobs over {min_size} bytes found.")
    else:
        print(f"\n📦 Done! {count} large composerData blobs saved to:\n{output_dir}")

except Exception as e:
    print(f"❌ Error: {e}")
finally:
    conn.close()