"""Webcam rep counting and form checks for Kurou Pet workouts.

Adapted from Kelvin Osei's camera app for Arc, the Hack Knights 2026 project
(https://github.com/swejasonzhang/Hackknight2026, computer-vision/movements.py).

Kept from the original: the exercise catalog, the start/finish rep state
machine, range-of-motion quality grades, and the fatigue/stall checks.

Changed for Kurou Pet:
- Pose detection uses MediaPipe's PoseLandmarker task, since the legacy
  mp.solutions.pose API no longer ships with current MediaPipe.
- Reps are measured from MediaPipe's 3D world landmarks in the body's own frame
  (arm raise, forward vs. sideways, torso lean, torso twist), not one 2D angle,
  so the camera angle matters less and similar movements can be told apart.
- Each exercise has form rules (e.g. curls keep the elbow at your side, rows
  need you bent over, squats need both knees bent and both feet down). A rep
  that breaks one doesn't count, and the window says why.
- Landmarks are smoothed and positions must hold for a few frames, so jitter
  can't count a rep.
- One exercise per session, chosen from the pet's menu (none of Arc's
  plan/upload code). Push-ups added; deadlifts moved to Legs.
- Every finished rep awards affection, more for good form.
"""

import math
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_styles, drawing_utils

MODEL_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_full.task"
WINDOW_TITLE = "Kurou Pet Workout"
WINDOW_SCREEN_FRACTION = 0.8  # Camera window height, as a share of the screen

# Affection per finished rep
GOOD_FORM = {"PERFECT", "GOOD"}
POINTS_GOOD_FORM = 5
POINTS_OTHER_FORM = 2

# Tracking tuning
MIN_VISIBILITY = 0.6  # Ignore joints MediaPipe isn't confident it can see
SIDE_SWITCH_MARGIN = 0.15  # Only switch tracked side when the other is clearly more visible
SMOOTHING = 0.5  # Weight of the newest frame in the landmark moving average
CONFIRM_FRAMES = 3  # Frames the start position must hold before a rep can begin
FINISH_FRAMES = 2  # Frames the finish position must hold before the rep counts
FORM_BREAK_FRAMES = 4  # Frames a form rule must fail before the rep is thrown out
MIN_REP_SECONDS = 0.25  # Faster than this is jitter, not a rep
MAX_REST_SECONDS = 8.0  # "Stalled?" after this long without a rep
WARNING_SECONDS = 2.5  # How long a form message stays on screen
SETTLE_FRAMES = 8  # Frames held nearly still that count as settling into a position

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

