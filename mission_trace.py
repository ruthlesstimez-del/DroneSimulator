"""Save measured flight positions and draw persistent planned/actual routes."""
import json
import time

import airsim
import numpy as np

from rl_environment import TargetTask


def planned_route(data, q, state):
    task = TargetTask(data['blocked'], data['station'], data['heading'])
    def point(cell):
        size = len(data['blocked'])
        return [data['center'][0] + (cell[0]-size/2)*data['cell_size'],
                data['center'][1] + (cell[1]-size/2)*data['cell_size'], data['center'][2]]
    points = [point(state)]
    seen = set()
    for _ in range(120):
        if state in seen:
            raise RuntimeError('Policy loops while previewing the route')
        seen.add(state)
        action = int(np.argmax(q[state]))
        following, _, done, info = task.step(state, action)
        if info['collision']:
            raise RuntimeError('Policy preview enters a blocked cell')
        if following[:2] != state[:2]:
            points.append(point(following))
        state = following
        if done:
            return points
    raise RuntimeError('Policy preview did not finish')


class MissionTrace:
    def __init__(self, client, data, q, state, folder):
        self.client = client
        self.path = folder / 'route.json'
        self.started = time.monotonic()
        self.published = 0.0
        self.data = {'target': data['target_name'], 'target_world': data['target_world'],
                     'planned': planned_route(data, q, state), 'actual': [],
                     'status': 'preview', 'action': 'Ready', 'source': 'measured AirSim positions'}
        client.simFlushPersistentMarkers()
        client.simPlotLineStrip([airsim.Vector3r(*p) for p in self.data['planned']],
                               [0.1, .8, 1, 1], thickness=7, is_persistent=True)
        client.simPlotPoints([airsim.Vector3r(*self.data['planned'][0])],
                            [1, .85, 0, 1], size=25, is_persistent=True)
        self.publish()

    def publish(self, final=False):
        temporary = self.path.with_suffix('.tmp')
        # A Windows reader/OneDrive can briefly deny file replacement. Telemetry
        # must never interrupt flight; the next sample retries noncritical writes.
        for attempt in range(20 if final else 1):
            try:
                temporary.write_text(json.dumps(self.data), encoding='utf-8')
                temporary.replace(self.path)
                self.published = time.monotonic()
                return True
            except PermissionError:
                if final:
                    time.sleep(.02)
        return False

    def sample(self, position, action=None, force=False):
        point = [position.x_val, position.y_val, position.z_val]
        previous = self.data['actual'][-1][:3] if self.data['actual'] else None
        if previous is None or np.linalg.norm(np.array(point)-previous) >= .05:
            self.data['actual'].append(point + [round(time.monotonic()-self.started, 3)])
            if previous is not None:
                self.client.simPlotLineStrip([airsim.Vector3r(*previous), position],
                    [.15, 1, .25, 1], thickness=5, is_persistent=True)
        if action:
            self.data['action'] = action
        if force or time.monotonic()-self.published >= .35:
            self.publish(final=force)

    def finish(self, status):
        self.sample(self.client.simGetVehiclePose().position, force=True)
        self.data['status'] = status
        self.publish(final=True)
