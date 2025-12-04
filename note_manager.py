"""
Note management system for calendar-linked and standalone notes.
Notes are stored as markdown files with YAML frontmatter.
"""

import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from calendar_integration import CalendarEvent
from indico_integration import get_agenda_for_description


@dataclass
class TodoItem:
    """Represents a single todo item found in a markdown file."""
    filepath: Path
    line_number: int  # 1-based line number
    content: str  # The todo text (without the #todo prefix)
    full_line: str  # The complete original line
    note_title: str  # Title of the note containing this todo

    @property
    def display_text(self) -> str:
        """Get the display text for the todo."""
        return self.content.strip()


@dataclass
class Note:
    """Represents a note with optional calendar event association."""
    filepath: Path
    title: str
    created_at: datetime
    updated_at: datetime
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    event_date: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)

    @property
    def is_event_note(self) -> bool:
        """Check if this note is associated with a calendar event."""
        return self.event_id is not None

    @property
    def filename(self) -> str:
        """Get the filename without path."""
        return self.filepath.name

    @property
    def relative_path(self) -> str:
        """Get the relative path from notes root."""
        return str(self.filepath)


class NoteManager:
    """Manages note creation, storage, and retrieval."""

    NOTES_DIR = "notes"
    EVENT_NOTES_DIR = "events"
    STANDALONE_DIR = "standalone"

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize the note manager.

        Args:
            base_path: Base directory for notes storage (defaults to current directory)
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        (self.base_path / self.NOTES_DIR / self.EVENT_NOTES_DIR).mkdir(
            parents=True, exist_ok=True
        )
        (self.base_path / self.NOTES_DIR / self.STANDALONE_DIR).mkdir(
            parents=True, exist_ok=True
        )

    def _sanitize_filename(self, name: str) -> str:
        """Convert a string to a safe filename."""
        # Remove or replace problematic characters
        safe = re.sub(r'[^\w\s\-]', '', name)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:100]  # Limit length

    def _generate_event_filename(self, event: CalendarEvent) -> str:
        """Generate a filename for an event note."""
        date_str = event.start_date.strftime("%Y-%m-%d")
        time_str = event.start_date.strftime("%H%M") if not event.is_all_day else "allday"
        # Convert to plain Python string before sanitizing
        title_safe = self._sanitize_filename(str(event.title))
        return f"{date_str}_{time_str}_{title_safe}.md"

    def _generate_standalone_filename(self, title: str) -> str:
        """Generate a filename for a standalone note."""
        date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        title_safe = self._sanitize_filename(title)
        return f"{date_str}_{title_safe}.md"

    def _to_python_str(self, value) -> Optional[str]:
        """Convert any string-like value to plain Python str (handles NSString from pyobjc)."""
        if value is None:
            return None
        return str(value)

    def _create_frontmatter(
        self,
        title: str,
        event: Optional[CalendarEvent] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Create YAML frontmatter for a note."""
        now = datetime.now().isoformat()
        frontmatter = {
            "title": self._to_python_str(title),
            "created": now,
            "updated": now,
            "tags": tags or [],
        }

        if event:
            frontmatter["event"] = {
                "id": self._to_python_str(event.event_id),
                "title": self._to_python_str(event.title),
                "date": event.start_date.isoformat(),
                "calendar": self._to_python_str(event.calendar_name),
                "location": self._to_python_str(event.location),
                "all_day": bool(event.is_all_day),
            }

        return yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)

    def _create_note_template(
        self,
        title: str,
        event: Optional[CalendarEvent] = None,
    ) -> str:
        """Create a note template with frontmatter and structure."""
        # Convert title to plain Python string
        title = self._to_python_str(title)
        frontmatter = self._create_frontmatter(title, event)

        if event:
            # Convert all event strings to plain Python strings
            calendar_name = self._to_python_str(event.calendar_name)
            location = self._to_python_str(event.location)
            notes = self._to_python_str(event.notes)
            
            content = f"""---
{frontmatter}---

# {title}

## Event Details

- **Date**: {event.date_str}
- **Time**: {event.time_str}
- **Duration**: {event.duration_str}
- **Calendar**: {calendar_name}
"""
            if location:
                content += f"- **Location**: {location}\n"

            content += """
## Notes

"""
            if notes:
                content += f"> {notes}\n\n"

            # Try to fetch Indico agenda if there's an Indico link in the notes
            agenda_markdown = None
            try:
                agenda_markdown = get_agenda_for_description(notes)
            except Exception:
                # Don't fail note creation if Indico fetch fails
                pass

            if agenda_markdown:
                content += agenda_markdown + "\n"

            content += """## Action Items

- [ ] 

## Summary

"""
        else:
            content = f"""---
{frontmatter}---

# {title}

## Notes

"""

        return content

    def create_note_for_event(self, event: CalendarEvent) -> Path:
        """
        Create a new note for a calendar event.

        Args:
            event: The calendar event to create a note for

        Returns:
            Path to the created note file
        """
        filename = self._generate_event_filename(event)
        filepath = self.base_path / self.NOTES_DIR / self.EVENT_NOTES_DIR / filename

        # Check if note already exists
        if filepath.exists():
            return filepath

        content = self._create_note_template(event.title, event)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def create_standalone_note(self, title: str, tags: Optional[list[str]] = None) -> Path:
        """
        Create a new standalone note not associated with any event.

        Args:
            title: Title for the note
            tags: Optional list of tags

        Returns:
            Path to the created note file
        """
        filename = self._generate_standalone_filename(title)
        filepath = self.base_path / self.NOTES_DIR / self.STANDALONE_DIR / filename

        frontmatter = self._create_frontmatter(title, tags=tags)
        content = f"""---
{frontmatter}---

# {title}

## Notes

"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def _parse_frontmatter(self, content: str) -> Optional[dict]:
        """Parse YAML frontmatter from note content."""
        if not content.startswith("---"):
            return None

        try:
            # Find the closing ---
            end_idx = content.find("---", 3)
            if end_idx == -1:
                return None

            frontmatter_str = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter_str)
        except yaml.YAMLError:
            return None

    def _load_note(self, filepath: Path) -> Optional[Note]:
        """Load a note from a file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter = self._parse_frontmatter(content)
            if not frontmatter:
                # Note without frontmatter - use filename as title
                return Note(
                    filepath=filepath,
                    title=filepath.stem,
                    created_at=datetime.fromtimestamp(filepath.stat().st_ctime),
                    updated_at=datetime.fromtimestamp(filepath.stat().st_mtime),
                )

            event_data = frontmatter.get("event", {})

            return Note(
                filepath=filepath,
                title=frontmatter.get("title", filepath.stem),
                created_at=datetime.fromisoformat(frontmatter.get("created", datetime.now().isoformat())),
                updated_at=datetime.fromisoformat(frontmatter.get("updated", datetime.now().isoformat())),
                event_id=event_data.get("id"),
                event_title=event_data.get("title"),
                event_date=datetime.fromisoformat(event_data["date"]) if event_data.get("date") else None,
                tags=frontmatter.get("tags", []),
            )
        except Exception:
            return None

    def get_all_notes(self) -> list[Note]:
        """Get all notes from both event and standalone directories."""
        notes = []
        notes_root = self.base_path / self.NOTES_DIR

        for md_file in notes_root.rglob("*.md"):
            note = self._load_note(md_file)
            if note:
                notes.append(note)

        # Sort by updated date, newest first
        notes.sort(key=lambda n: n.updated_at, reverse=True)
        return notes

    def get_event_notes(self) -> list[Note]:
        """Get all notes associated with calendar events."""
        notes = []
        events_dir = self.base_path / self.NOTES_DIR / self.EVENT_NOTES_DIR

        for md_file in events_dir.glob("*.md"):
            note = self._load_note(md_file)
            if note:
                notes.append(note)

        notes.sort(key=lambda n: n.event_date or n.created_at, reverse=True)
        return notes

    def get_standalone_notes(self) -> list[Note]:
        """Get all standalone notes."""
        notes = []
        standalone_dir = self.base_path / self.NOTES_DIR / self.STANDALONE_DIR

        for md_file in standalone_dir.glob("*.md"):
            note = self._load_note(md_file)
            if note:
                notes.append(note)

        notes.sort(key=lambda n: n.updated_at, reverse=True)
        return notes

    def find_note_for_event(self, event_id: str) -> Optional[Note]:
        """Find an existing note for a calendar event."""
        for note in self.get_event_notes():
            if note.event_id == event_id:
                return note
        return None

    def get_or_create_note_for_event(self, event: CalendarEvent) -> Path:
        """
        Get an existing note for an event, or create a new one.

        Args:
            event: The calendar event

        Returns:
            Path to the note file
        """
        existing = self.find_note_for_event(event.event_id)
        if existing:
            return existing.filepath
        return self.create_note_for_event(event)

    def search_notes(self, query: str) -> list[Note]:
        """Search notes by title and content (exact substring match)."""
        query_lower = query.lower()
        results = []

        for note in self.get_all_notes():
            # Check title
            if query_lower in note.title.lower():
                results.append(note)
                continue

            # Check content
            try:
                with open(note.filepath, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                if query_lower in content:
                    results.append(note)
            except Exception:
                pass

        return results

    def fuzzy_search_notes(self, query: str, threshold: int = 40) -> list[tuple[Note, int, Optional[str]]]:
        """
        Fuzzy search notes by title and content.
        
        Args:
            query: The search query
            threshold: Minimum fuzzy match score (0-100) to include in results
            
        Returns:
            List of tuples (note, score, matched_context) sorted by score descending.
            matched_context contains a snippet of the matched content if found in content.
        """
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            # Fall back to simple search if rapidfuzz not installed
            return [(note, 100, None) for note in self.search_notes(query)]
        
        if not query or len(query) < 1:
            return []
        
        results: list[tuple[Note, int, Optional[str]]] = []
        all_notes = self.get_all_notes()
        
        for note in all_notes:
            best_score = 0
            matched_context = None
            
            # Score the title with fuzzy matching
            title_score = fuzz.partial_ratio(query.lower(), note.title.lower())
            if title_score > best_score:
                best_score = title_score
                matched_context = None  # Title match, no context needed
            
            # Also check for token-based matching (handles word order differences)
            token_score = fuzz.token_set_ratio(query.lower(), note.title.lower())
            if token_score > best_score:
                best_score = token_score
                matched_context = None
            
            # Check content for fuzzy matches
            try:
                with open(note.filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Skip frontmatter
                if content.startswith("---"):
                    end_idx = content.find("---", 3)
                    if end_idx != -1:
                        content = content[end_idx + 3:]
                
                # Search in lines for better context
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    line_stripped = line.strip()
                    if len(line_stripped) < 3:  # Skip very short lines
                        continue
                    
                    # Score this line
                    line_score = fuzz.partial_ratio(query.lower(), line_stripped.lower())
                    
                    if line_score > best_score:
                        best_score = line_score
                        # Create context: show the matched line with surrounding context
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        context_lines = lines[start:end]
                        matched_context = ' '.join(l.strip() for l in context_lines if l.strip())
                        if len(matched_context) > 100:
                            matched_context = matched_context[:100] + "..."
                
            except Exception:
                pass
            
            # Add to results if score meets threshold
            if best_score >= threshold:
                results.append((note, best_score, matched_context))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def delete_note(self, note: Note) -> bool:
        """Delete a note file."""
        try:
            note.filepath.unlink()
            return True
        except Exception:
            return False

    def get_all_todos(self) -> list[TodoItem]:
        """
        Scan all markdown files for lines containing #todo.
        
        Returns:
            List of TodoItem objects found across all notes.
        """
        todos = []
        notes_root = self.base_path / self.NOTES_DIR

        for md_file in notes_root.rglob("*.md"):
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                # Get note title from frontmatter or filename
                note = self._load_note(md_file)
                note_title = note.title if note else md_file.stem
                
                for line_num, line in enumerate(lines, start=1):
                    line_lower = line.lower()
                    # Check if line contains #todo anywhere (case-insensitive)
                    todo_idx = line_lower.find("#todo")
                    if todo_idx != -1:
                        # Extract everything after #todo
                        content = line[todo_idx + 5:].strip()
                        if content.startswith(":"):
                            content = content[1:].strip()  # Remove optional colon
                        
                        todos.append(TodoItem(
                            filepath=md_file,
                            line_number=line_num,
                            content=content,
                            full_line=line,
                            note_title=note_title,
                        ))
            except Exception:
                continue
        
        return todos

    def complete_todo(self, todo: TodoItem) -> bool:
        """
        Mark a todo as complete by removing its line from the markdown file.
        
        Args:
            todo: The TodoItem to complete
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            with open(todo.filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Verify the line still matches (in case file was modified)
            if todo.line_number <= len(lines):
                current_line = lines[todo.line_number - 1]
                if current_line.strip() == todo.full_line.strip():
                    # Remove the line
                    del lines[todo.line_number - 1]
                    
                    with open(todo.filepath, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    return True
            return False
        except Exception:
            return False


if __name__ == "__main__":
    # Test the note manager
    manager = NoteManager()

    # Create a standalone note
    path = manager.create_standalone_note("Test Note", tags=["test", "example"])
    print(f"Created standalone note: {path}")

    # List all notes
    print("\nAll notes:")
    for note in manager.get_all_notes():
        event_marker = "📅 " if note.is_event_note else "📝 "
        print(f"  {event_marker}{note.title} ({note.filename})")

