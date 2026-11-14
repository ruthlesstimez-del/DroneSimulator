"""Arcade evasion game. AI scores proximity tags, not physical weapon hits."""
import argparse
import ctypes
from pathlib import Path
import time

import airsim
import numpy as np

from duel_learning import FOLDER, MOVES, evaluate, index
from rl_project import write_json
from radar_sensor import RadarSensor
from player_control import PlayerControlSupervisor
from duel_crash import CrashFall

AI, PLAYER = 'Drone1', 'PlayerDrone'
RADIUS = 6.0


def vector(position):
    return np.array((position.x_val,position.y_val,position.z_val),dtype=float)


class Duel:
    def __init__(self, client, policy):
        self.client, self.policy = client, policy
        self.phase = 'resetting'
        self.health = 3
        self.hits = 0
        self.last_hit = -100.0
        self.started = time.monotonic()
        self.paths = {AI: [], PLAYER: []}
        self.velocity = np.zeros(3)
        self.collision_time = 0
        self.round = 0
        self.radar=RadarSensor()
        self.recover_until=0.0
        self.recover_velocity=np.zeros(3)
        self.waiting_for_focus=False
        self.crash=CrashFall(client)

    def reset(self):
        self.phase = 'resetting'
        self.publish()
        self.client.reset()
        futures=[]
        for name in (AI,PLAYER):
            self.client.enableApiControl(True,vehicle_name=name)
            if not self.client.armDisarm(True,vehicle_name=name):
                raise RuntimeError(f'Could not arm {name}')
            futures.append(self.client.takeoffAsync(timeout_sec=20,vehicle_name=name))
        for future in futures:
            future.join()
        futures=[self.client.moveToZAsync(-20,4,timeout_sec=20,vehicle_name=name) for name in (AI,PLAYER)]
        for future in futures:
            future.join()
        for name in (AI,PLAYER):
            self.client.hoverAsync(vehicle_name=name).join()
        self.health,self.hits=3,0
        self.phase='paused'
        self.velocity=np.zeros(3)
        self.started=time.monotonic()
        self.last_hit=-100
        self.paths={AI:[],PLAYER:[]}
        self.collision_time=self.client.simGetCollisionInfo(vehicle_name=AI).time_stamp
        self.round+=1
        self.radar=RadarSensor(seed=12+self.round)
        self.recover_until=0.0
        self.crash=CrashFall(self.client)
        self.client.simPrintLogMessage('Drone Duel','Ready: F8 starts AI | F9 respawns | F10 stops game',0)
        self.publish()

    def positions(self):
        # Object poses share global map coordinates; each vehicle's telemetry
        # position instead has its own spawn-relative origin.
        return {name: self.client.simGetObjectPose(name).position for name in (AI,PLAYER)}

    def publish(self, positions=None):
        if positions is None:
            positions=self.positions()
        for name,point in positions.items():
            p=vector(point).tolist()
            if not self.paths[name] or np.linalg.norm(np.array(p)-self.paths[name][-1])>.2:
                self.paths[name].append(p)
                self.paths[name]=self.paths[name][-600:]
        state={'phase':self.phase,'health':self.health,'maximum_health':3,'hits':self.hits,
               'round':self.round,'seconds':round(time.monotonic()-self.started,1),
               'positions':{name:vector(p).tolist() for name,p in positions.items()},
               'paths':self.paths,'tag_radius':RADIUS,'distance':float(np.linalg.norm(vector(positions[AI])-vector(positions[PLAYER]))),
               'radar':self.radar.report(vector(positions[AI]),time.monotonic()),
               'recovering':time.monotonic()<self.recover_until,
               'waiting_for_focus':self.waiting_for_focus,
               'crash':self.crash.report(),
               'rules':'Arcade proximity tags; three hits disable the player. No physical projectiles.'}
        try:
            write_json(FOLDER/'state.json',state)
        except PermissionError:
            pass
        return state

    def clear_view(self, distance):
        if distance<2:
            return False
        a=self.client.getMultirotorState(vehicle_name=AI).gps_location
        b=self.client.getMultirotorState(vehicle_name=PLAYER).gps_location
        # Trim both endpoints to avoid testing against the drone bodies.
        fraction=min(.4,1.0/distance)
        def mix(t):
            point=airsim.GeoPoint()
            point.latitude=a.latitude+(b.latitude-a.latitude)*t
            point.longitude=a.longitude+(b.longitude-a.longitude)*t
            point.altitude=a.altitude+(b.altitude-a.altitude)*t
            return point
        return self.client.simTestLineOfSightBetweenPoints(mix(fraction),mix(1-fraction))

    def tick(self):
        positions=self.positions()
        if any(p.containsNan() for p in positions.values()):
            raise RuntimeError('A game drone disappeared from the scene')
        delta=vector(positions[PLAYER])-vector(positions[AI])
        distance=float(np.linalg.norm(delta))
        now=time.monotonic()
        visible=False
        if self.radar.due(now) and distance<=self.radar.range_m:
            visible=self.clear_view(distance)
        contact=self.radar.update(vector(positions[AI]),vector(positions[PLAYER]),visible,now)
        if self.phase=='defeated':
            self.crash.update(positions[PLAYER])
            return self.publish(positions)
        if self.phase=='active' and not self.waiting_for_focus:
            if now<self.recover_until:
                self.client.moveByVelocityAsync(*self.recover_velocity,.3,vehicle_name=AI)
                return self.publish(positions)
            if contact is None:
                if np.linalg.norm(self.velocity)>.01:
                    self.client.hoverAsync(vehicle_name=AI)
                    self.velocity=np.zeros(3)
                return self.publish(positions)
            # Pursuit observes only the last radar measurement, never the
            # hidden player's live world coordinates.
            detected_delta=np.asarray(contact)-vector(positions[AI])
            detected_distance=float(np.linalg.norm(detected_delta))
            state=np.rint(detected_delta/4).astype(int)
            action=int(self.policy[index(state)].argmax())
            if action==6 and detected_distance<=RADIUS:
                self.client.hoverAsync(vehicle_name=AI)
                self.velocity=np.zeros(3)
                if distance<=RADIUS and time.monotonic()-self.last_hit>=1.5 and self.clear_view(distance):
                    self.last_hit=time.monotonic()
                    self.health-=1
                    self.hits+=1
                    self.client.simPlotLineList([positions[AI],positions[PLAYER]],
                                               [1,.25,.1,1],thickness=5,duration=.2)
                    self.client.simPrintLogMessage('Drone Duel',f'Virtual hit! Player health {self.health}/3',1)
                    print(f'GAME HIT {self.hits}: health {self.health}/3',flush=True)
                    if self.health==0:
                        self.phase='defeated'
                        self.crash.start(positions[PLAYER])
                        self.client.simPrintLogMessage('Drone Duel','MOTORS LOST - falling! F9 respawns both drones.',2)
                        print('GAME OVER: player disabled by three virtual tags',flush=True)
            else:
                # The rounded RL state can suggest tagging just outside the
                # continuous game radius; mask that unavailable action.
                if action==6:
                    action=int(self.policy[index(state)][:6].argmax())
                target_velocity=MOVES[action].astype(float)*5.5
                self.velocity=.5*self.velocity+.5*target_velocity
                self.client.moveByVelocityAsync(*self.velocity,.3,vehicle_name=AI)
            collision=self.client.simGetCollisionInfo(vehicle_name=AI)
            if collision.has_collided and collision.time_stamp>self.collision_time:
                self.collision_time=collision.time_stamp
                self.recover_velocity=np.array((-self.velocity[0]*.4,-self.velocity[1]*.4,-2.0))
                self.recover_until=now+1.2
                self.velocity=np.zeros(3)
                self.client.simPrintLogMessage('Drone Duel','AI recovering from scenery contact; chase will resume.',1)
        return self.publish(positions)


