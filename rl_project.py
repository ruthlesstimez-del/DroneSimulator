"""Map a local AirSim area, train a Q policy, and run a game-target demonstration."""
import argparse
import csv
import ctypes
import json
import math
from pathlib import Path
import time
import uuid

import airsim
import numpy as np

from arcade_mode import Arcade
from rl_environment import ACTIONS, GAMMA, MOVES, TargetTask, evaluate, reachable
from mission_trace import MissionTrace
from mission_windows import arrange

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / 'rl_artifacts'
LOCK = ARTIFACTS / 'mission.lock'
CELL = 2.0
SIZE = 16


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    for attempt in range(25):
        try:
            temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 24:
                raise
            time.sleep(.02)


def read_voxels(path):
    with path.open('rb') as stream:
        if not stream.readline().startswith(b'#binvox'):
            raise ValueError('Invalid voxel file')
        dims = None
        while True:
            line = stream.readline()
            if not line:
                raise ValueError('Voxel header has no data section')
            if line.startswith(b'dim '):
                dims = tuple(map(int, line.split()[1:]))
            if line.strip() == b'data':
                break
        runs = np.frombuffer(stream.read(), dtype=np.uint8)
    if dims is None or len(runs) % 2:
        raise ValueError('Invalid voxel dimensions or run-length data')
    data = np.repeat(runs[::2], runs[1::2].astype(np.int64))
    # BINVOX headers use X/Z/Y axes for AirSim's world X/Y/Z volume.
    nx, nz, ny = dims
    if len(data) != nx * ny * nz:
        raise ValueError('Unexpected voxel count')
    # AirSim writes index x + nx * (z + nz*y), not the usual binvox ordering.
    return data.reshape(ny, nz, nx).transpose(2, 0, 1).astype(bool)


def world(task, cell):
    center = task['center']
    return (center[0] + (cell[0] - SIZE / 2) * CELL,
            center[1] + (cell[1] - SIZE / 2) * CELL, center[2])


