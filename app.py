#!/usr/bin/env python3
"""
Calendar Notes TUI - A terminal-based note-taking system with Apple Calendar integration.

Navigate through your calendar events and create/open associated notes in your preferred editor.
"""

import os
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer, Grid
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
    Rule,
    Switch,
    OptionList,
    Markdown,
)
from textual.widgets.option_list import Option
from textual.message import Message

from calendar_integration import CalendarAccess, CalendarEvent
from note_manager import NoteManager, Note, TodoItem


class SortOrder(Enum):
    """Sort order options for notes."""
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"
    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"
    UPDATED_DESC = "updated_desc"
    UPDATED_ASC = "updated_asc"


class ViewMode(Enum):
    """Calendar view mode."""
    DAY = "day"
    WEEK = "week"


# Calendar colors for visual distinction
CALENDAR_COLORS = [
    "cyan", "green", "yellow", "magenta", "blue", "red", 
    "bright_cyan", "bright_green", "bright_yellow", "bright_magenta"
]


def get_editor() -> list[str]:
    """Get the editor command from environment or default to nvim."""
    editor = os.environ.get("EDITOR", "nvim")
    # Handle editors that might need specific flags
    if "code" in editor.lower():
        return [editor, "--wait"]
    elif "subl" in editor.lower():
        return [editor, "--wait"]
    return [editor]


def get_editor_name() -> str:
    """Get a friendly name for the configured editor."""
    editor = os.environ.get("EDITOR", "nvim")
    editor_base = Path(editor).name.lower()
    names = {
        "nvim": "neovim",
        "vim": "vim",
        "code": "VS Code",
        "subl": "Sublime",
        "nano": "nano",
        "emacs": "emacs",
    }
    return names.get(editor_base, editor_base)


