"""Zoomed 2D mission route; reads telemetry files without streaming cameras."""
import json
from pathlib import Path
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / 'rl_artifacts'
TITLE = 'RL Mission Path - cyan planned, green flown'
WIDTH, HEIGHT = 640, 720


def load_state():
    task = json.loads((ARTIFACTS / 'task.json').read_text(encoding='utf-8'))
    route_path = ARTIFACTS / 'route.json'
    if route_path.exists():
        route = json.loads(route_path.read_text(encoding='utf-8'))
        if route['target'] == task['target_name']:
            return task, route
    result = json.loads((ARTIFACTS / 'mission_result.json').read_text(encoding='utf-8'))
    if result.get('target') != task['target_name']:
        raise ValueError('Waiting for the current mission')
    cells = [result['events'][0]['state'][:2]]
    cells += [event['next_state'][:2] for event in result['events'] if event['action'] in ('north','east','south','west')]
    size = len(task['blocked'])
    points = [[task['center'][0]+(x-size/2)*task['cell_size'],
               task['center'][1]+(y-size/2)*task['cell_size'],task['center'][2]] for x,y in cells]
    return task, {'planned': points, 'actual': [], 'target_world': task['target_world'],
                  'status': task['status'], 'action': 'Previous mission: executed waypoints',
                  'source': 'waypoint history; precise telemetry was not recorded'}


def render(task, route):
    image = np.full((HEIGHT, WIDTH, 3), (24, 21, 18), np.uint8)
    size, scale = len(task['blocked']), 32
    left, top = 64, 115
    origin_x = task['center'][0] - size/2*task['cell_size']
    origin_y = task['center'][1] - size/2*task['cell_size']
    def pixel(point):
        x, y = point[:2]
        return (round(left + ((y-origin_y)/task['cell_size']+.5)*scale),
                round(top + (size-.5-(x-origin_x)/task['cell_size'])*scale))
    for x in range(size):
        for y in range(size):
            a = left+y*scale, top+(size-1-x)*scale
            color = (65, 50, 80) if task['blocked'][x][y] else (43, 38, 33)
            cv2.rectangle(image, a, (a[0]+scale-2,a[1]+scale-2), color, -1)
    planned = np.array([pixel(p) for p in route['planned']], np.int32)
    if len(planned)>1:
        cv2.polylines(image, [planned], False, (255, 195, 60), 6, cv2.LINE_AA)
    actual = np.array([pixel(p) for p in route['actual']], np.int32)
    if len(actual)>1:
        cv2.polylines(image, [actual], False, (80, 245, 90), 3, cv2.LINE_AA)
    if len(planned):
        cv2.circle(image, tuple(planned[0]), 8, (0, 220, 255), -1)
        cv2.putText(image, 'START', (planned[0][0]+10, planned[0][1]+18), 0, .42, (0,220,255), 1)
        cv2.circle(image, tuple(planned[-1]), 9, (255,195,60), 2)
    target = pixel(route['target_world'])
    cv2.drawMarker(image, target, (70, 80, 255), cv2.MARKER_STAR, 23, 2)
    cv2.putText(image, 'TARGET', (target[0]-20,target[1]-17), 0, .42, (70,80,255), 1)
    if len(actual):
        cv2.circle(image, tuple(actual[-1]), 7, (255,255,255), -1)
    cv2.putText(image, 'RL MISSION | NORTH UP', (25,32), 0, .7, (240,240,240), 1, cv2.LINE_AA)
    cv2.putText(image, 'CYAN: policy route   GREEN: recorded flight   WHITE: drone', (25,60), 0, .46, (220,220,220), 1)
    cv2.putText(image, f"{route['status'].upper()}  |  {route['action']}", (25,86), 0, .48, (100,240,170), 1)
    cv2.putText(image, '2 metres per square | Firing station is the outlined circle', (25,656), 0, .46, (210,210,210), 1)
    cv2.putText(image, 'S: save image   Esc: close this view (mission continues)', (25,682), 0, .46, (210,210,210), 1)
    if not route['actual']:
        cv2.putText(image, 'Historical waypoints only; no measured track in this older run.', (25,708), 0, .39, (170,190,240), 1)
    return image


def main():
    cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITLE, 640, 720)
    saved_key = None
    try:
        while True:
            try:
                task, route = load_state()
                frame = render(task, route)
                key_to_save = (task['target_name'], len(route['actual']), route['status'])
                if route['status'] in ('success', 'stopped') and key_to_save != saved_key:
                    cv2.imwrite(str(ARTIFACTS / 'mission_path.png'), frame)
                    saved_key = key_to_save
            except (OSError, ValueError, KeyError, IndexError):
                frame = np.zeros((HEIGHT,WIDTH,3), np.uint8)
                cv2.putText(frame,'Waiting for mission route...', (40,80),0,.7,(220,220,220),1)
            cv2.imshow(TITLE, frame)
            key = cv2.waitKey(100) & 0xFF
            if key == 27 or cv2.getWindowProperty(TITLE,cv2.WND_PROP_VISIBLE)<1:
                break
            if key == ord('s'):
                cv2.imwrite(str(ARTIFACTS / 'mission_path.png'),frame)
    finally:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
