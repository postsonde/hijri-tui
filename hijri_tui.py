import asyncio
import datetime
import http.client
import json
import math
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import Footer, Header, Label, Static

DRACULA = Theme(
    name="dracula",
    primary="#BD93F9",      # Purple
    secondary="#8BE9FD",    # Cyan
    accent="#FF79C6",       # Pink
    foreground="#F8F8F2",   # Foreground
    background="#282A36",   # Background
    surface="#44475A",      # Selection / Current Line
    panel="#343746",
    success="#50FA7B",      # Green
    warning="#FFB86C",      # Orange
    error="#FF5555",        # Red
)

HIJRI_WEEKDAYS = [
    "Ahad",
    "☾ Ath",
    "Tha",
    "Arb",
    "☾ Kha",
    "🕌 Jum",
    "Sab",
]

GREGORIAN_WEEKDAYS = [
    "Sun",
    "☾ Mon",
    "Tue",
    "Wed",
    "☾ Thu",
    "🕌 Fri",
    "Sat",
]


def get_hijri_moon_phase(h_day: int) -> tuple[str, str]:
    """Returns (emoji, phase_name) based on the Hijri lunar day (1-30)."""
    if h_day <= 2:
        return "🌑", "New Moon (Hilal)"
    if h_day <= 6:
        return "🌒", "Waxing Crescent"
    if h_day <= 9:
        return "🌓", "First Quarter"
    if h_day <= 12:
        return "🌔", "Waxing Gibbous"
    if h_day <= 15:
        return "🌕", "Full Moon (Ayyam al-Bid)"
    if h_day <= 20:
        return "🌖", "Waning Gibbous"
    if h_day <= 24:
        return "🌗", "Last Quarter"
    return "🌘", "Waning Crescent"


def api_get_sync(path: str) -> dict:
    """Fetches JSON data from AlAdhan API using http.client."""
    host = ".".join(["api", "aladhan", "com"])
    conn = http.client.HTTPSConnection(host, timeout=10)
    headers = {"Accept": "application/json"}
    conn.request("GET", path, headers=headers)
    res = conn.getresponse()
    raw_data = res.read().decode("utf-8")
    conn.close()
    return {"status": res.status, "body": json.loads(raw_data)}


class DayCell(Static):
    """Single Hijri day tile inside the calendar grid."""

    can_focus = True

    def __init__(
        self,
        day_data: dict,
        is_today: bool = False,
        show_gregorian: bool = False,
    ) -> None:
        self.day_data = day_data
        self.is_today = is_today
        super().__init__("")
        self.add_class("day-cell")

        h_day = int(day_data["hijri"]["day"])
        weekday = day_data["gregorian"]["weekday"]["en"]
        holidays = day_data["hijri"].get("holidays", [])

        is_sunnah_fast = weekday in ("Monday", "Thursday")
        is_jumuah = weekday == "Friday"
        is_white_day = h_day in (13, 14, 15)
        has_holiday = len(holidays) > 0

        # Priority:
        # 1. Green (Official Holiday) overrides everything
        # 2. Yellow (Ayyam al-Bid 13-15) overrides Sunnah Fast days
        # 3. Cyan (Sunnah Fast Mon & Thu)
        # 4. Purple (Jumu'ah)
        if has_holiday:
            self.add_class("holiday")
        elif is_white_day:
            self.add_class("white-day")
        elif is_sunnah_fast:
            self.add_class("sunnah-fast")
        elif is_jumuah:
            self.add_class("jumuah-day")

        if is_today:
            self.add_class("today")

        self.refresh_label(show_gregorian)

    def refresh_label(self, show_gregorian: bool) -> None:
        h_day = int(self.day_data["hijri"]["day"])
        g_day = self.day_data["gregorian"]["day"]
        g_month = self.day_data["gregorian"]["month"]["en"][:3]
        weekday = self.day_data["gregorian"]["weekday"]["en"]
        holidays = self.day_data["hijri"].get("holidays", [])

        moon_emoji, _ = get_hijri_moon_phase(h_day)
        badges = [moon_emoji]

        if holidays:
            badges.append("★")
        if weekday == "Friday":
            badges.append("🕌")
        if weekday in ("Monday", "Thursday"):
            badges.append("☾")

        badge_str = " ".join(badges)

        if show_gregorian:
            self.update(f"[b]{h_day}[/b]  {badge_str}\n[#8BE9FD]{g_day} {g_month}[/]")
        else:
            self.update(f"[b]{h_day}[/b]\n{badge_str}")

    def on_focus(self) -> None:
        """Scroll tile into view and update right sidebar automatically."""
        self.scroll_visible()
        self.app.update_sidebar(self.day_data)

    def on_click(self) -> None:
        self.focus()


