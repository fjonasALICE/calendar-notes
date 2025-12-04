# 📅 Calendar Notes

A terminal-based note-taking system with Apple Calendar and Indico integration. Browse your calendar events in a TUI and create markdown notes linked to specific events—or create standalone notes for anything else.

## Features

- **Calendar Integration**: Access your Apple Calendar events directly from the terminal
- **Event-Linked Notes**: Create notes associated with specific calendar events
- **Indico Agenda Integration**: Automatically fetches meeting agendas from Indico links in event descriptions
- **Standalone Notes**: Create notes not tied to any event
- **Configurable Editor**: Opens notes in your preferred editor (nvim, VS Code, etc.)
- **Full-Text Search**: Search through note titles and content instantly
- **Note Preview**: See note content and metadata before opening
- **Sort Options**: Sort notes by date, title, or last updated
- **Color-Coded Calendars**: Each calendar gets a distinct color for easy identification
- **Week View**: Toggle between single-day and week overview
- **Date Navigation**: Browse events by day or week with keyboard shortcuts
- **YAML Frontmatter**: Notes include metadata for organization
- **Delete with Confirmation**: Safely delete notes you no longer need

## Installation

1. **Create a virtual environment** (recommended):
   ```bash
   cd ~/notes
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Grant Calendar Access**: On first run, macOS will prompt you to grant calendar access to the terminal/Python. Accept this to enable calendar integration.

## Usage

Run the application:

```bash
./app.py
# or
python app.py
```

### Configuring Your Editor

By default, notes open in `nvim`. To use a different editor, set the `$EDITOR` environment variable:

```bash
# For VS Code
export EDITOR="code"

# For Sublime Text
export EDITOR="subl"

# For Emacs
export EDITOR="emacs"

# For standard Vim
export EDITOR="vim"
```

Add this to your shell profile (`.zshrc`, `.bashrc`, etc.) to make it permanent.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` / `o` | Open/create note for selected item |
| `n` | Create new standalone note |
| `s` | Search notes (full-text fuzzy search) |
| `d` | Delete selected note (with confirmation) |
| `S` | Change sort order |
| `v` | Toggle day/week view |
| `r` | Refresh events and notes |
| `t` | Go to today |
| `←` / `→` | Previous/next day |
| `w` / `b` | Next/previous week |
| `g` | Go to specific date |
| `Tab` | Switch between Calendar Events and All Notes tabs |
| `?` | Show help |
| `q` | Quit |

### Search

Press `s` to open the search modal. Start typing to search through:
- Note titles
- Note content (full-text search)

Results update as you type. Press `Enter` to open the first result, or navigate to a specific result and press `Enter`.

### Sorting Notes

Press `S` (shift+s) to open the sort menu. Available options:
- **Date** (newest/oldest first) - Uses event date or creation date
- **Title** (A-Z / Z-A)
- **Updated** (newest/oldest first) - Based on last modification

### Views

Press `v` to toggle between:
- **Day View**: Shows events for a single day with full details
- **Week View**: Shows a week overview in the header

### Indico Agenda Integration

When creating notes for calendar events, the app automatically detects Indico links (e.g., `https://indico.cern.ch/event/1609411/`) in the event description and fetches the meeting agenda.

**For public events**: Works automatically, no setup required.

**For protected events**: Set your Indico API token:

```bash
# Add to your .zshrc or .bashrc
export INDICO_API_KEY="your-api-token-here"
```

To get an API token:
1. Log in to your Indico instance (e.g., https://indico.cern.ch)
2. Go to User Settings → API Tokens
3. Create a new token and copy it

The fetched agenda includes:
- List of contributions/talks
- Speaker names
- Scheduled times and durations
- Direct link to the Indico event

### Note Structure

Notes are stored in the `notes/` directory:

```
notes/
├── events/           # Notes linked to calendar events
│   └── 2024-12-03_1400_Team_Meeting.md
└── standalone/       # Notes not linked to events
    └── 2024-12-03_152030_Project_Ideas.md
```

Each note includes YAML frontmatter with metadata:

```yaml
---
title: Team Meeting
created: 2024-12-03T14:00:00
updated: 2024-12-03T14:30:00
tags: []
event:
  id: ABC123...
  title: Team Meeting
  date: 2024-12-03T14:00:00
  calendar: Work
  location: Conference Room A
  all_day: false
---
```

## Requirements

- macOS (for Apple Calendar integration via EventKit)
- Python 3.10+
- Your preferred editor installed and in PATH
- Calendar access permission

## Troubleshooting

### Calendar Access Denied
If you denied calendar access initially, you can re-enable it in:
**System Preferences → Privacy & Security → Calendar** → Enable for Terminal/your terminal app

### Editor Not Found
Ensure your editor is installed and in your PATH:
```bash
# For neovim
brew install neovim

# For VS Code (install "code" command from VS Code)
# Open VS Code → Cmd+Shift+P → "Shell Command: Install 'code' command in PATH"
```

### Search Not Finding Content
Search requires at least 2 characters. It searches both titles and the full content of notes.

## Architecture

- `app.py` - Main TUI application using Textual
- `calendar_integration.py` - Apple Calendar access via pyobjc/EventKit
- `note_manager.py` - Note creation, storage, and retrieval
- `indico_integration.py` - Fetches meeting agendas from Indico links

## What's New

### Latest Updates
- **Indico agenda integration** - Automatically fetches meeting agendas from Indico links
- **Full-text search** (`s` key) - Search through note titles and content
- **Note preview panel** - See note content before opening
- **Delete with confirmation** (`d` key) - Safely remove notes
- **Configurable editor** - Use `$EDITOR` environment variable
- **Sort options** (`S` key) - Sort by date, title, or updated
- **Week view** (`v` key) - Toggle between day and week views
- **Color-coded calendars** - Visual distinction between calendars
- **Improved UI** - Better styling and visual feedback

## License

MIT
