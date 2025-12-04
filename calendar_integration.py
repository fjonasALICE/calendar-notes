"""
Apple Calendar integration using EventKit via pyobjc.
Provides access to calendar events from macOS Calendar app.

For calendar access to work, you need to grant permission to Terminal (or your terminal app).
If the permission dialog doesn't appear, go to:
  System Settings → Privacy & Security → Calendar → Enable for Terminal
"""

from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import subprocess
import objc
from EventKit import (
    EKEventStore,
    EKEntityTypeEvent,
    EKAuthorizationStatusAuthorized,
    EKAuthorizationStatusNotDetermined,
    EKAuthorizationStatusDenied,
    EKAuthorizationStatusRestricted,
)
from Foundation import NSDate, NSRunLoop, NSDefaultRunLoopMode


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    event_id: str
    title: str
    start_date: datetime
    end_date: datetime
    calendar_name: str
    location: Optional[str] = None
    notes: Optional[str] = None
    is_all_day: bool = False

    @property
    def duration_str(self) -> str:
        """Return a formatted duration string."""
        if self.is_all_day:
            return "All day"
        duration = self.end_date - self.start_date
        hours, remainder = divmod(duration.seconds, 3600)
        minutes = remainder // 60
        if hours > 0:
            return f"{hours}h {minutes}m" if minutes else f"{hours}h"
        return f"{minutes}m"

    @property
    def time_str(self) -> str:
        """Return formatted time string."""
        if self.is_all_day:
            return "All day"
        return f"{self.start_date.strftime('%H:%M')} - {self.end_date.strftime('%H:%M')}"

    @property
    def date_str(self) -> str:
        """Return formatted date string."""
        return self.start_date.strftime("%Y-%m-%d")