def focused():
    user=ctypes.windll.user32
    user.GetForegroundWindow.restype=ctypes.c_void_p
    user.GetWindowTextW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int]
    title=ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(user.GetForegroundWindow(),title,len(title))
    return title.value.startswith(('CityEnviron','Drone Duel'))


def verify_radar(game):
    def wait_for(predicate,seconds=4):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            state=game.tick()
            if predicate(state['radar']):
                return state
            time.sleep(.15)
        raise RuntimeError('Live radar verification timed out')
    detected=wait_for(lambda radar:radar['contact'] is not None)
    client=game.client
    original=client.simGetVehiclePose(vehicle_name=PLAYER)
    distant=airsim.Pose(airsim.Vector3r(original.position.x_val,original.position.y_val,
                                      original.position.z_val-120),original.orientation)
    try:
        client.simSetVehiclePose(distant,True,vehicle_name=PLAYER)
        client.moveByVelocityAsync(0,0,0,.3,vehicle_name=PLAYER).join()
        client.hoverAsync(vehicle_name=PLAYER).join()
        lost=wait_for(lambda radar:radar['contact'] is None and radar['status']=='searching')
    finally:
        client.simSetVehiclePose(original,True,vehicle_name=PLAYER)
        client.moveByVelocityAsync(0,0,0,.3,vehicle_name=PLAYER).join()
        client.hoverAsync(vehicle_name=PLAYER).join()
    reacquired=wait_for(lambda radar:radar['contact'] is not None)
    result={'success':True,'detected_in_range':True,'lost_out_of_range':True,'reacquired':True,
            'range_m':game.radar.range_m,'out_of_range_distance':lost['distance'],
            'scope':'Game radar range/visibility abstraction tested with a temporary vertical relocation.'}
    write_json(FOLDER/'radar_verification.json',result)
    print('PASS: radar detected, lost an out-of-range player, and reacquired it.',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--autostart',action='store_true')
    args=parser.parse_args()
    FOLDER.mkdir(exist_ok=True)
    policy=np.load(FOLDER/'policy.npy')
    if evaluate(policy)['success_rate']<.95:
        raise RuntimeError('Policy evaluation failed')
    client=airsim.MultirotorClient(timeout_value=30)
    client.confirmConnection()
    if not {AI,PLAYER}.issubset(set(client.listVehicles())):
        raise SystemExit('Launch the simulator with settings_duel.json first.')
    game=Duel(client,policy)
    game.reset()
    if args.verify:
        verify_radar(game)
        print('Verifying a complete arcade round...',flush=True)
        game.phase='active'
        deadline=time.monotonic()+60
        while game.phase=='active' and time.monotonic()<deadline:
            game.tick()
            time.sleep(.15)
        if game.phase!='defeated' or game.health!=0:
            raise RuntimeError(f'Arcade verification failed: {game.phase}, health={game.health}')
        deadline=time.monotonic()+20
        while game.crash.status!='wrecked' and time.monotonic()<deadline:
            game.tick()
            time.sleep(.15)
        if game.crash.status!='wrecked' or game.crash.drop_m<5:
            raise RuntimeError(f'Crash fall was not confirmed: {game.crash.report()}')
        write_json(FOLDER/'crash_verification.json',{'success':True,**game.crash.report()})
        print(f'PASS: disabled drone fell {game.crash.drop_m:.1f} m and came to rest on {game.crash.surface}.',flush=True)
        write_json(FOLDER/'verification.json',{'success':True,'hits':game.hits,'health':game.health,
                   'scope':'Live AirSim round against a stationary player; moving-target evaluation is abstract.'})
        print('PASS: AI pursued, scored three visible virtual hits, and disabled PlayerDrone.',flush=True)
        game.reset()
    player_controls=PlayerControlSupervisor(FOLDER)
    player_controls.ensure_running()
    activate_at=time.monotonic()+5 if args.autostart else None
    if args.autostart:
        game.phase='starting'
        game.publish()
    print('READY: player controls active. AI starts automatically in 5 seconds.' if args.autostart else
          'READY: player controls active. F8 starts/pauses AI; F9 respawns; F10 stops.',flush=True)
    previous=set()
    try:
        while True:
            player_controls.ensure_running()
            if activate_at is not None and time.monotonic()>=activate_at:
                game.phase='active'
                activate_at=None
            keys={k for k in (0x77,0x78,0x79) if ctypes.windll.user32.GetAsyncKeyState(k)&0x8000}
            pressed=keys-previous
            previous=keys
            if focused():
                if 0x79 in pressed:
                    break
                if 0x78 in pressed:
                    game.reset()
                    if args.autostart:
                        game.phase='starting'
                        activate_at=time.monotonic()+5
                if 0x77 in pressed and game.phase in ('paused','active'):
                    game.phase='active' if game.phase=='paused' else 'paused'
                    if game.phase=='paused':
                        client.hoverAsync(vehicle_name=AI)
            waiting=game.phase=='active' and not focused()
            if waiting and not game.waiting_for_focus:
                client.hoverAsync(vehicle_name=AI)
                game.velocity=np.zeros(3)
            game.waiting_for_focus=waiting
            game.tick()
            time.sleep(.15)
    finally:
        client.hoverAsync(vehicle_name=AI)
        game.phase='stopped'
        game.publish()


if __name__=='__main__':
    main()
