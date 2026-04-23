import time

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import FaceLandmarkerResult
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import drawing_styles
import cv2
import numpy as np
import matplotlib.pyplot as plt

# Initialize Mediapipe FaceMesh and drawing utilities
# mp_face_mesh = mp.solutions.face_mesh
# mp_drawing = mp.solutions.drawing_utils
# mp_drawing_styles = mp.solutions.drawing_styles

#building the landmark 
BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
FaceLandmarkerResult = mp.tasks.vision.FaceLandmarkerResult
VisionRunningMode = mp.tasks.vision.RunningMode

#creates instance with live stream mode and sets the callback function to print the result
latest_result = None

#---------------DEFINE FUNCTIONS----------------

def result_callback(result, output_image, timestamp_ms):
    global latest_result
    latest_result = result

def draw_landmarks_on_image(image, detection_result):

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
            connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style())
        drawing_utils.draw_landmarks(
            image=annotated_image,
            landmark_list=face_landmarks,
            connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS,
            landmark_drawing_spec=None,
            connection_drawing_spec=drawing_styles.get_default_face_mesh_contours_style())
        drawing_utils.draw_landmarks(
            image=annotated_image,
            landmark_list=face_landmarks,
            connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS,
            landmark_drawing_spec=None,
            connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style())
        drawing_utils.draw_landmarks(
            image=annotated_image,
            landmark_list=face_landmarks,
            connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS,
            landmark_drawing_spec=None,
            connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style())

    return annotated_image

score = 100

def plot_face_blendshapes_bar_graph(face_blendshapes):
  #for category in face_blendshapes:
    # if category.category_name == "mouthClose" and category.score > 0.4:
    #     print(f"mouth close score: {category.score}")

    # eyeBlinkLeft
    # eyeBlinkRight
    # eyeLookDownLeft
    # eyeLookDownRight
    # eyeLookInLeft
    # eyeLookInRight
    # eyeLookOutLeft
    # eyeLookOutRight
    # eyeLookUpLeft
    # eyeLookUpRight
    # eyeSquintLeft
    # eyeSquintRight
    # eyeWideLeft
    # eyeWideRight

    for category in face_blendshapes:

       
        look_right = category.category_name == "eyeLookInLeft"
        #look_right_score = category.score if look_right else -1

        look_left = category.category_name == "eyeLookInRight"
        #look_left_score = category.score if look_left else -1

        look_down_left = category.category_name == "eyeLookDownLeft"
        #look_down_left_score = category.score if look_down_left else -1

        look_down_right = category.category_name == "eyeLookDownRight"
        #look_down_right_score = category.score if look_down_right else -1

        look_up_left = category.category_name == "eyeLookUpLeft"
        #look_up_left_score = category.score if look_up_left else -1

        look_up_right = category.category_name == "eyeLookUpRight"
        #look_up_right_score = category.score if look_up_right else -1

        scores = {c.category_name: c.score for c in face_blendshapes}

        look_right_score = scores.get("eyeLookInLeft", -1)
        look_left_score = scores.get("eyeLookInRight", -1)
        look_down_left_score = scores.get("eyeLookDownLeft", -1)
        look_down_right_score = scores.get("eyeLookDownRight", -1)
        look_up_left_score = scores.get("eyeLookUpLeft", -1)
        look_up_right_score = scores.get("eyeLookUpRight", -1)

        blink_left_score = scores.get("eyeBlinkLeft", -1)
        blink_right_score = scores.get("eyeBlinkRight", -1)


    #look_right > 0.5
    #look_left > 0.5
    #look_down_left & look_down_right > 0.65
    #look_up_left & look_up_right > 0.18
    # 
    # However both up and down depends on the position of your head + camera detection
        #Have a condition that first checks if the angle of your head is alligned with your camera -> this is forward
        #Another idea is having some sort of calculation that based on the position of your head, it increases or decreases the offset for the eyes continuously? 

        global score

        blink_time = None

        if look_right_score > 0.5 or look_left_score > 0.5 or look_up_left_score > 0.18 or look_up_right_score > 0.18 or blink_left_score > 0.25 or blink_right_score > 0.25:
            
        # if (look_down_right or look_left or look_down_left or look_down_right or look_up_left or look_up_right) and category.score > 0.65:
            # print(f"{category.category_name} score: {category.score}")
            # is_forward = Falseß
            #print(f"score: {category.score}")
            #print(f"LOOK FORWARD")

            score = max(0, score - 0.001)
        
        else:
            #print(f" ")
            score = min(100, score + 0.01)

        #print(f"score: {score:.2f}")
        
        
        # if blink_left_score > 0.2:
        #      if blink_time is None:
        #          blink_time = time.time()
        #      elif time.time() - blink_time >= 2:
        #          print(f"score {blink_left_score}")


        #if blink_left_score > 0.08:
        #if category.category_name == "eyeBlinkLeft" and category.score > 0.2:
    #     print(f"mouth close score: {category.score}")
        #print(f"score: {category.score}")

        #     score -= 1
        # else:
        #     score = min(100, score + 5)

    

    # if category.category_name == "eyeLookInLeft" and category.score > 0.001:
    #     print(f"jaw open score: {category.score}")



