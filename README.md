# 🧠 CursorRecovery

**Recover lost code history from [Cursor](https://www.cursor.so) even when your current project has been corrupted.**  
This toolkit helps you extract and recover previous file versions using Cursor's local history and AI interaction data.

---

## 📦 Contents

- `step_1.py` – Organize Cursor’s history snapshots by timestamp.
- `step_2.py` – Extract large `composerData` blobs from Cursor's internal SQLite store.
- `step_3.py` – Decode the largest AI interaction blob into readable JSON.
- `step_4.py` – Extract your AI requests and a timeline from the decoded data.

---

## 🛠️ Requirements

- Python 3.7+
- [`msgpack`](https://pypi.org/project/msgpack/) (`pip install msgpack`)
- Works on macOS (other platforms untested but may work if the paths are adjusted).

---

## 🧭 Usage

> It’s recommended to follow the steps in order.

### 🧩 Step 1: Organize Cursor History Snapshots

```bash
python3 step_1.py
```

This script scans the `~/Library/Application Support/Cursor/User/History/` folder and groups `entries.json` and source files into folders organized by timestamp. It helps you identify file versions that correspond to when your code was working correctly.

**What to do next:**

- Find the folder whose timestamp matches your last known good code.
- Compare files with your current project.
- Recover or merge as needed.
- Repeat the process, working backwards to retrieve the last good version of each file.

---

### 🧪 Step 2: Extract Full AI Interaction Blob

```bash
python3 step_2.py
```

This script accesses the internal Cursor SQLite database (`state.vscdb`) and extracts **large** `composerData` blobs (over 2KB), including the **largest** AI interaction history.

Blobs are saved in:

```
~/CursorRecovery/Extracted/
```

---

### 🔍 Step 3: Decode Full Composer Blob

```bash
python3 step_3.py
```

Decodes the binary `full_composer_blob.bin` using MessagePack and extracts the full JSON representation of your AI conversations and interactions.

Outputs a single file:

```
full_composer_blob_decoded.json
```

---

### 🗃️ Step 4: Extract AI Request Timeline

```bash
python3 step_4.py
```

Scans the decoded blob to find your AI requests and presents them in timestamped order:

```
ai_request_timeline.txt
```

This helps you pinpoint when you introduced breaking changes, lost important files, or otherwise got off track.

---

## 🧼 Notes

- Your original comments in the code are **always preserved**.
- Only non-destructive operations are performed: history is **copied**, not altered.
- If you're unsure when your project broke, just proceed through all the steps and check the timeline in Step 4.

---

## 🤝 Contributing

Suggestions welcome via Issues or PRs.

---

## 📜 License

MIT License — do what you want, but don’t blame us if something goes wrong!
