import sys
import threading
import uvicorn
from fastapi import FastAPI
from pet_window_tracking import DesktopPet, pet_status

# 1. Define your FastAPI app
api_app = FastAPI()

@api_app.get("/")
def index():
    return {"total_affection_points": pet_status.get_affection_points(),
            "total_happiness_count": pet_status.get_happiness_count(),
            "source_of_happiness": pet_status.happiness_causes,
            "total_anger_count": pet_status.get_anger_count(),
            "source_of_anger": pet_status.anger_causes
            }

# run_fastapi and the threading.Thread parts are from an LLM, not entirely sure how they work but cool that it does
# 2. Create a wrapper function to run the Uvicorn server
def run_fastapi():
    # uvicorn.run blocks the thread it is called in
    uvicorn.run(api_app, host="127.0.0.1", port=8000)

def main():
    # 3. Spin up the FastAPI server in a background thread
    # daemon=True ensures the server closes when you close the Desktop Pet
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()

if __name__ == "__main__":
    main()