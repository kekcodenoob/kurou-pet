import sys
import random
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QAction, qApp
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QCursor

class SpeechBubble(QLabel):
    # Transparent window for text bubbles
    def __init__(self, text, color, x, y, font_family, font_size):
        super().__init__()
        # Make window borderless, always on top, and hidden from the taskbar
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) # True per-pixel transparency
        self.setText(text)
        self.setStyleSheet(f"color: {color}; font-family: '{font_family}'; font-size: {font_size}px; font-weight: bold;")
        self.move(int(x), int(y))
        self.show()

class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        # Pet window setup
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) # Allows transparency

        # Variables
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.times_clicked = 0
        self.is_annoyed = False
        self.total_walk_distance = 0
        self.walk_direction = 0

        # Image setup
        self.load_image()
        
        # Initial position
        screen_geom = QApplication.desktop().availableGeometry(self)
        self.move(screen_geom.width() - self.width() - 50, screen_geom.height() - self.height())
        self.show()

        # Loops (Timers replace Pygame/Tkinter mainloop blocking)
        self.gravity_timer = QTimer(self)
        self.gravity_timer.timeout.connect(self.gravity)
        self.gravity_timer.start(25)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.idle_walk)
        self.walk_timer.start(25)

        self.active_bubbles = []

    def load_image(self):
        pet_width = 235
        pet_height = 235
        pixmap = QPixmap(r"C:\Users\retal\OneDrive\Pictures\roach.webp") # Finding image source
        
        # If image found use it, else make a square
        if not pixmap.isNull(): 
            self.pixmap = pixmap.scaled(pet_width, pet_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        else:
            print("No such image was found, maybe check your path? I'll use a block instead.")
            self.pixmap = QPixmap(pet_width, pet_height)
            self.pixmap.fill(Qt.transparent)
            painter = QPainter(self.pixmap)
            colors = [QColor("orange"), QColor("purple"), QColor("blue"), QColor("pink")]
            painter.setBrush(random.choice(colors))
            painter.drawRect(0, 0, pet_width - 1, pet_height - 1)
            painter.end()

        self.setPixmap(self.pixmap)
        self.resize(self.pixmap.width(), self.pixmap.height())
        
        # Ensures mouse click-through
        self.setMask(self.pixmap.mask())

    def gravity(self):
        if not self.is_dragging:
            # Get monitor info (most importantly left, right, and bottom of monitor)
            working_screen = QApplication.desktop().availableGeometry(self) # Monitor space excluding taskbar
            whole_screen = QApplication.desktop().screenGeometry(self) # Entire monitor space
            screen_bottom = working_screen.bottom()
            pet_right = self.x() + self.width()
            pet_bottom = self.y() + self.height()
            
            # If above taskbar, fall down
            if pet_bottom < screen_bottom:
                fall_amount = 20
                new_y = min(self.y() + fall_amount, screen_bottom - self.height())
                self.move(self.x(), new_y)
            
            # Anti-stuck mechanics
            if pet_right > whole_screen.right() or self.x() < whole_screen.left() or pet_bottom > screen_bottom + 30:
                self.move(whole_screen.right() - self.width(), screen_bottom - self.height())

    def idle_walk(self):
        screen_geom = QApplication.desktop().availableGeometry(self)
        
        if not self.is_dragging and not self.is_annoyed and self.y() + self.height() >= screen_geom.bottom():
            if self.total_walk_distance <= 0: # Reroll distance + direction once done walking
                if random.randint(1, 50) > 45:
                    self.total_walk_distance = random.randint(100, 350)
                    self.walk_direction = random.choice([-1, 1])
            else:
                next_x = self.x() + self.walk_direction
                # Limit movement within screen bounds
                if screen_geom.left() <= next_x <= screen_geom.right() - self.width():
                    self.move(next_x, self.y())
                    self.total_walk_distance -= 1
                else:
                    self.walk_direction *= -1 # Turn around at screen bounds

    # Mouse events
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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False

    def pet_left_click(self):
        speech_options = ["MEOOOOW", "HELLO!!", "HI", "SUP GUYS", "WHAT'S POPPIN"]
        color_options = ["orange", "purple", "blue", "pink"]
        center_x = self.x() + (self.width() / 2)

        if not self.is_annoyed:
            self.times_clicked += 1
            
            # Spawn text bubble
            bubble = SpeechBubble(
                text=random.choice(speech_options),
                color=random.choice(color_options),
                x=center_x + random.randint(-50, 50),
                y=self.y() - random.randint(100, 160),
                font_family="Comic Sans MS",
                font_size=20
            )
            self.active_bubbles.append(bubble)
            QTimer.singleShot(2000, bubble.deleteLater) # Kills text after 2 seconds

        if self.times_clicked >= 10 and not self.is_annoyed:
            self.is_annoyed = True
            
            annoyed_speech = SpeechBubble(
                text="OK THAT'S ENOUGH NOW!!",
                color="red",
                x=center_x - 180,
                y=self.y() - 100,
                font_family="Times New Roman",
                font_size=35
            )
            self.active_bubbles.append(annoyed_speech)

            # Reset logic after 5 seconds
            def not_annoyed():
                self.times_clicked = 0
                self.is_annoyed = False
                annoyed_speech.deleteLater()
                
            QTimer.singleShot(5000, not_annoyed)

    def pet_right_click(self, global_pos):
        menu = QMenu(self)
        
        pet_action = QAction("Pet", self)
        pet_action.triggered.connect(self.show_thanks)
        
        kill_action = QAction("Kill pet :(", self)
        kill_action.triggered.connect(qApp.quit) # Closes the application
        
        menu.addAction(pet_action)
        menu.addAction(kill_action)
        
        menu.exec_(global_pos)

    def show_thanks(self):
        color_options = ["orange", "purple", "blue", "pink"]
        center_x = self.x() + (self.width() / 2)
        
        thanks_speech = SpeechBubble(
            text="Thank you for the kind gesture, master.",
            color=random.choice(color_options),
            x=center_x - 150,
            y=self.y() - random.randint(100, 160),
            font_family="Comic Sans MS",
            font_size=20
        )
        self.active_bubbles.append(thanks_speech)
        QTimer.singleShot(3000, thanks_speech.deleteLater)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    sys.exit(app.exec_())