#   # Extract the face blendshapes category names and scores.
#   face_blendshapes_names = [face_blendshapes_category.category_name for face_blendshapes_category in face_blendshapes]
#   face_blendshapes_scores = [face_blendshapes_category.score for face_blendshapes_category in face_blendshapes]
#   # The blendshapes are ordered in decreasing score value.
#   face_blendshapes_ranks = range(len(face_blendshapes_names))

#   fig, ax = plt.subplots(figsize=(12, 12))
#   bar = ax.barh(face_blendshapes_ranks, face_blendshapes_scores, label=[str(x) for x in face_blendshapes_ranks])
#   ax.set_yticks(face_blendshapes_ranks, face_blendshapes_names)
#   ax.invert_yaxis()

#   # Label each bar with values
#   for score, patch in zip(face_blendshapes_scores, bar.patches):
#     plt.text(patch.get_x() + patch.get_width(), patch.get_y(), f"{score:.4f}", va="top")

#   ax.set_xlabel('Score')
#   ax.set_title("Face Blendshapes")
#   plt.tight_layout()
#   plt.pause(0.001)
#   #plt.show()
#---------------END OF FUNCTIONS----------------

#Creates a FaceLandermarker Object
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="face_landmarker.task"),
    running_mode=VisionRunningMode.LIVE_STREAM,
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    output_face_blendshapes=True,
    result_callback=result_callback,
)
cap = cv2.VideoCapture(0)

with FaceLandmarker.create_from_options(options) as landmarker:
    while cap.isOpened():
        ok, image = cap.read()

        if not ok:
            break
     # Convert BGR (OpenCV) → RGB (MediaPipe)
        rgb_frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        #mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)


        # Timestamp in milliseconds
        timestamp_ms = int(time.time() * 1000)
        landmarker.detect_async(mp_image, timestamp_ms)

        h, w = image.shape[:2]  # get dimensions for landmark scaling

        annotated_image = draw_landmarks_on_image(image, latest_result)
        if latest_result and latest_result.face_blendshapes:
            plot_face_blendshapes_bar_graph(latest_result.face_blendshapes[0])

        cv2.imshow("feed", annotated_image)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        #elif cv2.waitKey(1) & 0xFF == ord("b"):  # press 'b' to show blendshapes graph
             #if latest_result and latest_result.face_blendshapes:
                 #plot_face_blendshapes_bar_graph(latest_result.face_blendshapes[0])

    cap.release()
    cv2.destroyAllWindows()


#image = draw_landmarks_on_image(mp_image.numpy_view(), detection_result)
#cv2.imshow(cv2.cvtColor(mp_image, cv2.COLOR_RGB2BGR))
# Define the path to the MediaPipe face landmarker model file.
# model_path = 'face_landmarker_v2_with_blendshapes.task'

# # Create BaseOptions using the model asset path.
# base_options = python.BaseOptions(model_asset_path=model_path)

# # Create FaceLandmarkerOptions with the BaseOptions, setting output_face_blendshapes
# # and output_facial_transformation_matrixes to True.
# options = vision.FaceLandmarkerOptions(
#     base_options=base_options,
#     output_face_blendshapes=True,
#     output_facial_transformation_matrixes=True,
#     num_faces=1)



print("FaceLandmarker detector initialized successfully.")