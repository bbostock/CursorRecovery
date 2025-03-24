# cursor_recovery_ui.py v5.0
# Cursor Recovery Tool with proper history mapping and file recovery

import os
import json
import sqlite3
import tempfile
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timezone
import time
import subprocess

# Paths
DB_PATH = os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
DB_PATH_BACKUP = os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb.backup")
HISTORY_PATH = os.path.expanduser("~/Library/Application Support/Cursor/User/History/")
ORGANIZED_HISTORY = os.path.expanduser("~/CursorRecovered/_organized_history")
FINAL_RECOVERY = os.path.expanduser("~/CursorRecovered/final")

os.makedirs(ORGANIZED_HISTORY, exist_ok=True)
os.makedirs(FINAL_RECOVERY, exist_ok=True)

# --- STEP 1: Extract Largest Blob from DB ---
def extract_largest_blob_to_temp_json(use_backup=False):
    try:
        db_path = DB_PATH_BACKUP if use_backup else DB_PATH
        print(f"\n🔍 Opening database: {db_path}")
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.text_factory = bytes
        cursor = conn.cursor()

        cursor.execute("""
            SELECT key, LENGTH(value) as size
            FROM cursorDiskKV
            WHERE key LIKE 'composerData:%'
            ORDER BY size DESC
            LIMIT 1;
        """)
        row = cursor.fetchone()
        if not row:
            raise Exception("No composerData blobs found")

        key, size = row
        if isinstance(key, bytes):
            key = key.decode("utf-8")

        print(f"📦 Found largest blob: {key} ({size} bytes)")
        cursor.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (key,))
        blob_row = cursor.fetchone()
        if not blob_row:
            raise Exception("Failed to fetch blob data")

        blob = blob_row[0]
        if not isinstance(blob, bytes):
            raise Exception("Blob was not returned as bytes")

        decoded = blob.decode("utf-8")
        temp_path = os.path.join(tempfile.gettempdir(), "full_composer_blob_decoded.json")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(decoded)
        return temp_path
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
    finally:
        conn.close()

# --- Organize History ---
def organize_history_folders(project_name=None):
    print("\n🗃️ Organizing History folders...")
    if not os.path.exists(HISTORY_PATH):
        print("⚠️ History path does not exist.")
        return

    # Clear the organized history folder first
    if os.path.exists(ORGANIZED_HISTORY):
        shutil.rmtree(ORGANIZED_HISTORY)
    os.makedirs(ORGANIZED_HISTORY)

    # Iterate over each history folder
    for folder_name in os.listdir(HISTORY_PATH):
        folder_path = os.path.join(HISTORY_PATH, folder_name)

        if not os.path.isdir(folder_path):
            continue  # Skip non-directory items

        json_file = os.path.join(folder_path, "entries.json")

        if not os.path.exists(json_file):
            continue  # Skip folders without entries.json

        print(f"\n📄 Processing folder: {folder_name}")

        try:
            # Load JSON data
            with open(json_file, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict) or "resource" not in data or "entries" not in data:
                print(f"⚠️ Invalid JSON structure in {folder_name}")
                continue

            # Check if resource path contains project name
            resource_path = data["resource"]
            if project_name and project_name.lower() not in resource_path.lower():
                print(f"⏭️ Skipping {folder_name} (not part of project {project_name})")
                continue
            correct_filename = os.path.basename(resource_path)

            # Process each file version
            for entry in data["entries"]:
                if not isinstance(entry, dict):
                    continue

                original_filename = entry.get("id")
                timestamp = entry.get("timestamp")

                if not original_filename or not timestamp:
                    continue

                original_path = os.path.join(folder_path, original_filename)
                if not os.path.exists(original_path):
                    print(f"❌ Missing file: {original_path}")
                    continue

                # Convert timestamp to folder name
                timestamp_str = datetime.fromtimestamp(
                    timestamp / 1000, 
                    tz=timezone.utc
                ).strftime("%Y%m%d_%H%M%S")

                # Create timestamp-based folder
                target_folder = os.path.join(ORGANIZED_HISTORY, timestamp_str)
                os.makedirs(target_folder, exist_ok=True)

                # Set up target path with original filename
                target_path = os.path.join(target_folder, correct_filename)

                # Handle duplicates with numbering
                counter = 1
                while os.path.exists(target_path):
                    base, ext = os.path.splitext(correct_filename)
                    target_path = os.path.join(target_folder, f"{base}.{counter}{ext}")
                    counter += 1

                # Copy the file with metadata preserved
                shutil.copy2(original_path, target_path)
                print(f"✅ {original_filename} → {os.path.basename(target_path)}")

        except Exception as e:
            print(f"❌ Error processing {folder_name}: {str(e)}")
            continue

    print(f"\n✅ History organized in: {ORGANIZED_HISTORY}")

