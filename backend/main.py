import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
# Import the pet_status instance and the spawn function
from pet_window_tracking import spawn_pet, pet_status
from facelandmarker import FaceTracker

app = FastAPI()
#face_tracker = FaceTracker()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def get_pet_data():
    """Returns raw JSON data. This now reflects loaded persistent data."""
    return {
        "total_affection_points": pet_status.get_affection_points(),
        "total_happiness_count": pet_status.get_happiness_count(),
        "source_of_happiness": pet_status.happiness_causes,
        "total_anger_count": pet_status.get_anger_count(),
        "source_of_anger": pet_status.anger_causes
    }

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse('index.html')

def run_server():
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error") # Reduced log noise
    except Exception as e:
        print(f"CRITICAL: Server failed: {e}")


def main():
    # daemon=True ensures the server closes when you close the Desktop Pet
    # server_thread = threading.Thread(target=run_server, daemon=True)
    # server_thread.start()

    print("Dashboard available at: http://127.0.0.1:8000/dashboard")


    run_server()
    
    
    # 2. Start the Pet (This will block until the window is closed)
    # pet_status.load_from_file() is called inside PetStatus.__init__ automatically
    #spawn_pet()
    
if __name__ == "__main__":
    main()
