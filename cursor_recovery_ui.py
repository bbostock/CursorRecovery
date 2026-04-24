# cursor_recovery_ui.py v5.0
# Cursor Recovery Tool with proper history mapping and file recovery

import os
import json
import sqlite3
import tempfile
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
import time
import subprocess

# Paths — Cursor user data on Windows: %APPDATA%\Cursor\User (…\Roaming\Cursor\User)
_appdata = os.environ.get("APPDATA")
if not _appdata:
    _profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    _appdata = os.path.join(_profile, "AppData", "Roaming")
CURSOR_USER_DIR = os.path.join(_appdata, "Cursor", "User")
DB_PATH = os.path.join(CURSOR_USER_DIR, "globalStorage", "state.vscdb")
DB_PATH_BACKUP = os.path.join(CURSOR_USER_DIR, "globalStorage", "state.vscdb.backup")
WORKSPACE_STORAGE = os.path.join(CURSOR_USER_DIR, "workspaceStorage")
HISTORY_PATH = os.path.join(CURSOR_USER_DIR, "History")
ORGANIZED_HISTORY = os.path.expanduser(os.path.join("~", "CursorRecovered", "_organized_history"))
FINAL_RECOVERY = os.path.expanduser(os.path.join("~", "CursorRecovered", "final"))

os.makedirs(ORGANIZED_HISTORY, exist_ok=True)
os.makedirs(FINAL_RECOVERY, exist_ok=True)


def uri_to_local_path(uri: str) -> str:
    """Turn a file:// URI from workspace.json into a local path (Windows-friendly)."""
    if not uri or not isinstance(uri, str):
        return ""
    parsed = urlparse(uri.replace("\\", "/"))
    path = unquote(parsed.path or "")
    if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return os.path.normpath(path)


def list_workspace_databases():
    """
    Each Cursor/VS Code workspace folder under workspaceStorage may contain
    workspace.json (folder or workspace URI) and state.vscdb.
    Returns a list of {"label": str, "primary": str} sorted by label.
    """
    found = []
    if not os.path.isdir(WORKSPACE_STORAGE):
        return found
    for entry in os.listdir(WORKSPACE_STORAGE):
        folder = os.path.join(WORKSPACE_STORAGE, entry)
        if not os.path.isdir(folder):
            continue
        primary = os.path.join(folder, "state.vscdb")
        if not os.path.isfile(primary):
            continue
        label = entry[:12] + "…"
        wj = os.path.join(folder, "workspace.json")
        if os.path.isfile(wj):
            try:
                with open(wj, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                uri = meta.get("folder") or meta.get("workspace")
                if uri:
                    decoded = uri_to_local_path(uri)
                    if decoded:
                        label = decoded
            except (json.JSONDecodeError, OSError):
                pass
        found.append({"label": label, "primary": primary})
    found.sort(key=lambda x: x["label"].lower())
    return found


def resolve_db_path(primary_vscdb: str, use_backup: bool) -> str:
    """state.vscdb -> state.vscdb.backup when use_backup and the backup exists."""
    backup = primary_vscdb + ".backup"
    if use_backup and os.path.isfile(backup):
        return backup
    if use_backup:
        print(f"⚠️ No backup at {backup}; using primary DB.")
    return primary_vscdb


def _composer_session_ids_from_itemtable(cursor) -> list:
    """
    Workspace state.vscdb keeps only composer session UUIDs in ItemTable;
    large `composerData:{uuid}` payloads live in globalStorage/state.vscdb.
    """
    try:
        cursor.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("composer.composerData",),
        )
    except sqlite3.Error:
        return []
    row = cursor.fetchone()
    if not row or row[0] is None:
        return []
    raw = row[0]
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(meta, dict):
        return []
    ordered = []
    seen = set()
    for field in ("lastFocusedComposerIds", "selectedComposerIds"):
        for cid in meta.get(field) or []:
            if isinstance(cid, str) and cid and cid not in seen:
                seen.add(cid)
                ordered.append(cid)
    return ordered


def _fetch_largest_composer_blob_from_cursordisk(cursor):
    """Returns (key_str, size, blob_bytes) or (None, None, None)."""
    cursor.execute(
        """
        SELECT key, LENGTH(value) AS size, value
        FROM cursorDiskKV
        WHERE key LIKE 'composerData:%'
        ORDER BY size DESC
        LIMIT 1;
        """
    )
    row = cursor.fetchone()
    if not row:
        return None, None, None
    key, size, blob = row[0], row[1], row[2]
    if isinstance(key, bytes):
        key = key.decode("utf-8")
    return key, size, blob


def _fetch_composer_blob_for_session(cursor, session_id: str):
    key = f"composerData:{session_id}"
    cursor.execute(
        "SELECT value FROM cursorDiskKV WHERE key = ?",
        (key,),
    )
    row = cursor.fetchone()
    if not row:
        return None, None
    blob = row[0]
    ln = len(blob) if blob is not None else 0
    return key, blob


def _write_decoded_composer_temp(decoded: str) -> str:
    temp_path = os.path.join(tempfile.gettempdir(), "full_composer_blob_decoded.json")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(decoded)
    return temp_path


