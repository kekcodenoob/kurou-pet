"""Webcam rep counting and form checks for Kurou Pet workouts.

Adapted from Kelvin Osei's camera app for Arc, the Hack Knights 2026 project
(https://github.com/swejasonzhang/Hackknight2026, computer-vision/movements.py).

Kept from the original: the exercise catalog and its angle thresholds,
RoutineExercise, the angle helpers, rep counting, form quality grading, and the
fatigue/stall checks.

Changed for Kurou Pet:
- Pose detection uses MediaPipe's PoseLandmarker task, since the legacy
  mp.solutions.pose API no longer ships with current MediaPipe.
- One exercise per session, chosen from the pet's menu, instead of the
  interactive routine builder (and none of Arc's plan/upload code).
- Tracks whichever side of the body faces the camera.
- Push-ups added to the catalog.
- Every finished rep awards affection, more for good form.
"""

import math
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_styles, drawing_utils

MODEL_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_full.task"
WINDOW_TITLE = "Kurou Pet Workout"

# Affection per finished rep
GOOD_FORM = {"PERFECT", "GOOD"}
POINTS_GOOD_FORM = 5
POINTS_OTHER_FORM = 2
WORKOUT_HAPPINESS_CAUSE = "• Completed a workout rep"

MIN_VISIBILITY = 0.5  # Ignore joints MediaPipe isn't confident it can see
SIDE_SWITCH_MARGIN = 0.15  # Only switch tracked side when the other is clearly more visible

# MediaPipe pose landmark indices
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28

MIRRORED = {
    LEFT_SHOULDER: RIGHT_SHOULDER, RIGHT_SHOULDER: LEFT_SHOULDER,
    LEFT_ELBOW: RIGHT_ELBOW, RIGHT_ELBOW: LEFT_ELBOW,
    LEFT_WRIST: RIGHT_WRIST, RIGHT_WRIST: LEFT_WRIST,
    LEFT_HIP: RIGHT_HIP, RIGHT_HIP: LEFT_HIP,
    LEFT_KNEE: RIGHT_KNEE, RIGHT_KNEE: LEFT_KNEE,
    LEFT_ANKLE: RIGHT_ANKLE, RIGHT_ANKLE: LEFT_ANKLE,
}

