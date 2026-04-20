# BotGeneralCalendar

Telegram bot that creates the same calendar event in **two** iCloud calendars (two Apple IDs) using CalDAV.

## Features

- `/add` command with date/time and event title
- Optional event duration in minutes (default is 60)
- Creates the event in both iCloud accounts via CalDAV (ICLOUD1 and ICLOUD2)
- Each event includes a reminder 24 hours before start; optional second reminder (hours before start)

## Command format

```text
/add DATE TIME, description [, second_reminder_hours [, duration_minutes ]]
```

Order: **description** → **second reminder (hours before start)** → **duration (minutes)**. First reminder is always 24 hours before (unchanged).

Date/time (first matching format wins; preferred first):

- `DD.MM.YYYY HH:MM` (e.g. `22.04.2026 19:30`)
- `YYYY-MM-DD HH:MM`
- `DD/MM/YYYY HH:MM`

Duration-only without a second reminder: leave the third field empty, e.g. `..., title,, 90`.

Examples:

```text
/add 22.04.2026 19:30, Dinner
/add 22.04.2026 19:30, Meeting, 3
/add 22.04.2026 19:30, Movie, 2, 120
/add 22.04.2026 19:30, Lunch,, 90
```

## Setup

1. Create virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create `.env` from template:

```bash
cp .env.example .env
```

3. Fill `.env`:

- `TELEGRAM_BOT_TOKEN` - token from BotFather
- `TIMEZONE` - your timezone, for example `Europe/Moscow`
- For **each** iCloud account (ICLOUD1 and ICLOUD2):
  - Apple ID email
  - App-specific password (not your normal Apple ID password)
  - calendar name exactly as shown in the Calendar app

4. Run:

```bash
python bot.py
```

## How to get iCloud app-specific password

1. Go to [https://appleid.apple.com](https://appleid.apple.com)
2. Sign in
3. Open "Sign-In and Security" -> "App-Specific Passwords"
4. Generate a password and use it in `.env`

## Notes

- The bot needs network access to `caldav.icloud.com`.
- If a calendar is not found, the name in `.env` does not match the calendar name in iCloud.