class CalendarAccess:
    """Handles access to Apple Calendar via EventKit."""

    def __init__(self):
        self.event_store = EKEventStore.alloc().init()
        self._authorized = False

    def request_access(self) -> bool:
        """Request access to calendar. Returns True if access granted."""
        status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)

        if status == EKAuthorizationStatusAuthorized:
            self._authorized = True
            return True

        if status == EKAuthorizationStatusDenied or status == EKAuthorizationStatusRestricted:
            self._authorized = False
            return False

        if status == EKAuthorizationStatusNotDetermined:
            # Try multiple approaches to trigger the permission dialog
            
            # Approach 1: Use osascript to trigger calendar access
            # This reliably shows the permission dialog
            try:
                result = subprocess.run(
                    ["osascript", "-e", 'tell application "Calendar" to get name of calendars'],
                    capture_output=True,
                    timeout=30,
                )
                # If we got here without error, access was granted
                if result.returncode == 0:
                    self._authorized = True
                    return True
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass

            # Check if status changed after osascript attempt
            status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
            if status == EKAuthorizationStatusAuthorized:
                self._authorized = True
                return True

            # Approach 2: Try EventKit's native request as backup
            result = {"granted": False, "done": False}

            def completion_handler(granted_result, error_result):
                result["granted"] = granted_result
                result["done"] = True

            try:
                self.event_store.requestFullAccessToEventsWithCompletion_(completion_handler)
            except AttributeError:
                self.event_store.requestAccessToEntityType_completion_(
                    EKEntityTypeEvent, completion_handler
                )

            # Run the run loop to process the callback
            run_loop = NSRunLoop.currentRunLoop()
            timeout = 30.0
            start_time = datetime.now()
            
            while not result["done"]:
                run_loop.runMode_beforeDate_(
                    NSDefaultRunLoopMode,
                    NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )
                if (datetime.now() - start_time).total_seconds() > timeout:
                    break

            # Final check
            status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
            self._authorized = (status == EKAuthorizationStatusAuthorized)
            return self._authorized

        return False

    def get_authorization_status(self) -> str:
        """Get a human-readable authorization status."""
        status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
        status_map = {
            EKAuthorizationStatusAuthorized: "authorized",
            EKAuthorizationStatusDenied: "denied",
            EKAuthorizationStatusRestricted: "restricted",
            EKAuthorizationStatusNotDetermined: "not_determined",
        }
        return status_map.get(status, "unknown")

    def is_authorized(self) -> bool:
        """Check if calendar access is authorized."""
        status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
        return status == EKAuthorizationStatusAuthorized

    def _nsdate_from_datetime(self, dt: datetime) -> NSDate:
        """Convert Python datetime to NSDate."""
        return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())

    def _datetime_from_nsdate(self, nsdate: NSDate) -> datetime:
        """Convert NSDate to Python datetime."""
        return datetime.fromtimestamp(nsdate.timeIntervalSince1970())

    def _to_python_str(self, value) -> Optional[str]:
        """Convert NSString or any string-like value to plain Python str."""
        if value is None:
            return None
        return str(value)

    def get_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        calendars: Optional[list] = None,
    ) -> list[CalendarEvent]:
        """
        Fetch calendar events within the specified date range.

        Args:
            start_date: Start of date range (defaults to today)
            end_date: End of date range (defaults to 7 days from start)
            calendars: List of calendar names to filter (None = all calendars)

        Returns:
            List of CalendarEvent objects
        """
        if not self.is_authorized():
            if not self.request_access():
                return []

        # Default date range
        if start_date is None:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_date is None:
            end_date = start_date + timedelta(days=7)

        ns_start = self._nsdate_from_datetime(start_date)
        ns_end = self._nsdate_from_datetime(end_date)

        # Get all calendars or filter by name
        all_calendars = self.event_store.calendarsForEntityType_(EKEntityTypeEvent)
        if calendars:
            selected_calendars = [
                cal for cal in all_calendars if cal.title() in calendars
            ]
        else:
            selected_calendars = list(all_calendars)

        if not selected_calendars:
            return []

        # Create predicate and fetch events
        predicate = self.event_store.predicateForEventsWithStartDate_endDate_calendars_(
            ns_start, ns_end, selected_calendars
        )
        ek_events = self.event_store.eventsMatchingPredicate_(predicate)

        # Convert to CalendarEvent objects
        events = []
        for ek_event in ek_events:
            event = CalendarEvent(
                event_id=self._to_python_str(ek_event.eventIdentifier()),
                title=self._to_python_str(ek_event.title()) or "Untitled",
                start_date=self._datetime_from_nsdate(ek_event.startDate()),
                end_date=self._datetime_from_nsdate(ek_event.endDate()),
                calendar_name=self._to_python_str(ek_event.calendar().title()),
                location=self._to_python_str(ek_event.location()),
                notes=self._to_python_str(ek_event.notes()),
                is_all_day=bool(ek_event.isAllDay()),
            )
            events.append(event)

        # Sort by start date
        events.sort(key=lambda e: e.start_date)
        return events

    def get_events_for_day(self, date: datetime) -> list[CalendarEvent]:
        """Get all events for a specific day."""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.get_events(start, end)

    def get_events_today(self) -> list[CalendarEvent]:
        """Get all events for today."""
        return self.get_events_for_day(datetime.now())

    def get_events_this_week(self) -> list[CalendarEvent]:
        """Get all events for the current week."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Start from Monday
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
        return self.get_events(start, end)
    
    def get_events_for_range(self, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Get all events within a date range."""
        return self.get_events(start_date, end_date)

    def get_calendars(self) -> list[str]:
        """Get list of available calendar names."""
        if not self.is_authorized():
            if not self.request_access():
                return []

        calendars = self.event_store.calendarsForEntityType_(EKEntityTypeEvent)
        return [self._to_python_str(cal.title()) for cal in calendars]

    def get_event_by_id(self, event_id: str) -> Optional[CalendarEvent]:
        """Get a specific event by its ID."""
        if not self.is_authorized():
            return None

        ek_event = self.event_store.eventWithIdentifier_(event_id)
        if ek_event is None:
            return None

        return CalendarEvent(
            event_id=self._to_python_str(ek_event.eventIdentifier()),
            title=self._to_python_str(ek_event.title()) or "Untitled",
            start_date=self._datetime_from_nsdate(ek_event.startDate()),
            end_date=self._datetime_from_nsdate(ek_event.endDate()),
            calendar_name=self._to_python_str(ek_event.calendar().title()),
            location=self._to_python_str(ek_event.location()),
            notes=self._to_python_str(ek_event.notes()),
            is_all_day=bool(ek_event.isAllDay()),
        )


if __name__ == "__main__":
    # Test the calendar access
    cal = CalendarAccess()
    print(f"Authorization status: {cal.get_authorization_status()}")
    print(f"Is authorized: {cal.is_authorized()}")

    if not cal.is_authorized():
        print("\n⏳ Requesting calendar access...")
        print("   (A system dialog should appear - please grant access)")
        granted = cal.request_access()
        if granted:
            print("✅ Access granted!")
        else:
            status = cal.get_authorization_status()
            if status == "denied":
                print("❌ Access denied. Please enable in:")
                print("   System Settings → Privacy & Security → Calendar")
            elif status == "restricted":
                print("❌ Access restricted by system policy")
            else:
                print(f"❌ Access not granted (status: {status})")

    if cal.is_authorized():
        print(f"\n📅 Available calendars: {cal.get_calendars()}")

        print("\n📆 Events today:")
        events = cal.get_events_today()
        if events:
            for event in events:
                print(f"   • {event.time_str}: {event.title} ({event.calendar_name})")
        else:
            print("   No events today")

        print("\n📆 Events this week:")
        events = cal.get_events_this_week()
        if events:
            for event in events:
                print(f"   • {event.date_str} {event.time_str}: {event.title}")
        else:
            print("   No events this week")

