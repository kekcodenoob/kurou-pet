import sys

# Window titles can contain emoji; don't let a print crash the pet on a cp1252 console
sys.stdout.reconfigure(errors="replace")

import uvicorn
import threading
from typing import Literal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import the pet_status instance and the spawn function
from pet_window_tracking import DASHBOARD_DIST, spawn_pet, pet_status, history

app = FastAPI()

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
        "source_of_anger": pet_status.anger_causes,
    }


@app.get("/history")
def get_history(interval: Literal["5min", "day", "month"] = "5min"):
    """Affection earned/lost and minutes distracted per 5 minutes, day, or month."""
    return history.series(interval)


# Serve the built React dashboard (frontend/dist, from `npm run build`) at /dashboard/
if DASHBOARD_DIST.is_dir():
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")


def run_server():
    try:
        uvicorn.run(
            app, host="127.0.0.1", port=8000, log_level="error"
        )  # Reduced log noise
    except Exception as e:
        print(f"CRITICAL: Server failed: {e}")


def main():
    # daemon=True ensures the server closes when you close the Desktop Pet
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    if DASHBOARD_DIST.is_dir():
        print("Dashboard available at: http://127.0.0.1:8000/dashboard/")
    else:
        print("Dashboard not built yet. Run `npm install` and `npm run build` in frontend/.")

    # 2. Start the Pet (This will block until the window is closed)
    # pet_status.load_from_file() is called inside PetStatus.__init__ automatically
    spawn_pet()


if __name__ == "__main__":
    main()