class HijriCalendarApp(App):
    TITLE = "☪ ✦ H I J R I ✦ ☪"

    show_gregorian = reactive(False)

    CSS = """
    Screen {
        layout: horizontal;
    }

    Header {
        color: #F1FA8C;
        text-style: bold;
    }

    #left-pane {
        width: 72%;
        height: 100%;
        padding: 0 1;
    }

    #month-title {
        text-align: center;
        text-style: bold;
        color: #F1FA8C;
        padding: 1 0;
        width: 100%;
    }

    #weekday-header {
        grid-size: 7 1;
        grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr 1fr;
        height: 1;
        margin-bottom: 1;
    }

    .weekday-label {
        text-align: center;
        color: #6272A4;
        text-style: bold;
        width: 100%;
    }

    .weekday-fast {
        color: #8BE9FD;
    }

    .weekday-jumuah {
        color: #BD93F9;
    }

    #calendar-grid {
        grid-size: 7 5;
        grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr 1fr 1fr;
        grid-gutter: 1;
        height: 1fr;
    }

    .day-cell {
        width: 100%;
        height: 100%;
        border: round #44475A;
        background: #282A36;
        color: #F8F8F2;
        content-align: center middle;
        text-align: center;
    }

    .day-cell:focus {
        background: #44475A;
        border: heavy #F8F8F2;
        text-style: bold;
    }

    /* Official Holiday / Holy Day: Green (highest priority) */
    .holiday {
        border: round #50FA7B;
        color: #50FA7B;
        background: #24382C;
    }

    /* Ayyam al-Bid (13th, 14th, 15th): Soft Yellow (overrides Sunnah Fast) */
    .white-day {
        border: round #F1FA8C;
        color: #F1FA8C;
        background: #363626;
    }

    /* Monday & Thursday Sunnah Fast: Cyan */
    .sunnah-fast {
        border: round #8BE9FD;
        color: #8BE9FD;
        background: #24333D;
    }

    /* Friday / Jumu'ah: Purple */
    .jumuah-day {
        border: round #BD93F9;
        color: #BD93F9;
        background: #302940;
    }

    /* Today: Distinct double orange border while keeping day's color */
    .today {
        border: double #FFB86C;
        text-style: bold;
    }

    .today:focus {
        border: heavy #FFB86C;
    }

    .empty-cell {
        width: 100%;
        height: 100%;
        border: round #282A36;
        background: #282A36;
    }

    #sidebar {
        width: 28%;
        height: 100%;
        border: round $primary;
        padding: 1 2;
        background: #21222C;
        layout: vertical;
    }

    #details-pane {
        height: 1fr;
        overflow-y: auto;
    }

    .sidebar-heading {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    #legend {
        height: auto;
        border-top: solid #44475A;
        padding-top: 1;
        color: #6272A4;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "prev_month", "Prev Month"),
        ("n", "next_month", "Next Month"),
        ("t", "today", "Today"),
        ("g", "toggle_gregorian", "Toggle Gregorian"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.today = datetime.date.today()
        self.today_str = self.today.strftime("%d-%m-%Y")
        self.hijri_month: int | None = None
        self.hijri_year: int | None = None
        self.method = "UAQ"

    def on_mount(self) -> None:
        self.register_theme(DRACULA)
        self.theme = "dracula"
        self.run_worker(self._init_today_hijri(), exclusive=True)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Label("Loading Hijri calendar...", id="month-title")
                with Grid(id="weekday-header"):
                    for i, day_name in enumerate(HIJRI_WEEKDAYS):
                        classes = "weekday-label"
                        if i in (1, 4):
                            classes += " weekday-fast"
                        elif i == 5:
                            classes += " weekday-jumuah"
                        yield Label(day_name, classes=classes)
                yield Grid(id="calendar-grid")

            with Vertical(id="sidebar"):
                with Vertical(id="details-pane"):
                    yield Label("Day Details", classes="sidebar-heading")
                    yield Static("Select a day.", id="day-details")
                with Container(id="legend"):
                    yield Static(
                        "[#FFB86C]▢ Today[/]  [#50FA7B]★ Holy Day[/]\n"
                        "[#F1FA8C]🌕 13–15[/]  [#8BE9FD]☾ Fast[/]  [#BD93F9]🕌 Jumu'ah[/]"
                    )
        yield Footer()

    def watch_show_gregorian(self, value: bool) -> None:
        """Toggles Gregorian date display and weekday labels."""
        names = GREGORIAN_WEEKDAYS if value else HIJRI_WEEKDAYS
        for label, name in zip(self.query(".weekday-label"), names):
            label.update(name)
        for cell in self.query(DayCell):
            cell.refresh_label(value)

    def action_toggle_gregorian(self) -> None:
        self.show_gregorian = not self.show_gregorian

    def on_key(self, event: events.Key) -> None:
        """2D arrow key navigation across calendar tiles."""
        cells = list(self.query(DayCell))
        if not cells or self.focused not in cells:
            return

        idx = cells.index(self.focused)
        new_idx = None

        if event.key == "right":
            new_idx = min(idx + 1, len(cells) - 1)
        elif event.key == "left":
            new_idx = max(idx - 1, 0)
        elif event.key == "down":
            new_idx = min(idx + 7, len(cells) - 1)
        elif event.key == "up":
            new_idx = max(idx - 7, 0)

        if new_idx is not None and new_idx != idx:
            cells[new_idx].focus()
            event.prevent_default()

    async def _init_today_hijri(self) -> None:
        """Determines current Hijri month & year for today's date, then loads the month."""
        path = f"/v1/gToH/{self.today_str}?calendarMethod={self.method}"
        res = await asyncio.to_thread(api_get_sync, path)
        if res["status"] == 200 and isinstance(res["body"].get("data"), dict):
            h_info = res["body"]["data"]["hijri"]
            self.hijri_month = int(h_info["month"]["number"])
            self.hijri_year = int(h_info["year"])
            await self._fetch_hijri_month(self.hijri_month, self.hijri_year)
        else:
            self.query_one("#month-title", Label).update(
                f"API Error ({res['status']}): Could not resolve current Hijri date."
            )

    def load_month(self) -> None:
        if self.hijri_month and self.hijri_year:
            self.run_worker(
                self._fetch_hijri_month(self.hijri_month, self.hijri_year),
                exclusive=True,
            )

    async def _fetch_hijri_month(self, h_month: int, h_year: int) -> None:
        path = f"/v1/hToGCalendar/{h_month}/{h_year}?calendarMethod={self.method}"
        res = await asyncio.to_thread(api_get_sync, path)
        status = res["status"]
        payload = res["body"]

        if status != 200 or not isinstance(payload.get("data"), list):
            self.query_one("#month-title", Label).update(
                f"API Error ({status}): {payload.get('data', 'Unknown error')}"
            )
            return

        days = payload["data"]
        grid = self.query_one("#calendar-grid", Grid)
        await grid.remove_children()

        first_day = next(iter(days))
        h_month_en = first_day["hijri"]["month"]["en"]
        h_month_ar = first_day["hijri"]["month"]["ar"]
        g_months = list(dict.fromkeys(d["gregorian"]["month"]["en"] for d in days))
        g_years = list(dict.fromkeys(d["gregorian"]["year"] for d in days))

        title = (
            f"☪ {h_year} AH  •  {h_month_en} ({h_month_ar})  |  "
            f"{' / '.join(g_months)} {'/'.join(g_years)}"
        )
        self.query_one("#month-title", Label).update(title)

        # Align 1st day of Hijri month to Hijri week (Sunday/Ahad=0 ... Saturday/Sabt=6)
        first_g_str = first_day["gregorian"]["date"]
        first_g_date = datetime.datetime.strptime(first_g_str, "%d-%m-%Y").date()
        hijri_offset = (first_g_date.weekday() + 1) % 7

        # Dynamically set 5 or 6 equal-height rows fitting the terminal window
        total_slots = hijri_offset + len(days)
        num_rows = math.ceil(total_slots / 7)
        grid.styles.grid_size_rows = num_rows
        grid.styles.grid_rows = " ".join(["1fr"] * num_rows)

        for _ in range(hijri_offset):
            await grid.mount(Static("\n", classes="empty-cell"))

        focus_target = None
        for d in days:
            is_today = d["gregorian"]["date"] == self.today_str
            cell = DayCell(
                d,
                is_today=is_today,
                show_gregorian=self.show_gregorian,
            )
            await grid.mount(cell)
            if is_today:
                focus_target = cell

        # Fill trailing empty slots so grid layout stays completely uniform
        trailing = (num_rows * 7) - total_slots
        for _ in range(trailing):
            await grid.mount(Static("\n", classes="empty-cell"))

        if focus_target:
            focus_target.focus()
        else:
            first_cell = self.query(DayCell).first()
            if first_cell:
                first_cell.focus()

    def update_sidebar(self, d: dict) -> None:
        g = d["gregorian"]
        h = d["hijri"]
        h_day = int(h["day"])
        g_weekday = g["weekday"]["en"]
        h_weekday = h["weekday"]["en"]
        holidays = h.get("holidays", [])
        moon_emoji, moon_name = get_hijri_moon_phase(h_day)

        notes = [f"{moon_emoji} [#6272A4]Lunar Phase:[/] [#F1FA8C]{moon_name}[/]"]
        if holidays:
            notes.append(f"[b #50FA7B]★ Holy Day:[/] [#50FA7B]{', '.join(holidays)}[/]")
        if g_weekday == "Friday":
            notes.append("[b #BD93F9]🕌 Jumu'ah[/] [#6272A4](Al Juma'a)[/]")
        if h_day in (13, 14, 15):
            notes.append("[b #F1FA8C]🌕 Ayyam al-Bid[/] [#6272A4](White Days Fast)[/]")
        if g_weekday in ("Monday", "Thursday"):
            notes.append(f"[b #8BE9FD]☾ Sunnah Fast[/] [#6272A4]({h_weekday})[/]")

        notes_text = "\n\n".join(notes)

        text = (
            f"[b #F8F8F2]Hijri:[/]\n"
            f"[b #50FA7B]{h['day']}. {h['month']['en']}[/] [b #F1FA8C]{h['year']} AH[/]\n"
            f"[#BD93F9]{h_weekday} ({h['month']['ar']})[/]\n\n"
            f"[b #F8F8F2]Gregorian:[/]\n"
            f"[b #8BE9FD]{g['date']}[/] [#6272A4]({g_weekday})[/]\n\n"
            f"[b #F8F8F2]Notes:[/]\n{notes_text}"
        )
        self.query_one("#day-details", Static).update(text)

    def action_prev_month(self) -> None:
        if self.hijri_month is None or self.hijri_year is None:
            return
        if self.hijri_month == 1:
            self.hijri_month = 12
            self.hijri_year -= 1
        else:
            self.hijri_month -= 1
        self.load_month()

    def action_next_month(self) -> None:
        if self.hijri_month is None or self.hijri_year is None:
            return
        if self.hijri_month == 12:
            self.hijri_month = 1
            self.hijri_year += 1
        else:
            self.hijri_month += 1
        self.load_month()

    def action_today(self) -> None:
        self.run_worker(self._init_today_hijri(), exclusive=True)


def main() -> None:
    HijriCalendarApp().run()


if __name__ == "__main__":
    main()