# --- STEP 2: Recovery Logic ---
def recover_files_up_to(recovery_time):
    seen_files = {}  # Change to dict to track latest timestamp for each file
    count = 0
    print("\n✅ Starting Recovery with target date/time: ", recovery_time)

    # First pass: Find the most recent version of each file before recovery_time
    for folder_name in sorted(os.listdir(ORGANIZED_HISTORY), reverse=True):
        try:
            folder_dt = datetime.strptime(folder_name, "%Y%m%d_%H%M%S")
        except ValueError:
            print(f"⚠️ Skipping invalid folder: {folder_name}")
            continue

        if folder_dt > recovery_time:
            print(f"⏭️ Skipping future folder: {folder_name}")
            continue

        folder_path = os.path.join(ORGANIZED_HISTORY, folder_name)
        
        # Look for files directly in the folder
        for file_name in os.listdir(folder_path):
            if file_name == "entries.json":
                continue
                
            file_path = os.path.join(folder_path, file_name)
            if os.path.isfile(file_path):
                # Only store if we haven't seen this file before (since we're going newest to oldest)
                if file_name not in seen_files:
                    seen_files[file_name] = {
                        'path': file_path,
                        'timestamp': folder_dt
                    }
                    print(f"📄 Found version of {file_name} from {folder_dt}")

    # Second pass: Copy the most recent version of each file
    for file_name, info in seen_files.items():
        source_path = info['path']
        target_path = os.path.join(FINAL_RECOVERY, file_name)
        
        if os.path.exists(source_path):
            shutil.copy2(source_path, target_path)
            count += 1
            print(f"✅ Recovered: {file_name} (from {info['timestamp']})")
        else:
            print(f"❌ Source file missing: {source_path}")

    return count


