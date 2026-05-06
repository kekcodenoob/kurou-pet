import sys
import random
import pyautogui
import platform
import os
import json
import pywinctl as pwc
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMenu,
    QAction,
    qApp,
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
)
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QColor

from facelandmarker import face_tracker


class PerformanceReviewWindow(QWidget):
    # Pop-up to display the same stats as in pet_status
    def __init__(self, status):
        super().__init__()
        self.status = status
        self.setWindowTitle("Pet Performance Review")
        self.setFixedSize(400, 500)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # Keep it above other windows

        layout = QVBoxLayout()
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        layout.addWidget(self.text_display)

        refresh_btn = QPushButton("Refresh Stats")
        refresh_btn.clicked.connect(self.update_stats)
        layout.addWidget(refresh_btn)

        self.setLayout(layout)
        self.update_stats()

    def update_stats(self):
        """Formats the data from PetStatus into a readable report."""
        report = "--- PET OVERALL STATUS ---\n"
        report += f"Affection Points: {self.status.get_affection_points()}\n"
        report += f"Happiness Total: {self.status.get_happiness_count()}\n"
        report += f"Anger Total: {self.status.get_anger_count()}\n\n"

        report += "--- SOURCES OF JOY ---\n"
        for joy, count in self.status.happiness_causes.items():
            report += f"• {joy}: {count} times\n"

        report += "\n--- SOURCES OF ANGER ---\n"
        for platform_name, data in self.status.anger_causes.items():
            if platform_name == "Desktop Pet":
                report += f"• {platform_name}: {data.get('Excessive taps', 0)} annoying taps\n"
            else:
                report += f"• {platform_name}: {data.get('Total seconds', 0)}s spent distracted\n"
                for tab, seconds in data.get("Tabs", {}).items():
                    report += f"   - {tab[:30]}... ({seconds}s)\n"

        self.text_display.setPlainText(report)


# --- END NEW CLASS ---


class AngerSource:
    name: str
    seconds: int


