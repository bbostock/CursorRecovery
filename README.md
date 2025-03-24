# Cursor Recovery Tool 🔄

A Python utility for recovering file history from the Cursor IDE's local storage. This tool helps you retrieve and organize previous versions of your code files.

## Features ✨

- 📂 Extracts file history from Cursor's SQLite database
- 🔍 Project-specific file filtering
- 📅 Timestamp-based version organization
- 💾 Support for both main and backup databases
- 🖥️ User-friendly GUI interface

## Requirements 📋

- Python 3.x
- tkinter (usually comes with Python)
- macOS (currently only supports Cursor's macOS file paths)

## Installation 🚀

1. Clone this repository:
```bash
git clone https://github.com/yourusername/cursor-recovery-tool.git
cd cursor-recovery-tool
```

2. Make sure you have Python 3.x installed:
```bash
python3 --version
```

## Usage 💡

1. Run the tool:
```bash
python3 cursor_recovery_ui5.0.py
```

2. In the GUI:
   - Choose between main or backup database using the checkbox
   - Click "Load Database" to load the conversation history
   - (Optional) Enter a project name to filter specific files
   - Click "Recover Files" to start the recovery process

## File Locations 📍

- Default database: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- Backup database: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb.backup`
- History folder: `~/Library/Application Support/Cursor/User/History/`
- Recovery output: `~/CursorRecovered/final/`

## How It Works 🔧

1. Extracts conversation history from Cursor's SQLite database
2. Organizes file versions by timestamp
3. Filters files by project name (if specified)
4. Recovers the most recent version of each file up to the selected point in time

## Notes 📝

- Always make sure to have backups of your important files
- The tool works with Cursor's default macOS file locations
- Recovered files are organized by timestamp in the output directory

## Contributing 🤝

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## License 📄

[MIT License](LICENSE)