class EventDetailPanel(Static):
    """Panel showing details of selected calendar event."""

    def __init__(self, note_manager: Optional["NoteManager"] = None, **kwargs):
        super().__init__(**kwargs)
        self.event: Optional[CalendarEvent] = None
        self.note_manager = note_manager

    def set_note_manager(self, note_manager: "NoteManager"):
        """Set the note manager for note preview functionality."""
        self.note_manager = note_manager

    def update_event(self, event: Optional[CalendarEvent], calendar_color: str = "cyan"):
        """Update the panel with event details."""
        self.event = event
        if event:
            location = f"\n📍 {event.location}" if event.location else ""
            notes = f"\n\n[dim italic]> {event.notes[:200]}...[/]" if event.notes and len(event.notes) > 200 else (f"\n\n[dim italic]> {event.notes}[/]" if event.notes else "")
            
            editor_name = get_editor_name()
            
            # Get note preview if note exists
            note_preview = ""
            if self.note_manager:
                note = self.note_manager.find_note_for_event(event.event_id)
                if note:
                    try:
                        with open(note.filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                            # Skip frontmatter
                            if content.startswith("---"):
                                end_idx = content.find("---", 3)
                                if end_idx != -1:
                                    content = content[end_idx + 3:].strip()
                            # Get first ~400 chars
                            preview = content[:400]
                            if len(content) > 400:
                                preview += "..."
                            note_preview = f"\n\n[bold]─── Note Preview ───[/]\n\n{preview}"
                    except Exception:
                        note_preview = "\n\n[bold]─── Note Preview ───[/]\n\n[dim]Unable to load preview[/]"
                else:
                    note_preview = "\n\n[dim italic]No note yet - press Enter to create one[/]"
            
            self.update(f"""[bold {calendar_color}]{event.title}[/]

📅 {event.date_str}
⏰ {event.time_str}
⏱️  {event.duration_str}
🗓️  [{calendar_color}]{event.calendar_name}[/]{location}{notes}{note_preview}

[dim]Press [bold]Enter[/] to open note in {editor_name}[/]""")
        else:
            self.update("[dim]Select an event to see details[/]")


class NoteDetailPanel(Static):
    """Panel showing details and preview of selected note."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.note: Optional[Note] = None

    def update_note(self, note: Optional[Note]):
        """Update the panel with note details and preview."""
        self.note = note
        if note:
            note_type = "[cyan]📅 Event Note[/]" if note.is_event_note else "[green]📝 Standalone[/]"
            tags_str = ", ".join(f"[yellow]#{tag}[/]" for tag in note.tags) if note.tags else "[dim]no tags[/]"
            
            # Read note content for preview
            preview = ""
            try:
                with open(note.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Skip frontmatter
                    if content.startswith("---"):
                        end_idx = content.find("---", 3)
                        if end_idx != -1:
                            content = content[end_idx + 3:].strip()
                    # Get first ~500 chars
                    preview = content[:500]
                    if len(content) > 500:
                        preview += "..."
            except Exception:
                preview = "[dim]Unable to load preview[/]"
            
            event_info = ""
            if note.is_event_note and note.event_title:
                event_info = f"\n🗓️  [cyan]{note.event_title}[/]"
                if note.event_date:
                    event_info += f"\n📅 {note.event_date.strftime('%Y-%m-%d %H:%M')}"
            
            editor_name = get_editor_name()
            self.update(f"""[bold]{note.title}[/]

{note_type}{event_info}
🏷️  {tags_str}
📁 [dim]{note.filename}[/]

[bold]─── Preview ───[/]

{preview}

[dim]Press [bold]Enter[/] to edit in {editor_name}
Press [bold]d[/] to delete[/]""")
        else:
            self.update("[dim]Select a note to see preview[/]")


class TodoDetailPanel(Static):
    """Panel showing details of selected todo item."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.todo: Optional[TodoItem] = None

    def update_todo(self, todo: Optional[TodoItem]):
        """Update the panel with todo details."""
        self.todo = todo
        if todo:
            editor_name = get_editor_name()
            self.update(f"""[bold yellow]☐ {todo.content or "(empty todo)"}[/]

📁 [dim]{todo.filepath.name}[/]
📄 [cyan]{todo.note_title}[/]
📍 Line {todo.line_number}

[bold]─── Original Line ───[/]

[dim]{todo.full_line.strip()}[/]

[dim]Press [bold]Enter[/] to open note in {editor_name}
Press [bold]Space[/] to complete (removes line)[/]""")
        else:
            self.update("[dim]Select a todo to see details[/]")


class SearchModal(ModalScreen[Optional[str]]):
    """Modal for fuzzy searching notes in real-time."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "focus_results", "Navigate Down", show=False),
        Binding("up", "focus_input", "Navigate Up", show=False),
    ]

    CSS = """
    SearchModal {
        align: center middle;
    }
    
    SearchModal > Container {
        width: 90;
        height: auto;
        max-height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    SearchModal Input {
        margin: 1 0;
    }
    
    SearchModal #search-results {
        height: auto;
        max-height: 25;
        margin: 1 0;
        border: round $primary-darken-2;
    }
    
    SearchModal .buttons {
        margin-top: 1;
        align: center middle;
    }
    
    SearchModal Button {
        margin: 0 1;
    }
    
    SearchModal OptionList {
        height: auto;
        max-height: 20;
    }
    
    SearchModal .result-count {
        text-align: right;
        color: $text-muted;
        height: 1;
    }
    
    SearchModal .search-hint {
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }
    """

    def __init__(self, note_manager: NoteManager):
        super().__init__()
        self.note_manager = note_manager
        self.search_results: list[Note] = []
        self.fuzzy_results: list[tuple[Note, int, Optional[str]]] = []

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold]🔍 Fuzzy Search Notes[/]")
            yield Static("[dim]Type to search, ↓/↑ to navigate results, Enter to open[/]", classes="search-hint")
            yield Input(placeholder="Start typing to search...", id="search-input")
            yield Static("", id="result-count", classes="result-count")
            yield OptionList(id="search-results")
            with Horizontal(classes="buttons"):
                yield Button("Open", variant="primary", id="open-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self):
        self.query_one("#search-input", Input).focus()
        self._update_results([])

    def on_key(self, event) -> None:
        """Handle key events for navigation."""
        input_widget = self.query_one("#search-input", Input)
        option_list = self.query_one("#search-results", OptionList)
        
        # If we're in the input and press down, move to results
        if event.key == "down" and input_widget.has_focus:
            if self.search_results:
                option_list.focus()
                if option_list.highlighted is None:
                    option_list.highlighted = 0
                event.prevent_default()
                event.stop()
        # If we're in results and press up at the top, go back to input
        elif event.key == "up" and option_list.has_focus:
            if option_list.highlighted == 0 or option_list.highlighted is None:
                input_widget.focus()
                event.prevent_default()
                event.stop()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed):
        """Handle search input changes - real-time fuzzy search."""
        query = event.value.strip()
        if len(query) >= 1:
            # Use fuzzy search for better matching
            self.fuzzy_results = self.note_manager.fuzzy_search_notes(query, threshold=35)
            self.search_results = [result[0] for result in self.fuzzy_results]
        else:
            self.fuzzy_results = []
            self.search_results = []
        self._update_results(self.fuzzy_results)

    def _update_results(self, results: list[tuple[Note, int, Optional[str]]]):
        """Update the results list with fuzzy match info."""
        option_list = self.query_one("#search-results", OptionList)
        option_list.clear_options()
        
        count_label = self.query_one("#result-count", Static)
        
        if not results:
            count_label.update("[dim]No results - try different keywords[/]")
            return
        
        count_label.update(f"[dim]{len(results)} match{'es' if len(results) != 1 else ''} found[/]")
        
        for note, score, context in results[:25]:  # Show up to 25 results
            icon = "📅" if note.is_event_note else "📝"
            date_str = note.event_date.strftime("%Y-%m-%d") if note.event_date else note.created_at.strftime("%Y-%m-%d")
            
            # Color-code score
            if score >= 90:
                score_display = f"[green]{score}%[/]"
            elif score >= 70:
                score_display = f"[yellow]{score}%[/]"
            else:
                score_display = f"[dim]{score}%[/]"
            
            # Build the display line
            title_truncated = note.title[:40] + "…" if len(note.title) > 40 else note.title
            display = f"{icon} {title_truncated} [dim]({date_str})[/] {score_display}"
            
            # Add context snippet if available
            if context:
                context_short = context[:50] + "…" if len(context) > 50 else context
                display += f"\n   [dim italic]→ {context_short}[/]"
            
            option_list.add_option(Option(display, id=str(note.filepath)))

    @on(Button.Pressed, "#open-btn")
    def on_open(self):
        option_list = self.query_one("#search-results", OptionList)
        if option_list.highlighted is not None and self.search_results:
            idx = option_list.highlighted
            if idx < len(self.search_results):
                self.dismiss(str(self.search_results[idx].filepath))
        else:
            self.notify("Select a note first", severity="warning")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.dismiss(None)

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected):
        """Handle double-click or Enter on result."""
        if event.option.id:
            self.dismiss(event.option.id)

    @on(Input.Submitted)
    def on_input_submitted(self):
        """Handle Enter in search input - open first/selected result."""
        option_list = self.query_one("#search-results", OptionList)
        # If there's a highlighted result, open that one
        if option_list.highlighted is not None and self.search_results:
            idx = option_list.highlighted
            if idx < len(self.search_results):
                self.dismiss(str(self.search_results[idx].filepath))
                return
        # Otherwise open the first result
        if self.search_results:
            self.dismiss(str(self.search_results[0].filepath))

    def action_cancel(self):
        self.dismiss(None)

    def action_focus_results(self):
        """Focus the results list."""
        if self.search_results:
            option_list = self.query_one("#search-results", OptionList)
            option_list.focus()
            if option_list.highlighted is None:
                option_list.highlighted = 0

    def action_focus_input(self):
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()


class DeleteConfirmModal(ModalScreen[bool]):
    """Modal for confirming note deletion."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    CSS = """
    DeleteConfirmModal {
        align: center middle;
    }
    
    DeleteConfirmModal > Container {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    
    DeleteConfirmModal .warning {
        color: $error;
        text-align: center;
        margin: 1 0;
    }
    
    DeleteConfirmModal .note-title {
        text-align: center;
        margin: 1 0;
    }
    
    DeleteConfirmModal .buttons {
        margin-top: 1;
        align: center middle;
    }
    
    DeleteConfirmModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, note_title: str):
        super().__init__()
        self.note_title = note_title

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold]⚠️  Delete Note?[/]", classes="warning")
            yield Label(f"[bold]{self.note_title}[/]", classes="note-title")
            yield Label("[dim]This action cannot be undone.[/]", classes="warning")
            with Horizontal(classes="buttons"):
                yield Button("Delete", variant="error", id="delete-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self):
        self.query_one("#cancel-btn", Button).focus()

    @on(Button.Pressed, "#delete-btn")
    def on_delete(self):
        self.dismiss(True)

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.dismiss(False)

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)