def prepare(client):
    client.enableApiControl(True)
    state = client.getMultirotorState()
    if not client.armDisarm(True):
        raise RuntimeError('Could not arm the simulated drone')
    if state.landed_state == airsim.LandedState.Landed:
        client.takeoffAsync(timeout_sec=20).join()
    # Start above nearby ground/roof surfaces, even when SimpleFlight still
    # reports Flying while resting on a roof.
    z = client.getMultirotorState().kinematics_estimated.position.z_val - 8
    client.moveToZAsync(z, 2, timeout_sec=15).join()
    if abs(client.getMultirotorState().kinematics_estimated.position.z_val-z) > 1:
        raise RuntimeError('Could not reach the initial sampling altitude')
    client.hoverAsync().join()
    time.sleep(0.5)
    pose = client.simGetVehiclePose()
    p = pose.position
    voxel_path = ARTIFACTS / 'local_obstacles.binvox'
    print('Sampling a 32 x 32 x 6 m local volume...', flush=True)
    if not client.simCreateVoxelGrid(p, 32, 32, 6, CELL, str(voxel_path)):
        raise RuntimeError('AirSim could not build the local obstacle grid')
    volume = read_voxels(voxel_path)
    if volume.shape != (SIZE, SIZE, 3):
        raise RuntimeError(f'Unexpected grid shape: {volume.shape}')
    # The overlap query includes the vehicle occupying the sampling center.
    # Exclude only its center voxel, not surrounding obstacle cells.
    volume[SIZE//2, SIZE//2, 1] = False
    blocked = volume.any(axis=2)
    # Add one cell of clearance around sampled static obstacles.
    padded = blocked.copy()
    for x, y in np.argwhere(blocked):
        padded[max(0, x-1):min(SIZE, x+2), max(0, y-1):min(SIZE, y+2)] = True
    start = (SIZE // 2, SIZE // 2)
    if padded[start]:
        raise RuntimeError('The current drone position has insufficient clearance. Move to open space and retry.')
    distances = reachable(padded, start)
    choices = []
    for station, distance in distances.items():
        if not 6 <= distance <= 12:
            continue
        for heading, (dx, dy) in enumerate(MOVES):
            middle = station[0] + dx, station[1] + dy
            target = station[0] + 2*dx, station[1] + 2*dy
            if (1 <= target[0] < SIZE-1 and 1 <= target[1] < SIZE-1
                    and not padded[middle] and not padded[target] and target != start):
                choices.append((distance, station, heading, target))
    if not choices:
        raise RuntimeError('No reachable target position in this local area. Move to a more open area and retry.')
    _, station, heading, target = sorted(choices, reverse=True)[0]
    padded[target] = True
    if station not in reachable(padded, start):
        raise RuntimeError('Target placement blocked the route')
    task = {'center': [p.x_val, p.y_val, p.z_val], 'cell_size': CELL,
            'blocked': padded.astype(int).tolist(), 'start': start, 'station': station,
            'heading': heading, 'target_cell': target, 'status': 'training',
            'description': 'Local static-grid target practice, not a general navigation model.'}
    task['target_world'] = world(task, target)
    old = client.simListSceneObjects('RL_Crate_Target.*')
    for name in old:
        client.simDestroyObject(name)
    target_pose = airsim.Pose(airsim.Vector3r(*task['target_world']), airsim.to_quaternion(0, 0, 0))
    # Unreal can retain a destroyed actor name until garbage collection.
    # Never reuse one across retries in the same loaded level.
    target_name = 'RL_Crate_Target_' + uuid.uuid4().hex[:12]
    task['target_name'] = client.simSpawnObject(target_name, 'Cube', target_pose,
                                               airsim.Vector3r(1.5, 1.5, 1.5), False)
    # Runtime-spawned meshes do not automatically enable segmentation rendering.
    if not client.simSetSegmentationObjectID(task['target_name'], 230):
        raise RuntimeError('Could not initialize game-target hit identification')
    point = target_pose.position
    client.simPlotStrings(['RL GAME TARGET'], [point + airsim.Vector3r(0, 0, -2)],
                         scale=2, color_rgba=[0, 1, 0.3, 1], duration=600)
    write_json(ARTIFACTS / 'task.json', task)
    print(f'Created {task["target_name"]} at {task["target_world"]}; firing station {station}.', flush=True)
    return task


def train(task_data, episodes, seed):
    task = TargetTask(task_data['blocked'], task_data['station'], task_data['heading'])
    q = np.zeros((SIZE, SIZE, 4, len(ACTIONS)), dtype=np.float32)
    rng = np.random.default_rng(seed)
    baseline = evaluate(task, q)
    history = []
    started = time.perf_counter()
    for episode in range(episodes):
        state = task.sample_start(rng)
        epsilon = max(0.05, 0.95 * (1 - episode / (episodes * .8)))
        total, success, collisions = 0.0, False, 0
        for step in range(120):
            action = int(rng.integers(len(ACTIONS))) if rng.random() < epsilon else int(np.argmax(q[state]))
            next_state, reward, done, info = task.step(state, action)
            target = reward + (0 if done else GAMMA * float(q[next_state].max()))
            q[state + (action,)] += 0.25 * (target - q[state + (action,)])
            state = next_state
            total += reward
            collisions += int(info['collision'])
            if done:
                success = info['success']
                break
        history.append((episode+1, total, step+1, int(success), collisions, epsilon))
        if (episode+1) % 2000 == 0:
            recent = history[-1000:]
            print(f'Episode {episode+1}/{episodes}: recent training success '
                  f'{sum(r[3] for r in recent)/len(recent):.1%}', flush=True)
    metrics = {'algorithm': 'tabular Q-learning', 'seed': seed, 'training_episodes': episodes,
               'training_seconds': time.perf_counter()-started, 'before_training': baseline,
               'evaluation': evaluate(task, q), 'scope': 'Random starts on this same sampled local grid.'}
    np.save(ARTIFACTS / 'q_table.npy', q)
    with (ARTIFACTS / 'training.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('episode', 'reward', 'steps', 'success', 'collisions', 'epsilon'))
        writer.writerows(history)
    write_json(ARTIFACTS / 'metrics.json', metrics)
    print('Evaluation:', json.dumps(metrics['evaluation']), flush=True)
    return q, metrics


def execute(client, data, q):
    task = TargetTask(data['blocked'], data['station'], data['heading'])
    heading = int(round(airsim.to_eularian_angles(client.simGetVehiclePose().orientation)[2] / (math.pi/2))) % 4
    state = (*data['start'], heading)
    trace = MissionTrace(client, data, q, state, ARTIFACTS)
    trace.sample(client.simGetVehiclePose().position, force=True)
    arrange()
    for remaining in range(8, 0, -1):
        client.simPrintLogMessage('RL Mission', f'Starts in {remaining}s - cyan planned / green flown', 0)
        time.sleep(1)
    trace.data['status'] = 'flying'
    trace.publish()
    visits = {}
    events = []
    collision_time = client.simGetCollisionInfo().time_stamp
    data['status'] = 'flying'
    write_json(ARTIFACTS / 'task.json', data)
    for step in range(120):
        if ctypes.windll.user32.GetAsyncKeyState(0x23) & 0x8000:
            raise KeyboardInterrupt('End pressed: demonstration stopped')
        visits[state] = visits.get(state, 0) + 1
        if visits[state] > 4:
            raise RuntimeError('Learned policy looped; stopping the demonstration')
        action = int(np.argmax(q[state]))
        next_state, _, done, info = task.step(state, action)
        if info['collision']:
            raise RuntimeError('Policy attempted to enter a blocked grid cell')
        print(f'Step {step+1}: {ACTIONS[action]} at {state}', flush=True)
        trace.data['action'] = f'Step {step+1}: {ACTIONS[action]}'
        trace.publish()
        client.simPrintLogMessage('RL Mission', trace.data['action'], 0)
        if action < 4:
            x, y, z = world(data, next_state[:2])
            # AirSim's normal waypoint completion radius is coarse relative to
            # a 2 m grid. Use feedback to execute the policy's selected cell.
            destination = airsim.Vector3r(x, y, z)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                actual = client.getMultirotorState().kinematics_estimated.position
                trace.sample(actual)
                error = destination - actual
                distance = error.get_length()
                if distance < 0.25:
                    client.hoverAsync().join()
                    break
                velocity = error * min(1.5, 2.5 / distance)
                client.moveByVelocityAsync(velocity.x_val, velocity.y_val, velocity.z_val, .2,
                    yaw_mode=airsim.YawMode(False, state[2]*90)).join()
            else:
                raise RuntimeError(f'Waypoint not reached; remaining error {distance:.2f} m')
        elif action in (4, 5):
            client.rotateToYawAsync(next_state[2]*90, timeout_sec=12, margin=3).join()
        else:
            if not done or not info['success']:
                raise RuntimeError('Policy fired outside the game target station')
            client.hoverAsync().join()
            client.rotateToYawAsync(data['heading']*90, timeout_sec=12, margin=2).join()
            client.simSetCameraPose('0', airsim.Pose(airsim.Vector3r(0.5, 0, 0), airsim.to_quaternion(0, 0, 0)))
            time.sleep(.25)
            game = Arcade(client)
            game.image()
            frame = game.image()
            h, w = frame.shape[:2]
            actor = game.actor_at(w//2, h//2, w, h)
            if actor != data['target_name']:
                raise RuntimeError(f'Target not confirmed in camera center (saw {actor}); no shot fired')
            game.fire(w//2, h//2, w, h, confirmed_actor=actor)
            if not client.simGetObjectPose(data['target_name']).position.containsNan():
                raise RuntimeError('Game target was not removed after the virtual shot')
        hit = client.simGetCollisionInfo()
        if hit.has_collided and hit.time_stamp > collision_time:
            raise RuntimeError(f'New collision with {hit.object_name}; demonstration stopped')
        events.append({'step': step+1, 'state': state, 'action': ACTIONS[action], 'next_state': next_state})
        trace.sample(client.simGetVehiclePose().position, force=True)
        state = next_state
        if done:
            client.hoverAsync().join()
            data['status'] = 'success'
            write_json(ARTIFACTS / 'task.json', data)
            write_json(ARTIFACTS / 'mission_result.json', {'success': True, 'steps': len(events),
                       'target': data['target_name'], 'events': events,
                       'route_file': 'route.json', 'actual_positions': trace.data['actual']})
            trace.finish('success')
            client.simPrintLogMessage('RL Mission', 'SUCCESS - target cleared; route remains visible', 0)
            print('SUCCESS: learned navigation, aiming, and virtual target destruction.', flush=True)
            return
    raise RuntimeError('Policy exceeded the step limit')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--episodes', type=int, default=20000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--train-only', action='store_true')
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error('--episodes must be positive')
    ARTIFACTS.mkdir(exist_ok=True)
    try:
        with LOCK.open('x') as stream:
            stream.write(str(time.time()))
    except FileExistsError:
        raise SystemExit('Another RL mission is active; check it before removing mission.lock.')
    client = airsim.MultirotorClient(timeout_value=45)
    data = None
    try:
        client.confirmConnection()
        data = prepare(client)
        q, metrics = train(data, args.episodes, args.seed)
        if metrics['evaluation']['success_rate'] < .98 or metrics['evaluation']['collision_actions']:
            raise RuntimeError('Evaluation did not meet the deployment threshold; no demonstration started')
        if not args.train_only:
            execute(client, data, q)
    except BaseException as error:
        write_json(ARTIFACTS / 'mission_result.json', {'success': False, 'error': str(error)})
        if data:
            data['status'] = 'stopped'
            write_json(ARTIFACTS / 'task.json', data)
            route_path = ARTIFACTS / 'route.json'
            if route_path.exists():
                route = json.loads(route_path.read_text(encoding='utf-8'))
                if route.get('target') == data.get('target_name'):
                    route['status'] = 'stopped'
                    route['action'] = str(error)
                    write_json(route_path, route)
        raise
    finally:
        try:
            client.hoverAsync().join()
        finally:
            LOCK.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
