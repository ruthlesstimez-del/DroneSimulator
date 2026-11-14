# Drone simulator

## Start

Open PowerShell in this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1
```

This starts City in third-person chase view, keyboard controls, and a compact 2D map.
It also opens a lightweight mouse crosshair, without the old first-person Arcade window.

## Controls

Click the main simulator window before flying.

| Key | Action |
| --- | --- |
| T | Take off |
| W / S | Forward / backward |
| A / D | Left / right |
| Up / Down arrows | Ascend / descend |
| Q / E | Turn left / right |
| Space | Hover |
| Left mouse / J | Fire a virtual shot at the mouse crosshair |
| Shift | Boost horizontal speed from 6 m/s to 12 m/s |
| L | Land |
| End | Land and stop keyboard controls |
| B | Third-person follow view |
| / | Third-person chase view (default) |
| I / K | Front / rear camera views |
| Backslash | Ground observer view |
| F | Optional first-person view |
| 1 | Toggle the built-in overhead inset (off by default) |

Altitude no longer uses R/F: AirSim uses R for recording and F for first-person view.
Escape is AirSim's own exit key; use L or End when landing.
Releasing movement keys or switching windows requests a hover.
Manual flight does not yet avoid obstacles.

## Graphics and movement

The main viewport is 1280 x 720 with high shadows, effects, postprocessing, textures,
motion blur, and native internal render scale. A 60 FPS target is configured;
actual FPS depends on the scene and hardware. Flight speed is independent of graphics:
6 m/s normally, 12 m/s while holding Shift, 3 m/s vertically, with smooth acceleration.
The launcher stops recording and applies `performance_setup.py` on startup.

The map captures a 400 x 400 overhead background once every 15 seconds and updates
its drone marker/trail about five times per second. Destroyed scenery can therefore
take up to 15 seconds to appear on the map. The duplicate map inset is hidden by default.

Shooting captures images only when clicking or pressing J and uses a separate worker/client.
Normal hit checks use one segmentation image; ambiguous IDs use a slower confirmation.
There is no continuous first-person capture or additional first-person window.

## Arcade destruction

Move the mouse onto an object in the main simulator window and left-click (or press J).
A transparent click-through crosshair tracks the pointer. An on-demand proxy camera
matches the active player camera for third-person, chase, front, rear, and first-person
aiming. It assumes the standard 90-degree horizontal FOV and 16:9 game viewport.
Buildings take three hits; smaller
supported props take one. Hits show short tracers and a compact simulator message.
Confirmed destruction awards points. Ground, roads, sky, and simulator infrastructure
are scenery. Whole scene actors disappear; buildings do not fracture into rubble.
Reload City to restore destroyed actors. Vehicle reset does not restore them.

`arcade_mode.py` is the previous optional camera-window prototype. It is not launched
by the project launcher. `arcade_controls.py` supplies the lightweight shooting worker.

## Maps

City and Park are separate official prebuilt AirSim environments.
Close the current simulator before switching maps:

```powershell
powershell -ExecutionPolicy Bypass -File .\launch_simulator.ps1 -Map City
powershell -ExecutionPolicy Bypass -File .\launch_simulator.ps1 -Map Park
powershell -ExecutionPolicy Bypass -File .\launch_simulator.ps1 -Map Blocks
```

The overhead camera covers a fixed 600 m square around the starting point. S in the
map window saves `map_snapshot.png`; Esc in that window closes only the map.
The same LiDAR/drone configuration applies to all maps.

## Python

The isolated `.venv` uses project-local Python 3.10.11 with AirSim 1.8.1.

```powershell
.\.venv\Scripts\python.exe .\check_connection.py
.\.venv\Scripts\python.exe .\first_flight.py
```

Do not run the automatic flight script while keyboard controls are active.
Coordinates are metres in North-East-Down: negative Z is above the origin.

To reinstall dependencies (AirSim requires this order):

```powershell
.\.venv\Scripts\python.exe -m pip install numpy==1.26.4 wheel setuptools msgpack-rpc-python==0.4.1
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -r requirements.txt
```

The Windows simulator requires Microsoft's legacy DirectX runtime.
Broader navigation, dynamic obstacle avoidance, and generalization to new maps remain to be implemented.

## Reinforcement-learning target practice

Start the simulator first, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_rl.ps1
```

