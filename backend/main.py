import threading
import uvicorn
from fastapi import FastAPI
from pet_window_tracking import pet_status, spawn_pet
from facelandmarker import FaceTracker

app = FastAPI()
face_tracker = FaceTracker()


@app.get("/")
def index():
    return {
        "total_affection_points": pet_status.get_affection_points(),
        "total_happiness_count": pet_status.get_happiness_count(),
        "source_of_happiness": pet_status.happiness_causes,
        "total_anger_count": pet_status.get_anger_count(),
        "source_of_anger": pet_status.anger_causes,
    }


@app.get("/score")
def get_score():
    return {"score": face_tracker.get_score()}


def main():
    # daemon=True ensures the server closes when you close the Desktop Pet
    pet_thread = threading.Thread(target=spawn_pet, daemon=True)
    pet_thread.start()

    tracker_thread = threading.Thread(target=face_tracker.start, daemon=True)
    tracker_thread.start()

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
