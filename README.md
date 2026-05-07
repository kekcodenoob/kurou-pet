# Kurou Pet

An interactive pet prototype built by Team 4 (SP'26).

### Made by:

- Kelvin ([@kekcodenoob](https://github.com/kekcodenoob))
- Vanessa ([@vanessa0135](https://github.com/vanessa0135))
- Sam ([@sams222](https://github.com/sams222))
- Lemuel ([@lemueldls](https://github.com/lemueldls))

## Overview

In the modern day, jobs often mandate many hours spent behind a computer screen.
With Kurou Pet, we aim to make this time more productive and meaningful while
improving your physical fitness. In Kurou Pet you're rewarded for staying
focused on work and taking breaks to exercise. You can then use those rewards to
take care of your Kurou Pet!

## Features

- Face tracking with Mediapipe Landmark
- Kurou Pet System
- Movenet Pose tracking for exercise detection
- Window & tab activity tracking

### Window Tracking

Kurou Pet keeps an eye on what you're actually doing on your machine so the pet
can react to it. The tracker enumerates open windows on a regular interval and
classifies each one — work apps, games, and known social media / video sites
(YouTube, Twitter, Reddit, TikTok, etc) are recognized by window title and
class name. Time spent on distraction windows is logged per source and per tab,
which is what populates the dashboard.

## Repository Layout

- `/backend`
  - `main.py` - The entrypoint
  - `facelandmarker.py` - Face tracking with Mediapipe
  - `movenet.py` - Body tracking push up counter with Movenet
  - `pet_window_tracking.py` - Kurou Pet backend code

- `/frontend`
  - Nothing much yet

## Running Locally

```console
cd backend
```

```console
uv run main.py
```

## Future Improvements

- **Expanded Exercise Library** — Scaling Movenet capabilities beyond push-ups
  to track squats, stretching, and mobility routines.
- **Pet Evolution Mechanics** — Introducing dynamic visual upgrades and
  lifecycles for the pet based on long-term user focus streaks.
- **Community Aspect** — Allowing stats to be shareable across users to
  encourage them to work hard like their peers.