class NewNoteModal(ModalScreen[Optional[str]]):
    """Modal for creating a new standalone note."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    NewNoteModal {
        align: center middle;
    }
    
    NewNoteModal > Container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    NewNoteModal Input {
        margin: 1 0;
    }
    
    NewNoteModal .buttons {
        margin-top: 1;
        align: center middle;
    }
    
    NewNoteModal Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold]📝 Create Standalone Note[/]")
            yield Label("[dim]Not linked to any calendar event[/]")
            yield Input(placeholder="Enter note title...", id="note-title")
            with Horizontal(classes="buttons"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self):
        self.query_one("#note-title", Input).focus()

    @on(Button.Pressed, "#create-btn")
    def on_create(self):
        title = self.query_one("#note-title", Input).value.strip()
        if title:
            self.dismiss(title)
        else:
            self.notify("Please enter a title", severity="warning")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted)
    def on_input_submitted(self):
        self.on_create()

    def action_cancel(self):
        self.dismiss(None)


class DatePickerModal(ModalScreen[Optional[datetime]]):
    """Modal for selecting a date to view events."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    DatePickerModal {
        align: center middle;
    }
    
    DatePickerModal > Container {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    DatePickerModal Input {
        margin: 1 0;
    }
    
    DatePickerModal .buttons {
        margin-top: 1;
        align: center middle;
    }
    
    DatePickerModal Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold]📅 Go to Date[/]")
            yield Label("[dim]Format: YYYY-MM-DD[/]")
            yield Input(
                placeholder=datetime.now().strftime("%Y-%m-%d"),
                id="date-input",
                value=datetime.now().strftime("%Y-%m-%d"),
            )
            with Horizontal(classes="buttons"):
                yield Button("Go", variant="primary", id="go-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self):
        input_widget = self.query_one("#date-input", Input)
        input_widget.focus()
        input_widget.action_select_all()

    @on(Button.Pressed, "#go-btn")
    def on_go(self):
        date_str = self.query_one("#date-input", Input).value.strip()
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            self.dismiss(date)
        except ValueError:
            self.notify("Invalid date format. Use YYYY-MM-DD", severity="error")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted)
    def on_input_submitted(self):
        self.on_go()

    def action_cancel(self):
        self.dismiss(None)


class SortModal(ModalScreen[Optional[SortOrder]]):
    """Modal for selecting sort order."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    SortModal {
        align: center middle;
    }
    
    SortModal > Container {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    
    SortModal OptionList {
        height: auto;
        margin: 1 0;
    }
    
    SortModal .buttons {
        margin-top: 1;
        align: center middle;
    }
    """

    def __init__(self, current_sort: SortOrder):
        super().__init__()
        self.current_sort = current_sort

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("[bold]📊 Sort Notes By[/]")
            yield OptionList(
                Option("📅 Date (Newest First)", id=SortOrder.DATE_DESC.value),
                Option("📅 Date (Oldest First)", id=SortOrder.DATE_ASC.value),
                Option("🔤 Title (A-Z)", id=SortOrder.TITLE_ASC.value),
                Option("🔤 Title (Z-A)", id=SortOrder.TITLE_DESC.value),
                Option("🕐 Updated (Newest First)", id=SortOrder.UPDATED_DESC.value),
                Option("🕐 Updated (Oldest First)", id=SortOrder.UPDATED_ASC.value),
                id="sort-options"
            )
            with Horizontal(classes="buttons"):
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self):
        self.query_one("#sort-options", OptionList).focus()

    @on(OptionList.OptionSelected, "#sort-options")
    def on_sort_selected(self, event: OptionList.OptionSelected):
        if event.option.id:
            self.dismiss(SortOrder(event.option.id))

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.dismiss(None)

    def action_cancel(self):
        self.dismiss(None)


