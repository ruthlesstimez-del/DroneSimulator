"""Windows keyboard flight controls, active only while the simulator has focus."""
import ctypes
import argparse
import json
import math
from pathlib import Path
import time

import airsim
from arcade_controls import ArcadeControls
from view_input import cursor_aim
from vehicle_client import VehicleClient
from player_control import reclaim_controls

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]


def down(key):
    return bool(user32.GetAsyncKeyState(key) & 0x8000)


def simulator_focused():
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(user32.GetForegroundWindow(), title, len(title))
    return title.value.startswith(('CityEnviron', 'Blocks', 'AbandonedPark'))


def land(client):
    print('Landing...', flush=True)
    client.landAsync(timeout_sec=30).join()
    time.sleep(3)
    state = client.getMultirotorState()
    hit = client.simGetCollisionInfo()
    position = state.kinematics_estimated.position
    resting = (
        hit.has_collided and hit.normal.z_val < -0.7
        and (position - hit.position).get_length() < 0.15
        and state.kinematics_estimated.linear_velocity.get_length() < 0.1
    )
    if state.landed_state == airsim.LandedState.Landed or resting:
        if client.armDisarm(False):
            client.enableApiControl(False)
            print('Landed and disarmed.', flush=True)
            return True
    client.hoverAsync().join()
    print('Touchdown not confirmed; hovering. Press L to retry.', flush=True)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vehicle', default='Drone1')
    parser.add_argument('--no-shooting', action='store_true')
    args = parser.parse_args()
    client = VehicleClient(airsim.MultirotorClient(timeout_value=40), args.vehicle)
    client.confirmConnection()
    print('Click the simulator window to activate keyboard controls.\n'
          'T take off | W/S forward/back | A/D sideways | Up/Down altitude\n'
          'Q/E turn | Space hover | Left click/J fire at crosshair | Shift boost | L land | End stop\n'
          'Views: B third-person | / chase | I front | K rear | F optional first-person\n'
          'Release movement keys to hover. Switching windows also stops movement.\n'
          'Manual flight does not avoid obstacles.', flush=True)
    # Attach to an already airborne drone when this controller is restarted.
    flying = (client.isApiControlEnabled()
              and client.getMultirotorState().landed_state == airsim.LandedState.Flying)
    moving = False
    previous = set()
    arcade = None if args.no_shooting else ArcadeControls()
    velocity = [0.0, 0.0, 0.0, 0.0]
    last_update = time.monotonic()
    mission_lock = Path(__file__).parent / 'rl_artifacts' / 'mission.lock'
    was_autonomous = False
    duel_path = Path(__file__).parent / 'duel_artifacts' / 'state.json'
    duel_disabled = False
    duel_round=None
    next_control_retry=0.0
    try:
        while True:
            keys = {key for key in [*(ord(c) for c in 'TWASDQELJ'), 0x26, 0x28, 0x23, 0x01] if down(key)}
            if args.vehicle == 'PlayerDrone' and duel_path.exists():
                try:
                    duel = json.loads(duel_path.read_text(encoding='utf-8'))
                    if duel.get('phase') in ('defeated', 'resetting') or duel.get('health',3)<=0:
                        duel_disabled = True
                        flying = False
                        moving = False
                        velocity = [0.0] * 4
                        previous = keys
                        time.sleep(.05)
                        continue
                    if duel_disabled or duel.get('round') != duel_round:
                        if time.monotonic()<next_control_retry:
                            time.sleep(.02)
                            continue
                        try:
                            if not reclaim_controls(client):
                                next_control_retry=time.monotonic()+.2
                                continue
                        except Exception as error:
                            print(f'Retrying respawn control handoff: {error}',flush=True)
                            next_control_retry=time.monotonic()+.2
                            continue
                        flying=True
                        duel_round=duel.get('round')
                        duel_disabled=False
                        moving=False
                        velocity=[0.0]*4
                        last_update=time.monotonic()
                        print(f'PLAYER CONTROL READY: round {duel_round}',flush=True)
                except (OSError, ValueError):
                    pass
            if mission_lock.exists():
                was_autonomous = True
                moving = False
                velocity = [0.0] * 4
                previous = keys
                time.sleep(0.05)
                continue
            if was_autonomous:
                flying = (client.isApiControlEnabled() and
                          client.getMultirotorState().landed_state == airsim.LandedState.Flying)
                was_autonomous = False
                last_update = time.monotonic()
            if not simulator_focused():
                if flying and moving:
                    client.hoverAsync()
                    moving = False
                    velocity = [0.0] * 4
                previous = keys
                time.sleep(0.1)
                continue
            pressed = keys - previous
            previous = keys
            if 0x23 in pressed:
                break
            if arcade and (ord('J') in pressed or 0x01 in pressed):
                aim = cursor_aim()
                if aim:
                    arcade.fire(aim[:2])
            if ord('L') in pressed and flying:
                flying = not land(client)
                moving = False
                velocity = [0.0] * 4
                continue
            if ord('T') in pressed and not flying:
                client.enableApiControl(True)
                if not client.armDisarm(True):
                    raise RuntimeError('Simulator refused to arm')
                flying = True
                print('Taking off...', flush=True)
                client.takeoffAsync(timeout_sec=20).join()
                client.hoverAsync().join()
                continue
            if flying:
                speed = 12.0 if down(0x10) else 6.0
                dx = int(ord('W') in keys) - int(ord('S') in keys)
                dy = int(ord('D') in keys) - int(ord('A') in keys)
                norm = max(1.0, math.hypot(dx, dy))
                vx, vy = speed * dx / norm, speed * dy / norm
                vz = 3.0 * (int(0x28 in keys) - int(0x26 in keys))
                yaw = 65.0 * (int(ord('E') in keys) - int(ord('Q') in keys))
                if down(0x20):
                    vx = vy = vz = yaw = 0.0
                now = time.monotonic()
                elapsed = now - last_update
                if elapsed < 0.05:
                    time.sleep(0.01)
                    continue
                last_update = now
                blend = 1 - math.exp(-elapsed / 0.12)
                velocity = [old + blend * (target - old)
                            for old, target in zip(velocity, (vx, vy, vz, yaw))]
                vx, vy, vz, yaw = velocity
                if any(abs(value) > limit for value, limit in zip(velocity, (.05, .05, .05, .5))):
                    client.moveByVelocityBodyFrameAsync(
                        vx, vy, vz, 0.25, yaw_mode=airsim.YawMode(True, yaw))
                    moving = True
                elif moving:
                    client.hoverAsync()
                    moving = False
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        if arcade:
            arcade.close()
        if flying:
            land(client)


if __name__ == '__main__':
    main()