# --- STEP 1: Extract Largest Blob from DB ---
def extract_largest_blob_to_temp_json(primary_db_path: str, use_backup=False):
    conn = None
    global_conn = None
    try:
        db_path = resolve_db_path(primary_db_path, use_backup)
        print(f"\n🔍 Opening database: {db_path}")
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.text_factory = bytes
        cursor = conn.cursor()

        key, size, blob = _fetch_largest_composer_blob_from_cursordisk(cursor)
        if blob is not None:
            if not isinstance(blob, bytes):
                raise Exception("Blob was not returned as bytes")
            print(f"📦 Found largest blob: {key} ({size} bytes)")
            decoded = blob.decode("utf-8")
            return _write_decoded_composer_temp(decoded)

        # Workspace (and similar) DBs: cursorDiskKV is empty; session IDs are in ItemTable.
        session_ids = _composer_session_ids_from_itemtable(cursor)
        if not session_ids:
            raise Exception(
                "No composerData rows in cursorDiskKV and no composer.composerData session "
                "list in ItemTable. Open this folder in Cursor and use Composer at least once."
            )

        global_db_path = resolve_db_path(DB_PATH, use_backup)
        print(
            f"📎 Workspace DB has no composer payloads (IDs only). "
            f"Loading composerData blobs from global DB:\n   {global_db_path}"
        )
        global_conn = sqlite3.connect(global_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        global_conn.text_factory = bytes
        gcursor = global_conn.cursor()

        best_key, best_blob, best_size = None, None, -1
        for sid in session_ids:
            k, b = _fetch_composer_blob_for_session(gcursor, sid)
            if b is None or not isinstance(b, bytes):
                continue
            ln = len(b)
            if ln > best_size:
                best_key, best_blob, best_size = k, b, ln

        if best_blob is None:
            raise Exception(
                "Found composer session ID(s) in the workspace DB but no matching "
                f"composerData:* rows in the global database. Sessions tried: {', '.join(session_ids)}"
            )

        print(f"📦 Using workspace-linked blob: {best_key} ({best_size} bytes)")
        decoded = best_blob.decode("utf-8")
        return _write_decoded_composer_temp(decoded)
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
        if global_conn is not None:
            global_conn.close()


def _sqlite_value_to_json_obj(value):
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, bytes):
        return json.loads(value.decode("utf-8"))
    return json.loads(str(value))