# Getting info from the pet to display on the FastAPI server
class PetStatus:
    def __init__(self, filename="pet_data.json"):
        self.filename = filename
        self.affection_points = 0
        self.happiness_count = 0
        self.happiness_causes = {}
        self.anger_count = 0
        self.anger_causes = {}
        self.load_from_file()  # Auto-load on creation

    def save_to_file(self):
        """Writes current state to JSON."""
        data = {
            "affection_points": self.affection_points,
            "happiness_count": self.happiness_count,
            "happiness_causes": self.happiness_causes,
            "anger_count": self.anger_count,
            "anger_causes": self.anger_causes,
        }
        with open(self.filename, "w") as f:
            json.dump(data, f, indent=4)

    def load_from_file(self):
        """Reads previous state from JSON if it exists."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    data = json.load(f)
                    self.affection_points = data.get("affection_points", 0)
                    self.happiness_count = data.get("happiness_count", 0)
                    self.happiness_causes = data.get("happiness_causes", {})
                    self.anger_count = data.get("anger_count", 0)
                    self.anger_causes = data.get("anger_causes", {})
            except Exception as e:
                print(f"Error loading save file: {e}")

    def increment_anger(self):
        self.affection_points -= 1
        self.anger_count += 1

    def increment_happiness(self):
        self.affection_points += 1
        self.happiness_count += 1

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

        return self.anger_causes

    def get_happiness_count(self):
        return self.happiness_count

    def find_happiness_causes(self, happiness_source):
        for joy in happiness_source:
            if joy in self.happiness_causes:
                self.happiness_causes[joy] += 1
            else:
                self.happiness_causes[joy] = 1
        return self.happiness_causes


pet_status = PetStatus()


# Window tracking stuff
def focus_keeper(target_title):
    # Brings intended window to foreground if possible
    # Forces window pop up with simulated keystrokes across each platform
    if platform.system() == "Windows":
        pyautogui.press("alt")
    elif platform.system() == "Darwin":  # macOS
        pyautogui.hotkey("command", "tab")
    elif platform.system() == "Linux":
        pyautogui.hotkey("alt", "tab")

    try:
        windows = pwc.getWindowsWithTitle(target_title)
        if windows:
            target = windows[0]
            if target.isMinimized:
                target.restore()
            target.activate()
        else:
            print(f"Couldn't focus '{target_title}'. Window may not be present.")
    except Exception as e:
        print(f"Focus error: {e}")


def get_active_distractions():
    # Hunts for games/social media by scanning visible window titles.
    game_title = [
        "Steam",
        "Launcher",
        "v1.0",
        "Early Access",
        "Alpha",
        "Beta",
        "Made with Unity",
        "Unreal Engine",
        "CryEngine",
        "DEMO",
        "Loading Bay",
        "DELTARUNE",
    ]
    social_title = [
        "Facebook",
        "Twitter",
        "Instagram",
        "Reddit",
        "r/",
        "YouTube",
        "TikTok",
        "Twitch",
        "Pinterest",
    ]

    try:
        all_titles = pwc.getAllTitles()
    except Exception as e:
        print(f"Window scan error: {e}")
        return []

    found_distractions = []
    for title in all_titles:
        if not title:
            continue
        lowered = title.lower()

        # Trying to match Tabs to their general platforms
        matched_platform = None
        for keyword in game_title:
            if keyword.lower() in lowered:
                if keyword == "Launcher":
                    matched_platform = "Game Launcher"
                else:
                    matched_platform = keyword
                break
        if not matched_platform:
            for keyword in social_title:
                if keyword.lower() in lowered:
                    if keyword == "r/":  # r/ was weird so I replaced its displayed name
                        matched_platform = "Reddit"
                    else:
                        matched_platform = keyword
                    break
        # Add platform and specific window name to distractions
        if matched_platform:
            found_distractions.append((matched_platform, title))

    return found_distractions


# Desktop pet related classes
class SpeechBubble(QLabel):
    def __init__(self, text, color, x, y, font_family, font_size):
        super().__init__()
        # Speech always on top of monitor
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.raise_()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setText(text)
        self.setStyleSheet(
            f"color: {color}; font-family: '{font_family}'; font-size: {font_size}px; font-weight: bold;"
        )
        self.setFixedSize(self.sizeHint())
        self.move(int(x), int(y))
        self.show()


class DesktopPet(QLabel):
    def __init__(self, productivity_app="Firefox Nightly"):  # Subject to change ofc :P
        super().__init__()
        # Pet always on top of monitor
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Variables
        self.productivity_app = productivity_app
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.times_clicked = 0
        self.is_annoyed = False
        self.is_punishing = False
        self.total_walk_distance = 0
        self.walk_direction = 0

        self.review_window = None
        self.is_tracking_work = False
        self.is_tracking_workout = False

        # Image setup
        self.load_image()
        screen_geom = QApplication.desktop().availableGeometry(self)
        self.move(
            screen_geom.width() - self.width() - 50,
            screen_geom.height() - self.height(),
        )
        self.show()

        # Timers and loops
        self.gravity_timer = QTimer(self)
        self.gravity_timer.timeout.connect(self.gravity)
        self.gravity_timer.start(25)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.idle_walk)
        self.walk_timer.start(25)

        # Scanning windows
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_for_distractions)
        self.scan_timer.start(5000)

        self.active_bubbles = []
        self.punish_bubble = None

    def load_image(self):
        pet_width = 235
        pet_height = 235
        pixmap = QPixmap(r"roach.webp")

        if not pixmap.isNull():
            self.pixmap = pixmap.scaled(
                pet_width, pet_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
        else:
            self.pixmap = QPixmap(pet_width, pet_height)
            self.pixmap.fill(Qt.transparent)
            painter = QPainter(self.pixmap)
            colors = [
                QColor("orange"),
                QColor("purple"),
                QColor("blue"),
                QColor("pink"),
            ]
            painter.setBrush(random.choice(colors))
            painter.drawRect(0, 0, pet_width - 1, pet_height - 1)
            painter.end()

        self.setPixmap(self.pixmap)
        self.setFixedSize(self.pixmap.width(), self.pixmap.height())
        self.setMask(self.pixmap.mask())

    # Same distraction hunter as OG window tracking
    def scan_for_distractions(self):
        # Pet always returns on top even with forced-fullscreen games (like DELTARUNE)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        self.raise_()
        found_distractions = get_active_distractions()

        if found_distractions:
            # Chose to print only titles since we know the platform from just that :DD
            titles_only = [item[1] for item in found_distractions]
            print(f"Active distractions: {titles_only}")

            pet_status.find_anger_causes(found_distractions)
            self.trigger_punishment()
            pet_status.increment_anger()
        else:
            self.stop_punishment()

    def trigger_punishment(self):
        self.is_punishing = True
        focus_keeper(self.productivity_app)  # Bring app to front

        # Create angry message only if it's not already there
        if not self.punish_bubble:
            center_x = self.x() + (self.width() / 2)
            self.punish_bubble = SpeechBubble(
                text="GET BACK ON THE GRIND!!!",
                color="red",
                x=center_x - 100,
                y=self.y() - 100,
                font_family="Times New Roman",
                font_size=35,
            )

        # Boost pet movement frequency to emulate anger
        self.walk_timer.setInterval(5)

    def stop_punishment(self):
        if self.is_punishing:
            print("Distractions eliminated.")
            self.is_punishing = False
            self.walk_timer.setInterval(25)  # Return to normal speed

            if self.punish_bubble:
                self.punish_bubble.deleteLater()
                self.punish_bubble = None

    # OG pet functions
    def gravity(self):
        if not self.is_dragging:
            working_screen = QApplication.desktop().availableGeometry(self)
            whole_screen = QApplication.desktop().screenGeometry(self)
            screen_bottom = working_screen.bottom()
            pet_right = self.x() + self.width()
            pet_bottom = self.y() + self.height()

            if pet_bottom < screen_bottom:
                fall_amount = 20
                new_y = min(self.y() + fall_amount, screen_bottom - self.height())
                self.move(self.x(), new_y)

            if (
                pet_right > whole_screen.right()
                or self.x() < whole_screen.left()
                or pet_bottom > screen_bottom + 30
            ):
                self.move(
                    whole_screen.right() - self.width(), screen_bottom - self.height()
                )

    def idle_walk(self):  # TBD: Random chatter while chilling on screen
        screen_geom = QApplication.desktop().availableGeometry(self)

        if (
            not self.is_dragging
            and not self.is_annoyed
            and self.y() + self.height() >= screen_geom.bottom()
        ):
            if self.total_walk_distance <= 0:
                if self.is_punishing:
                    # Small distances w/ swift movement like pacing back and forth erratically
                    self.total_walk_distance = random.randint(20, 50)
                    self.walk_direction = random.choice([-5, 5])
                elif random.randint(1, 50) > 45:  # Normal walking
                    self.total_walk_distance = random.randint(100, 350)
                    self.walk_direction = random.choice([-1, 1])
            else:
                next_x = self.x() + self.walk_direction
                if screen_geom.left() <= next_x <= screen_geom.right() - self.width():
                    self.move(next_x, self.y())
                    self.total_walk_distance -= 1
                    # Keep the punishment bubble tracking above pet
                    if self.punish_bubble:
                        self.punish_bubble.move(
                            int(self.x() + (self.width() / 2) - 180),
                            int(self.y() - 100),
                        )
                else:
                    self.walk_direction *= -1

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_offset = event.globalPos() - self.pos()
            self.pet_left_click()
        elif event.button() == Qt.RightButton:
            self.pet_right_click(event.globalPos())

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.move(event.globalPos() - self.drag_offset)
            if self.punish_bubble:
                self.punish_bubble.move(
                    int(self.x() + (self.width() / 2) - 180), int(self.y() - 100)
                )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False

    def pet_left_click(self):
        speech_options = ["MEOOOOW", "HELLO!!", "HI", "SUP GUYS", "WHAT'S POPPIN"]
        color_options = ["orange", "purple", "blue", "pink"]
        center_x = self.x() + (self.width() / 2)

        if not self.is_annoyed and not self.is_punishing:
            self.times_clicked += 1
            bubble = SpeechBubble(
                text=random.choice(speech_options),
                color=random.choice(color_options),
                x=center_x + random.randint(-100, 10),
                y=self.y() - random.randint(50, 150),
                font_family="Comic Sans MS",
                font_size=20,
            )
            self.active_bubbles.append(bubble)
            QTimer.singleShot(2000, bubble.deleteLater)

        if self.times_clicked >= 10 and not self.is_annoyed and not self.is_punishing:
            self.is_annoyed = True
            annoyed_speech = SpeechBubble(
                text="OK THAT'S ENOUGH NOW!!",
                color="red",
                x=center_x - 240,
                y=self.y() - 100,
                font_family="Times New Roman",
                font_size=35,
            )
            # Formatted pet specific anger causes like the platform/title ones, so I can increment excessive taps by 1
            pet_status.find_anger_causes(
                [("Desktop Pet", "Too many taps")], increment_num=1
            )
            pet_status.increment_anger()
            self.active_bubbles.append(annoyed_speech)

            def not_annoyed():
                self.times_clicked = 0
                self.is_annoyed = False
                annoyed_speech.deleteLater()

            QTimer.singleShot(5000, not_annoyed)

    def pet_right_click(self, global_pos):
        menu = QMenu(self)

        # New Performance Review Action
        review_action = QAction("Performance Review", self)
        review_action.triggered.connect(self.show_performance_review)
        menu.addAction(review_action)

        menu.addSeparator()

        focus_1_minute_action = QAction("Focus for 1 minute", self)
        focus_1_minute_action.setChecked(self.is_tracking_work)
        focus_1_minute_action.triggered.connect(lambda: self.start_focus_timer(1))
        menu.addAction(focus_1_minute_action)

        focus_15_minute_action = QAction("Focus for 15 minutes", self)
        focus_15_minute_action.setChecked(self.is_tracking_work)
        focus_15_minute_action.triggered.connect(lambda: self.start_focus_timer(15))
        menu.addAction(focus_15_minute_action)

        focus_30_minute_action = QAction("Focus for 30 minutes", self)
        focus_30_minute_action.setChecked(self.is_tracking_work)
        focus_30_minute_action.triggered.connect(lambda: self.start_focus_timer(30))
        menu.addAction(focus_30_minute_action)

        focus_1_hour_action = QAction("Focus for 1 hour", self)
        focus_1_hour_action.setChecked(self.is_tracking_work)
        focus_1_hour_action.triggered.connect(lambda: self.start_focus_timer(60))
        menu.addAction(focus_1_hour_action)

        menu.addSeparator()

        workout_action = QAction("Track Workout", self, checkable=True)
        workout_action.setChecked(self.is_tracking_workout)
        workout_action.triggered.connect(lambda: self.toggle_tracking("workout"))
        menu.addAction(workout_action)

        menu.addSeparator()

        pet_action = QAction("Pet", self)
        pet_action.triggered.connect(self.show_thanks)
        menu.addAction(pet_action)

        kill_action = QAction("Kill pet >:)", self)
        kill_action.triggered.connect(qApp.quit)
        menu.addAction(kill_action)

        menu.exec_(global_pos)

    def start_focus_timer(self, minutes):
        good_job = face_tracker.start_timer(minutes)
        if good_job:
            print("yippee")
            pet_status.find_happiness_causes(["Adequately focused"])
            pet_status.increment_happiness()
        else:
            print("damn.")

    def show_performance_review(self):
        """Creates or updates the review window."""
        if not self.review_window:
            self.review_window = PerformanceReviewWindow(pet_status)
        else:
            self.review_window.update_stats()
        self.review_window.show()

    def toggle_tracking(self, mode):
        """Toggles the CV tracking states."""
        if mode == "work":
            self.is_tracking_work = not self.is_tracking_work
            print(f"Work Tracking: {self.is_tracking_work}")
        elif mode == "workout":
            self.is_tracking_workout = not self.is_tracking_workout
            print(f"Workout Tracking: {self.is_tracking_workout}")

    def show_thanks(self):
        if not self.is_punishing:
            color_options = ["orange", "purple", "blue", "pink"]
            center_x = self.x() + (self.width() / 2)
            thanks_options = [
                "Thank you for the kind gesture, master.",
                "Much appreciated.",
                "Ah, that felt amazing. :)",
                "Once more, please.",
            ]
            thanks_speech = SpeechBubble(
                text=random.choice(thanks_options),
                color=random.choice(color_options),
                x=center_x - random.randint(100, 200),
                y=self.y() - random.randint(100, 200),
                font_family="Comic Sans MS",
                font_size=20,
            )
            pet_status.find_happiness_causes(["Pet the pet"])
            pet_status.increment_happiness()  # Reduce anger count for each sign of affection
            self.active_bubbles.append(thanks_speech)
            QTimer.singleShot(3000, thanks_speech.deleteLater)


def spawn_pet():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Added because menu kept closing the pet
    pet = DesktopPet(productivity_app="Firefox Nightly")
    status_code = app.exec_()
    pet_status.save_to_file()
    sys.exit(status_code)


if __name__ == "__main__":
    spawn_pet()
