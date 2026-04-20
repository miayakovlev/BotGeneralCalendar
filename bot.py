import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import caldav
from dotenv import load_dotenv
from icalendar import Alarm, Calendar, Event
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


ICLOUD_CALDAV_URL = "https://caldav.icloud.com"


@dataclass
class CalendarConfig:
    label: str
    apple_id: str
    app_password: str
    calendar_name: str


def load_calendar_configs() -> list[CalendarConfig]:
    return [
        CalendarConfig(
            label="ICLOUD1",
            apple_id=get_required_env("ICLOUD1_APPLE_ID"),
            app_password=get_required_env("ICLOUD1_APP_PASSWORD"),
            calendar_name=get_required_env("ICLOUD1_CALENDAR_NAME"),
        ),
        CalendarConfig(
            label="ICLOUD2",
            apple_id=get_required_env("ICLOUD2_APPLE_ID"),
            app_password=get_required_env("ICLOUD2_APP_PASSWORD"),
            calendar_name=get_required_env("ICLOUD2_CALENDAR_NAME"),
        ),
    ]


def get_calendar(config: CalendarConfig):
    principal = caldav.DAVClient(
        url=ICLOUD_CALDAV_URL,
        username=config.apple_id,
        password=config.app_password,
    ).principal()

    for calendar in principal.calendars():
        if calendar.name == config.calendar_name:
            return calendar

    raise RuntimeError(
        f"[{config.label}] Календарь «{config.calendar_name}» не найден "
        f"для {config.apple_id} (проверьте точное имя в приложении «Календарь»)"
    )

def parse_event_datetime(datetime_part: str, tz_name: str) -> datetime:
    """Parse local date/time; priority: dd.mm.yyyy HH:MM, then other supported formats."""
    normalized = " ".join(datetime_part.split())
    formats = (
        ("%d.%m.%Y %H:%M", "DD.MM.YYYY HH:MM"),
        ("%Y-%m-%d %H:%M", "YYYY-MM-DD HH:MM"),
        ("%d/%m/%Y %H:%M", "DD/MM/YYYY HH:MM"),
    )
    last_err: Exception | None = None
    for fmt, _label in formats:
        try:
            naive = datetime.strptime(normalized, fmt)
            return naive.replace(tzinfo=ZoneInfo(tz_name))
        except ValueError as exc:
            last_err = exc
            continue
    raise ValueError(
        "Не удалось разобрать дату и время. Примеры: "
        "22.04.2026 19:30 (приоритет), 2026-04-22 19:30, 22/04/2026 19:30"
    ) from last_err


def create_ics_payload(
    title: str,
    start_dt: datetime,
    end_dt: datetime,
    tz_name: str,
    second_reminder_hours: float | None = None,
) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//BotGeneralCalendar//Telegram ICS Export//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-timezone", tz_name)
    cal.add("x-wr-calname", "Bot General Calendar")

    now = datetime.now(tz=ZoneInfo(tz_name))
    event = Event()
    event.add("uid", f"{uuid.uuid4()}@botgeneralcalendar")
    event.add("summary", title)
    # Apple Calendar is happiest when DTSTART/DTEND are explicitly TZID-tagged
    # for time-zoned local times.
    event.add("dtstart", start_dt, parameters={"TZID": tz_name})
    event.add("dtend", end_dt, parameters={"TZID": tz_name})
    event.add("dtstamp", now.astimezone(ZoneInfo("UTC")))
    event.add("sequence", 0)
    event.add("status", "CONFIRMED")
    event.add("transp", "OPAQUE")
    event.add("created", now)
    event.add("last-modified", now)

    # iOS/macOS/iCloud: first alert — 24h before start.
    alarm1 = Alarm()
    alarm1.add("action", "DISPLAY")
    alarm1.add("description", f"Напоминание (за сутки): {title}")
    alarm1.add("trigger", timedelta(days=-1))
    event.add_component(alarm1)

    if second_reminder_hours is not None:
        alarm2 = Alarm()
        alarm2.add("action", "DISPLAY")
        alarm2.add("description", f"Напоминание 2: {title}")
        alarm2.add("trigger", timedelta(hours=-second_reminder_hours))
        event.add_component(alarm2)

    cal.add_component(event)
    return cal.to_ical()