The launcher temporarily closes manual controls and restores them afterward.
The script arms the simulated drone, climbs 8 m for clearance, samples a local
32 x 32 x 6 m occupancy volume, and creates a uniquely named cube game target.
The red star in the map and the green world label mark that target.

Tabular Q-learning trains on a 2 m grid derived from the sampled static geometry.
Its state is grid X/Y plus four discrete headings. Actions are four translations,
two turns, and a virtual fire action. Rewards favor reaching the firing station
and successful target practice, with penalties for blocked moves, early fire,
and time. Training randomizes starting cells and headings on this same grid.

Deployment requires at least 98% success and zero blocked-cell actions in 200
evaluation episodes. The live drone executes the learned policy's actions with
a low-level feedback controller. Before firing, it must reach the station,
turn correctly, and confirm the spawned cube at the center of its camera.
The autonomous script can only fire at its own game target. It does not select
city buildings as autonomous targets. End stops the demonstration between moves;
Ctrl+C in the mission terminal also interrupts it. The drone hovers afterward.

Artifacts in `rl_artifacts`:

- `q_table.npy`: learned policy values.
- `training.csv`: episode rewards, success, collisions, and exploration rate.
- `metrics.json`: pre-training baseline and post-training evaluation.
- `task.json`: sampled grid, target position, and task status.
- `mission_result.json`: actual simulator outcome and executed actions.
- `local_obstacles.binvox`: sampled AirSim geometry.
- `route.json`: planned route and measured flight positions, updated during the mission.
- `mission_path.png`: saved zoomed route image after completion.

The RL launcher opens **RL Mission Path** alongside the simulator and selects third-person
view. An eight-second countdown lets you watch the start. Cyan lines show the learned
route, green lines the measured flight, yellow marks the start, and a red star the target.
The same colored paths are drawn persistently inside the 3D scene. Both remain after
completion, until the next mission or a simulator reload. The route viewer reads saved
telemetry files rather than streaming another camera.

To reopen the previous path without starting a mission:

```powershell
.\.venv\Scripts\python.exe .\mission_view.py
```

Older missions without measured telemetry show their saved waypoint history with an
explicit label. That history does not reconstruct the exact flight between waypoints.

This is a local, fixed-altitude training task. Evaluation uses new random seeds
on the same grid, not unseen city layouts. It does not yet learn from raw camera
pixels or generalize to moving obstacles, different altitudes, or arbitrary maps.
The one center voxel occupied by the drone is excluded from the scene scan.

The first completed run trained for 20,000 episodes, improved from 0/200 to 200/200
successful grid evaluations, and completed a 13-action live AirSim mission ending
in confirmed game-target destruction. That sampled flight layer was otherwise clear;
this result does not demonstrate avoidance of trees or buildings in a cluttered course.

Run environment checks with `.\.venv\Scripts\python.exe -m unittest test_rl_environment -v`.

## References

## Player-versus-AI arcade duel

**Double-click `START_GAME.cmd` to start the complete game.** Opening CityEnviron.exe
alone opens the map without keyboard input or the AI controller. The launcher starts
both background controllers and the radar HUD. If defeated, press F9 in the City
window to respawn. F8 pauses/resumes pursuit.
The AI automatically waits while you are outside the game/HUD windows, so it does
not keep attacking while you read instructions in another app. Click City to resume.

```powershell
powershell -ExecutionPolicy Bypass -File .\run_duel.ps1
```

This restarts City using `settings_duel.json`, with **PlayerDrone** under keyboard
control and **Drone1** controlled by a separately trained arcade pursuit policy.
The third-person camera follows PlayerDrone. Both start in the air. You can fly
around the map using WASD, altitude arrows, Q/E, and Shift boost.
Colored labels follow each drone in the 3D view: **AI Drone** in red and
**HumanDrone** in green. These match their radar labels and persist across respawns.

