import sys
import random
import time
import pyautogui
import platform
import pywinctl as pwc
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QAction, qApp
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QColor

class AngerSource:
    name: str
    seconds: int

# Getting info from the pet to display on the FastAPI server
class PetStatus:
    def __init__(self):
        self.affection_points = 0
        self.happiness_count = 0
        self.happiness_causes = {}
        self.anger_count = 0
        self.anger_causes = {}
        # self.begin_time = time.time() TBD: Get details like how long the pet has been around or how far it has moved
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
    def get_happiness_count(self):
        return self.happiness_count
    def find_happiness_causes(self, happiness_source):
        for joy in happiness_source:
            if joy in self.happiness_causes:
                self.happiness_causes[joy] += 1
            else:
                self.happiness_causes[joy] = 1
        return self.happiness_causes
    def find_anger_causes(self, found_distractions):
        for app in found_distractions:
            snakecase_app = app.strip().lower().replace(" ", "_")
            if snakecase_app in self.anger_causes:
                self.anger_causes[snakecase_app] += 1
            else:
                self.anger_causes[snakecase_app] = 1
        return self.anger_causes
    
pet_status = PetStatus()

# Window tracking stuff
def focus_keeper(target_title):
    # Brings intended window to foreground if possible
    # Forces window pop up with simulated keystrokes across each platform
    if platform.system() == "Windows":
        pyautogui.press("alt") 
    elif platform.system() == "Darwin": # macOS
        pyautogui.hotkey('command', 'tab')
    elif platform.system() == "Linux":
        pyautogui.hotkey('alt', 'tab')

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
        "- Steam",
        "Version",
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
        "DELTARUNE"
    ]
    social_title = [
        "Facebook",
        "Twitter",
        "Instagram",
        "Reddit",
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
        is_game = any(keyword.lower() in lowered for keyword in game_title)
        is_social = any(keyword.lower() in lowered for keyword in social_title)
        if is_game or is_social:
            found_distractions.append(title)
    return found_distractions

# Desktop pet related classes
class SpeechBubble(QLabel):
    def __init__(self, text, color, x, y, font_family, font_size):
        super().__init__()
        # Speech always on top of monitor
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint)
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
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint)
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
            print(f"Active distractions: {found_distractions}")
            pet_status.find_anger_causes(found_distractions) # Track name of distractions for server reporting
            self.trigger_punishment()
            pet_status.increment_anger() # Increase anger count when distractions are open
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
            pet_status.find_anger_causes(["too_many_taps"]) # The annoyed speech seemed irrelevant, made it more impactful
            pet_status.increment_anger()
            self.active_bubbles.append(annoyed_speech)

            def not_annoyed():
                self.times_clicked = 0
                self.is_annoyed = False
                annoyed_speech.deleteLater()

            QTimer.singleShot(5000, not_annoyed)

    def pet_right_click(self, global_pos):
        menu = QMenu(self)
        pet_action = QAction("Pet", self)
        pet_action.triggered.connect(self.show_thanks)
        kill_action = QAction("Kill pet >:)", self)
        kill_action.triggered.connect(qApp.quit)
        menu.addAction(pet_action)
        menu.addAction(kill_action)
        menu.exec_(global_pos)

    def show_thanks(self):
        if not self.is_punishing:
            color_options = ["orange", "purple", "blue", "pink"]
            center_x = self.x() + (self.width() / 2)
            thanks_options = ["Thank you for the kind gesture, master.", "Much appreciated.", "Ah, that felt amazing. :)", "Once more, please."]
            thanks_speech = SpeechBubble(
                text=random.choice(thanks_options),
                color=random.choice(color_options),
                x=center_x - random.randint(100, 200),
                y=self.y() - random.randint(100, 200),
                font_family="Comic Sans MS",
                font_size=20,
            )
            pet_status.find_happiness_causes(["pet_the_pet"])
            pet_status.increment_happiness() # Reduce anger count for each sign of affection
            self.active_bubbles.append(thanks_speech)
            QTimer.singleShot(3000, thanks_speech.deleteLater)

def spawn_pet():
    app = QApplication(sys.argv)
    pet = DesktopPet(productivity_app="Firefox Nightly")
    sys.exit(app.exec_())