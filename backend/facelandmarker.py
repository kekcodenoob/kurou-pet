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

# Scoring is time-based so it doesn't depend on the webcam's frame rate.
# Looking away for FULL_DRAIN_SECONDS straight fails a session (half the session
# for very short ones, so the 10-second test can fail too); looking back recovers.
FULL_DRAIN_SECONDS = 20.0
RECOVERY_PER_SECOND = 10.0
MAX_HEAD_TURN_DEGREES = 30.0  # Head turned further than this from the camera counts as away
EYES_CLOSED_SECONDS = 2.0
# Every this many seconds spent looking away (added up over the session) is
# reported through `on_distracted`
DISTRACTION_SECONDS = 1.0


class FaceTracker:
    latest_result = None
    score = 100.0
    blink_time = None
    focus_time = None
    is_blink = False

    # Returns true if the user successfully focused for the specified time, false if they lost all their focus points
    def start_timer(self, minutes, on_distracted=None):
        """`on_distracted(seconds)` is called (from this worker thread) for every
        DISTRACTION_SECONDS spent looking away."""
        # Fresh session: without this, one failed session left the score at 0
        # and every later session failed immediately.
        self.score = 100.0
        self.blink_time = None
        self.is_blink = False
        self.latest_result = None
        self.focus_time = time.time() + minutes * 60
        self.drain_per_second = 100.0 / min(FULL_DRAIN_SECONDS, minutes * 60 / 2)
        self.away_seconds = 0.0
        self.on_distracted = on_distracted
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
            output_facial_transformation_matrixes=True,  # Head direction
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
            last_frame = time.time()
            while cap.isOpened():
                now = time.time()
                if self.focus_time is None or now >= self.focus_time:
                    return True

                if self.score <= 0:
                    # Round leftover time to the nearest second, so failing right at
                    # a second mark doesn't lose that one to timing
                    if self.on_distracted and self.away_seconds >= DISTRACTION_SECONDS / 2:
                        self.on_distracted(DISTRACTION_SECONDS)
                    return False

                elapsed, last_frame = now - last_frame, now
                if self.latest_result is None:
                    pass  # Model still warming up; don't count it against the user
                elif self.is_focused():
                    self.score = min(100.0, self.score + RECOVERY_PER_SECOND * elapsed)
                else:
                    self.score = max(0.0, self.score - self.drain_per_second * elapsed)
                    self.away_seconds += elapsed
                    if self.away_seconds >= DISTRACTION_SECONDS:
                        self.away_seconds -= DISTRACTION_SECONDS
                        if self.on_distracted:
                            self.on_distracted(DISTRACTION_SECONDS)

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

    def is_focused(self):
        """True if a face is in view, facing the screen, with eyes on it and open."""
        result = self.latest_result
        if not result or not result.face_blendshapes:
            return False  # No face found: the user left or turned away
        if result.facial_transformation_matrixes and head_turn_degrees(
            result.facial_transformation_matrixes[0]
        ) > MAX_HEAD_TURN_DEGREES:
            return False
        return not self.eyes_looking_away(result.face_blendshapes[0])

    def eyes_looking_away(self, face_blendshapes):

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

        # Eyes closed for 2+ seconds counts as looking away
        if blink_left_score > 0.3 and blink_right_score > 0.3:
            if self.blink_time is None:  # when its the first time checking
                self.blink_time = time.time()  # saves the current time to blink_time
            elif time.time() - self.blink_time >= EYES_CLOSED_SECONDS:
                self.is_blink = True
        else:
            self.blink_time = None
            self.is_blink = False

        return (
            look_right_score > 0.5
            or look_left_score > 0.5
            or look_up_left_score > 0.1
            or look_up_right_score > 0.1
            or self.is_blink
        )

    def get_score(self):
        return self.score


def head_turn_degrees(transform):
    """Angle between the way the face points and the camera's axis (0 = facing it)."""
    # abs(): works whether the face model points along +z or -z
    facing = np.clip(abs(np.asarray(transform)[2, 2]), 0.0, 1.0)
    return float(np.degrees(np.arccos(facing)))


face_tracker = FaceTracker()

if __name__ == "__main__":
    face_tracker.start_timer(0.5)