# --- UI ---
class RecoveryApp:
    def __init__(self, root):
        self.root = root
        root.title("Cursor Chat Recovery")
        root.geometry("1100x700")

        # Add database choice frame
        self.db_frame = ttk.Frame(root)
        self.db_frame.pack(fill=tk.X, pady=5, padx=10)
        
        self.use_backup = tk.BooleanVar(value=False)
        self.backup_checkbox = ttk.Checkbutton(
            self.db_frame, 
            text="Use Backup Database", 
            variable=self.use_backup
        )
        self.backup_checkbox.pack(side=tk.LEFT)

        # Add Load Database button
        self.load_button = ttk.Button(
            self.db_frame,
            text="Load Database",
            command=self.load_data
        )
        self.load_button.pack(side=tk.LEFT, padx=10)

       # Add project name frame
        self.project_frame = ttk.Frame(root)
        self.project_frame.pack(fill=tk.X, pady=10, padx=10)
        
        self.project_label = ttk.Label(self.project_frame, text="Project Name:")
        self.project_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.project_entry = ttk.Entry(self.project_frame)
        self.project_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.results_frame = ttk.Frame(root)
        self.results_frame.pack(fill=tk.BOTH, expand=True)

        self.scrollbar = ttk.Scrollbar(self.results_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Add Text widget configuration for highlighting
        self.results_text = tk.Text(self.results_frame, yscrollcommand=self.scrollbar.set, wrap=tk.WORD)
        self.results_text.pack(fill=tk.BOTH, expand=True)
        self.results_text.tag_configure("highlight", background="yellow")
        self.scrollbar.config(command=self.results_text.yview)
        
        # Track the current highlight
        self.current_highlight = None
        
        # Bind click event to text widget
        self.results_text.bind("<Button-1>", self.handle_click)

         # Update recover button to be disabled initially
        self.recover_button = ttk.Button(
            root,
            text="Recover Files",
            command=self.recover_files,
            state="disabled"  # Initially disabled
        )
        self.recover_button.pack(pady=10)

    def handle_click(self, event):
        # Get clicked line
        index = self.results_text.index(f"@{event.x},{event.y}")
        linestart = self.results_text.index(f"{index} linestart")
        lineend = self.results_text.index(f"{index} lineend")
        line = self.results_text.get(linestart, lineend)
        
        # Check if clicked line contains a timestamp
        if "🕓" in line:
            # Remove previous highlight
            if self.current_highlight:
                self.results_text.tag_remove("highlight", *self.current_highlight)
            
            # Add new highlight
            next_lineend = self.results_text.index(f"{lineend} +1 line")
            self.current_highlight = (linestart, next_lineend)
            self.results_text.tag_add("highlight", *self.current_highlight)

    def load_data(self):
        print("📥 Extracting conversation from largest blob...")
        temp_json = extract_largest_blob_to_temp_json(self.use_backup.get())
        if not temp_json:
            print("❌ No data extracted.")
            messagebox.showerror("Error", "No data could be extracted from the database")
            return


        with open(temp_json, "r", encoding="utf-8") as f:
            try:
                self.raw_data = json.load(f)
            except json.JSONDecodeError as e:
                print("❌ JSON decode error:", e)
                return

        self.entries = []
        last_valid_ts = None
        convo = self.raw_data.get("conversation", [])

        for i, item in enumerate(convo):
            if not isinstance(item, dict):
                continue

            text = item.get("text", "").strip()
            if not text:
                continue

            timing_info = item.get("timingInfo", {})
            ts = timing_info.get("clientStartTime") or timing_info.get("clientRpcSendTime")
            if ts:
                dt = datetime.fromtimestamp(ts / 1000)
                formatted_time = dt.strftime("%Y%m%d %H%M%S")
                last_valid_ts = formatted_time
            else:
                formatted_time = last_valid_ts or "(No Time)"

            speaker = "👤 You" if item.get("type") == 1 else "🤖 AI"
            self.entries.append((formatted_time, f"{speaker}: {text}", item))

        self.entries.sort(key=lambda x: x[0], reverse=True)
        self.display_entries()
        
        # Enable recover button after successful load
        self.recover_button.config(state="normal")
        messagebox.showinfo("Success", "Database loaded successfully")

    def display_entries(self):
        self.results_text.delete(1.0, tk.END)
        self.current_highlight = None  # Reset highlight
        for ts, line, _ in self.entries:
            self.results_text.insert(tk.END, f"🕓 {ts}\n{line}\n\n")

    def recover_files(self):
        # Get highlighted timestamp if any
        if self.current_highlight:
            line = self.results_text.get(*self.current_highlight).split('\n')[0]
            timestamp_str = line.replace('🕓 ', '').strip()
        else:
            # Fall back to most recent entry if nothing selected
            timestamp_str = self.entries[0][0]
            
        print(f"\n⚙️ Recovering files up to: {timestamp_str}")
        project_name = self.project_entry.get().strip()
        
        if project_name:
            print(f"🎯 Filtering for project: {project_name}")
        else:
            if not messagebox.askyesno("Confirm", "No project name entered. Recover all files?"):
                return
        
        organize_history_folders(project_name)
        
        try:
            recovery_time = datetime.strptime(timestamp_str, "%Y%m%d %H%M%S")
            count = recover_files_up_to(recovery_time)
            messagebox.showinfo("Recovery Complete", f"✅ Recovered {count} files to: {FINAL_RECOVERY}")
            self.root.quit()
        except ValueError as ve:
            print("❌ Failed to parse timestamp for recovery:", ve)

# --- Run ---
if __name__ == "__main__":
    root = tk.Tk()
    app = RecoveryApp(root)
    root.mainloop()