def parse_add_args(raw_text: str, tz_name: str):
    # /add ДАТА ВРЕМЯ, описание [, второе_напоминание_ч [, длительность_мин ]]
    # Порядок: дата+время, название, (опц.) за сколько часов второе уведомление, (опц.) длительность в минутах.
    # Только длительность без второго напоминания: /add ..., название,, 90
    parts = [part.strip() for part in raw_text.split(",")]
    if len(parts) < 2:
        raise ValueError(
            "Формат: /add ДАТА ВРЕМЯ, описание [, второе_уведомление_ч [, длительность_мин ]]\n"
            "Дата (приоритет): DD.MM.YYYY HH:MM; также: YYYY-MM-DD HH:MM, DD/MM/YYYY HH:MM"
        )
    if len(parts) > 4:
        raise ValueError(
            "Слишком много полей (максимум: дата, описание, второе уведомление, длительность). "
            "Если в названии есть запятая — уберите её или замените."
        )

    datetime_part = parts[0].replace("/add", "", 1).strip()
    title = parts[1]
    if not title:
        raise ValueError("Укажите описание события")

    duration_minutes = 60
    second_reminder_hours: float | None = None

    if len(parts) >= 4:
        if parts[2]:
            second_reminder_hours = float(parts[2].replace(",", "."))
            if second_reminder_hours <= 0:
                raise ValueError("Второе напоминание: укажите число часов больше 0")
        if parts[3]:
            duration_minutes = int(parts[3])
            if duration_minutes <= 0:
                raise ValueError("Длительность должна быть больше 0")
    elif len(parts) == 3 and parts[2]:
        second_reminder_hours = float(parts[2].replace(",", "."))
        if second_reminder_hours <= 0:
            raise ValueError("Второе напоминание: укажите число часов больше 0")

    start_dt = parse_event_datetime(datetime_part, tz_name)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return title, start_dt, end_dt, duration_minutes, second_reminder_hours


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Создаю одно и то же событие в двух iCloud-календарях (ICLOUD1 и ICLOUD2).\n"
        "Нужны оба набора: ICLOUD1_* и ICLOUD2_* (Apple ID, app-specific password, имя календаря).\n"
        "Напоминания: всегда первое за 24 часа; второе — опционально (за сколько часов до начала).\n\n"
        "Формат:\n"
        "/add ДАТА ВРЕМЯ, описание [, второе_уведомление_ч [, длительность_мин ]]\n\n"
        "Порядок: описание → второе уведомление (часы до начала) → длительность (минуты).\n\n"
        "Дата и время (приоритет — первый формат):\n"
        "• DD.MM.YYYY HH:MM — например 22.04.2026 19:30\n"
        "• YYYY-MM-DD HH:MM — например 2026-04-22 19:30\n"
        "• DD/MM/YYYY HH:MM — например 22/04/2026 19:30\n\n"
        "Примеры:\n"
        "/add 22.04.2026 19:30, Ужин\n"
        "/add 22.04.2026 19:30, Встреча, 3\n"
        "  (второе напоминание за 3 ч; длительность по умолчанию 60 мин)\n"
        "/add 22.04.2026 19:30, Кино, 2, 120\n"
        "  (второе за 2 ч; длительность 120 мин)\n"
        "/add 22.04.2026 19:30, Обед,, 90\n"
        "  (без второго напоминания; длительность 90 мин)"
    )
    await update.message.reply_text(text)

async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_text = update.message.text
    tz_name = get_required_env("TIMEZONE")

    try:
        title, start_dt, end_dt, duration_minutes, second_hours = parse_add_args(
            raw_text, tz_name
        )
    except ValueError as exc:
        await update.message.reply_text(f"Ошибка ввода: {exc}")
        return

    payload = create_ics_payload(
        title=title,
        start_dt=start_dt,
        end_dt=end_dt,
        tz_name=tz_name,
        second_reminder_hours=second_hours,
    )
    ical_text = payload.decode("utf-8")
    event_time = start_dt.strftime("%Y-%m-%d %H:%M")
    results: list[str] = []
    for config in load_calendar_configs():
        try:
            calendar = get_calendar(config)
            calendar.add_event(ical_text)
            results.append(f"OK: {config.label} → {config.calendar_name}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("CalDAV add_event failed: %s", config.label)
            results.append(f"ERROR: {config.label} → {config.calendar_name}: {exc}")

    remind_lines = "Напоминание 1: за 24 часа\n"
    if second_hours is not None:
        remind_lines += f"Напоминание 2: за {second_hours:g} ч до начала\n"

    await update.message.reply_text(
        "Событие обработано (CalDAV).\n"
        f"Название: {title}\n"
        f"Старт: {event_time} ({tz_name})\n"
        f"Длительность: {duration_minutes} мин\n"
        + remind_lines
        + "\n"
        + "\n".join(results)
    )

def main() -> None:
    load_dotenv(dotenv_path=ENV_PATH)
    token = get_required_env("TELEGRAM_BOT_TOKEN")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("add", add_handler))

    # Python 3.14 does not create a default event loop automatically.
    asyncio.set_event_loop(asyncio.new_event_loop())
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
