from movenet import main as movenet_main
import threading
import uvicorn
from fastapi import FastAPI
from pet_window_tracking import spawn_pet, pet_status
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

def run_server():
    uvicorn.run(app)

def main():
    # daemon=True ensures the server closes when you close the Desktop Pet
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    tracker_thread = threading.Thread(target=face_tracker.start, daemon=True)
    tracker_thread.start()

    spawn_pet()

    movenet_main()


if __name__ == "__main__":
    main()
