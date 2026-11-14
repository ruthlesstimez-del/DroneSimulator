"""Live north-up overhead map with drone marker and flight trail."""
import math
import json
import time
from pathlib import Path

import airsim
import cv2
import numpy as np

TITLE = 'AirSim 2D Map - Esc closes map, S saves image'


def main():
    client = airsim.MultirotorClient(timeout_value=15)
    client.confirmConnection()
    trail = []
    cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITLE, 400, 400)
    background = None
    next_refresh = 0.0
    map_center = (0.0, 0.0)
    mission = None
    task_path = Path(__file__).parent / 'rl_artifacts' / 'task.json'
    task_stamp = None
    try:
        while True:
            if task_path.exists() and task_path.stat().st_mtime_ns != task_stamp:
                try:
                    mission = json.loads(task_path.read_text(encoding='utf-8'))
                    task_stamp = task_path.stat().st_mtime_ns
                    center = tuple(mission['center'][:2])
                    if center != map_center:
                        map_center = center
                        client.simSetCameraPose('Overview', airsim.Pose(
                            airsim.Vector3r(*center, -250), airsim.to_quaternion(-math.pi/2, 0, 0)), external=True)
                        background = None
                        trail.clear()
                except (OSError, ValueError, KeyError):
                    pass
            if background is None or time.monotonic() >= next_refresh:
                replies = client.simGetImages([
                    airsim.ImageRequest('Overview', airsim.ImageType.Scene, False, True)
                ], external=True)
                if not replies or not replies[0].image_data_uint8:
                    raise RuntimeError('Overview camera returned no image. Restart AirSim with settings.json.')
                background = cv2.imdecode(np.frombuffer(replies[0].image_data_uint8, np.uint8), cv2.IMREAD_COLOR)
                if background is None:
                    raise RuntimeError('Could not decode overview image')
                next_refresh = time.monotonic() + 15.0
            frame = background.copy()
            state = client.getMultirotorState()
            position = state.kinematics_estimated.position
            h, w = frame.shape[:2]
            pixel = (round(w / 2 + (position.y_val-map_center[1]) * w / 600),
                     round(h / 2 - (position.x_val-map_center[0]) * h / 600))
            if mission and mission.get('status') != 'success':
                tx, ty, _ = mission['target_world']
                target_pixel = (round(w/2 + (ty-map_center[1])*w/600),
                                round(h/2 - (tx-map_center[0])*h/600))
                cv2.drawMarker(frame, target_pixel, (40, 70, 255), cv2.MARKER_STAR, 18, 2)
                cv2.putText(frame, 'RL TARGET', (target_pixel[0]+10, target_pixel[1]-10),
                            cv2.FONT_HERSHEY_SIMPLEX, .4, (40, 70, 255), 1)
            trail.append(pixel)
            trail = trail[-3000:]
            if len(trail) > 1:
                cv2.polylines(frame, [np.array(trail, np.int32)], False, (0, 220, 255), 2)
            if 0 <= pixel[0] < w and 0 <= pixel[1] < h:
                _, _, yaw = airsim.to_eularian_angles(state.kinematics_estimated.orientation)
                tip = (round(pixel[0] + 18 * math.sin(yaw)), round(pixel[1] - 18 * math.cos(yaw)))
                cv2.circle(frame, pixel, 7, (0, 255, 255), -1)
                cv2.arrowedLine(frame, pixel, tip, (0, 0, 255), 3, tipLength=0.4)
            else:
                cv2.putText(frame, 'Drone outside this 600 m overview', (15, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            cv2.rectangle(frame, (0, 0), (w, 65), (25, 25, 25), -1)
            cv2.putText(frame, 'NORTH UP | yellow = drone / trail | 600 m across', (15, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, (255, 255, 255), 1)
            cv2.putText(frame, f'X {position.x_val:.1f} m  Y {position.y_val:.1f} m  Z {position.z_val:.1f} m',
                        (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.imshow(TITLE, frame)
            key = cv2.waitKey(200) & 0xFF
            if key == 27 or cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord('s'):
                path = Path(__file__).resolve().parent / 'map_snapshot.png'
                cv2.imwrite(str(path), frame)
                print(f'Saved {path}', flush=True)
    finally:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