class WeekDayColumn(Static):
    """A single day column in the week view."""
    
    def __init__(self, date: datetime, events: list[CalendarEvent], is_today: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.date = date
        self.day_events = events
        self.is_today = is_today
    
    def compose(self) -> ComposeResult:
        day_name = self.date.strftime("%a")
        day_num = self.date.strftime("%d")
        
        if self.is_today:
            header = f"[bold cyan]{day_name}[/]\n[bold cyan]{day_num}[/]"
        else:
            header = f"[bold]{day_name}[/]\n{day_num}"
        
        content = header + "\n" + "─" * 8 + "\n"
        
        if self.day_events:
            for event in self.day_events[:5]:  # Max 5 events per day
                time_str = event.start_date.strftime("%H:%M") if not event.is_all_day else "••••"
                title_short = event.title[:8] + "…" if len(event.title) > 9 else event.title
                content += f"[dim]{time_str}[/]\n{title_short}\n"
            if len(self.day_events) > 5:
                content += f"[dim]+{len(self.day_events) - 5} more[/]"
        else:
            content += "[dim]No events[/]"
        
        self.update(content)


class CalendarNotesApp(App):
    """Main TUI application for calendar notes."""

    theme = "tokyo-night"

    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        height: 100%;
    }
    
    #content {
        height: 1fr;
    }
    
    #events-container {
        width: 2fr;
        height: 100%;
        border: round $primary;
        padding: 0 1;
    }
    
    #detail-container {
        width: 1fr;
        height: 100%;
        border: round $secondary;
        padding: 1;
        overflow-y: auto;
    }
    
    #notes-content {
        height: 1fr;
    }
    
    #notes-container {
        width: 2fr;
        height: 100%;
        border: round $primary;
        padding: 0 1;
    }
    
    #note-detail-container {
        width: 1fr;
        height: 100%;
        border: round $secondary;
        padding: 1;
        overflow-y: auto;
    }
    
    .title-bar {
        dock: top;
        height: 3;
        background: $primary-darken-2;
        color: $text;
        padding: 1;
    }
    
    DataTable {
        height: 1fr;
    }
    
    DataTable > .datatable--cursor {
        background: $accent;
        color: $text;
    }
    
    #date-nav {
        height: 3;
        background: $primary-darken-1;
        padding: 0 1;
    }
    
    #date-nav Button {
        min-width: 3;
    }
    
    #current-date {
        width: 1fr;
        text-align: center;
        padding: 1;
    }
    
    #notes-header {
        height: 3;
        background: $primary-darken-1;
        padding: 0 1;
    }
    
    #notes-header Button {
        min-width: 8;
    }
    
    #notes-title {
        width: 1fr;
        text-align: left;
        padding: 1;
    }
    
    #sort-info {
        width: auto;
        padding: 1;
        color: $text-muted;
    }
    
    #notes-table {
        height: 1fr;
    }
    
    #todos-content {
        height: 1fr;
    }
    
    #todos-container {
        width: 2fr;
        height: 100%;
        border: round $primary;
        padding: 0 1;
    }
    
    #todo-detail-container {
        width: 1fr;
        height: 100%;
        border: round $secondary;
        padding: 1;
        overflow-y: auto;
    }
    
    #todos-header {
        height: 3;
        background: $primary-darken-1;
        padding: 0 1;
    }
    
    #todos-header Button {
        min-width: 8;
    }
    
    #todos-title {
        width: 1fr;
        text-align: left;
        padding: 1;
    }
    
    #todos-count {
        width: auto;
        padding: 1;
        color: $text-muted;
    }
    
    #todos-table {
        height: 1fr;
    }
    
    #todo-detail {
        height: 100%;
    }
    
    #event-detail {
        height: 100%;
    }
    
    #note-detail {
        height: 100%;
    }
    
    .status-bar {
        dock: bottom;
        height: 1;
        background: $primary-darken-3;
        color: $text-muted;
        padding: 0 1;
    }
    
    TabbedContent {
        height: 100%;
    }
    
    TabPane {
        padding: 0;
    }
    
    #week-view {
        height: 100%;
        padding: 1;
    }
    
    #week-grid {
        height: 1fr;
        grid-size: 7;
        grid-gutter: 1;
    }
    
    .week-day {
        height: 100%;
        border: round $primary-darken-2;
        padding: 0 1;
        text-align: center;
    }
    
    .week-day-today {
        border: round $accent;
    }
    
    #view-toggle {
        height: 3;
        background: $primary-darken-1;
        padding: 0 1;
    }
    
    #view-toggle Button {
        min-width: 8;
    }
    
    #week-nav-label {
        width: 1fr;
        text-align: center;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_note", "New Standalone"),
        Binding("r", "refresh", "Refresh"),
        Binding("g", "goto_date", "Go to Date"),
        Binding("t", "today", "Today"),
        Binding("left", "prev_day", "Prev Day", show=False),
        Binding("right", "next_day", "Next Day", show=False),
        Binding("w", "next_week", "+Week"),
        Binding("b", "prev_week", "-Week"),
        Binding("o", "open_note", "Open"),
        Binding("s", "search", "Search"),
        Binding("d", "delete_note", "Delete"),
        Binding("S", "sort_notes", "Sort"),
        Binding("v", "toggle_view", "View"),
        Binding("?", "show_help", "Help"),
        Binding("1", "show_calendar", "Calendar"),
        Binding("2", "show_notes", "Notes"),
        Binding("3", "show_todos", "Todos"),
        Binding("space", "complete_todo", "Complete", show=False),
        Binding("tab", "switch_tab", "Switch Tab", show=False),
    ]

    TITLE = "📅 Calendar Notes"
    SUB_TITLE = "Your notes, organized by events"

    def __init__(self):
        super().__init__()
        self.calendar = CalendarAccess()
        self.note_manager = NoteManager()
        self.current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.events: list[CalendarEvent] = []
        self.notes: list[Note] = []
        self.todos: list[TodoItem] = []
        self.selected_event: Optional[CalendarEvent] = None
        self.selected_note: Optional[Note] = None
        self.selected_todo: Optional[TodoItem] = None
        self.sort_order = SortOrder.DATE_DESC
        self.view_mode = ViewMode.DAY
        self.calendar_colors: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Vertical(id="main-container"):
            with TabbedContent():
                with TabPane("Calendar Events", id="events-tab"):
                    with Horizontal(id="date-nav"):
                        yield Button("◀◀", id="prev-week-btn", variant="default")
                        yield Button("◀", id="prev-day-btn", variant="default")
                        yield Static(self._format_date_header(), id="current-date")
                        yield Button("▶", id="next-day-btn", variant="default")
                        yield Button("▶▶", id="next-week-btn", variant="default")
                        yield Button("Today", id="today-btn", variant="primary")
                        yield Button("Week", id="view-btn", variant="default")
                    
                    with Horizontal(id="content"):
                        with Container(id="events-container"):
                            yield DataTable(id="events-table", cursor_type="row")
                        with ScrollableContainer(id="detail-container"):
                            yield EventDetailPanel(id="event-detail")
                
                with TabPane("All Notes", id="notes-tab"):
                    with Horizontal(id="notes-header"):
                        yield Static("[bold]📝 All Notes[/]", id="notes-title")
                        yield Static("", id="sort-info")
                        yield Button("Sort", id="sort-btn", variant="default")
                        yield Button("Search", id="search-btn", variant="primary")
                    
                    with Horizontal(id="notes-content"):
                        with Container(id="notes-container"):
                            yield DataTable(id="notes-table", cursor_type="row")
                        with ScrollableContainer(id="note-detail-container"):
                            yield NoteDetailPanel(id="note-detail")
                
                with TabPane("Todos", id="todos-tab"):
                    with Horizontal(id="todos-header"):
                        yield Static("[bold]☐ Todos[/]", id="todos-title")
                        yield Static("", id="todos-count")
                        yield Button("Refresh", id="refresh-todos-btn", variant="default")
                    
                    with Horizontal(id="todos-content"):
                        with Container(id="todos-container"):
                            yield DataTable(id="todos-table", cursor_type="row")
                        with ScrollableContainer(id="todo-detail-container"):
                            yield TodoDetailPanel(id="todo-detail")
        
        yield Footer()

    def _format_date_header(self) -> str:
        """Format the current date for the header."""
        today = datetime.now().date()
        if self.view_mode == ViewMode.WEEK:
            # Show week range
            week_start = self.current_date - timedelta(days=self.current_date.weekday())
            week_end = week_start + timedelta(days=6)
            return f"[bold]Week of[/] {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        
        if self.current_date.date() == today:
            return f"[bold cyan]Today[/] • {self.current_date.strftime('%A, %B %d, %Y')}"
        elif self.current_date.date() == today - timedelta(days=1):
            return f"[yellow]Yesterday[/] • {self.current_date.strftime('%A, %B %d, %Y')}"
        elif self.current_date.date() == today + timedelta(days=1):
            return f"[green]Tomorrow[/] • {self.current_date.strftime('%A, %B %d, %Y')}"
        return self.current_date.strftime("%A, %B %d, %Y")

    def _get_calendar_color(self, calendar_name: str) -> str:
        """Get a consistent color for a calendar."""
        if calendar_name not in self.calendar_colors:
            idx = len(self.calendar_colors) % len(CALENDAR_COLORS)
            self.calendar_colors[calendar_name] = CALENDAR_COLORS[idx]
        return self.calendar_colors[calendar_name]

    def on_mount(self):
        """Initialize the app on mount."""
        # Check calendar access
        if not self.calendar.is_authorized():
            self.notify(
                "Calendar access needed. Please grant permission when prompted.",
                severity="warning",
                timeout=5,
            )
            self.calendar.request_access()

        # Set note manager on event detail panel for preview functionality
        self.query_one("#event-detail", EventDetailPanel).set_note_manager(self.note_manager)

        self._setup_events_table()
        self._setup_notes_table()
        self._setup_todos_table()
        self._refresh_events()
        self._refresh_notes()
        self._refresh_todos()
        self._update_sort_info()
        
        # Focus the events table by default
        self.query_one("#events-table", DataTable).focus()

    def _setup_events_table(self):
        """Configure the events data table."""
        table = self.query_one("#events-table", DataTable)
        table.add_column("Time", width=12, key="time")
        table.add_column("Event", width=32, key="event")
        table.add_column("Calendar", width=14, key="calendar")
        table.add_column("Tags", width=16, key="tags")
        table.add_column("📝", width=4, key="note")

    def _setup_notes_table(self):
        """Configure the notes data table."""
        table = self.query_one("#notes-table", DataTable)
        table.add_column("", width=3, key="type")
        table.add_column("Title", width=30, key="title")
        table.add_column("Tags", width=18, key="tags")
        table.add_column("Date", width=12, key="date")
        table.add_column("Updated", width=12, key="updated")

    def _setup_todos_table(self):
        """Configure the todos data table."""
        table = self.query_one("#todos-table", DataTable)
        table.add_column("☐", width=3, key="checkbox")
        table.add_column("Todo", width=40, key="todo")
        table.add_column("Note", width=25, key="note")
        table.add_column("Line", width=6, key="line")

    def _update_sort_info(self):
        """Update the sort info label."""
        sort_labels = {
            SortOrder.DATE_DESC: "📅 Date ↓",
            SortOrder.DATE_ASC: "📅 Date ↑",
            SortOrder.TITLE_ASC: "🔤 Title A-Z",
            SortOrder.TITLE_DESC: "🔤 Title Z-A",
            SortOrder.UPDATED_DESC: "🕐 Updated ↓",
            SortOrder.UPDATED_ASC: "🕐 Updated ↑",
        }
        self.query_one("#sort-info", Static).update(f"[dim]{sort_labels[self.sort_order]}[/]")

    def _sort_notes(self, notes: list[Note]) -> list[Note]:
        """Sort notes according to current sort order."""
        if self.sort_order == SortOrder.DATE_DESC:
            return sorted(notes, key=lambda n: n.event_date or n.created_at, reverse=True)
        elif self.sort_order == SortOrder.DATE_ASC:
            return sorted(notes, key=lambda n: n.event_date or n.created_at)
        elif self.sort_order == SortOrder.TITLE_ASC:
            return sorted(notes, key=lambda n: n.title.lower())
        elif self.sort_order == SortOrder.TITLE_DESC:
            return sorted(notes, key=lambda n: n.title.lower(), reverse=True)
        elif self.sort_order == SortOrder.UPDATED_DESC:
            return sorted(notes, key=lambda n: n.updated_at, reverse=True)
        elif self.sort_order == SortOrder.UPDATED_ASC:
            return sorted(notes, key=lambda n: n.updated_at)
        return notes

    def _refresh_events(self):
        """Refresh the events list for the current date."""
        table = self.query_one("#events-table", DataTable)
        table.clear()

        # Update date header
        date_label = self.query_one("#current-date", Static)
        date_label.update(self._format_date_header())
        
        # Update view button text
        view_btn = self.query_one("#view-btn", Button)
        view_btn.label = "Day" if self.view_mode == ViewMode.WEEK else "Week"

        # Get events for the current day
        self.events = self.calendar.get_events_for_day(self.current_date)

        if not self.events:
            table.add_row("", "[dim]No events for this day[/]", "", "", "", key="empty")
        else:
            for event in self.events:
                # Check if note exists for this event and get tags
                note = self.note_manager.find_note_for_event(event.event_id)
                note_marker = "[green]✓[/]" if note else ""
                
                # Format tags from the note
                if note and note.tags:
                    tags_str = " ".join(f"[yellow]#{t}[/]" for t in note.tags[:2])
                    if len(note.tags) > 2:
                        tags_str += f" [dim]+{len(note.tags) - 2}[/]"
                else:
                    tags_str = "[dim]-[/]"
                
                # Get calendar color
                cal_color = self._get_calendar_color(event.calendar_name)
                cal_display = f"[{cal_color}]●[/] {event.calendar_name[:10]}" + ("…" if len(event.calendar_name) > 12 else "")

                table.add_row(
                    event.time_str,
                    event.title[:30] + "…" if len(event.title) > 32 else event.title,
                    cal_display,
                    tags_str,
                    note_marker,
                    key=event.event_id,
                )

        # Reset selection
        self.selected_event = None
        self.query_one("#event-detail", EventDetailPanel).update_event(None)

    def _refresh_notes(self):
        """Refresh the notes list."""
        table = self.query_one("#notes-table", DataTable)
        table.clear()

        self.notes = self._sort_notes(self.note_manager.get_all_notes())

        if not self.notes:
            table.add_row("", "[dim]No notes yet. Press 'n' to create one.[/]", "", "", "", key="empty")
        else:
            for note in self.notes:
                note_type = "[cyan]📅[/]" if note.is_event_note else "[green]📝[/]"
                date_str = note.event_date.strftime("%Y-%m-%d") if note.event_date else note.created_at.strftime("%Y-%m-%d")
                updated_str = note.updated_at.strftime("%Y-%m-%d")
                
                # Format tags for display
                if note.tags:
                    tags_str = " ".join(f"[yellow]#{t}[/]" for t in note.tags[:3])
                    if len(note.tags) > 3:
                        tags_str += f" [dim]+{len(note.tags) - 3}[/]"
                else:
                    tags_str = "[dim]-[/]"

                table.add_row(
                    note_type,
                    note.title[:28] + "…" if len(note.title) > 30 else note.title,
                    tags_str,
                    date_str,
                    updated_str,
                    key=str(note.filepath),
                )
        
        # Reset note detail
        self.selected_note = None
        self.query_one("#note-detail", NoteDetailPanel).update_note(None)

    def _refresh_todos(self):
        """Refresh the todos list."""
        table = self.query_one("#todos-table", DataTable)
        table.clear()

        self.todos = self.note_manager.get_all_todos()
        
        # Update count display
        count_label = self.query_one("#todos-count", Static)
        count_label.update(f"[dim]{len(self.todos)} todo{'s' if len(self.todos) != 1 else ''}[/]")

        if not self.todos:
            table.add_row("", "[dim]No todos found. Add #todo lines to your notes.[/]", "", "", key="empty")
        else:
            for idx, todo in enumerate(self.todos):
                todo_text = todo.content[:38] + "…" if len(todo.content) > 40 else todo.content
                if not todo_text:
                    todo_text = "[dim](empty)[/]"
                note_name = todo.note_title[:23] + "…" if len(todo.note_title) > 25 else todo.note_title
                
                table.add_row(
                    "[yellow]☐[/]",
                    todo_text,
                    f"[dim]{note_name}[/]",
                    f"[dim]{todo.line_number}[/]",
                    key=f"todo_{idx}",
                )
        
        # Reset todo detail
        self.selected_todo = None
        self.query_one("#todo-detail", TodoDetailPanel).update_todo(None)

    @on(DataTable.RowSelected, "#events-table")
    def on_event_selected(self, event: DataTable.RowSelected):
        """Handle event selection in the table - opens note for the event."""
        if event.row_key and event.row_key.value != "empty":
            # Find the selected event
            for cal_event in self.events:
                if cal_event.event_id == event.row_key.value:
                    self.selected_event = cal_event
                    cal_color = self._get_calendar_color(cal_event.calendar_name)
                    self.query_one("#event-detail", EventDetailPanel).update_event(cal_event, cal_color)
                    # Open or create note for this event
                    filepath = self.note_manager.get_or_create_note_for_event(cal_event)
                    self._open_in_editor(filepath)
                    break

    @on(DataTable.RowHighlighted, "#events-table")
    def on_event_highlighted(self, event: DataTable.RowHighlighted):
        """Update detail panel when row is highlighted."""
        if event.row_key and event.row_key.value != "empty":
            for cal_event in self.events:
                if cal_event.event_id == event.row_key.value:
                    self.selected_event = cal_event
                    cal_color = self._get_calendar_color(cal_event.calendar_name)
                    self.query_one("#event-detail", EventDetailPanel).update_event(cal_event, cal_color)
                    break

    @on(DataTable.RowSelected, "#notes-table")
    def on_note_selected(self, event: DataTable.RowSelected):
        """Handle note selection - open in editor."""
        if event.row_key and event.row_key.value != "empty":
            filepath = Path(event.row_key.value)
            self._open_in_editor(filepath)

    @on(DataTable.RowHighlighted, "#notes-table")
    def on_note_highlighted(self, event: DataTable.RowHighlighted):
        """Update note detail panel when row is highlighted."""
        if event.row_key and event.row_key.value != "empty":
            filepath = Path(event.row_key.value)
            for note in self.notes:
                if note.filepath == filepath:
                    self.selected_note = note
                    self.query_one("#note-detail", NoteDetailPanel).update_note(note)
                    break

    @on(DataTable.RowSelected, "#todos-table")
    def on_todo_selected(self, event: DataTable.RowSelected):
        """Handle todo selection - open the note containing the todo."""
        if event.row_key and event.row_key.value != "empty":
            # Extract index from key (format: "todo_N")
            try:
                idx = int(event.row_key.value.split("_")[1])
                if idx < len(self.todos):
                    todo = self.todos[idx]
                    self._open_in_editor(todo.filepath)
            except (ValueError, IndexError):
                pass

    @on(DataTable.RowHighlighted, "#todos-table")
    def on_todo_highlighted(self, event: DataTable.RowHighlighted):
        """Update todo detail panel when row is highlighted."""
        if event.row_key and event.row_key.value != "empty":
            try:
                idx = int(event.row_key.value.split("_")[1])
                if idx < len(self.todos):
                    self.selected_todo = self.todos[idx]
                    self.query_one("#todo-detail", TodoDetailPanel).update_todo(self.selected_todo)
            except (ValueError, IndexError):
                pass

    def _complete_todo(self, todo: TodoItem):
        """Complete a todo by removing it from the file."""
        if self.note_manager.complete_todo(todo):
            self.notify(f"Completed: {todo.content[:30]}..." if len(todo.content) > 30 else f"Completed: {todo.content}", severity="information")
            self._refresh_todos()
        else:
            self.notify("Failed to complete todo - file may have changed", severity="error")

    @on(Button.Pressed, "#prev-day-btn")
    def on_prev_day_btn(self):
        self.action_prev_day()

    @on(Button.Pressed, "#next-day-btn")
    def on_next_day_btn(self):
        self.action_next_day()

    @on(Button.Pressed, "#prev-week-btn")
    def on_prev_week_btn(self):
        self.action_prev_week()

    @on(Button.Pressed, "#next-week-btn")
    def on_next_week_btn(self):
        self.action_next_week()

    @on(Button.Pressed, "#today-btn")
    def on_today_btn(self):
        self.action_today()

    @on(Button.Pressed, "#view-btn")
    def on_view_btn(self):
        self.action_toggle_view()

    @on(Button.Pressed, "#sort-btn")
    def on_sort_btn(self):
        self.action_sort_notes()

    @on(Button.Pressed, "#search-btn")
    def on_search_btn(self):
        self.action_search()

    @on(Button.Pressed, "#refresh-todos-btn")
    def on_refresh_todos_btn(self):
        self._refresh_todos()
        self.notify("Todos refreshed", timeout=1)

    def _open_in_editor(self, filepath: Path):
        """Open a note file in the configured editor."""
        editor_cmd = get_editor()
        editor_name = get_editor_name()
        
        try:
            # Suspend the TUI and open editor
            with self.suspend():
                subprocess.run(editor_cmd + [str(filepath)])
            # Refresh after returning from editor
            self._refresh_events()
            self._refresh_notes()
        except FileNotFoundError:
            self.notify(f"{editor_name} not found. Set $EDITOR or install {editor_name}.", severity="error")
        except Exception as e:
            self.notify(f"Error opening {editor_name}: {e}", severity="error")

    def action_open_note(self):
        """Open or create a note for the selected event."""
        # Check which tab is active
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "notes-tab":
            # On notes tab - get selected note
            table = self.query_one("#notes-table", DataTable)
            if table.cursor_row is not None:
                row_key = table.get_row_at(table.cursor_row)
                if row_key:
                    coord = table.cursor_coordinate
                    cell_key = table.coordinate_to_cell_key(coord)
                    if cell_key.row_key.value != "empty":
                        filepath = Path(cell_key.row_key.value)
                        self._open_in_editor(filepath)
        else:
            # On events tab
            if self.selected_event:
                filepath = self.note_manager.get_or_create_note_for_event(self.selected_event)
                self._open_in_editor(filepath)
            else:
                self.notify("Select an event first", severity="warning")

    def action_new_note(self):
        """Create a new standalone note."""
        def handle_result(title: Optional[str]):
            if title:
                filepath = self.note_manager.create_standalone_note(title)
                self._refresh_notes()
                self._open_in_editor(filepath)

        self.push_screen(NewNoteModal(), handle_result)

    def action_search(self):
        """Open search modal."""
        def handle_result(filepath: Optional[str]):
            if filepath:
                self._open_in_editor(Path(filepath))

        self.push_screen(SearchModal(self.note_manager), handle_result)

    def action_delete_note(self):
        """Delete the selected note with confirmation."""
        tabbed = self.query_one(TabbedContent)
        if tabbed.active != "notes-tab":
            self.notify("Switch to Notes tab to delete notes", severity="warning")
            return

        if not self.selected_note:
            self.notify("Select a note first", severity="warning")
            return

        note_to_delete = self.selected_note

        def handle_result(confirmed: bool):
            if confirmed:
                if self.note_manager.delete_note(note_to_delete):
                    self.notify(f"Deleted: {note_to_delete.title}", severity="information")
                    self._refresh_notes()
                    self._refresh_events()  # Update note markers
                else:
                    self.notify("Failed to delete note", severity="error")

        self.push_screen(DeleteConfirmModal(note_to_delete.title), handle_result)

    def action_sort_notes(self):
        """Open sort order modal."""
        def handle_result(sort_order: Optional[SortOrder]):
            if sort_order:
                self.sort_order = sort_order
                self._update_sort_info()
                self._refresh_notes()

        self.push_screen(SortModal(self.sort_order), handle_result)

    def action_toggle_view(self):
        """Toggle between day and week view."""
        if self.view_mode == ViewMode.DAY:
            self.view_mode = ViewMode.WEEK
            self.notify("Week view - use arrow keys to navigate days", timeout=2)
        else:
            self.view_mode = ViewMode.DAY
        self._refresh_events()

    def action_refresh(self):
        """Refresh events and notes."""
        self._refresh_events()
        self._refresh_notes()
        self.notify("Refreshed", timeout=1)

    def action_prev_day(self):
        """Go to previous day."""
        self.current_date -= timedelta(days=1)
        self._refresh_events()

    def action_next_day(self):
        """Go to next day."""
        self.current_date += timedelta(days=1)
        self._refresh_events()

    def action_prev_week(self):
        """Go to previous week."""
        self.current_date -= timedelta(weeks=1)
        self._refresh_events()

    def action_next_week(self):
        """Go to next week."""
        self.current_date += timedelta(weeks=1)
        self._refresh_events()

    def action_today(self):
        """Go to today."""
        self.current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._refresh_events()

    def action_goto_date(self):
        """Open date picker to go to a specific date."""
        def handle_result(date: Optional[datetime]):
            if date:
                self.current_date = date
                self._refresh_events()

        self.push_screen(DatePickerModal(), handle_result)

    def action_show_help(self):
        """Show help information."""
        editor_name = get_editor_name()
        self.notify(
            f"Keys: Enter/o=Open ({editor_name}), n=New note, s=Search, d=Delete, "
            f"S=Sort, v=View, t=Today, ←/→=Day, w/b=Week, g=Go to Date, "
            f"1=Calendar, 2=Notes, 3=Todos, Space=Complete todo, q=Quit",
            timeout=10,
        )

    def action_switch_tab(self):
        """Cycle through Calendar Events, All Notes, and Todos tabs."""
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "events-tab":
            self.action_show_notes()
        elif tabbed.active == "notes-tab":
            self.action_show_todos()
        else:
            self.action_show_calendar()

    def action_show_calendar(self):
        """Switch to Calendar Events tab."""
        tabbed = self.query_one(TabbedContent)
        tabbed.active = "events-tab"
        self.query_one("#events-table", DataTable).focus()

    def action_show_notes(self):
        """Switch to All Notes tab."""
        tabbed = self.query_one(TabbedContent)
        tabbed.active = "notes-tab"
        self.query_one("#notes-table", DataTable).focus()

    def action_show_todos(self):
        """Switch to Todos tab."""
        tabbed = self.query_one(TabbedContent)
        tabbed.active = "todos-tab"
        self._refresh_todos()  # Refresh when switching to tab
        self.query_one("#todos-table", DataTable).focus()

    def action_complete_todo(self):
        """Complete the selected todo (removes the line from file)."""
        tabbed = self.query_one(TabbedContent)
        if tabbed.active != "todos-tab":
            return
        
        if self.selected_todo:
            self._complete_todo(self.selected_todo)
        else:
            self.notify("Select a todo first", severity="warning")


def main():
    """Run the Calendar Notes TUI application."""
    app = CalendarNotesApp()
    app.run()


if __name__ == "__main__":
    main()
