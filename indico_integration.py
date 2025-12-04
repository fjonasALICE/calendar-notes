"""
Indico meeting system integration.
Fetches meeting agendas from Indico links found in event descriptions.

Authentication:
    - Set INDICO_API_KEY environment variable with your personal API token
    - Generate token at: Indico → User Settings → API Tokens
    - For CERN: https://indico.cern.ch/user/api-keys/

The module will try to fetch agendas without authentication first (for public events),
then fall back to using the API key if available.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
import requests


@dataclass
class IndicoContribution:
    """Represents a single contribution/talk in an Indico meeting."""
    title: str
    speakers: list[str] = field(default_factory=list)
    start_time: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    material_url: Optional[str] = None


@dataclass
class IndicoAgenda:
    """Represents a meeting agenda from Indico."""
    event_id: str
    title: str
    description: Optional[str] = None
    contributions: list[IndicoContribution] = field(default_factory=list)
    url: str = ""
    fetched: bool = True
    error: Optional[str] = None


class IndicoClient:
    """Client for fetching meeting agendas from Indico."""

    # Regex patterns for Indico URLs
    # Matches: https://indico.cern.ch/event/1609411/ or similar
    INDICO_URL_PATTERN = re.compile(
        r'https?://([^/]+)/event/(\d+)/?',
        re.IGNORECASE
    )

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        """
        Initialize the Indico client.

        Args:
            api_key: Indico API key (defaults to INDICO_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("INDICO_API_KEY")
        self.timeout = timeout

    def find_indico_urls(self, text: str) -> list[tuple[str, str, str]]:
        """
        Find Indico event URLs in text.

        Args:
            text: Text to search for Indico URLs

        Returns:
            List of tuples: (full_url, host, event_id)
        """
        if not text:
            return []

        matches = self.INDICO_URL_PATTERN.findall(text)
        results = []
        for match in self.INDICO_URL_PATTERN.finditer(text):
            full_url = match.group(0)
            host = match.group(1)
            event_id = match.group(2)
            results.append((full_url, host, event_id))

        return results

    def _get_headers(self) -> dict:
        """Get request headers, including auth if API key is set."""
        headers = {
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _fetch_json(self, url: str, use_auth: bool = True) -> Optional[dict]:
        """
        Fetch JSON from URL.

        Args:
            url: URL to fetch
            use_auth: Whether to include authentication headers

        Returns:
            JSON data or None if request failed
        """
        headers = self._get_headers() if use_auth else {"Accept": "application/json"}
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None

    def _parse_speakers(self, speakers_data: list) -> list[str]:
        """Extract speaker names from Indico API response."""
        names = []
        for speaker in speakers_data or []:
            if isinstance(speaker, dict):
                # Try different fields that might contain the name
                # fullName is the most common in newer API responses (format: "Last, First")
                # full_name and name are alternatives
                name = speaker.get("fullName") or speaker.get("full_name") or speaker.get("name")
                if name:
                    # Convert "Last, First" to "First Last" for readability
                    if ", " in str(name):
                        parts = str(name).split(", ", 1)
                        if len(parts) == 2:
                            name = f"{parts[1]} {parts[0]}"
                    names.append(str(name))
            elif isinstance(speaker, str):
                names.append(speaker)
        return names

    def _parse_duration(self, minutes: Optional[int]) -> Optional[str]:
        """Convert duration in minutes to human-readable string."""
        if not minutes:
            return None
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h {mins}m" if mins else f"{hours}h"
        return f"{minutes}m"

    def _parse_contributions_from_timetable(self, timetable: dict) -> list[IndicoContribution]:
        """Parse contributions from timetable export format."""
        contributions = []
        entries = []

        # Timetable format can vary - it might be a dict with day keys
        # or a flat list of entries. Sessions contain nested 'entries'.
        def extract_entries(data, parent_session=None):
            if isinstance(data, dict):
                entry_type = data.get("entryType", "")
                
                # If this is a session, extract its nested entries
                if entry_type == "Session":
                    session_title = data.get("title") or data.get("slotTitle")
                    nested_entries = data.get("entries", {})
                    if nested_entries:
                        extract_entries(nested_entries, parent_session=session_title)
                    # Don't add the session itself as a contribution
                    return
                
                # If this is a contribution, add it
                if entry_type == "Contribution":
                    entry_copy = dict(data)
                    if parent_session:
                        entry_copy["_parent_session"] = parent_session
                    entries.append(entry_copy)
                    return
                
                # Otherwise recurse into nested structures (date dicts, entry collections, etc.)
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        extract_entries(value, parent_session)
                    
            elif isinstance(data, list):
                for item in data:
                    extract_entries(item, parent_session)

        extract_entries(timetable)

        for entry in entries:
            entry_type = entry.get("entryType", "").lower()
            title = entry.get("title", "")

            # Skip session entries (should already be filtered, but just in case)
            if entry_type == "session":
                continue

            if not title:
                continue

            speakers = self._parse_speakers(entry.get("speakers", []) or entry.get("presenters", []))
            start_time = entry.get("startDate", {}).get("time") if isinstance(entry.get("startDate"), dict) else None
            duration = self._parse_duration(entry.get("duration"))
            
            # Include session context in title if available
            parent_session = entry.get("_parent_session")

            contributions.append(IndicoContribution(
                title=title,
                speakers=speakers,
                start_time=start_time,
                duration=duration,
                description=entry.get("description"),
            ))

        # Sort by start time
        contributions.sort(key=lambda c: c.start_time or "")

        return contributions

    def _parse_contributions_from_event(self, event_data: dict) -> list[IndicoContribution]:
        """Parse contributions from event export format."""
        contributions = []

        # Event format typically has 'contributions' key
        contribs = event_data.get("contributions", [])
        if not contribs:
            # Try 'results' wrapper
            results = event_data.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                contribs = results[0].get("contributions", [])

        for contrib in contribs:
            title = contrib.get("title", "")
            if not title:
                continue

            speakers = self._parse_speakers(contrib.get("speakers", []) or contrib.get("presenters", []))
            start_time = contrib.get("startDate", {}).get("time") if isinstance(contrib.get("startDate"), dict) else None
            duration = self._parse_duration(contrib.get("duration"))

            contributions.append(IndicoContribution(
                title=title,
                speakers=speakers,
                start_time=start_time,
                duration=duration,
                description=contrib.get("description"),
            ))

        # Sort by start time
        contributions.sort(key=lambda c: c.start_time or "99:99:99")

        return contributions

    def fetch_agenda(self, host: str, event_id: str) -> IndicoAgenda:
        """
        Fetch meeting agenda from Indico.

        Args:
            host: Indico host (e.g., 'indico.cern.ch')
            event_id: Event ID

        Returns:
            IndicoAgenda with contributions or error info
        """
        base_url = f"https://{host}"
        event_url = f"{base_url}/event/{event_id}/"

        # Use event export with detail=contributions (cleaner API)
        # Also try detail=sessions which includes session grouping
        event_contrib_url = f"{base_url}/export/event/{event_id}.json?detail=contributions"
        event_sessions_url = f"{base_url}/export/event/{event_id}.json?detail=sessions"
        timetable_url = f"{base_url}/export/timetable/{event_id}.json"

        # Try without auth first (for public events), then with auth
        for use_auth in [False, True] if self.api_key else [False]:
            # Try event export with detail=contributions first (cleanest format)
            data = self._fetch_json(event_contrib_url, use_auth=use_auth)
            if data:
                results = data.get("results", [])
                if results and isinstance(results, list) and len(results) > 0:
                    event_data = results[0]
                    contributions = self._parse_contributions_from_event(event_data)
                    if contributions:
                        return IndicoAgenda(
                            event_id=event_id,
                            title=event_data.get("title", f"Event {event_id}"),
                            description=event_data.get("description"),
                            contributions=contributions,
                            url=event_url,
                        )

            # Try event export with detail=sessions (includes session-grouped contribs)
            data = self._fetch_json(event_sessions_url, use_auth=use_auth)
            if data:
                results = data.get("results", [])
                if results and isinstance(results, list) and len(results) > 0:
                    event_data = results[0]
                    contributions = self._parse_contributions_from_event(event_data)
                    if contributions:
                        return IndicoAgenda(
                            event_id=event_id,
                            title=event_data.get("title", f"Event {event_id}"),
                            description=event_data.get("description"),
                            contributions=contributions,
                            url=event_url,
                        )

            # Try timetable export as fallback (more complex nested structure)
            data = self._fetch_json(timetable_url, use_auth=use_auth)
            if data:
                results = data.get("results", {})
                if results:
                    # Timetable results is a dict keyed by event_id
                    if isinstance(results, dict):
                        timetable_data = results.get(event_id, results)
                    else:
                        timetable_data = results[0] if results else {}
                    
                    contributions = self._parse_contributions_from_timetable(timetable_data)
                    if contributions:
                        return IndicoAgenda(
                            event_id=event_id,
                            title=f"Event {event_id}",
                            description=None,
                            contributions=contributions,
                            url=event_url,
                        )

        # Could not fetch agenda with contributions - return basic info
        # Try one more time to at least get the event title
        data = self._fetch_json(f"{base_url}/export/event/{event_id}.json", use_auth=bool(self.api_key))
        if data:
            results = data.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                event_data = results[0]
                return IndicoAgenda(
                    event_id=event_id,
                    title=event_data.get("title", f"Event {event_id}"),
                    description=event_data.get("description"),
                    contributions=[],
                    url=event_url,
                )

        # Could not fetch agenda at all
        return IndicoAgenda(
            event_id=event_id,
            title=f"Event {event_id}",
            url=event_url,
            fetched=False,
            error="Could not fetch agenda. Event may require authentication.",
        )

    def fetch_agenda_from_url(self, url: str) -> Optional[IndicoAgenda]:
        """
        Fetch agenda from an Indico URL.

        Args:
            url: Full Indico event URL

        Returns:
            IndicoAgenda or None if URL is not valid
        """
        matches = self.find_indico_urls(url)
        if not matches:
            return None

        _, host, event_id = matches[0]
        return self.fetch_agenda(host, event_id)


def format_agenda_markdown(agenda: IndicoAgenda) -> str:
    """
    Format an Indico agenda as markdown.

    Args:
        agenda: IndicoAgenda to format

    Returns:
        Markdown string
    """
    lines = ["## Indico Agenda", ""]
    lines.append(f"📅 [View on Indico]({agenda.url})")
    lines.append("")

    if not agenda.fetched:
        lines.append(f"> ⚠️ {agenda.error}")
        lines.append("> ")
        lines.append("> To enable agenda fetching, set `INDICO_API_KEY` environment variable")
        lines.append("> with your personal API token from Indico → User Settings → API Tokens")
        lines.append("")
        return "\n".join(lines)

    if agenda.description:
        lines.append(f"> {agenda.description}")
        lines.append("")

    if not agenda.contributions:
        lines.append("*No contributions/talks found in this event.*")
        lines.append("")
        return "\n".join(lines)

    for i, contrib in enumerate(agenda.contributions, 1):
        # Title with optional time
        if contrib.start_time:
            lines.append(f"**{contrib.start_time}** - {contrib.title}")
        else:
            lines.append(f"**{i}.** {contrib.title}")

        # Speakers
        if contrib.speakers:
            speakers_str = ", ".join(contrib.speakers)
            lines.append(f"   - *Speakers*: {speakers_str}")

        # Duration
        if contrib.duration:
            lines.append(f"   - *Duration*: {contrib.duration}")

        lines.append("")

    return "\n".join(lines)


def get_agenda_for_description(description: str) -> Optional[str]:
    """
    Check if description contains an Indico URL and fetch the agenda.

    Args:
        description: Event description text

    Returns:
        Formatted markdown agenda or None if no Indico URL found
    """
    if not description:
        return None

    client = IndicoClient()
    urls = client.find_indico_urls(description)

    if not urls:
        return None

    # Fetch agenda for the first Indico URL found
    full_url, host, event_id = urls[0]
    agenda = client.fetch_agenda(host, event_id)

    return format_agenda_markdown(agenda)


if __name__ == "__main__":
    # Test the Indico integration
    print("Testing Indico Integration")
    print("=" * 50)

    # Test URL detection
    test_text = """
    Speakers: David d'Enterria (CERN)
    https://indico.cern.ch/event/1609411/
    Zoom: https://cern.zoom.us/j/61216079456
    """

    client = IndicoClient()
    urls = client.find_indico_urls(test_text)

    print(f"\nFound Indico URLs: {urls}")

    if urls:
        full_url, host, event_id = urls[0]
        print(f"\nFetching agenda for event {event_id} from {host}...")

        agenda = client.fetch_agenda(host, event_id)
        print(f"\nAgenda fetched: {agenda.fetched}")
        print(f"Title: {agenda.title}")
        print(f"Contributions: {len(agenda.contributions)}")

        if agenda.contributions:
            print("\nContributions:")
            for contrib in agenda.contributions:
                print(f"  - {contrib.title}")
                if contrib.speakers:
                    print(f"    Speakers: {', '.join(contrib.speakers)}")

        print("\n" + "=" * 50)
        print("Formatted Markdown:")
        print("=" * 50)
        print(format_agenda_markdown(agenda))

