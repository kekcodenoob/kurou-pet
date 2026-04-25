import threading 
import uvicorn
from facelandmarker import FaceTracker
from fastapi import FastAPI

app = FastAPI()
face_tracker = FaceTracker()


@app.get("/")
def index():
    return "hiii"

@app.get("/score")
def get_score():
    return {"score": face_tracker.get_score()}

def run_fastapi():
    uvicorn.run(app)

def main():
    #run_fastapi()
    thread = threading.Thread(target=run_fastapi, daemon=True)
    thread.start()

    face_tracker.start() 

if __name__ == "__main__":
    main()