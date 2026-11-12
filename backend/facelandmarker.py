import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import FaceLandmarkerResult
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import drawing_styles

# building the landmark
BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
FaceLandmarkerResult = mp.tasks.vision.FaceLandmarkerResult
VisionRunningMode = mp.tasks.vision.RunningMode

MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_landmarker.task"


class FaceTracker:
    latest_result = None
    score = 100.0
    blink_time = None
    focus_time = None
    is_blink = False

    # Returns true if the user successfully focused for the specified time, false if they lost all their focus points
    def start_timer(self, minutes):
        # Fresh session: without this, one failed session left the score at 0
        # and every later session failed immediately.
        self.score = 100.0
        self.blink_time = None
        self.is_blink = False
        self.latest_result = None
        self.focus_time = time.time() + minutes * 60
        return self.start()

    def start(self):
        # Creates a FaceLandermarker Object
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=VisionRunningMode.LIVE_STREAM,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
            result_callback=self.result_callback,
        )
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap.release()
            return None  # No webcam, so the pet can say so instead of "you lost focus"
        try:
            return self._run(options, cap)
        finally:
            # Previously skipped on success/failure returns, leaving the webcam on
            cap.release()
            cv2.destroyAllWindows()

    def _run(self, options, cap):
        with FaceLandmarker.create_from_options(options) as landmarker:
            while cap.isOpened():
                if self.focus_time is None or time.time() >= self.focus_time:
                    return True

                if self.score <= 0:
                    return False

                self.score = max(0, self.score - 0.2)

                ok, image = cap.read()

                if not ok:
                    break
                # Convert BGR (OpenCV) → RGB (MediaPipe)
                rgb_frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                # mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # Timestamp in milliseconds
                timestamp_ms = int(time.time() * 1000)
                landmarker.detect_async(mp_image, timestamp_ms)

                if self.latest_result and self.latest_result.face_blendshapes:
                    self.plot_face_blendshapes_bar_graph(
                        self.latest_result.face_blendshapes[0]
                    )

                # Debug preview: cv2.imshow("feed", self.draw_landmarks_on_image(image, self.latest_result))
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
        return False

    def result_callback(self, result, output_image, timestamp_ms):

        self.latest_result = result

    # styles the model
    def draw_landmarks_on_image(self, image, detection_result):

        if not detection_result or not detection_result.face_landmarks:
            return image

        h, w = image.shape[:2]

        face_landmarks_list = detection_result.face_landmarks
        annotated_image = np.copy(image)

        # Loop through the detected faces to visualize.
        for idx in range(len(face_landmarks_list)):
            face_landmarks = face_landmarks_list[idx]

            # Draw the face landmarks.
            drawing_utils.draw_landmarks(
                image=annotated_image,
                landmark_list=face_landmarks,
                connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style(),
            )
            drawing_utils.draw_landmarks(
                image=annotated_image,
                landmark_list=face_landmarks,
                connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=drawing_styles.get_default_face_mesh_contours_style(),
            )
            drawing_utils.draw_landmarks(
                image=annotated_image,
                landmark_list=face_landmarks,
                connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS,
                landmark_drawing_spec=None,
                connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style(),
            )
            drawing_utils.draw_landmarks(
                image=annotated_image,
                landmark_list=face_landmarks,
                connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS,
                landmark_drawing_spec=None,
                connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style(),
            )

        return annotated_image

    def plot_face_blendshapes_bar_graph(self, face_blendshapes):

        # creates a dictionary for face blendshape
        scores = {c.category_name: c.score for c in face_blendshapes}

        look_right_score = scores.get("eyeLookInLeft", -1)
        look_left_score = scores.get("eyeLookInRight", -1)
        look_down_left_score = scores.get("eyeLookDownLeft", -1)
        look_down_right_score = scores.get("eyeLookDownRight", -1)
        look_up_left_score = scores.get("eyeLookUpLeft", -1)
        look_up_right_score = scores.get("eyeLookUpRight", -1)

        blink_left_score = scores.get("eyeBlinkLeft", -1)
        blink_right_score = scores.get("eyeBlinkRight", -1)

        # look_right > 0.5
        # look_left > 0.5
        # look_down_left & look_down_right > 0.65
        # look_up_left & look_up_right > 0.18

        looking_away = (
            look_right_score > 0.5
            or look_left_score > 0.5
            or look_up_left_score > 0.1
            or look_up_right_score > 0.1
            or self.is_blink
        )
        if not looking_away:
            self.score = min(100, self.score + 0.8)

        # Eyes closed for 2+ seconds counts as looking away
        if blink_left_score > 0.3 and blink_right_score > 0.3:
            if self.blink_time is None:  # when its the first time checking
                self.blink_time = time.time()  # saves the current time to blink_time
            elif time.time() - self.blink_time >= 2:
                self.is_blink = True
        else:
            self.blink_time = None
            self.is_blink = False

    def get_score(self):
        return self.score


face_tracker = FaceTracker()

if __name__ == "__main__":
    face_tracker.start_timer(0.5)
