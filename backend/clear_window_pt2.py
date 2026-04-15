import sys
import random
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QAction, qApp
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QCursor

class SpeechBubble(QLabel):
    """A separate tiny transparent window just for the text bubbles."""
    def __init__(self, text, color, x, y, font_family, font_size):
        super().__init__()
        # Make it borderless, always on top, and hidden from the taskbar
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) # True per-pixel transparency
        self.setText(text)
        self.setStyleSheet(f"color: {color}; font-family: '{font_family}'; font-size: {font_size}px; font-weight: bold;")
        self.move(x, y)
        self.show()

class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        # --- Window Settings ---
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) # Allows true alpha transparency

        # --- Pet Variables ---
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.times_clicked = 0
        self.is_annoyed = False
        self.total_walk_distance = 0
        self.walk_direction = 0

        # --- Image Setup ---
        self.load_image()
        
        # Initial position
        screen_geom = QApplication.desktop().availableGeometry(self)
        self.move(screen_geom.width() - 300, screen_geom.height() - 200)
        self.show()

        # --- Game Loops (Timers replace Pygame/Tkinter mainloop blocking) ---
        self.gravity_timer = QTimer(self)
        self.gravity_timer.timeout.connect(self.gravity)
        self.gravity_timer.start(25)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.idle_walk)
        self.walk_timer.start(25)

        self.active_bubbles = []

    def load_image(self):
        pixmap = QPixmap(r"C:\Users\retal\OneDrive\Pictures\cat.jpg")
        
        if not pixmap.isNull():
            # Scale to 200x200 while keeping smooth edges
            self.pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            print("No such image was found, maybe check your path? I'll use a block instead.")
            self.pixmap = QPixmap(200, 200)
            self.pixmap.fill(Qt.transparent)
            painter = QPainter(self.pixmap)
            colors = [QColor("orange"), QColor("purple"), QColor("blue"), QColor("pink")]
            painter.setBrush(random.choice(colors))
            painter.drawRect(0, 0, 199, 199)
            painter.end()

        self.setPixmap(self.pixmap)
        self.resize(self.pixmap.width(), self.pixmap.height())
        
        # This mask ensures your mouse clicks pass through the transparent pixels of the image!
        self.setMask(self.pixmap.mask())

    def gravity(self):
        if not self.is_dragging:
            screen_geom = QApplication.desktop().availableGeometry(self)
            screen_bottom = screen_geom.bottom()
            
            # If above taskbar, fall down
            if self.y() + self.height() < screen_bottom:
                fall_amount = 20
                new_y = min(self.y() + fall_amount, screen_bottom - self.height())
                self.move(self.x(), new_y)
            
            # Anti-stuck mechanics
            if self.x() > screen_geom.right() or self.x() < screen_geom.left() or self.y() > screen_bottom + 30:
                self.move(screen_geom.right() - 200, screen_bottom - self.height())

    def idle_walk(self):
        screen_geom = QApplication.desktop().availableGeometry(self)
        
        if not self.is_dragging and not self.is_annoyed and self.y() + self.height() >= screen_geom.bottom():
            if self.total_walk_distance <= 0:
                if random.randint(1, 50) > 45:
                    self.total_walk_distance = random.randint(100, 350)
                    self.walk_direction = random.choice([-1, 1])
            else:
                next_x = self.x() + self.walk_direction
                # Check screen bounds
                if screen_geom.left() <= next_x <= screen_geom.right() - self.width():
                    self.move(next_x, self.y())
                    self.total_walk_distance -= 1
                else:
                    self.walk_direction *= -1 # Turn around at edges

    # Mouse Events (Dragging & Clicking) ---
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

        if not self.is_annoyed:
            self.times_clicked += 1
            
            # Spawn text bubble
            bubble = SpeechBubble(
                text=random.choice(speech_options),
                color=random.choice(color_options),
                x=self.x() + random.randint(-100, 100),
                y=self.y() - random.randint(150, 250),
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
                x=self.x() - 150,
                y=self.y() - 200,
                font_family="Times New Roman",
                font_size=40
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
        thanks_speech = SpeechBubble(
            text="Thank you for the kind gesture, master.",
            color=random.choice(color_options),
            x=self.x() - 100,
            y=self.y() - random.randint(150, 250),
            font_family="Comic Sans MS",
            font_size=20
        )
        QTimer.singleShot(3000, thanks_speech.deleteLater)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    sys.exit(app.exec_())