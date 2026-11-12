"""How fresh the data is: the last ingestion that worked, in words and with a level."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# The ingester runs every 15 minutes. These match the dbt source freshness (warn after 6 hours).
LATE_AFTER = timedelta(hours=1)
STALE_AFTER = timedelta(hours=6)

OK, LATE, STALE, UNKNOWN = "ok", "late", "stale", "unknown"
DOT = {OK: "🟢", LATE: "🟠", STALE: "🔴", UNKNOWN: "⚪"}


@dataclass(frozen=True)
class Freshness:
    level: str
    text: str  # "Última sincronización: hace 12 minutos"
    failures: int = 0

    @property
    def dot(self) -> str:
        return DOT[self.level]


def ago(delta: timedelta) -> str:
    """'hace 12 minutos', 'hace 3 horas', 'hace 2 días'."""
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 1:
        return "hace instantes"
    if minutes < 60:
        return f"hace {minutes} {'minuto' if minutes == 1 else 'minutos'}"
    hours = minutes // 60
    if hours < 48:
        return f"hace {hours} {'hora' if hours == 1 else 'horas'}"
    return f"hace {hours // 24} días"


def freshness(
    last_ok_at: datetime | None, failures: int = 0, now: datetime | None = None
) -> Freshness:
    """The level goes by how long ago the last good run was. Failures only add to the message:
    a single failed run between two good ones is not worth an alarm."""
    if last_ok_at is None:
        return Freshness(UNKNOWN, "Última sincronización: sin registro", failures)
    now = now or datetime.now(UTC)
    age = now - last_ok_at
    level = OK if age < LATE_AFTER else LATE if age < STALE_AFTER else STALE
    return Freshness(level, f"Última sincronización: {ago(age)}", failures)