ARM = (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST)
LEG = (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
TORSO = (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE)

# Features (see body_features), angles in degrees:
#   elbow       elbow bend (180 = straight)
#   elev        how far the upper arm is raised from hanging (0 down, 90 level, 180 overhead)
#   plane       direction of the raised arm (0 out to the side, 90 forward, -90 back)
#   forearm_up  forearm angle from pointing straight up
#   knee, hip   knee bend and hip bend (shoulder-hip-knee), 180 = straight
#   torso_lean  torso tilt from upright (0 standing, 90 lying flat)
#   chest_down  angle between the chest's facing and the floor (0 face down, 180 face up)
#   twist       shoulders rotated against the hips
#   *_avg, *_max, *_min_both, *_max_both   both sides combined
#   wrist_spread  distance between the wrists, in shoulder widths
#   ankle_height_diff, ankle_spread  in meters (feet level / feet apart)
#
# Exercise fields:
#   metric          feature that moves through the rep
#   start, finish   a rep starts past `start` and counts once it passes `finish`
#   too_far         (optional) going past this beyond `start` means a different movement;
#                   a rep can only start again once the user settles in the start zone
#   ideal           (start, finish) values of a full range rep, for the quality grade
#   tolerance       error allowed for PERFECT (GOOD allows 2.5x), in the metric's units
#   visible         joints that must be in view (left side; mirrored for the right)
#   bilateral       True if both sides are measured (otherwise the side facing the camera)
#   hold            rules for the whole rep: (feature, min, max, message)
#   at_start, at_finish   rules for the start/finish positions
#   start_hint      shown while waiting for the start position
EXERCISE_CATEGORIES = {
    "Arms": {
        "bicep_curls": {
            "name": "Bicep Curls",
            "metric": "elbow", "label": "Elbow",
            "start": 145, "finish": 55, "ideal": (160, 40),
            "visible": ARM,
            "hold": [("elev", None, 45, "Keep your elbow pinned to your side")],
            "at_finish": [("forearm_up", None, 70, "Curl all the way up to your shoulder")],
            "start_hint": "arm straight down at your side",
        },
        "tricep_extensions": {
            "name": "Tricep Extensions",
            "metric": "elbow", "label": "Elbow",
            "start": 75, "finish": 145, "ideal": (50, 170),
            "visible": ARM,
            "hold": [("elev", 120, None, "Keep your elbow pointing at the ceiling")],
            "start_hint": "elbow up, hand behind your head",
        },
    },
    "Shoulders": {
        "shoulder_press": {
            "name": "Shoulder Press",
            "metric": "elev", "label": "Arm raise",
            "start": 110, "finish": 145, "ideal": (85, 165),
            "too_far": 65,  # Elbows dropping below this is a pulldown, not a press
            "visible": ARM,
            "hold": [("forearm_up", None, 55, "Press straight up, forearms vertical")],
            "at_start": [("elbow", None, 115, "Start with your elbows bent")],
            "at_finish": [("elbow", 145, None, "Straighten your arms overhead")],
            "start_hint": "elbows bent at shoulder height, hands up",
        },
        "lateral_raises": {
            "name": "Lateral Raises",
            "metric": "elev", "label": "Arm raise",
            "start": 30, "finish": 75, "ideal": (15, 90),
            "visible": ARM,
            "hold": [("elbow", 130, None, "Keep your arms almost straight")],
            "at_finish": [("plane", -40, 40, "Raise your arms out to the sides, not forward")],
            "start_hint": "arms down at your sides",
        },
        "front_raises": {
            "name": "Front Raises",
            "metric": "elev", "label": "Arm raise",
            "start": 30, "finish": 75, "ideal": (15, 90),
            "visible": ARM,
            "hold": [("elbow", 130, None, "Keep your arms almost straight")],
            "at_finish": [("plane", 50, None, "Raise your arms in front of you, not to the side")],
            "start_hint": "arms down in front of you",
        },
    },
    "Chest": {
        "push_ups": {
            "name": "Push-ups",
            "metric": "elbow", "label": "Elbow",
            "start": 150, "finish": 100, "ideal": (165, 80),
            "visible": ARM + (LEFT_HIP, LEFT_KNEE),
            "hold": [
                ("torso_lean", 50, None, "Get into a plank, body parallel to the floor"),
                ("hip", 140, None, "Keep your hips in line with your body"),
            ],
            "start_hint": "plank with arms straight",
        },
        "chest_press": {
            "name": "Chest Press",
            "metric": "elbow", "label": "Elbow",
            "start": 95, "finish": 150, "ideal": (75, 170),
            "visible": ARM,
            "hold": [("chest_down", 60, None, "Stand, sit, or lie face up for chest press")],
            "at_start": [("elev", 40, 120, "Bring your elbows to chest height")],
            "at_finish": [
                ("elev", 55, 125, "Push forward, not overhead"),
                ("plane", 35, None, "Push straight out in front of you"),
            ],
            "start_hint": "elbows bent, hands at your chest",
        },
        "pec_fly": {
            "name": "Pec Fly",
            "metric": "wrist_spread", "label": "Hand spread", "unit": "x",
            "start": 2.0, "finish": 1.1, "ideal": (2.4, 0.7), "tolerance": 0.15,
            "visible": ARM, "bilateral": True,
            "hold": [
                ("elbow_min_both", 100, None, "Keep your arms wide with a slight bend"),
                ("elev_min_both", 45, None, "Keep your arms up at chest height"),
                ("elev_max_both", None, 130, "Keep your arms at chest height"),
            ],
            "start_hint": "arms open wide at chest height",
        },
    },
    "Back": {
        "lat_pulldown": {
            "name": "Lat Pulldown",
            "metric": "elev", "label": "Arm raise",
            "start": 140, "finish": 70, "ideal": (165, 45),
            "visible": ARM,
            "at_start": [("elbow", 135, None, "Start with your arms straight overhead")],
            "at_finish": [("elbow", None, 110, "Pull your elbows down and bend your arms")],
            "start_hint": "arms straight overhead",
        },
        "bent_over_rows": {
            "name": "Bent-Over Rows",
            "metric": "elbow", "label": "Elbow",
            "start": 140, "finish": 100, "ideal": (165, 75),
            "visible": ARM + (LEFT_HIP, LEFT_KNEE),
            "hold": [
                ("torso_lean", 30, None, "Hinge forward at the hips"),
                ("hip", None, 150, "Stand with your legs under you, hinged at the hips"),
            ],
            "start_hint": "bent over, arm hanging straight",
        },
    },
    "Legs": {
        "squats": {
            "name": "Squats",
            "metric": "knee_avg", "label": "Knees",
            "start": 155, "finish": 105, "ideal": (170, 85),
            "visible": LEG + (LEFT_SHOULDER,), "bilateral": True,
            "hold": [("ankle_height_diff", None, 0.15, "Keep both feet on the ground")],
            "at_finish": [
                ("knee_max", None, 120, "Bend both knees"),
                ("hip_avg", None, 130, "Sit your hips back and down"),
            ],
            "start_hint": "standing tall",
        },
        "lunges": {
            "name": "Lunges",
            "metric": "knee_avg", "label": "Knees",
            "start": 150, "finish": 115, "ideal": (170, 90),
            "visible": LEG, "bilateral": True,
            "hold": [("ankle_height_diff", None, 0.22, "Keep your front foot planted")],
            "at_finish": [
                ("knee_max", None, 130, "Bend both knees"),
                ("ankle_spread", 0.45, None, "Take a longer step"),
            ],
            "start_hint": "standing tall",
        },
        "deadlifts": {
            "name": "Deadlifts",
            "metric": "hip_avg", "label": "Hips",
            "start": 125, "finish": 160, "ideal": (100, 175),
            "visible": LEG + (LEFT_SHOULDER,), "bilateral": True,
            "hold": [("ankle_height_diff", None, 0.12, "Keep both feet planted")],
            "at_start": [
                ("torso_lean", 35, None, "Hinge forward at the hips"),
                ("knee_avg", 100, None, "Keep your legs straighter (hinge, don't squat)"),
            ],
            "start_hint": "hinged forward, back flat",
        },
    },
    "Core": {
        "ab_twists": {
            "name": "Ab Twists",
            "metric": "twist", "label": "Twist",
            "start": 20, "finish": 45, "ideal": (5, 60),
            "visible": (LEFT_SHOULDER, LEFT_HIP), "bilateral": True,
            "start_hint": "facing forward",
        },
        "crunches": {
            "name": "Crunches",
            "metric": "torso_lean", "label": "Torso",
            "start": 75, "finish": 62, "ideal": (88, 50),
            "visible": TORSO,
            "start_hint": "lying on your back",
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

WORLD_UP = np.array([0.0, -1.0, 0.0])  # MediaPipe world y points down


# Geometry
def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _vec_angle(u, v):
    cos = np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _line_angle(u, v):
    """Angle between two lines, ignoring direction (0-90)."""
    angle = _vec_angle(u, v)
    return min(angle, 180.0 - angle)


def _joint_angle(a, b, c):
    """Angle at b between a and c."""
    return _vec_angle(a - b, c - b)


def _flat(v, normal):
    """v with its component along `normal` removed."""
    return v - np.dot(v, normal) * normal


def side_index(i, side):
    return i if side == 0 else MIRRORED.get(i, i)


def body_features(w, side):
    """Measurements for one frame of 3D world landmarks `w` (33x3, meters).

    Side-specific features use `side` (0 = left landmarks, 1 = right); the rest
    combine both sides. No feature depends on which way the axes point, so
    mirroring the image doesn't change them.
    """
    ls, rs, lh, rh = w[LEFT_SHOULDER], w[RIGHT_SHOULDER], w[LEFT_HIP], w[RIGHT_HIP]
    mid_shoulder, mid_hip = (ls + rs) / 2, (lh + rh) / 2

    # The body's own axes: up the spine, across the shoulders, and out the chest
    up = _unit(mid_shoulder - mid_hip)
    lateral = _unit(_flat(rs - ls, up))
    forward = np.cross(up, lateral)
    if np.dot(w[NOSE] - mid_shoulder, forward) < 0:
        forward = -forward  # Point it the way the face points

    def arm(s):
        sh, el, wr = (w[side_index(i, s)] for i in ARM)
        upper = el - sh
        return {
            "elbow": _joint_angle(sh, el, wr),
            "elev": _vec_angle(upper, -up),
            "plane": math.degrees(math.atan2(np.dot(upper, forward), abs(np.dot(upper, lateral)))),
            "forearm_up": _vec_angle(wr - el, up),
        }

    def leg(s):
        sh, hip, knee, ankle = (w[side_index(i, s)] for i in (LEFT_SHOULDER,) + LEG)
        return {"knee": _joint_angle(hip, knee, ankle), "hip": _joint_angle(sh, hip, knee)}

    arms = [arm(0), arm(1)]
    legs = [leg(0), leg(1)]
    ankle_gap = w[LEFT_ANKLE] - w[RIGHT_ANKLE]

    return {
        **arms[side],
        **legs[side],
        "elbow_min_both": min(a["elbow"] for a in arms),
        "elev_min_both": min(a["elev"] for a in arms),
        "elev_max_both": max(a["elev"] for a in arms),
        "knee_avg": (legs[0]["knee"] + legs[1]["knee"]) / 2,
        "knee_max": max(lg["knee"] for lg in legs),
        "hip_avg": (legs[0]["hip"] + legs[1]["hip"]) / 2,
        "torso_lean": _line_angle(up, WORLD_UP),
        "chest_down": _vec_angle(forward, -WORLD_UP),
        "twist": _line_angle(_flat(rs - ls, up), _flat(rh - lh, up)),
        "wrist_spread": float(np.linalg.norm(w[LEFT_WRIST] - w[RIGHT_WRIST]))
        / (float(np.linalg.norm(rs - ls)) + 1e-9),
        "ankle_height_diff": abs(float(ankle_gap[1])),
        "ankle_spread": math.hypot(ankle_gap[0], ankle_gap[2]),
    }


def _failing_rule(rules, features):
    """Message of the first rule `features` break, or None."""
    for feature, low, high, message in rules:
        value = features[feature]
        if (low is not None and value < low) or (high is not None and value > high):
            return message
    return None


class ExerciseTracker:
    """Counts reps of one exercise from pose landmarks and checks their form."""

    def __init__(self, exercise_id, target_reps, grace_period_duration=3.0, clock=time.monotonic):
        spec = EXERCISES[exercise_id]
        self.spec = spec
        self.name = spec["name"]
        self.target_reps = target_reps
        self.metric = spec["metric"]
        self.start, self.finish = spec["start"], spec["finish"]
        self.rising = self.finish > self.start  # Does the metric go up during the rep?
        self.tolerance = spec.get("tolerance", 10.0)
        self.bilateral = spec.get("bilateral", False)
        self.too_far = spec.get("too_far")
        self.blocked = False  # Went past `too_far`; waiting to settle in the start zone
        self.recent = deque(maxlen=SETTLE_FRAMES)
        self.needs_legs = any(i in spec["visible"] for i in (LEFT_KNEE, LEFT_ANKLE))
        self.clock = clock

        self.current_side = 0
        self.smoothed = None

        # Rep state: "wait_start" until the start position is held, then "in_rep"
        self.stage = "wait_start"
        self.start_frames = self.finish_frames = self.break_frames = 0
        self.best_start = self.best_finish = None
        self.left_start_at = None

        self.reps = 0
        self.rep_logs = []
        self.last_rep_quality = None  # (label, color)
        self.last_rep_time = clock()
        self.warning = None
        self.warning_until = 0.0
        self.grace_period_end = clock() + grace_period_duration

    def in_grace_period(self):
        if self.grace_period_end is None:
            return False
        if self.clock() < self.grace_period_end:
            return True
        # Grace period over: start the stall clock now, not at launch
        self.grace_period_end = None
        self.last_rep_time = self.clock()
        return False

    # Measuring
    def required_joints(self, side):
        joints = [side_index(i, side) for i in self.spec["visible"]]
        if self.bilateral:
            joints += [side_index(i, 1 - side) for i in self.spec["visible"]]
        return joints

    def measure(self, landmarks, world_landmarks, w, h):
        """Returns (features, joint pixel points) for this frame, or None if not in view."""

        def visibility(side):
            return min(landmarks[i].visibility for i in self.required_joints(side))

        if not self.bilateral:
            # Track the side facing the camera, switching only when the other is clearly better
            other = 1 - self.current_side
            if visibility(other) > visibility(self.current_side) + SIDE_SWITCH_MARGIN:
                self.current_side = other
        if visibility(self.current_side) < MIN_VISIBILITY:
            self.smoothed = None
            return None

        world = np.array([[p.x, p.y, p.z] for p in world_landmarks])
        features = self.features_from_world(world)

        sides = (0, 1) if self.bilateral else (self.current_side,)
        triple = self.spec["visible"][:3]
        points = [
            [(landmarks[side_index(i, s)].x * w, landmarks[side_index(i, s)].y * h) for i in triple]
            for s in sides
        ] if len(triple) == 3 else []
        return features, points

    def features_from_world(self, world):
        if self.smoothed is None:
            self.smoothed = world
        else:
            self.smoothed = SMOOTHING * world + (1 - SMOOTHING) * self.smoothed
        return body_features(self.smoothed, self.current_side)

    # Rep counting
    def _past_start(self, value):
        return value <= self.start if self.rising else value >= self.start

    def _past_finish(self, value):
        return value >= self.finish if self.rising else value <= self.finish

    def _beyond_too_far(self, value):
        return value < self.too_far if self.rising else value > self.too_far

    def _settled(self):
        """True if the metric has barely moved over the last few frames."""
        return (
            len(self.recent) == self.recent.maxlen
            and max(self.recent) - min(self.recent) < self.tolerance * 0.6
        )

    def _toward_start(self, a, b):
        return min(a, b) if self.rising else max(a, b)

    def _toward_finish(self, a, b):
        return max(a, b) if self.rising else min(a, b)

    def warn(self, message):
        self.warning = message
        self.warning_until = self.clock() + WARNING_SECONDS

    def reset_rep(self):
        self.stage = "wait_start"
        self.start_frames = self.finish_frames = self.break_frames = 0
        self.best_start = self.best_finish = None
        self.left_start_at = None

    def process(self, features):
        """Advances the rep state machine. Returns (label, color) when a rep counts."""
        value = features[self.metric]
        now = self.clock()
        self.recent.append(value)

        if self.too_far is not None:
            if self._beyond_too_far(value):
                if self.stage == "in_rep":
                    self.reset_rep()
                self.blocked = True
                return None
            if self.blocked:
                # Passing through the start zone doesn't count; leaving it toward
                # the finish or settling in it does
                if not self._past_start(value) or self._settled():
                    self.blocked = False
                else:
                    return None

        if self.stage == "wait_start":
            if not self._past_start(value):
                self.start_frames = 0
                return None
            problem = _failing_rule(self.spec.get("at_start", []), features)
            if problem:
                self.start_frames = 0
                self.warn(problem)
                return None
            self.start_frames += 1
            if self.start_frames >= CONFIRM_FRAMES:
                self.stage = "in_rep"
                self.best_start = value
            return None

        # In a rep: the form rules must hold the whole way through
        problem = _failing_rule(self.spec.get("hold", []), features)
        if problem:
            self.break_frames += 1
            if self.break_frames >= FORM_BREAK_FRAMES:
                self.warn(problem)
                self.reset_rep()  # Must return to the start position to try again
            return None
        self.break_frames = 0

        if self._past_start(value):
            # Still at (or back at) the start position
            self.best_start = self._toward_start(self.best_start, value)
            self.left_start_at = None
            self.best_finish = None
            self.finish_frames = 0
            return None

        if self.left_start_at is None:
            self.left_start_at = now
        self.best_finish = value if self.best_finish is None else self._toward_finish(self.best_finish, value)

        if not self._past_finish(value):
            self.finish_frames = 0
            return None

        problem = _failing_rule(self.spec.get("at_finish", []), features)
        if problem:
            self.finish_frames = 0
            self.break_frames += 1
            if self.break_frames >= FORM_BREAK_FRAMES:
                self.warn(problem)  # Wrong movement, e.g. a front raise during lateral raises
                self.reset_rep()
            return None

        self.finish_frames += 1
        duration = now - self.left_start_at
        if self.finish_frames < FINISH_FRAMES or duration < MIN_REP_SECONDS:
            return None
        return self.count_rep(now, duration)

    def count_rep(self, now, duration):
        quality = self.evaluate_rep_quality(self.best_start, self.best_finish)
        self.reps += 1
        self.rep_logs.append(
            {
                "rep": self.reps,
                "start_value": round(float(self.best_start), 2),
                "finish_value": round(float(self.best_finish), 2),
                "duration": round(duration, 2),
                "rest_time": round(now - self.last_rep_time, 1),
                "quality": quality[0],
            }
        )
        self.last_rep_time = now
        self.last_rep_quality = quality
        self.reset_rep()
        return quality

    def evaluate_rep_quality(self, start_value, finish_value):
        """Grades a finished rep's range of motion. Returns (label, BGR color)."""
        ideal_start, ideal_finish = self.spec["ideal"]
        direction = 1 if self.rising else -1
        start_shortfall = max(0.0, (start_value - ideal_start) * direction)
        finish_shortfall = max(0.0, (ideal_finish - finish_value) * direction)
        error = start_shortfall + finish_shortfall

        if error <= self.tolerance:
            return "PERFECT", GREEN
        if error <= self.tolerance * 2.5:
            return "GOOD", YELLOW
        return "INCOMPLETE ROM", ORANGE

    def status(self):
        """(text, color) for the HUD's status line."""
        now = self.clock()
        if self.warning and now < self.warning_until:
            return self.warning, ORANGE

        resting = now - self.last_rep_time
        if resting > MAX_REST_SECONDS:
            return f"Stalled? Resting {int(resting)}s", RED

        if len(self.rep_logs) >= 3:
            finishes = [log["finish_value"] for log in self.rep_logs]
            durations = [log["duration"] for log in self.rep_logs]
            if np.std(finishes) > self.tolerance * 2:
                return "Fatigue: inconsistent range of motion", ORANGE
            if durations[-1] > 1.5 * (sum(durations[:-1]) / len(durations[:-1])):
                return "Fatigue: reps slowing down", ORANGE

        if self.stage == "wait_start":
            return f"Start: {self.spec['start_hint']}", GREY
        return f"Rest: {int(resting)}s", GREY


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
    result = WorkoutResult(exercise=tracker.name, target_reps=limit)

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
                world = detection.pose_world_landmarks[0] if detection.pose_world_landmarks else None

                measured = tracker.measure(landmarks, world, w, h) if landmarks and world else None
                if not measured:
                    tracker.smoothed = None  # Don't blend across a gap in tracking
                value = measured[0][tracker.metric] if measured else None

                if measured and not tracker.in_grace_period():
                    quality = tracker.process(measured[0])
                    if quality:
                        award_rep(status_tracker, result, quality[0])

                if landmarks:
                    draw_skeleton(frame, landmarks, measured[1] if measured else None)
                draw_hud(frame, tracker, result, value, body_visible=measured is not None)
                if not window_shown:
                    open_large_window(w, h)
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


def open_large_window(frame_w, frame_h):
    """Opens the camera window scaled up to most of the screen height, centered."""
    import ctypes  # Windows-only, like the rest of the app

    user32 = ctypes.windll.user32
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    scale = min(WINDOW_SCREEN_FRACTION * screen_h / frame_h, 0.9 * screen_w / frame_w)
    win_w, win_h = int(frame_w * scale), int(frame_h * scale)
    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(WINDOW_TITLE, win_w, win_h)
    cv2.moveWindow(WINDOW_TITLE, (screen_w - win_w) // 2, max(0, (screen_h - win_h) // 2 - 30))


def award_rep(status_tracker, result, quality_label):
    good_form = quality_label in GOOD_FORM
    points = POINTS_GOOD_FORM if good_form else POINTS_OTHER_FORM
    result.reps += 1
    result.good_form_reps += good_form
    result.points += points
    status_tracker.increment_happiness(points, source="Workouts", detail=result.exercise)
    status_tracker.save_to_file()


def draw_skeleton(frame, landmarks, highlight):
    drawing_utils.draw_landmarks(
        image=frame,
        landmark_list=landmarks,
        connections=vision.PoseLandmarksConnections.POSE_LANDMARKS,
        landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
    )
    # Highlight the joints being measured
    for joints in highlight or []:
        p1, p2, p3 = (tuple(map(int, p)) for p in joints)
        cv2.line(frame, p1, p2, YELLOW, 5)
        cv2.line(frame, p2, p3, YELLOW, 5)
        cv2.circle(frame, p2, 9, YELLOW, -1)


def draw_text(frame, text, origin, scale=0.7, color=WHITE, thickness=2):
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def format_metric(tracker, value):
    unit = tracker.spec.get("unit", "deg")
    shown = f"{value:.1f}{unit}" if unit == "x" else f"{int(value)} {unit}"
    return f"{tracker.spec['label']}: {shown}"


def draw_hud(frame, tracker, result, value, body_visible):
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (15, 15), (min(w - 15, 560), 200), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, dst=frame)

    draw_text(frame, tracker.name, (30, 50), 0.9)
    draw_text(frame, f"Reps: {result.reps}/{tracker.target_reps}", (30, 90), 0.9, GREEN)
    if tracker.last_rep_quality:
        label, color = tracker.last_rep_quality
        draw_text(frame, f"Last rep: {label}", (30, 125), 0.65, color)
    if value is not None:
        draw_text(frame, format_metric(tracker, value), (30, 155), 0.6, GREY, 1)
    if not tracker.in_grace_period():
        text, color = tracker.status()
        draw_text(frame, text, (30, 185), 0.55, color, 1)

    if tracker.in_grace_period():
        remaining = max(0.0, tracker.grace_period_end - tracker.clock())
        draw_text(frame, f"Get ready... {remaining:.1f}", (w // 2 - 140, h // 2), 1.2, YELLOW, 3)
    elif not body_visible:
        if tracker.needs_legs:
            message, offset = "Step back so your whole body is in view", 260
        else:
            message, offset = "Step back so your arms and shoulders are in view", 310
        draw_text(frame, message, (w // 2 - offset, h // 2), 0.8, ORANGE)

    if result.completed or result.reps >= tracker.target_reps:
        draw_text(frame, "Workout complete!", (w // 2 - 170, h // 2 + 50), 1.2, GREEN, 3)

    draw_text(frame, "Press Q to stop", (30, h - 25), 0.6, WHITE, 1)
