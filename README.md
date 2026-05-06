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

A lot of stuff
