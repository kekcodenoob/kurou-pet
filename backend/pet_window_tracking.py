import sys
import math
import time
import random
import threading
import os
import json
import socket
from pathlib import Path
import webbrowser
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QWidget, qApp
from PyQt5.QtCore import Qt, QTimer, QPoint, QPointF, QRect, QRectF, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)

from facelandmarker import face_tracker
from history import DISTRACTED, GAINED, LOST, History
from exercise_tracker import EXERCISE_CATEGORIES, EXERCISES, workout
from desktop_windows import focus_keeper, get_active_distractions, list_open_apps


# Focus Mode timers: (label, minutes)
FOCUS_TIMES = [
    ("5 minutes", 5),
    ("15 minutes", 15),
    ("30 minutes", 30),
    ("1 hour", 60),
]
TEST_FOCUS_TIME = ("10 seconds", 10 / 60)  # Quick session for testing, at the bottom of the menu
FOCUS_LABELS = {minutes: label for label, minutes in FOCUS_TIMES + [TEST_FOCUS_TIME]}

FOCUS_SUCCESS, FOCUS_FAILED, FOCUS_NO_CAMERA = 1, 0, -1
# Every 5-second scan on a distracting window, and every second spent looking
# away during Focus Mode, costs this much affection and happiness and adds this
# much anger. Affection has no floor, so it can go negative.
DISTRACTION_PENALTY = 1
LOOKED_AWAY_REMINDER_SECONDS = 5  # The pet speaks up once per this many seconds looking away
LOOKING_AWAY = "Looking away"  # Anger source name for Focus Mode distractions


def focus_reward(minutes):
    # About 1 affection point per 5 seconds focused (15 minutes -> 180)
    return max(1, round(minutes * 12))


def migrate_happiness_causes(causes):
    """Converts the old flat {"• Pet the pet": count} format to the per-source format.

    The old format only counted events, so points are estimated from the rewards.
    """
    if all(isinstance(v, dict) for v in causes.values()):
        return causes
    migrated = {}

    def add(source, detail, points):
        entry = migrated.setdefault(source, {"Total points": 0, "Breakdown": {}})
        entry["Total points"] += points
        entry["Breakdown"][detail] = entry["Breakdown"].get(detail, 0) + points

    for name, value in causes.items():
        if isinstance(value, dict):
            migrated[name] = value
            continue
        label = name.lstrip("• ").strip()
        if label == "Pet the pet":
            add("Petting", "Pet the pet", value)
        elif label.startswith("Adequately focused for "):
            session = label.removeprefix("Adequately focused for ")
            minutes = next((m for m, l in FOCUS_LABELS.items() if l == session), 0)
            add("Focus Mode", session, value * focus_reward(minutes) if minutes else value)
        elif label == "Completed a workout rep":
            add("Workouts", "Earlier workouts", value * 2)  # Exercise and form weren't logged
        else:
            add("Other", label, value)
    return migrated