def hydrate_conversation_from_bubble_rows(composer_json: dict, global_db_path: str) -> dict:
    """
    Migrated Composer sessions often omit inline `conversation` and instead store
    `fullConversationHeadersOnly`, with each turn in global `cursorDiskKV` under
    bubbleId:{composerId}:{bubbleId}.
    """
    conv = composer_json.get("conversation")
    if isinstance(conv, list) and len(conv) > 0:
        return composer_json

    headers = composer_json.get("fullConversationHeadersOnly")
    composer_id = composer_json.get("composerId")
    if not isinstance(headers, list) or not headers or not composer_id:
        return composer_json

    conn = sqlite3.connect(global_db_path)
    try:
        cur = conn.cursor()
        new_convo = []
        missing = 0
        for h in headers:
            if not isinstance(h, dict):
                continue
            bub_id = h.get("bubbleId")
            header_type = h.get("type")
            if not bub_id:
                continue
            key = f"bubbleId:{composer_id}:{bub_id}"
            cur.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                missing += 1
                continue
            try:
                item = _sqlite_value_to_json_obj(row[0])
            except (json.JSONDecodeError, UnicodeDecodeError):
                missing += 1
                continue
            if not isinstance(item, dict):
                continue
            if header_type is not None:
                item["type"] = header_type
            new_convo.append(item)
        if new_convo:
            composer_json["conversation"] = new_convo
            print(
                f"🔗 Hydrated {len(new_convo)} message(s) from bubbleId rows "
                f"in global DB ({missing} header(s) had no row)."
            )
        elif headers:
            print(
                f"⚠️ fullConversationHeadersOnly has {len(headers)} entr(y/ies) but "
                f"no matching bubbleId:* rows in:\n   {global_db_path}"
            )
        return composer_json
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

        self.db_source = tk.StringVar(value="global")

        self.source_frame = ttk.LabelFrame(root, text="Database source")
        self.source_frame.pack(fill=tk.X, pady=5, padx=10)

        rb_row = ttk.Frame(self.source_frame)
        rb_row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Radiobutton(
            rb_row,
            text="Global (…\\Cursor\\User\\globalStorage\\state.vscdb)",
            variable=self.db_source,
            value="global",
            command=self.on_db_source_changed,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            rb_row,
            text="Workspace (per-folder state under workspaceStorage)",
            variable=self.db_source,
            value="workspace",
            command=self.on_db_source_changed,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            rb_row,
            text="Custom file…",
            variable=self.db_source,
            value="custom",
            command=self.on_db_source_changed,
        ).pack(side=tk.LEFT)

        ws_row = ttk.Frame(self.source_frame)
        ws_row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(ws_row, text="Workspace:").pack(side=tk.LEFT, padx=(0, 6))
        self.workspace_combo = ttk.Combobox(ws_row, width=72, state="disabled")
        self.workspace_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.refresh_ws_btn = ttk.Button(ws_row, text="Refresh list", command=self.refresh_workspaces)
        self.refresh_ws_btn.pack(side=tk.LEFT, padx=(0, 6))

        custom_row = ttk.Frame(self.source_frame)
        custom_row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(custom_row, text="Custom path:").pack(side=tk.LEFT, padx=(0, 6))
        self.custom_db_var = tk.StringVar(value="")
        self.custom_path_entry = ttk.Entry(custom_row, textvariable=self.custom_db_var, state="disabled")
        self.custom_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.browse_db_btn = ttk.Button(custom_row, text="Browse…", command=self.browse_custom_db, state="disabled")
        self.browse_db_btn.pack(side=tk.LEFT)

        self._workspace_options = []
        self.refresh_workspaces()

        self.db_frame = ttk.Frame(root)
        self.db_frame.pack(fill=tk.X, pady=5, padx=10)

        self.use_backup = tk.BooleanVar(value=False)
        self.backup_checkbox = ttk.Checkbutton(
            self.db_frame,
            text="Use Backup Database (state.vscdb.backup next to the chosen DB)",
            variable=self.use_backup,
        )
        self.backup_checkbox.pack(side=tk.LEFT)

        self.load_button = ttk.Button(
            self.db_frame,
            text="Load Database",
            command=self.load_data,
        )
        self.load_button.pack(side=tk.LEFT, padx=10)

        self.on_db_source_changed()

        # Add project name frame
        self.project_frame = ttk.Frame(root)
        self.project_frame.pack(fill=tk.X, pady=10, padx=10)

        self.project_label = ttk.Label(
            self.project_frame,
            text="History filter (Recover only): path substring, e.g. repo folder name —",
        )
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

        # Recover button disabled until a DB load succeeds
        self.recover_button = ttk.Button(
            root,
            text="Recover Files",
            command=self.recover_files,
            state="disabled"  # Initially disabled
        )
        self.recover_button.pack(pady=10)

    def on_db_source_changed(self, *args):
        mode = self.db_source.get()
        if mode == "global":
            self.workspace_combo.configure(state="disabled")
            self.refresh_ws_btn.configure(state="disabled")
            self.custom_path_entry.configure(state="disabled")
            self.browse_db_btn.configure(state="disabled")
        elif mode == "workspace":
            self.workspace_combo.configure(state="readonly" if self._workspace_options else "disabled")
            self.refresh_ws_btn.configure(state="normal")
            self.custom_path_entry.configure(state="disabled")
            self.browse_db_btn.configure(state="disabled")
        else:
            self.workspace_combo.configure(state="disabled")
            self.refresh_ws_btn.configure(state="disabled")
            self.custom_path_entry.configure(state="normal")
            self.browse_db_btn.configure(state="normal")

    def refresh_workspaces(self):
        self._workspace_options = list_workspace_databases()
        labels = [o["label"] for o in self._workspace_options]
        self.workspace_combo["values"] = labels
        if labels:
            self.workspace_combo.set(labels[0])
        else:
            self.workspace_combo.set("")
        if self.db_source.get() == "workspace":
            self.workspace_combo.configure(state="readonly" if labels else "disabled")

    def browse_custom_db(self):
        path = filedialog.askopenfilename(
            title="Select state.vscdb",
            filetypes=[("VS Code / Cursor state DB", "*.vscdb"), ("All files", "*.*")],
            initialdir=WORKSPACE_STORAGE if os.path.isdir(WORKSPACE_STORAGE) else CURSOR_USER_DIR,
        )
        if path:
            self.custom_db_var.set(path)

    def get_primary_database_path(self):
        mode = self.db_source.get()
        if mode == "global":
            return DB_PATH
        if mode == "workspace":
            if not self._workspace_options:
                messagebox.showwarning(
                    "Workspace",
                    "No workspaces found under workspaceStorage.\n"
                    "Open the folder in Cursor once, then click Refresh list.",
                )
                return None
            label = self.workspace_combo.get()
            for opt in self._workspace_options:
                if opt["label"] == label:
                    return opt["primary"]
            messagebox.showwarning(
                "Workspace",
                "Choose a workspace from the list, or click Refresh list.",
            )
            return None
        path = self.custom_db_var.get().strip()
        if not path:
            messagebox.showwarning("Custom DB", "Browse or paste the full path to state.vscdb.")
            return None
        if not os.path.isfile(path):
            messagebox.showerror("Custom DB", f"File not found:\n{path}")
            return None
        return path

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
        primary = self.get_primary_database_path()
        if not primary:
            return
        print("📥 Extracting conversation from largest blob...")
        temp_json = extract_largest_blob_to_temp_json(primary, self.use_backup.get())
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

        global_kv_path = resolve_db_path(DB_PATH, self.use_backup.get())
        self.raw_data = hydrate_conversation_from_bubble_rows(self.raw_data, global_kv_path)

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