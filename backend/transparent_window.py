import tkinter as tk
import win32api
import win32con
from PIL import Image, ImageTk
import random

class DesktopPet:
    def __init__(self):
        # Making a window: root = tk.Tk(screenName=None, baseName=None, className='Tk', useTk=1)
        self.root = tk.Tk()

        self.root.title("pet test") # Naming the window: root.title(text)
        self.root.overrideredirect(True) # Removes borders from window, ensuring it can't be minimized
        self.root.state("zoomed") # Full screened since graphic was being cut off
        self.root.attributes("-topmost", True) # Ensures the window's graphic stays on the screen
        self.root.attributes("-transparentcolor", "white") # Sets a certain color to transparent

        self.canvas = tk.Canvas(self.root, bg="white", highlightthickness=0) # Background set to transparent color. Highlight is for adding graphic border to window
        self.canvas.pack(fill="both", expand=True) # Fill value makes x-axis, y-axis, or both transparent around the graphic

        self.is_dragging = False
        self.current_pos = {"x": 0, "y": 0}
        self.times_clicked = 0
        self.is_annoyed = False

        self.total_walk_distance = 0
        self.walk_direction = 0

        try:
            pet = Image.open(r"C:\Users\retal\OneDrive\Pictures\roach.webp") # Store path to image with PIL function
            pet = pet.resize((200,200)) # Resize: x, y as usual
            self.root.photo = ImageTk.PhotoImage(pet) # Store with tkinter function for later functionality :P
            self.pet_id = self.canvas.create_image(1340, 912, image=self.root.photo, anchor="sw") # Make and position image with tkinter
        except:
            print("No such image was found, maybe check your path? I'll use a block instead.")
            self.root.photo = None
            color_options = ["orange", "purple", "blue", "pink"]
            self.pet_id = self.canvas.create_rectangle(1300, 700, 1530, 912, fill=random.choice(color_options), outline=random.choice(color_options)) # If no image just make whatever

        # Binds
        self.canvas.tag_bind(self.pet_id, "<Button-1>", self.pet_left_click)
        self.canvas.tag_bind(self.pet_id, "<B1-Motion>", self.pet_drag)
        self.canvas.tag_bind(self.pet_id, "<ButtonRelease-1>", self.stop_drag)
        self.canvas.tag_bind(self.pet_id, "<Button-3>", self.pet_right_click)
        self.root.bind("<Escape>", lambda e: self.root.destroy()) # Closes window after pressing Esc

        # Loop stuff
        self.gravity()
        self.idle_walk()
        self.root.mainloop() # Allowing window's processes until closed

    def idle_walk(self):
        screen_info = self.find_screen_info()
        screen_left = screen_info[0]
        screen_right = screen_info[2]
        screen_bottom = screen_info[3]
        pet_coords = self.canvas.coords(self.pet_id)
        x_coord = pet_coords[0]
        y_coord = pet_coords[1]
        if self.is_dragging == False and self.is_annoyed == False and y_coord >= screen_bottom:
            if self.total_walk_distance <= 0: # Once done walking, reroll and get new distance + direction
                if random.randint(1, 50) > 45:
                    self.total_walk_distance = random.randint(100, 350)
                    self.walk_direction = random.choice([-1, 1])
            else:
                if screen_left <= x_coord + self.walk_direction <= screen_right - 150:
                    self.canvas.move(self.pet_id, self.walk_direction, 0)
                    self.total_walk_distance -= 1
                else: # If pet walks to horizontal ends of screen swap direction or stop
                    self.walk_direction *= -1
        self.root.after(25, self.idle_walk)

    def begin_drag(self, mouse): # Getting current mouse position
        self.is_dragging = True
        self.current_pos["x"] = mouse.x
        self.current_pos["y"] = mouse.y

    def stop_drag(self, mouse):
        self.is_dragging = False

    def pet_drag(self, mouse): # Adjusting graphic position based on change in mouse position
        change_x = mouse.x - self.current_pos["x"]
        change_y = mouse.y - self.current_pos["y"]
        self.canvas.move(self.pet_id, change_x, change_y)
        self.current_pos["x"] = mouse.x
        self.current_pos["y"] = mouse.y
        #print(f"X coord: {self.current_pos['x']}")
        #print(f"Y coord: {self.current_pos['y']}")

    def find_screen_info(self):
        monitor = win32api.MonitorFromPoint((0,0)) # Finds available monitor
        monitor_info = win32api.GetMonitorInfo(monitor) # Gets screen resolution including space excluding taskbar
        non_taskbar_space = monitor_info.get("Work") # Apparently Work is a tuple stored as (left_x, top_y, right_x, bottom_y). Convenient :P
        return non_taskbar_space

    def gravity(self): # Making pet fall to taskbar
        screen_info = self.find_screen_info()
        screen_left = screen_info[0]
        screen_right = screen_info[2]
        screen_bottom = screen_info[3]
        if self.is_dragging == False:
            pet_coords = self.canvas.coords(self.pet_id)
            x_coord = pet_coords[0]
            y_coord = pet_coords[1]
            if y_coord < screen_bottom: # If pet is above the taskbar
                fall_amount = 20
                if y_coord + fall_amount > screen_bottom:
                    self.canvas.move(self.pet_id, 0, screen_bottom - y_coord) # Sometimes didn't land on taskbar, fixed
                else:
                    self.canvas.move(self.pet_id, 0, fall_amount)
            if x_coord > screen_right - 150 or x_coord < screen_left or y_coord > screen_bottom + 30: # Added to avoid pet getting stuck/hidden
                self.canvas.coords(self.pet_id, screen_right - 200, screen_bottom)
        self.root.after(25, self.gravity)

    def pet_left_click(self, mouse):
        self.begin_drag(mouse) # Gets mouse position the moment graphic is left clicked
        speech_options = ["MEOOOOW", "HELLO!!", "HI", "SUP GUYS", "WHAT'S POPPIN"]
        color_options = ["orange", "purple", "blue", "pink"]
        if self.is_annoyed == False:
            self.times_clicked += 1
            pet_text_x, pet_text_y = self.canvas.coords(self.pet_id) # Getting coords so text spawns near pet's position
            speech = self.canvas.create_text(pet_text_x + random.randint(-100, 100), pet_text_y - random.randint(200, 300), text=random.choice(speech_options), fill=random.choice(color_options), font=("Comic Sans MS", 20, "bold"))
            self.root.after(2000, lambda: self.canvas.delete(speech)) # Text dies after 2 seconds on-screen
        if self.times_clicked >= 10 and self.is_annoyed == False:
            self.is_annoyed = True
            pet_text_x, pet_text_y = self.canvas.coords(self.pet_id)
            annoyed_speech = self.canvas.create_text(pet_text_x - random.randint(180, 250), pet_text_y - 200, text="OK THAT'S ENOUGH NOW!!", fill="red", font=("Times New Roman", 40, "bold"))
            
            def not_annoyed():
                self.times_clicked = 0
                self.is_annoyed = False
                self.canvas.delete(annoyed_speech)
            self.root.after(5000, not_annoyed)

    def pet_right_click(self, mouse):
        pet_text_x, pet_text_y = self.canvas.coords(self.pet_id)
        color_options = ["orange", "purple", "blue", "pink"]
        
        def show_thanks():
            thanks_speech = self.canvas.create_text(pet_text_x - random.randint(130, 200), pet_text_y - random.randint(200, 300), text="Thank you for the kind gesture, master.", fill=random.choice(color_options), font=("Comic Sans MS", 20, "bold"))
            self.root.after(3000, lambda: self.canvas.delete(thanks_speech))
            
        menu = tk.Menu(self.root, tearoff=0) # Tearoff removes a weird paper lookin thing above the commands
        menu.add_command(label="Pet", command=show_thanks)
        menu.add_command(label="Kill pet :(", command=self.root.destroy)
        menu.post(mouse.x_root, mouse.y_root) # Keeps menu on the pet

if __name__ == "__main__":
    DesktopPet()