import tensorflow as tf
import tensorflow_hub as hub
import cv2
import numpy as np

# Load the MoveNet Lightning model from TF Hub
model = hub.load("https://tfhub.dev/google/movenet/singlepose/lightning/4")
movenet = model.signatures['serving_default']

# MoveNet keypoint indices for the arms.
LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST = 5, 7, 9
RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST = 6, 8, 10

# Push-up state-machine thresholds (elbow angle, degrees).
# Hysteresis: angle must drop below DOWN_ANGLE to enter "down",
# then rise above UP_ANGLE to count a rep. The gap prevents noisy flicker.
DOWN_ANGLE = 90
UP_ANGLE = 160

# Minimum per-keypoint confidence required to trust an arm's angle.
ARM_CONF_THRESHOLD = 0.3


def compute_angle(a, b, c):
    """Angle at vertex b (in degrees) formed by points a-b-c."""
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def arm_angle(keypoints, shoulder_i, elbow_i, wrist_i):
    """Return (elbow_angle, min_confidence) for one arm, or (None, 0) if unusable."""
    s, e, w = keypoints[shoulder_i], keypoints[elbow_i], keypoints[wrist_i]
    min_conf = float(min(s[2], e[2], w[2]))
    if min_conf < ARM_CONF_THRESHOLD:
        return None, min_conf
    # Keypoints are (y, x, conf); use just (y, x) for angle math.
    return compute_angle(s[:2], e[:2], w[:2]), min_conf


def best_elbow_angle(keypoints):
    """Return the elbow angle from whichever arm has higher-confidence keypoints."""
    left, left_conf = arm_angle(keypoints, LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST)
    right, right_conf = arm_angle(keypoints, RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST)
    if left is None and right is None:
        return None
    if left is None:
        return right
    if right is None:
        return left
    return left if left_conf >= right_conf else right


def draw_keypoints(frame, keypoints, confidence_threshold=0.2):
    y, x, c = frame.shape
    shaped = np.multiply(keypoints, [y, x, 1])
    
    for kp in shaped:
        ky, kx, kp_conf = kp
        if kp_conf > confidence_threshold:
            cv2.circle(frame, (int(kx), int(ky)), 4, (0, 255, 0), -1)

def draw_connections(frame, keypoints, confidence_threshold=0.2):
    # MoveNet keypoint connections (pairs)
    EDGES = {
        (0, 1): 'm', (0, 2): 'c', (1, 3): 'm', (2, 4): 'c', (0, 5): 'm', (0, 6): 'c',
        (5, 7): 'm', (7, 9): 'm', (6, 8): 'c', (8, 10): 'c', (5, 6): 'y', (5, 11): 'm',
        (6, 12): 'c', (11, 12): 'y', (11, 13): 'm', (13, 15): 'm', (12, 14): 'c', (14, 16): 'c'
    }
    
    y, x, c = frame.shape
    shaped = np.multiply(keypoints, [y, x, 1])
    
    for edge, color in EDGES.items():
        p1, p2 = edge
        y1, x1, c1 = shaped[p1]
        y2, x2, c2 = shaped[p2]
        
        if (c1 > confidence_threshold) & (c2 > confidence_threshold):
            cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)

def main():
    cap = cv2.VideoCapture(0)
    print("MoveNet Lightning Livestreaming Started. Press 'q' to quit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Resize and pad the image to keep the aspect ratio and fit the model input size (192x192)
        img = frame.copy()
        img = tf.image.resize_with_pad(np.expand_dims(img, axis=0), 192, 192)
        input_image = tf.cast(img, dtype=tf.int32)

        # Run inference
        outputs = movenet(input_image)
        # Output is a [1, 1, 17, 3] tensor
        keypoints = outputs['output_0'].numpy()[0, 0, :, :]

        # Draw onto the original frame
        draw_connections(frame, keypoints)
        draw_keypoints(frame, keypoints)

        cv2.imshow('MoveNet Lightning', frame)

        if cv2.waitKey(10) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