# Getting info from the pet to display on the FastAPI server
class PetStatus:
    def __init__(self, filename="pet_data.json"):
        self.filename = filename
        self._save_lock = threading.Lock()  # Camera sessions save from a worker thread
        self.unlocked_sprites = ["roach.webp"] # Added to prevent sprites from getting locked after buying them
        self.affection_points = 0
        self.happiness_count = 0
        self.happiness_causes = {}
        self.anger_count = 0
        self.anger_causes = {}
        self.productivity_app = None  # Process name of the user's focus app, e.g. "Code.exe"
        self.current_sprite = "roach.webp"
        self.pet_size = "Medium"
        self.always_on_top = True
        self.last_exercise = None  # Workout shortcut at the top of the Workout menu
        self.load_from_file()  # Auto-load on creation

    def save_to_file(self):
        """Writes current state to JSON."""
        data = {
            "unlocked_sprites": self.unlocked_sprites,
            "affection_points": self.affection_points,
            "happiness_count": self.happiness_count,
            "happiness_causes": self.happiness_causes,
            "anger_count": self.anger_count,
            "anger_causes": self.anger_causes,
            "productivity_app": self.productivity_app,
            "current_sprite": self.current_sprite,
            "pet_size": self.pet_size,
            "always_on_top": self.always_on_top,
            "last_exercise": self.last_exercise,
        }
        with self._save_lock, open(self.filename, "w") as f:
            json.dump(data, f, indent=4)

    def load_from_file(self):
        """Reads previous state from JSON if it exists."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    data = json.load(f)
                    self.unlocked_sprites = data.get("unlocked_sprites", ["roach.webp"])
                    self.affection_points = data.get("affection_points", 0)
                    self.happiness_count = data.get("happiness_count", 0)
                    self.happiness_causes = migrate_happiness_causes(data.get("happiness_causes", {}))
                    self.anger_count = data.get("anger_count", 0)
                    self.anger_causes = data.get("anger_causes", {})
                    self.productivity_app = data.get("productivity_app")
                    self.current_sprite = data.get("current_sprite", "roach.webp")
                    self.pet_size = data.get("pet_size", "Medium")
                    self.always_on_top = data.get("always_on_top", True)
                    self.last_exercise = data.get("last_exercise")
            except Exception as e:
                print(f"Error loading save file: {e}")

    def increment_anger(self, cause=None, amount=1):
        """Takes `amount` affection and happiness and adds `amount` anger."""
        self.affection_points -= amount
        self.happiness_count = max(0, self.happiness_count - amount)
        self.anger_count += amount
        history.record(LOST, amount, cause)

    def increment_happiness(self, happy_amount=1, source="Other", detail=None):
        """Adds affection and logs where it came from, e.g. ("Workouts", "Bicep Curls")."""
        self.affection_points += happy_amount
        self.happiness_count += happy_amount
        self.find_happiness_causes(source, detail or source, happy_amount)
        history.record(GAINED, happy_amount, f"{source}: {detail}" if detail else source)

    def get_affection_points(self):
        return self.affection_points

    def get_anger_count(self):
        return self.anger_count

    def find_anger_causes(self, found_distractions, increment_num=5):
        # found_distractions now strucutred like (distraction platform, tab title). Ex: "Youtube" : 20 seconds, "Game Playthrough - Youtube": 15 seconds)
        for platform_name, title in found_distractions:
            stripped_app = title.strip()

            # Storing pet annoyances and new platform distractions (Youtube, Reddit, etc.)
            if platform_name not in self.anger_causes:
                if platform_name == "Desktop Pet":
                    self.anger_causes[platform_name] = {"Excessive taps": 0}
                else:
                    self.anger_causes[platform_name] = {"Total seconds": 0, "Tabs": {}}
            # Added this to track times pet was tapped too much, since that's not a time-based metric
            if platform_name == "Desktop Pet":
                self.anger_causes[platform_name]["Excessive taps"] += increment_num
            else:
                self.anger_causes[platform_name]["Total seconds"] += increment_num

                # Storing new titles in distractions (ex: DELTARUNE Playthrough - Youtube)
                if stripped_app not in self.anger_causes[platform_name]["Tabs"]:
                    self.anger_causes[platform_name]["Tabs"][stripped_app] = 0
                # Same deal with the platform stuff
                self.anger_causes[platform_name]["Tabs"][stripped_app] += increment_num
                history.record(DISTRACTED, increment_num, platform_name)

        return self.anger_causes

    def get_happiness_count(self):
        return self.happiness_count

    def find_happiness_causes(self, source, detail, points):
        # Mirrors anger_causes: one entry per source ("Workouts", "Focus Mode", "Petting")
        # with its total and a breakdown, e.g. {"Total points": 30, "Breakdown": {"Bicep Curls": 30}}
        entry = self.happiness_causes.setdefault(source, {"Total points": 0, "Breakdown": {}})
        entry["Total points"] += points
        entry["Breakdown"][detail] = entry["Breakdown"].get(detail, 0) + points
        return self.happiness_causes


history = History()
pet_status = PetStatus()


WORKOUT_REPS = 10

# (display name, file, cost, sprite faces left) - left-facing sprites get mirrored when walking right
PET_MODELS = [
    ("Kurourushi", "roach.webp", 0, False),  # Starter
    ("Spinda", "spinda.png", 250, True),
    ("Pompompurin", "pompompurin.png", 500, False),
    ("Toon Link", "toon_link.png", 500, True),
]
MODELS_BY_FILE = {model[1]: model for model in PET_MODELS}

# (label, height in px)
PET_SIZES = [("Small", 170), ("Medium", 235), ("Large", 300)]

DIALOGUE = {
    "greet": [
        "Hi again! Ready to get some work done?",
        "I'm here. Let's have a focused session.",
        "Welcome back! I'll keep an eye out for distractions.",
    ],
    "first_run_tip": "Hi! Right-click me to choose your focus app.",
    "click": [
        "Hi!",
        "Need something?",
        "I'm on watch duty.",
        "Hehe.",
        "Keep it up!",
        "*happy chirp*",
    ],
    "annoyed": [
        "Okay, okay, that's enough poking!",
        "Hey! I'm not a stress ball!",
    ],
    "petted": [
        "Aww, thank you!",
        "I needed that.",
        "Best owner ever.",
        "Mmm, right there.",
    ],
    "idle": [
        "Remember to drink some water.",
        "How's the work going?",
        "You're doing great. Keep going!",
        "Relax your shoulders for a sec.",
        "A quick stretch might feel nice soon.",
        "I believe in you.",
    ],
    "distracted": [
        "{platform}? Not right now!",
        "I saw that. Back to work!",
        "Hey! {platform} can wait.",
    ],
    "back_on_track": [
        "Much better.",
        "Thank you. Back to it!",
        "That's what I like to see.",
    ],
    "focus_start": "Focus mode: {label}. Eyes on your work!",
    "focus_success": "You stayed focused for {label}! +{points} affection",
    "focus_fail": [
        "You looked away too long! That focus session is a bust.",
        "Hey! You were supposed to be focusing! No reward this time.",
        "I saw that. Eyes off the screen means no reward.",
    ],
    "focus_looked_away": [
        "Eyes on your work! -{points} affection this session",
        "I'm watching you! Look back at the screen. -{points} affection this session",
        "Where are you looking? Focus! -{points} affection this session",
    ],
    "no_camera": "I couldn't open your webcam.",
    "camera_busy": "I'm already watching the camera!",
    "workout_start": "Workout time! {reps} {exercise}. Press Q in the camera window to stop.",
    "workout_done": "{reps} {exercise} done, {good} with good form! +{points} affection",
    "workout_partial": "Nice effort: {reps} {exercise}, {good} with good form. +{points} affection",
    "workout_cancelled": "Workout cancelled. Maybe later?",
    "new_look": "Ooh, a new look!",
    "need_points": "I need {missing} more affection for that one.",
    "focus_app_set": "Got it! I'll send you back to {app}.",
    "focus_app_cleared": "Okay, I won't switch your apps.",
    "dashboard_missing": "The dashboard isn't built yet. Run npm install, then npm run build, in the frontend folder.",
}

DASHBOARD_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
BUILT_DASHBOARD_URL = "http://127.0.0.1:8000/dashboard/"
DEV_DASHBOARD_PORT = 5173
DEV_DASHBOARD_URL = f"http://localhost:{DEV_DASHBOARD_PORT}/"


def port_is_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False

# Movement tuning (per 25 ms tick)
TICK_MS = 25
GRAVITY = 1.6
MAX_FALL_SPEED = 28
HOP_SPEED = 11
WALK_SPEED = 1
PANIC_SPEED = 4
WADDLE_DEGREES = 4
WADDLE_TICKS = 6  # Ticks per waddle frame
IDLE_PAUSE = (3, 10)  # Seconds to stand still between walks
RAPID_CLICK_WINDOW = 6  # Seconds
RAPID_CLICK_LIMIT = 8  # Clicks inside the window before the pet gets annoyed
CHATTER_INTERVAL_MS = 60_000
CHATTER_CHANCE = 0.3


# Desktop pet related classes
class SpeechBubble(QWidget):
    """Rounded speech bubble with a tail that points at the pet."""

    PADDING = 10
    TAIL = 10
    RADIUS = 12
    MAX_TEXT_WIDTH = 240
    STYLES = {  # mood: (fill, border, text)
        "normal": ("#ffffff", "#4a4a4a", "#222222"),
        "happy": ("#fff8e1", "#e0a100", "#5a3d00"),
        "angry": ("#ffebee", "#d32f2f", "#b71c1c"),
    }

    def __init__(self, text, mood="normal"):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.text = text
        self.fill, self.border, self.text_color = self.STYLES.get(mood, self.STYLES["normal"])
        self.text_font = QFont("Segoe UI", 11, QFont.Bold if mood == "angry" else QFont.DemiBold)

        text_rect = QFontMetrics(self.text_font).boundingRect(
            QRect(0, 0, self.MAX_TEXT_WIDTH, 1000), Qt.AlignCenter | Qt.TextWordWrap, text
        )
        self.setFixedSize(
            text_rect.width() + 2 * self.PADDING + 4,
            text_rect.height() + 2 * self.PADDING + self.TAIL + 4,
        )
        self.tail_x = self.width() // 2

    def set_tail_x(self, x):
        self.tail_x = min(max(x, self.RADIUS + 10), self.width() - self.RADIUS - 10)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        body = QRectF(2, 2, self.width() - 4, self.height() - 4 - self.TAIL)
        shape = QPainterPath()
        shape.addRoundedRect(body, self.RADIUS, self.RADIUS)
        tail = QPainterPath()
        tail.moveTo(self.tail_x - 8, body.bottom() - 1)
        tail.lineTo(self.tail_x, body.bottom() + self.TAIL)
        tail.lineTo(self.tail_x + 8, body.bottom() - 1)
        tail.closeSubpath()
        shape = shape.united(tail)

        painter.setPen(QPen(QColor(self.border), 2))
        painter.setBrush(QColor(self.fill))
        painter.drawPath(shape)

        painter.setPen(QColor(self.text_color))
        painter.setFont(self.text_font)
        text_area = body.adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        painter.drawText(text_area, Qt.AlignCenter | Qt.TextWordWrap, self.text)


class DesktopPet(QLabel):
    # Emitted from camera worker threads; Qt delivers them on the UI thread
    focus_session_done = pyqtSignal(float, int)  # minutes, FOCUS_* result
    focus_distracted = pyqtSignal(float, str)  # seconds looked away, session label
    workout_done = pyqtSignal(object)  # exercise_tracker.WorkoutResult
    camera_session_ended = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Never take focus from the user's window
        self._on_top_applied = None

        self.camera_busy = False  # Only one webcam session (focus or workout) at a time
        self.focus_session_done.connect(self.on_focus_session_done)
        self.focus_distracted.connect(self.on_focus_distracted)
        self.workout_done.connect(self.on_workout_done)
        self.camera_session_ended.connect(self.on_camera_session_ended)

        # Interaction state
        self.is_dragging = False
        self.dragged = False
        self.press_pos = QPoint()
        self.drag_offset = QPoint()
        self.recent_clicks = []
        self.is_annoyed = False
        self.is_punishing = False

        # Movement state
        self.vy = 0.0
        self.walk_remaining = 0
        self.walk_direction = 1
        self.facing_right = False
        self.next_walk_at = time.monotonic() + random.uniform(2, 5)
        self.tick_count = 0
        self.frame_key = None

        # Speech
        self.bubble = None
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self.hide_bubble)

        # Appearance (restored from the save file)
        if pet_status.current_sprite not in pet_status.unlocked_sprites:
            pet_status.current_sprite = "roach.webp"
        self.load_image()
        area = self.screen_area()
        self.move(area.x() + area.width() - self.width() - 50, self.floor_y(area))
        self.apply_window_state()

        # Timers and loops
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(TICK_MS)

        # Scanning windows
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_for_distractions)
        self.scan_timer.start(5000)
        self.focus_away_seconds = 0  # Seconds spent looking away in the current Focus Mode session

        self.chatter_timer = QTimer(self)
        self.chatter_timer.timeout.connect(self.idle_chatter)
        self.chatter_timer.start(CHATTER_INTERVAL_MS)

        QTimer.singleShot(800, self.greet)

    # Window state
    def apply_window_state(self, force_top=False):
        """Applies Always on Top from the user's preference or during punishment."""
        on_top = force_top or pet_status.always_on_top
        if on_top == self._on_top_applied:
            return  # setWindowFlags hides the window, so skip it when nothing changed
        self._on_top_applied = on_top
        # WindowDoesNotAcceptFocus: clicking or raising the pet must never take focus
        # from the user's window, or the distraction check would see the pet instead
        flags = (
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        if on_top:
            flags |= Qt.WindowStaysOnTopHint
        pos = self.pos()
        self.setWindowFlags(flags)
        self.move(pos)
        self.show()

    def toggle_always_on_top(self):
        pet_status.always_on_top = not pet_status.always_on_top
        pet_status.save_to_file()
        if not self.is_punishing:
            self.apply_window_state()

    def screen_area(self):
        return QApplication.desktop().availableGeometry(self)

    def floor_y(self, area):
        return area.y() + area.height() - self.height()

    # Appearance
    def load_image(self):
        """Builds the waddle frames for the current model and size."""
        model = MODELS_BY_FILE.get(pet_status.current_sprite)
        self.faces_left = model[3] if model else False
        size = dict(PET_SIZES).get(pet_status.pet_size, 235)

        source = QPixmap(pet_status.current_sprite)
        if source.isNull():
            # Fallback if image path is wrong
            source = QPixmap(size, size)
            source.fill(Qt.transparent)
            painter = QPainter(source)
            painter.setBrush(QColor("gray"))
            painter.drawRoundedRect(0, 0, size - 1, size - 1, 16, 16)
            painter.end()

        base = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        mirrored = base.transformed(QTransform().scale(-1, 1))
        # Room on each side so the waddle doesn't clip the sprite
        pad = round(base.height() * math.sin(math.radians(WADDLE_DEGREES))) + 2

        self.frames = {}
        for flip, image in ((False, base), (True, mirrored)):
            for angle in (-WADDLE_DEGREES, 0, WADDLE_DEGREES):
                canvas = QPixmap(image.width() + 2 * pad, image.height())
                canvas.fill(Qt.transparent)
                painter = QPainter(canvas)
                painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
                painter.translate(canvas.width() / 2, canvas.height())  # Pivot on the feet
                painter.rotate(angle)
                painter.drawPixmap(QPointF(-image.width() / 2, -image.height()), image)
                painter.end()
                self.frames[(flip, angle)] = canvas

        self.setFixedSize(canvas.size())
        self.frame_key = None
        self.update_frame()

    def reload_appearance(self):
        """Reloads the sprite while keeping the pet's feet where they were."""
        bottom = self.y() + self.height()
        self.load_image()
        self.move(self.x(), bottom - self.height())

    def update_frame(self):
        walking = self.walk_remaining > 0 and not self.is_dragging
        angle = 0
        if walking:
            ticks_per_frame = WADDLE_TICKS // 2 if self.is_punishing else WADDLE_TICKS
            phase = (self.tick_count // ticks_per_frame) % 4
            angle = (0, WADDLE_DEGREES, 0, -WADDLE_DEGREES)[phase]
        key = (self.faces_left and self.facing_right, angle)
        if key != self.frame_key:
            self.frame_key = key
            self.setPixmap(self.frames[key])

    def change_pet_sprite(self, model_name, image_path, cost):
        if image_path not in pet_status.unlocked_sprites:
            if pet_status.affection_points < cost:
                missing = cost - pet_status.affection_points
                self.say(DIALOGUE["need_points"].format(missing=missing))
                return
            # Getting new sprites costs points
            pet_status.affection_points -= cost
            pet_status.unlocked_sprites.append(image_path)
            print(f"Unlocked {model_name} for {cost} points.")
        elif image_path == pet_status.current_sprite:
            return

        pet_status.current_sprite = image_path
        pet_status.save_to_file()
        self.reload_appearance()
        self.say(DIALOGUE["new_look"], "happy")
        self.hop()

    def set_pet_size(self, label):
        pet_status.pet_size = label
        pet_status.save_to_file()
        self.reload_appearance()

    # Movement
    def tick(self):
        self.tick_count += 1
        self.apply_physics()
        self.walk()
        self.update_frame()

    def on_ground(self):
        return not self.is_dragging and self.vy == 0 and self.y() >= self.floor_y(self.screen_area())

    def apply_physics(self):
        if self.is_dragging:
            return
        area = self.screen_area()
        floor = self.floor_y(area)
        x = min(max(self.x(), area.x()), area.x() + area.width() - self.width())
        y = self.y()

        if y < floor or self.vy < 0:
            self.vy = min(self.vy + GRAVITY, MAX_FALL_SPEED)
            y = min(y + round(self.vy), floor)
            if y >= floor:
                self.vy = 0
        elif y > floor:
            y = floor  # e.g. dragged below the taskbar

        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def hop(self):
        if self.on_ground():
            self.vy = -HOP_SPEED

    def walk(self):
        if self.is_dragging or self.is_annoyed or not self.on_ground():
            return

        if self.walk_remaining <= 0:
            if self.is_punishing:
                # Short, fast pacing back and forth
                self.walk_remaining = random.randint(30, 80)
            elif time.monotonic() >= self.next_walk_at:
                self.walk_remaining = random.randint(80, 320)
            else:
                return
            self.walk_direction = random.choice([-1, 1])
            self.facing_right = self.walk_direction > 0

        area = self.screen_area()
        speed = PANIC_SPEED if self.is_punishing else WALK_SPEED
        next_x = self.x() + self.walk_direction * speed
        if not area.x() <= next_x <= area.x() + area.width() - self.width():
            self.walk_direction *= -1
            self.facing_right = self.walk_direction > 0
            return

        self.move(next_x, self.y())
        self.walk_remaining -= speed
        if self.walk_remaining <= 0:
            self.walk_remaining = 0
            self.next_walk_at = time.monotonic() + random.uniform(*IDLE_PAUSE)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.position_bubble()

    # Speech
    def say(self, text, mood="normal", duration_ms=None, persistent=False, force=False):
        """Shows a speech bubble above the pet. While punishing, only forced lines show."""
        if self.is_punishing and not force:
            return
        self.hide_bubble()
        self.bubble = SpeechBubble(text, mood)
        self.position_bubble()
        self.bubble.show()
        if persistent:
            self.bubble_timer.stop()
        else:
            self.bubble_timer.start(duration_ms or min(7000, 2000 + 60 * len(text)))

    def hide_bubble(self):
        if self.bubble:
            self.bubble.close()
            self.bubble.deleteLater()
            self.bubble = None

    def position_bubble(self):
        if not self.bubble:
            return
        area = self.screen_area()
        bubble = self.bubble
        center = self.x() + self.width() // 2
        left = min(
            max(center - bubble.width() // 2, area.x() + 4),
            area.x() + area.width() - bubble.width() - 4,
        )
        top = max(self.y() - bubble.height() + 6, area.y())
        bubble.move(left, top)
        bubble.set_tail_x(center - left)

    def greet(self):
        if pet_status.productivity_app is None:
            self.say(DIALOGUE["first_run_tip"], duration_ms=7000)
        else:
            self.say(random.choice(DIALOGUE["greet"]))
        self.hop()

    def idle_chatter(self):
        if (
            self.bubble
            or self.is_punishing
            or self.is_annoyed
            or self.is_dragging
            or self.camera_busy
        ):
            return
        if random.random() < CHATTER_CHANCE:
            self.say(random.choice(DIALOGUE["idle"]))

    # Distraction tracking
    def scan_for_distractions(self):
        # The pet's right-click menu takes focus while open, so the active window says
        # nothing about what the user is doing. Keep the current mood until it closes.
        if QApplication.activePopupWidget():
            return

        found_distractions = get_active_distractions()
        if found_distractions is None:
            return  # The pet's own window is active; same as above

        if not found_distractions:
            self.stop_punishment()
            return

        # Pet stays on top no matter what whenever a distraction is found
        self.apply_window_state(force_top=True)
        self.raise_()

        titles_only = [item[1] for item in found_distractions]
        print(f"Active distractions: {titles_only}")
        pet_status.find_anger_causes(found_distractions)
        pet_status.increment_anger(cause=found_distractions[0][0], amount=DISTRACTION_PENALTY)

        if not self.is_punishing:
            self.is_punishing = True
            self.walk_remaining = 0
            platform_name = found_distractions[0][0]
            line = random.choice(DIALOGUE["distracted"]).format(platform=platform_name)
            self.say(line, "angry", persistent=True, force=True)

        if pet_status.productivity_app:
            focus_keeper(pet_status.productivity_app)  # Bring app to front

    def stop_punishment(self):
        if not self.is_punishing:
            return
        print("Distractions eliminated.")
        self.is_punishing = False
        self.walk_remaining = 0
        self.next_walk_at = time.monotonic() + random.uniform(*IDLE_PAUSE)
        self.say(random.choice(DIALOGUE["back_on_track"]), "happy")
        # Always on Top preference stays the same
        self.apply_window_state()

    # Mouse interaction
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.dragged = False
            self.press_pos = event.globalPos()
            self.drag_offset = event.globalPos() - self.pos()
            self.vy = 0
        elif event.button() == Qt.RightButton:
            self.pet_right_click(event.globalPos())

    def mouseMoveEvent(self, event):
        if not self.is_dragging:
            return
        # Small wobbles still count as a click
        if not self.dragged and (event.globalPos() - self.press_pos).manhattanLength() < 5:
            return
        self.dragged = True
        self.walk_remaining = 0
        self.move(event.globalPos() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.is_dragging:
            return
        self.is_dragging = False
        if self.dragged:
            self.next_walk_at = time.monotonic() + random.uniform(*IDLE_PAUSE)
        else:
            self.pet_left_click()

    def pet_left_click(self):
        if self.is_annoyed or self.is_punishing:
            return

        now = time.monotonic()
        self.recent_clicks = [t for t in self.recent_clicks if now - t < RAPID_CLICK_WINDOW]
        self.recent_clicks.append(now)

        if len(self.recent_clicks) < RAPID_CLICK_LIMIT:
            self.say(random.choice(DIALOGUE["click"]))
            return

        self.recent_clicks.clear()
        self.is_annoyed = True
        self.walk_remaining = 0
        self.say(random.choice(DIALOGUE["annoyed"]), "angry", duration_ms=4000)
        # Formatted like the platform/title anger causes so excessive taps increment by 1
        pet_status.find_anger_causes([("Desktop Pet", "Too many taps")], increment_num=1)
        pet_status.increment_anger(cause="Too many taps")
        QTimer.singleShot(5000, self.calm_down)

    def calm_down(self):
        self.is_annoyed = False

    def show_thanks(self):
        if self.is_punishing:
            return
        self.say(random.choice(DIALOGUE["petted"]), "happy")
        self.hop()
        pet_status.increment_happiness(source="Petting", detail="Pet the pet")

    def pet_right_click(self, global_pos):
        menu = QMenu(self)

        header = menu.addAction(f"♥  {pet_status.get_affection_points()} affection")
        header.setEnabled(False)
        menu.addSeparator()

        pet_action = menu.addAction("Pet")
        pet_action.triggered.connect(self.show_thanks)

        focus_menu = menu.addMenu("Focus Mode")
        focus_menu.setEnabled(not self.camera_busy)
        for label, minutes in FOCUS_TIMES:
            action = focus_menu.addAction(f"Focus for {label}")
            action.triggered.connect(lambda checked, l=label, m=minutes: self.start_focus_timer(l, m))

        workout_menu = menu.addMenu("Workout")
        workout_menu.setEnabled(not self.camera_busy)
        last = pet_status.last_exercise
        if last in EXERCISES:
            again = workout_menu.addAction(f"{EXERCISES[last]['name']} again")
            again.triggered.connect(lambda checked, e=last: self.start_workout(e))
            workout_menu.addSeparator()
        for category, exercises in EXERCISE_CATEGORIES.items():
            category_menu = workout_menu.addMenu(category)
            for exercise_id, data in exercises.items():
                action = category_menu.addAction(data["name"])
                action.triggered.connect(lambda checked, e=exercise_id: self.start_workout(e))

        menu.addSeparator()

        current_affection = pet_status.get_affection_points()
        sprite_menu = menu.addMenu("Change Model")
        for name, path, cost, _ in PET_MODELS:
            is_owned = path in pet_status.unlocked_sprites
            can_afford = current_affection >= cost
            if is_owned:
                display_name = name
            elif can_afford:
                display_name = f"Unlock {name} ({cost} pts)"
            else:
                display_name = f"{name} (needs {cost - current_affection} more pts)"

            action = sprite_menu.addAction(display_name)
            if not is_owned and not can_afford:
                action.setEnabled(False)
            else:
                action.setCheckable(True)
                action.setChecked(pet_status.current_sprite == path)
                action.triggered.connect(
                    lambda checked, n=name, p=path, c=cost: self.change_pet_sprite(n, p, c)
                )

        size_menu = menu.addMenu("Pet Size")
        for label, _ in PET_SIZES:
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(pet_status.pet_size == label)
            action.triggered.connect(lambda checked, l=label: self.set_pet_size(l))

        # Focus app the pet drags you back to when it catches a distraction.
        # Filled when the submenu opens because scanning apps takes a second or two.
        app_menu = menu.addMenu("Focus App")
        app_menu.aboutToShow.connect(lambda: self.populate_focus_app_menu(app_menu))

        top_action = menu.addAction("Always on Top")
        top_action.setCheckable(True)
        top_action.setChecked(pet_status.always_on_top)
        top_action.triggered.connect(self.toggle_always_on_top)

        dashboard_action = menu.addAction("Open Dashboard")
        dashboard_action.triggered.connect(self.open_dashboard)

        menu.addSeparator()

        quit_action = menu.addAction("Quit Kurou Pet")
        quit_action.triggered.connect(qApp.quit)

        # Testing shortcuts
        menu.addSeparator()
        test_label, test_minutes = TEST_FOCUS_TIME
        test_focus_action = menu.addAction(f"Test: Focus for {test_label}")
        test_focus_action.setEnabled(not self.camera_busy)
        test_focus_action.triggered.connect(
            lambda: self.start_focus_timer(test_label, test_minutes)
        )
        unlock_action = menu.addAction("Test: Unlock all models")
        unlock_action.triggered.connect(self.debug_unlock_all)

        menu.exec_(global_pos)

    def populate_focus_app_menu(self, app_menu):
        app_menu.clear()
        current = pet_status.productivity_app

        none_action = app_menu.addAction("None (don't switch apps)")
        none_action.setCheckable(True)
        none_action.setChecked(current is None)
        none_action.triggered.connect(lambda: self.set_focus_app(None))
        app_menu.addSeparator()

        open_apps = list_open_apps()
        # Keep showing the saved choice even if it has no usable window right now
        if current and current not in open_apps:
            open_apps[current] = "no work window open"

        for app_name, title in sorted(open_apps.items(), key=lambda kv: kv[0].lower()):
            short_title = title if len(title) <= 40 else title[:37] + "..."
            action = app_menu.addAction(f"{display_app_name(app_name)} - {short_title}")
            action.setCheckable(True)
            action.setChecked(app_name == current)
            action.triggered.connect(lambda checked, a=app_name: self.set_focus_app(a))

    def set_focus_app(self, app_name):
        pet_status.productivity_app = app_name
        pet_status.save_to_file()
        print(f"Focus app set to: {app_name}")
        if app_name:
            self.say(DIALOGUE["focus_app_set"].format(app=display_app_name(app_name)))
        else:
            self.say(DIALOGUE["focus_app_cleared"])

    def debug_unlock_all(self):
        for _, path, _, _ in PET_MODELS:
            if path not in pet_status.unlocked_sprites:
                pet_status.unlocked_sprites.append(path)
        pet_status.save_to_file()
        self.say("All models unlocked!", "happy")

    def open_dashboard(self):
        # Prefer the Vite dev server when it's running (live frontend edits),
        # otherwise the built dashboard served by the pet's own API server.
        if port_is_open(DEV_DASHBOARD_PORT):
            webbrowser.open(DEV_DASHBOARD_URL)
        elif DASHBOARD_DIST.is_dir():
            webbrowser.open(BUILT_DASHBOARD_URL)
        else:
            self.say(DIALOGUE["dashboard_missing"], duration_ms=8000)

    # Webcam sessions
    def start_camera_session(self, target):
        """Runs a blocking webcam loop off the UI thread so the pet stays responsive."""
        self.camera_busy = True

        def run():
            try:
                target()
            except Exception as e:
                print(f"Camera session error: {e}")
            finally:
                self.camera_session_ended.emit()

        threading.Thread(target=run, daemon=True).start()

    def on_camera_session_ended(self):
        self.camera_busy = False

    def start_focus_timer(self, label, minutes):
        if self.camera_busy:
            self.say(DIALOGUE["camera_busy"])
            return
        self.say(DIALOGUE["focus_start"].format(label=label))
        self.focus_away_seconds = 0

        def run():
            # The tracker reports looking away from its worker thread; the signal
            # hands it to the UI thread
            result = face_tracker.start_timer(
                minutes, on_distracted=lambda seconds: self.focus_distracted.emit(seconds, label)
            )
            if result is None:
                status = FOCUS_NO_CAMERA
            else:
                status = FOCUS_SUCCESS if result else FOCUS_FAILED
            self.focus_session_done.emit(minutes, status)

        self.start_camera_session(run)

    def on_focus_session_done(self, minutes, status):
        label = FOCUS_LABELS.get(minutes, f"{minutes:g} minutes")
        if status == FOCUS_SUCCESS:
            points = focus_reward(minutes)
            pet_status.increment_happiness(points, source="Focus Mode", detail=label)
            pet_status.save_to_file()
            self.say(DIALOGUE["focus_success"].format(label=label, points=points), "happy")
            self.hop()
        elif status == FOCUS_NO_CAMERA:
            self.say(DIALOGUE["no_camera"])
        else:
            self.fail_focus(label)

    def on_focus_distracted(self, seconds, label):
        """Every second spent looking away during Focus Mode costs a point."""
        seconds = int(seconds)
        pet_status.find_anger_causes([(LOOKING_AWAY, f"Focus Mode ({label})")], increment_num=seconds)
        pet_status.increment_anger(cause=LOOKING_AWAY, amount=DISTRACTION_PENALTY * seconds)
        pet_status.save_to_file()
        # Speak up every few seconds rather than every second, so the bubble isn't spammed
        before = self.focus_away_seconds
        self.focus_away_seconds += seconds
        if before // LOOKED_AWAY_REMINDER_SECONDS != self.focus_away_seconds // LOOKED_AWAY_REMINDER_SECONDS:
            self.say(
                random.choice(DIALOGUE["focus_looked_away"]).format(
                    points=DISTRACTION_PENALTY * self.focus_away_seconds
                ),
                "angry",
                duration_ms=4000,
            )

    def fail_focus(self, label):
        # Same angry reaction as being poked too much: red bubble, stops in place.
        # The looking-away penalties were already taken; failing just loses the reward.
        self.is_annoyed = True
        self.walk_remaining = 0
        self.say(random.choice(DIALOGUE["focus_fail"]), "angry", duration_ms=5000, force=True)
        failed = pet_status.anger_causes.setdefault("Focus Mode", {"Failed sessions": 0})
        failed["Failed sessions"] += 1
        pet_status.save_to_file()
        QTimer.singleShot(5000, self.calm_down)

    def start_workout(self, exercise_id):
        if self.camera_busy:
            self.say(DIALOGUE["camera_busy"])
            return
        pet_status.last_exercise = exercise_id
        pet_status.save_to_file()
        name = EXERCISES[exercise_id]["name"]
        self.say(
            DIALOGUE["workout_start"].format(reps=WORKOUT_REPS, exercise=name.lower()),
            duration_ms=6000,
        )

        def run():
            result = workout(pet_status, limit=WORKOUT_REPS, exercise=exercise_id)
            self.workout_done.emit(result)

        self.start_camera_session(run)

    def on_workout_done(self, result):
        history.record_workout(result)
        details = {
            "reps": result.reps,
            "exercise": result.exercise.lower(),
            "good": result.good_form_reps,
            "points": result.points,
        }
        if not result.camera_ok:
            self.say(DIALOGUE["no_camera"])
        elif result.completed:
            self.say(DIALOGUE["workout_done"].format(**details), "happy")
            self.hop()
        elif result.reps > 0:
            self.say(DIALOGUE["workout_partial"].format(**details), "happy")
        else:
            self.say(DIALOGUE["workout_cancelled"])


def display_app_name(app_name):
    """'Code.exe' -> 'Code'"""
    return app_name[:-4] if app_name.lower().endswith(".exe") else app_name


def spawn_pet():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Added because menu kept closing the pet
    pet = DesktopPet()  # noqa: F841 - keep a reference so the window isn't garbage collected
    status_code = app.exec_()
    pet_status.save_to_file()
    sys.exit(status_code)


if __name__ == "__main__":
    spawn_pet()
