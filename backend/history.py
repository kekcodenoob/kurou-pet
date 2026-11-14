"""Timestamped log of pet activity.

Every change is stored as its own event with the exact time it happened and
what caused it (e.g. +180 affection from "Focus Mode", 5 seconds distracted on
"YouTube"). Workout sessions are logged separately with their reps and form. The dashboard groups events into 5-minute, daily, or monthly
periods when it asks for a chart.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta

GAINED = "gained"  # Affection earned
LOST = "lost"  # Affection lost
DISTRACTED = "distracted"  # Seconds spent on a distraction
KINDS = (GAINED, LOST, DISTRACTED)

# How far back each dashboard chart goes
FIVE_MINUTE_WINDOW = timedelta(hours=6)
DAILY_WINDOW_DAYS = 30
MONTHLY_WINDOW_MONTHS = 12


class History:
    def __init__(self, path="pet_history.db"):
        self._lock = threading.Lock()  # Workouts record from a worker thread
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,  -- Unix time, seconds
                kind TEXT NOT NULL,       -- gained | lost | distracted
                amount INTEGER NOT NULL,  -- points, or seconds for distracted
                cause TEXT                -- e.g. "Focus Mode", "YouTube"
            );
            CREATE INDEX IF NOT EXISTS events_by_time ON events (timestamp);
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,     -- Unix time the session ended
                exercise TEXT NOT NULL,      -- e.g. "Bicep Curls"
                target_reps INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                good_form_reps INTEGER NOT NULL,
                points INTEGER NOT NULL,
                completed INTEGER NOT NULL   -- 1 if the target was reached
            );
            """
        )
        self._migrate_buckets()
        self._conn.commit()

    def _migrate_buckets(self):
        """Converts the earlier 5-minute bucket table into events (one-time)."""
        has_buckets = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'buckets'"
        ).fetchone()
        if not has_buckets:
            return
        for column, kind in (("gained", GAINED), ("lost", LOST), ("distracted_seconds", DISTRACTED)):
            self._conn.execute(
                f"""
                INSERT INTO events (timestamp, kind, amount, cause)
                SELECT start, ?, {column}, NULL FROM buckets WHERE {column} > 0
                """,
                (kind,),
            )
        self._conn.execute("DROP TABLE buckets")

    def record(self, kind, amount, cause=None):
        if kind not in KINDS:
            raise ValueError(f"Unknown event kind: {kind}")
        if amount <= 0:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (timestamp, kind, amount, cause) VALUES (?, ?, ?, ?)",
                (time.time(), kind, amount, cause),
            )
            self._conn.commit()

    def record_workout(self, result):
        """Logs one workout session (an exercise_tracker.WorkoutResult)."""
        if result.reps <= 0:
            return
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workouts
                    (timestamp, exercise, target_reps, reps, good_form_reps, points, completed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    result.exercise,
                    result.target_reps,
                    result.reps,
                    result.good_form_reps,
                    result.points,
                    int(result.completed),
                ),
            )
            self._conn.commit()

    def workouts(self, recent=10):
        """Totals per exercise plus the most recent sessions, for the dashboard."""
        with self._lock:
            per_exercise = self._conn.execute(
                """
                SELECT exercise, COUNT(*), SUM(reps), SUM(good_form_reps), SUM(points),
                       MAX(timestamp)
                FROM workouts GROUP BY exercise ORDER BY SUM(reps) DESC
                """
            ).fetchall()
            sessions = self._conn.execute(
                """
                SELECT timestamp, exercise, target_reps, reps, good_form_reps, points, completed
                FROM workouts ORDER BY timestamp DESC LIMIT ?
                """,
                (recent,),
            ).fetchall()

        exercises = [
            {
                "exercise": name,
                "sessions": count,
                "reps": reps,
                "good_form_reps": good,
                "points": points,
                "last_done": int(last * 1000),
            }
            for name, count, reps, good, points, last in per_exercise
        ]
        return {
            "total_sessions": sum(e["sessions"] for e in exercises),
            "total_reps": sum(e["reps"] for e in exercises),
            "total_good_form_reps": sum(e["good_form_reps"] for e in exercises),
            "exercises": exercises,
            "recent": [
                {
                    "time": int(ts * 1000),
                    "exercise": name,
                    "target_reps": target,
                    "reps": reps,
                    "good_form_reps": good,
                    "points": points,
                    "completed": bool(done),
                }
                for ts, name, target, reps, good, points, done in sessions
            ],
        }

    def series(self, interval):
        """Returns one point per period ("5min", "day" or "month"), oldest first.

        Periods with no activity are included as zeros so the chart has no gaps.
        """
        now = datetime.now()
        if interval == "5min":
            periods = self._five_minute_periods(now)
        elif interval == "day":
            periods = self._day_periods(now)
        elif interval == "month":
            periods = self._month_periods(now)
        else:
            raise ValueError(f"Unknown interval: {interval}")

        totals = {p: {**dict.fromkeys(KINDS, 0), "reps": 0} for p in periods}
        since = periods[0].timestamp()
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, kind, amount FROM events WHERE timestamp >= ?", (since,)
            ).fetchall()
            workout_rows = self._conn.execute(
                "SELECT timestamp, reps FROM workouts WHERE timestamp >= ?", (since,)
            ).fetchall()

        for timestamp, kind, amount in rows:
            period = self._period_of(datetime.fromtimestamp(timestamp), interval)
            if period in totals and kind in KINDS:
                totals[period][kind] += amount
        for timestamp, reps in workout_rows:
            period = self._period_of(datetime.fromtimestamp(timestamp), interval)
            if period in totals:
                totals[period]["reps"] += reps

        return [
            {
                "start": int(p.timestamp() * 1000),  # ms, for JavaScript Dates
                "gained": t[GAINED],
                "lost": t[LOST],
                "distracted_minutes": round(t[DISTRACTED] / 60, 1),
                "workout_reps": t["reps"],
            }
            for p, t in totals.items()
        ]

    @staticmethod
    def _period_of(moment, interval):
        if interval == "5min":
            return moment.replace(
                minute=moment.minute - moment.minute % 5, second=0, microsecond=0
            )
        if interval == "day":
            return moment.replace(hour=0, minute=0, second=0, microsecond=0)
        return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _five_minute_periods(self, now):
        current = self._period_of(now, "5min")
        count = int(FIVE_MINUTE_WINDOW / timedelta(minutes=5))
        return [current - timedelta(minutes=5 * i) for i in reversed(range(count))]

    def _day_periods(self, now):
        today = self._period_of(now, "day")
        return [today - timedelta(days=i) for i in reversed(range(DAILY_WINDOW_DAYS))]

    def _month_periods(self, now):
        month = self._period_of(now, "month")
        periods = [month]
        for _ in range(MONTHLY_WINDOW_MONTHS - 1):
            month = (month - timedelta(days=1)).replace(day=1)
            periods.append(month)
        return list(reversed(periods))
