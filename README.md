# Kurou Pet

> An interactive pet prototype built by Team 4 (SP'26)

## Demo

> 🎥 Demo video coming soon.

<!-- To add the video: drag the .mp4 into the README editor on GitHub and paste
the generated https://github.com/user-attachments/... link on its own line here. -->

### Made by:

- Kelvin Osei ([@kekcodenoob](https://github.com/kekcodenoob))
- Vanessa Balbuena ([@vanessa0135](https://github.com/vanessa0135))
- Sam Strugger ([@sams222](https://github.com/sams222))
- Lemuel De Los Santos ([@lemueldls](https://github.com/lemueldls))

## Overview

In the modern day, jobs often mandate many hours spent behind a computer screen.
With Kurou Pet, we aim to make this time more productive and meaningful while
improving your physical fitness. In Kurou Pet you're rewarded for staying
focused on work and taking breaks to exercise. You can then use those rewards to
take care of your Kurou Pet!

> **Platform:** Kurou Pet runs on **Windows only** (x64). The window tracking,
> focus switching, and dependency lockfile all target Windows.

## Features

- Kurou Pet System: affection points, unlockable pet models, and reactions to
  how you spend your time
- Focus Mode: timed focus sessions scored with MediaPipe Face Landmarker
  through your webcam. Looking away or closing your eyes drains the score, every
  second of it costs 1 affection, and an empty score fails the session
- Distractions: every 5 seconds on a distracting window costs 1 affection and 1
  happiness and adds 1 anger. Affection can go negative
- Focus App: pick the app the pet pulls you back to from its right-click menu
  (saved between sessions)
- Workouts: pick an exercise from the pet's menu (push-ups, squats, lunges,
  curls, presses, raises, rows, crunches and more) and the webcam counts your
  reps with MediaPipe 3D pose tracking. Each exercise has its own form rules,
  so a different movement (like a knee raise during squats) doesn't count, and
  the camera window tells you what to fix. Every rep earns affection, with more
  for good form
- Window & tab activity tracking
- Dashboard: affection earned and lost and minutes distracted, charted in
  5-minute, daily, and monthly increments (refreshes every 5 minutes), plus
  affection per source (focus sessions, workouts, petting), time per
  distraction, and workout history (reps, form, and points per exercise)

### Window Tracking

Kurou Pet keeps an eye on what you're actually doing on your machine so the pet
can react to it. Every few seconds the tracker checks the window you're
currently using: game launchers, games, and social media / streaming sites
(YouTube, Netflix, Hulu, Twitter, Reddit, TikTok, etc) are recognized by app and
window title. A browser tab only counts when you're on the site itself, so
searching for "apple tv" or reading a Wikipedia article about YouTube doesn't.
Distractions left open in the background don't count; the pet only gets angry
when you switch to one. Time spent on distraction windows is logged per source and per tab,
which is what populates the dashboard.

## Results

We ran a week-long survey of 20 friends, family members, and clubmates on how
Kurou Pet affected their day-to-day productivity. **17 of 20 said it helped them
stay on task.** We used their feedback to adjust how often and how quickly the
pet's behaviors trigger.

## Repository Layout

- `/backend`
  - `main.py` - The entrypoint
  - `facelandmarker.py` - Face tracking focus score for Focus Mode
  - `exercise_tracker.py` - Webcam rep counting and form checks with MediaPipe Pose
  - `pet_window_tracking.py` - Kurou Pet backend code
  - `desktop_windows.py` - Open windows, the active window, and distraction detection
  - `history.py` - Timestamped activity log behind the dashboard charts (saved to `pet_history.db`)

- `/frontend`
  - `src/App.jsx` - Dashboard to visualize data from the backend

## Running Locally

### Requirements

- Windows 10/11 (x64)
- [uv](https://docs.astral.sh/uv/) (installs Python and the backend dependencies)
- [Node.js](https://nodejs.org/) (to build the dashboard)
- A webcam (for Focus Mode and workout tracking)

### 1. Build the dashboard (once)

Run this the first time, and again whenever the frontend code changes:

```console
cd frontend
npm install
npm run build
```

### 2. Start Kurou Pet

Run this every time you want to use the app:

```console
cd backend
uv run main.py
```

The pet appears in the bottom-right corner of your screen. Right-click it for
the menu, then choose **Focus App** to pick the app it should send you back to.

### 3. Open the dashboard

Right-click the pet and choose **Open Dashboard**, or go to
<http://127.0.0.1:8000/dashboard/> while the pet is running.

### Working on the dashboard

For live reload while editing the frontend, run the Vite dev server alongside
the pet:

```console
cd frontend
npm run dev
```

**Open Dashboard** uses the dev server (<http://localhost:5173/>) automatically
while it's running.

### Testing shortcuts

The bottom of the pet's right-click menu has two shortcuts for testing:

- **Test: Focus for 10 seconds** runs a full Focus Mode session in 10 seconds.
- **Test: Unlock all models** unlocks every pet model without spending points.

## Future Improvements

- **Stretching & Mobility** — Extending the workout tracker to timed holds,
  stretches, and multi-exercise routines.
- **Pet Evolution Mechanics** — Introducing dynamic visual upgrades and
  lifecycles for the pet based on long-term user focus streaks.
- **Community Aspect** — Allowing stats to be shareable across users to
  encourage them to work hard like their peers.

## Credits

The workout tracker (`backend/exercise_tracker.py`) is adapted from the camera
app Kelvin Osei wrote for [Arc](https://github.com/swejasonzhang/Hackknight2026),
a Hack Knights 2026 project (`computer-vision/movements.py`): its exercise
catalog, rep state machine, form grading, and fatigue checks, ported to
MediaPipe's PoseLandmarker task and extended with 3D body-relative
measurements and per-exercise form rules. Pose and face tracking use Google's
[MediaPipe](https://ai.google.dev/edge/mediapipe) models.