# Exercise catalog: category -> {id: definition}. Thresholds are from the original
# camera app. "indices" is (point A, vertex, point C); the mirrored side is tried too.
# invert_logic=True means the rep finishes at the extended end of the movement.
EXERCISE_CATEGORIES = {
    "Arms": {
        "bicep_curls": {
            "name": "Bicep Curls",
            "indices": (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            "flex_threshold": 40.0,
            "extend_threshold": 150.0,
            "invert_logic": False,
            "max_allowed_extension": 175.0,
        },
        "tricep_extensions": {
            "name": "Tricep Extensions",
            "indices": (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            "flex_threshold": 60.0,
            "extend_threshold": 140.0,
            "invert_logic": True,
            "max_allowed_extension": 180.0,
        },
    },
    "Shoulders": {
        "shoulder_press": {
            "name": "Shoulder Press",
            "indices": (LEFT_HIP, LEFT_SHOULDER, LEFT_ELBOW),
            "flex_threshold": 80.0,
            "extend_threshold": 160.0,
            "invert_logic": True,
            "max_allowed_extension": 180.0,
        },
        "lateral_raises": {
            "name": "Lateral Raises",
            "indices": (LEFT_HIP, LEFT_SHOULDER, LEFT_ELBOW),
            "flex_threshold": 25.0,
            "extend_threshold": 85.0,
            "invert_logic": True,
            "max_allowed_extension": 110.0,
        },
        "front_raises": {
            "name": "Front Raises",
            "indices": (LEFT_HIP, LEFT_SHOULDER, LEFT_WRIST),
            "flex_threshold": 25.0,
            "extend_threshold": 135.0,
            "invert_logic": True,
            "max_allowed_extension": 160.0,
        },
    },
    "Chest": {
        "push_ups": {
            "name": "Push-ups",
            "indices": (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            "flex_threshold": 90.0,
            "extend_threshold": 160.0,
            "invert_logic": False,
            "max_allowed_extension": 180.0,
        },
        "chest_press": {
            "name": "Chest Press",
            "indices": (LEFT_WRIST, LEFT_ELBOW, LEFT_SHOULDER),
            "flex_threshold": 70.0,
            "extend_threshold": 155.0,
            "invert_logic": True,
            "max_allowed_extension": 175.0,
        },
        "pec_fly": {
            "name": "Pec Fly",
            "indices": (LEFT_WRIST, LEFT_SHOULDER, RIGHT_WRIST),
            "flex_threshold": 25.0,
            "extend_threshold": 75.0,
            "invert_logic": False,
            "max_allowed_extension": 105.0,
        },
    },
    "Back": {
        "lat_pulldown": {
            "name": "Lat Pulldown",
            "indices": (LEFT_HIP, LEFT_SHOULDER, LEFT_ELBOW),
            "flex_threshold": 70.0,
            "extend_threshold": 155.0,
            "invert_logic": False,
            "max_allowed_extension": 175.0,
        },
        "bent_over_rows": {
            "name": "Bent-Over Rows",
            "indices": (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
            "flex_threshold": 70.0,
            "extend_threshold": 150.0,
            "invert_logic": False,
            "max_allowed_extension": 175.0,
        },
        "deadlifts": {
            "name": "Deadlifts",
            "indices": (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE),
            "flex_threshold": 130.0,
            "extend_threshold": 165.0,
            "invert_logic": True,
            "max_allowed_extension": 180.0,
        },
    },
    "Legs": {
        "squats": {
            "name": "Squats",
            "indices": (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE),
            "flex_threshold": 90.0,
            "extend_threshold": 160.0,
            "invert_logic": False,
            "max_allowed_extension": 180.0,
        },
        "lunges": {
            "name": "Lunges",
            "indices": (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE),
            "flex_threshold": 95.0,
            "extend_threshold": 165.0,
            "invert_logic": False,
            "max_allowed_extension": 180.0,
        },
    },
    "Core": {
        "ab_twists": {
            "name": "Ab Twists",
            "twist": True,  # Measured from shoulder tilt, not a joint angle
            "indices": (LEFT_SHOULDER, RIGHT_SHOULDER, NOSE),
            "flex_threshold": 2.5,
            "extend_threshold": 8.5,
            "invert_logic": True,
            "max_allowed_extension": 40.0,
        },
        "crunches": {
            "name": "Crunches",
            "indices": (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE),
            "flex_threshold": 135.0,
            "extend_threshold": 165.0,
            "invert_logic": False,
            "max_allowed_extension": 180.0,
        },
    },
}
EXERCISES = {
    exercise_id: data
    for category in EXERCISE_CATEGORIES.values()
    for exercise_id, data in category.items()
}

# BGR colors
GREEN, YELLOW, ORANGE, RED = (0, 255, 0), (0, 255, 255), (0, 165, 255), (0, 0, 255)
WHITE, GREY = (255, 255, 255), (200, 200, 200)


class RoutineExercise:

    def __init__(
        self,
        name,
        primary_joint_indices,
        flex_threshold=50.0,
        extend_threshold=150.0,
        target_reps=5,
        target_sets=1,
        max_rest_limit=8.0,
        invert_logic=False,
        max_allowed_extension=175.0,  # Threshold for bad form / hyper-extension penalty
    ):
        """Configuration for a routine exercise.

        indices: (Point_A, Point_B_Vertex, Point_C)
        """
        self.name = name
        self.indices = primary_joint_indices
        self.flex_threshold = flex_threshold
        self.extend_threshold = extend_threshold
        self.target_reps = target_reps
        self.target_sets = target_sets
        self.max_rest_limit = max_rest_limit
        self.invert_logic = invert_logic
        self.max_allowed_extension = max_allowed_extension

        # Live State
        self.reps_completed = 0
        self.current_set = 1
        self.current_stage = "up"  # Set to 'up' so starting bent doesn't auto-trigger reps
        self.min_angle = 180.0
        self.max_angle = 0.0

        # Detailed Rep Metrics
        self.rep_logs = []
        self.rep_start_time = None
        self.last_rep_completion_time = time.time()
        self.current_rep_min = 180.0
        self.current_rep_max = 0.0

    def evaluate_rep_quality(self, min_ang, max_ang):
        """Grades a finished rep's range of motion. Returns (label, BGR color)."""
        if max_ang > self.max_allowed_extension:
            return "POOR FORM (OVER-EXTENSION)", RED

        if self.invert_logic:
            extension_shortfall = max(0.0, self.extend_threshold - max_ang)
            flexion_shortfall = max(0.0, min_ang - self.flex_threshold)
        else:
            flexion_shortfall = max(0.0, min_ang - self.flex_threshold)
            extension_shortfall = max(0.0, self.extend_threshold - max_ang)

        total_error = flexion_shortfall + extension_shortfall

        if total_error <= 10.0:
            return "PERFECT", GREEN
        elif total_error <= 25.0:
            return "GOOD", YELLOW
        elif total_error <= 45.0:
            return "INCOMPLETE ROM", ORANGE
        else:
            return "POOR FORM", RED


class ExerciseTracker:
    """Counts reps of one exercise from pose landmarks and checks their form."""

    def __init__(self, exercise_id, target_reps, grace_period_duration=3.0):
        data = EXERCISES[exercise_id]
        self.is_twist = data.get("twist", False)
        self.exercise = RoutineExercise(
            name=data["name"],
            primary_joint_indices=data["indices"],
            flex_threshold=data["flex_threshold"],
            extend_threshold=data["extend_threshold"],
            target_reps=target_reps,
            target_sets=1,
            invert_logic=data["invert_logic"],
            max_allowed_extension=data["max_allowed_extension"],
        )
        self.side_indices = (data["indices"], tuple(MIRRORED.get(i, i) for i in data["indices"]))
        self.current_side = 0
        self.warning_status = ("Get ready", GREY)
        self.last_rep_quality = None  # (label, color)
        self.grace_period_end = time.time() + grace_period_duration

    def in_grace_period(self):
        if self.grace_period_end is None:
            return False
        if time.time() < self.grace_period_end:
            return True
        # Grace period over: start the stall clock now, not at launch
        self.grace_period_end = None
        self.exercise.last_rep_completion_time = time.time()
        return False

    @staticmethod
    def calculate_angle(a, b, c):
        a, b, c = np.array(a), np.array(b), np.array(c)
        radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(
            a[1] - b[1], a[0] - b[0]
        )
        angle = np.abs(radians * 180.0 / np.pi)
        if angle > 180.0:
            angle = 360 - angle
        return float(angle)

    @staticmethod
    def calculate_torso_twist_angle(left_shoulder, right_shoulder):
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        radians = math.atan2(dy, dx)
        angle = abs(radians * 180.0 / math.pi)
        # The tilt off the level either way (0-90): in the mirrored frame the right
        # shoulder can sit left of the left one, which reads a level line as 180.
        return 180.0 - angle if angle > 90.0 else angle

    def measure(self, landmarks, w, h):
        """Returns (angle, joint pixel points) for the current frame, or None if not visible."""

        def point(i):
            return [landmarks[i].x * w, landmarks[i].y * h]

        def visibility(indices):
            return min(landmarks[i].visibility for i in indices)

        if self.is_twist:
            if visibility((LEFT_SHOULDER, RIGHT_SHOULDER)) < MIN_VISIBILITY:
                return None
            ls, rs = point(LEFT_SHOULDER), point(RIGHT_SHOULDER)
            return self.calculate_torso_twist_angle(ls, rs), (ls, rs)

        # Track the side facing the camera, switching only when the other is clearly better
        scores = [visibility(indices) for indices in self.side_indices]
        other = 1 - self.current_side
        if scores[other] > scores[self.current_side] + SIDE_SWITCH_MARGIN:
            self.current_side = other
        if scores[self.current_side] < MIN_VISIBILITY:
            return None

        p1, p2, p3 = (point(i) for i in self.side_indices[self.current_side])
        return self.calculate_angle(p1, p2, p3), (p1, p2, p3)

    def check_fatigue_and_stalls(self, current_exercise):
        now = time.time()
        time_since_last_rep = round(now - current_exercise.last_rep_completion_time, 1)

        if time_since_last_rep > current_exercise.max_rest_limit:
            self.warning_status = (f"Stalled? Resting {int(time_since_last_rep)}s", RED)
            return time_since_last_rep

        if len(current_exercise.rep_logs) >= 2:
            durations = [log["duration"] for log in current_exercise.rep_logs]
            if current_exercise.invert_logic:
                peak_angles = [log["max_angle"] for log in current_exercise.rep_logs]
            else:
                peak_angles = [log["min_angle"] for log in current_exercise.rep_logs]
            rom_std_dev = np.std(peak_angles)

            recent_duration = durations[-1]
            avg_duration = sum(durations[:-1]) / len(durations[:-1])

            if rom_std_dev > 12.0:
                self.warning_status = ("Fatigue: inconsistent range of motion", ORANGE)
                return time_since_last_rep
            elif recent_duration > avg_duration * 1.5:
                self.warning_status = ("Fatigue: reps slowing down", ORANGE)
                return time_since_last_rep

        self.warning_status = (f"Rest: {int(time_since_last_rep)}s", GREY)
        return time_since_last_rep

    def process_reps(self, current_exercise, angle):
        """Advances the rep state machine. Returns (label, color) when a rep finishes."""
        current_exercise.min_angle = min(current_exercise.min_angle, angle)
        current_exercise.max_angle = max(current_exercise.max_angle, angle)

        current_exercise.current_rep_min = min(current_exercise.current_rep_min, angle)
        current_exercise.current_rep_max = max(current_exercise.current_rep_max, angle)

        time_since_last = self.check_fatigue_and_stalls(current_exercise)

        if not current_exercise.invert_logic:
            # Standard flexion movements: start extended, finish the rep when flexed
            start_position = angle > current_exercise.extend_threshold
            finish_position = angle < current_exercise.flex_threshold
        else:
            # Inverted movements: start flexed, finish the rep when extended
            start_position = angle < current_exercise.flex_threshold
            finish_position = angle > current_exercise.extend_threshold

        if start_position and current_exercise.current_stage != "down":
            current_exercise.current_stage = "down"
            current_exercise.rep_start_time = time.time()
            current_exercise.current_rep_min = angle
            current_exercise.current_rep_max = angle

        if not (finish_position and current_exercise.current_stage == "down"):
            return None

        now = time.time()
        current_exercise.current_stage = "up"
        current_exercise.reps_completed += 1

        rep_duration = (
            round(now - current_exercise.rep_start_time, 2)
            if current_exercise.rep_start_time
            else 0.0
        )

        quality = current_exercise.evaluate_rep_quality(
            current_exercise.current_rep_min, current_exercise.current_rep_max
        )

        current_exercise.rep_logs.append(
            {
                "set": current_exercise.current_set,
                "rep": current_exercise.reps_completed,
                "min_angle": int(current_exercise.current_rep_min),
                "max_angle": int(current_exercise.current_rep_max),
                "duration": rep_duration,
                "rest_time": time_since_last,
                "quality": quality[0],
            }
        )

        current_exercise.last_rep_completion_time = now
        current_exercise.current_rep_min = 180.0
        current_exercise.current_rep_max = 0.0
        self.last_rep_quality = quality
        return quality


@dataclass
class WorkoutResult:
    exercise: str
    target_reps: int
    reps: int = 0
    good_form_reps: int = 0
    points: int = 0
    completed: bool = False
    camera_ok: bool = True

    def __bool__(self):
        # Truthy when the target was reached, like the old workout() return value
        return self.completed


def workout(status_tracker, limit=10, exercise="push_ups", camera_index=0):
    """Opens the webcam and counts reps of `exercise` until `limit` reps or Q.

    Every finished rep boosts the pet's affection through `status_tracker`.
    Returns a WorkoutResult, which is truthy if the workout was completed.
    """
    tracker = ExerciseTracker(exercise, limit)
    result = WorkoutResult(exercise=tracker.exercise.name, target_reps=limit)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        result.camera_ok = False
        return result

    options = vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    try:
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            started = time.monotonic()
            last_timestamp = -1
            window_shown = False

            while cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break

                frame = cv2.flip(frame, 1)  # Mirror, so moving right looks right
                h, w = frame.shape[:2]
                # VIDEO mode needs strictly increasing timestamps
                timestamp = max(int((time.monotonic() - started) * 1000), last_timestamp + 1)
                last_timestamp = timestamp
                image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                )
                detection = landmarker.detect_for_video(image, timestamp)
                landmarks = detection.pose_landmarks[0] if detection.pose_landmarks else None

                measured = tracker.measure(landmarks, w, h) if landmarks else None
                angle = measured[0] if measured else None

                if measured and not tracker.in_grace_period():
                    quality = tracker.process_reps(tracker.exercise, angle)
                    if quality:
                        award_rep(status_tracker, result, quality[0])

                if landmarks:
                    draw_skeleton(frame, landmarks, measured)
                draw_hud(frame, tracker, result, angle, body_visible=measured is not None)
                cv2.imshow(WINDOW_TITLE, frame)
                window_shown = True

                if result.reps >= limit:
                    result.completed = True
                    cv2.waitKey(1200)  # Let the final count show for a moment
                    break

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):  # Q or Esc
                    break
                if window_shown and cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    break  # Window closed with the X button
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return result


def award_rep(status_tracker, result, quality_label):
    good_form = quality_label in GOOD_FORM
    points = POINTS_GOOD_FORM if good_form else POINTS_OTHER_FORM
    result.reps += 1
    result.good_form_reps += good_form
    result.points += points
    status_tracker.find_happiness_causes([WORKOUT_HAPPINESS_CAUSE])
    status_tracker.increment_happiness(points, cause=f"Workout: {result.exercise}")
    status_tracker.save_to_file()


def draw_skeleton(frame, landmarks, measured):
    drawing_utils.draw_landmarks(
        image=frame,
        landmark_list=landmarks,
        connections=vision.PoseLandmarksConnections.POSE_LANDMARKS,
        landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
    )
    # Highlight the joint being measured
    if measured and len(measured[1]) == 3:
        p1, p2, p3 = (tuple(map(int, p)) for p in measured[1])
        cv2.line(frame, p1, p2, YELLOW, 5)
        cv2.line(frame, p2, p3, YELLOW, 5)
        cv2.circle(frame, p2, 9, YELLOW, -1)


def draw_text(frame, text, origin, scale=0.7, color=WHITE, thickness=2):
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_hud(frame, tracker, result, angle, body_visible):
    h, w = frame.shape[:2]
    exercise = tracker.exercise

    overlay = frame.copy()
    cv2.rectangle(overlay, (15, 15), (480, 200), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, dst=frame)

    draw_text(frame, exercise.name, (30, 50), 0.9)
    draw_text(frame, f"Reps: {result.reps}/{exercise.target_reps}", (30, 90), 0.9, GREEN)
    if tracker.last_rep_quality:
        label, color = tracker.last_rep_quality
        draw_text(frame, f"Last rep: {label}", (30, 125), 0.65, color)
    if angle is not None:
        draw_text(frame, f"Angle: {int(angle)} deg", (30, 155), 0.6, GREY, 1)
    if not tracker.in_grace_period():
        draw_text(frame, tracker.warning_status[0], (30, 185), 0.6, tracker.warning_status[1], 1)

    if tracker.in_grace_period():
        remaining = max(0.0, tracker.grace_period_end - time.time())
        draw_text(frame, f"Get ready... {remaining:.1f}", (w // 2 - 140, h // 2), 1.2, YELLOW, 3)
    elif not body_visible:
        draw_text(frame, "Step back so your whole body is in view", (w // 2 - 260, h // 2), 0.8, ORANGE)

    if result.completed or result.reps >= exercise.target_reps:
        draw_text(frame, "Workout complete!", (w // 2 - 170, h // 2 + 50), 1.2, GREEN, 3)

    draw_text(frame, "Press Q to stop", (30, h - 25), 0.6, WHITE, 1)