- **F8** starts or pauses AI pursuit.
- **F9** resets both drones and restores three health segments.
- **F10** stops the AI game loop; player flight remains available.

AI starts automatically after a five-second countdown. The compact Duel HUD shows player
health, distance, both drones, and their recent paths. The player is green; AI is red.
The AI earns virtual arcade tags at close range with a clear visibility check.
Three tags disable the simulated player drone, which can then be respawned.
On defeat, motor output is explicitly cut to zero so gravity makes the player
drone fall. The camera follows the falling body. After stable surface contact,
the wreck is disarmed and stays down until F9. This avoids relying on an in-flight
disarm request, which SimpleFlight can reject. Crash status is shown on the HUD.
`duel_artifacts/crash_verification.json` records the tested fall distance and surface.
These are game rules, with visible tracer effects, not physical projectiles.

The new policy is tabular Q-learning on a relative 3D grid with randomly moving
game targets, using `duel_learning.py`. It is separate from stationary target training.
Positions are compared in shared map coordinates, not each drone's local spawn frame.
The prototype has limited scenery avoidance: after contact it briefly backs away
and climbs, then resumes pursuit. F9 resets the round if it gets stuck. It is not
a generally trained city-flight policy.

### AI radar / human pilot

PlayerDrone remains exclusively under human keyboard control. Drone1 now receives
player position only through the simulated radar contact interface, rather than
using the player's live coordinates directly for pursuit.

- 80 m spherical range and a 360-degree scan once per second.
- Scene visibility gates contacts; range/bearing/elevation are reported.
- 0.35 m standard deviation on measured position.
- A lost return briefly coasts on the last measurement, then expires after 1.8 s.
- With no contact, the AI stops pursuit and hovers; it reacquires automatically.
- Actual game distance and visibility still validate virtual hits independently.

The Duel HUD is an AI-centered radar scope: green shows a measured player contact,
amber a coasting contact, and searching means no current contact. Hidden player
positions are not drawn as radar detections. The animated sweep is a visual indicator;
the software sensor samples the full 360-degree volume on each update.

This is a game sensor abstraction driven by simulated scene positions, not an RF
radar physics model, hardware driver, or native AirSim radar sensor.
`duel_artifacts/radar_verification.json` records the live range-loss/reacquisition test.

`duel_artifacts/metrics.json` records abstract evaluation. `verification.json` records
the separate live stationary-player test. `state.json` provides live HUD state.
`game.log` and `error.log` contain controller diagnostics.

`run_duel.ps1 -Verify` runs a complete stationary-player test, then resets the game
and leaves the AI paused. The normal launcher does not require this test every time.

Close the two-drone simulator before returning to `run_project.ps1`. Stationary
target RL and duel controllers must not run concurrently.

Run game-rule and vehicle-binding checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest test_duel -v
```

## Source links

### Enemy-aware third-person camera

The default duel camera is outside PlayerDrone and tracks the AI's approach.
It adapts its distance for vertical separation, so an opponent above or below
does not require rotating the player drone to find it. No extra camera stream is opened.

- **Z / X**: orbit the camera left / right without turning the drone.
- **C**: cycle enemy chase, wide side view, and top view.
- **V**: toggle AI tracking; also returns to the orbit camera.
- **+ / -**: zoom in / out.
- **F**: return to the enemy-aware orbit camera.
- **B**, **/**, **I**, **K**: existing native viewpoints remain available.

The native FPV camera slot is repositioned outside the drone for this mode; F
therefore shows a third-person orbit rather than the former first-person view.
The on-screen camera status reports whether the AI is above or below you.

After F9, the player controller explicitly reacquires API control and arming for
the new round, even if it missed the brief death/reset states. The duel process
supervises the keyboard controller and restarts it if it exits unexpectedly.

- https://github.com/microsoft/AirSim/releases/tag/v1.8.1-windows
- https://microsoft.github.io/AirSim/settings/
- https://microsoft.github.io/AirSim/api_docs/html/
- https://microsoft.github.io/AirSim/seg_rgbs.txt
