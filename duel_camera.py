"""Enemy-aware third-person orbit camera, using the native viewport only."""
import ctypes
import json
import math
from pathlib import Path
import time

import airsim
import numpy as np

FOLDER=Path(__file__).parent/'duel_artifacts'
MODES=('enemy chase','wide side view','top view')


def vec(value):
    return np.array((value.x_val,value.y_val,value.z_val),dtype=float)


def rotate(q,value):
    q=q/q.get_length()
    answer=q*airsim.Quaternionr(*value,0)*q.conjugate()
    return vec(answer)


def look_rotation(eye,look):
    delta=np.asarray(look)-np.asarray(eye)
    return airsim.to_quaternion(math.atan2(-delta[2],math.hypot(delta[0],delta[1])),
                                0,math.atan2(delta[1],delta[0]))


def local_pose(player,eye,look,mount):
    inverse=player.orientation.conjugate()/player.orientation.get_length()
    local=rotate(inverse,np.asarray(eye)-vec(player.position))-mount
    return airsim.Pose(airsim.Vector3r(*local),inverse*look_rotation(eye,look))


def desired_view(player,enemy,yaw,orbit,zoom,mode):
    delta=enemy-player
    bearing=math.atan2(delta[1],delta[0]) if math.hypot(delta[0],delta[1])>.2 else yaw
    side=math.pi/2 if mode==1 else 0
    angle=bearing+orbit+side
    radius=max(zoom,abs(delta[2])*1.1, np.linalg.norm(delta[:2])*abs(math.sin(orbit+side))*.8)
    radius=min(radius,60)
    look=player+delta*.35
    if mode==2:
        eye=np.array((look[0],look[1],min(player[2],enemy[2])-max(15,zoom*2)))
    else:
        eye=player-np.array((math.cos(angle)*radius,math.sin(angle)*radius,4.0))
    return eye,look


def game_window():
    user=ctypes.windll.user32
    user.GetForegroundWindow.restype=ctypes.c_void_p
    user.GetWindowTextW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int]
    window=user.GetForegroundWindow()
    title=ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(window,title,len(title))
    return window if title.value.startswith(('CityEnviron','Blocks','AbandonedPark')) else None


def activate(window):
    user=ctypes.windll.user32
    user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    user.PostMessageW(window,0x100,ord('F'),0)
    user.PostMessageW(window,0x101,ord('F'),0)


def main():
    client=airsim.MultirotorClient(timeout_value=8)
    client.confirmConnection()
    client.simSetCameraPose('0',airsim.Pose(airsim.Vector3r(),airsim.to_quaternion(0,0,0)),vehicle_name='PlayerDrone')
    player=client.simGetObjectPose('PlayerDrone')
    camera=client.simGetCameraInfo('0',vehicle_name='PlayerDrone')
    mount=rotate(player.orientation.conjugate(),vec(camera.pose.position)-vec(player.position))
    client.simSetCameraFov('0',105,vehicle_name='PlayerDrone')
    user=ctypes.windll.user32
    user.GetAsyncKeyState.argtypes=[ctypes.c_int]
    user.GetAsyncKeyState.restype=ctypes.c_short
    mode,orbit,zoom,tracking,active=0,0.0,9.0,True,True
    previous=set()
    eye=look=None
    last=time.monotonic()
    last_status=0
    first_activation=True
    while True:
        started=time.monotonic()
        dt=min(.15,started-last)
        last=started
        window=game_window()
        keys={key for key in (ord('Z'),ord('X'),ord('C'),ord('V'),ord('F'),ord('B'),ord('I'),ord('K'),0xBF,0xBB,0xBD)
              if user.GetAsyncKeyState(key)&0x8000}
        pressed=keys-previous
        previous=keys
        if window:
            if pressed & {ord('B'),ord('I'),ord('K'),0xBF}:
                active=False
            if ord('V') in pressed:
                tracking=not tracking
            if ord('C') in pressed:
                mode=(mode+1)%3
            if keys & {ord('Z'),ord('X')}:
                orbit+=(int(ord('X') in keys)-int(ord('Z') in keys))*dt*math.radians(85)
            zoom=max(6,min(45,zoom+(int(0xBD in keys)-int(0xBB in keys))*dt*12))
            if first_activation or pressed & {ord('Z'),ord('X'),ord('C'),ord('V'),ord('F'),0xBB,0xBD}:
                active=True
                activate(window)
                first_activation=False
        try:
            player=client.simGetObjectPose('PlayerDrone')
            enemy=vec(client.simGetObjectPose('Drone1').position)
            point=vec(player.position)
            if np.any(np.isnan(enemy)) or np.any(np.isnan(point)):
                time.sleep(.1)
                continue
            yaw=airsim.to_eularian_angles(player.orientation)[2]
            target=enemy if tracking else point+np.array((math.cos(yaw)*12,math.sin(yaw)*12,0))
            desired_eye,desired_look=desired_view(point,target,yaw,orbit,zoom,mode)
            try:
                game_state=json.loads((FOLDER/'state.json').read_text())
                if game_state.get('phase')=='defeated':
                    desired_eye=point-np.array((math.cos(yaw)*9,math.sin(yaw)*9,4))
                    desired_look=point
            except (OSError,ValueError):
                pass
            blend=1-math.exp(-dt/.12)
            if eye is None or np.linalg.norm(eye-desired_eye)>60:
                eye,look=desired_eye,desired_look
            else:
                eye=eye+(desired_eye-eye)*blend
                look=look+(desired_look-look)*blend
            client.simSetCameraPose('0',local_pose(player,eye,look,mount),vehicle_name='PlayerDrone')
            if started-last_status>.8:
                relative_height=point[2]-enemy[2]
                status={'mode':MODES[mode],'tracking_ai':tracking,'orbit_degrees':math.degrees(orbit)%360,
                        'zoom':zoom,'active':active,'ai_height_relative':relative_height,
                        'eye':eye.tolist(),'look':look.tolist()}
                actual_camera=client.simGetCameraInfo('0',vehicle_name='PlayerDrone').pose
                camera_error=vec(actual_camera.position)-eye
                status['camera_position_error_m']=float(np.linalg.norm(camera_error))
                if np.linalg.norm(camera_error)>.5:
                    mount+=rotate(player.orientation.conjugate(),camera_error)*.5
                try:
                    (FOLDER/'camera_state.json').write_text(json.dumps(status),encoding='utf-8')
                except OSError:
                    pass
                if window and active:
                    height=f"AI {'ABOVE' if relative_height>0 else 'BELOW'} {abs(relative_height):.0f}m"
                    client.simPrintLogMessage('Camera',f'{MODES[mode]} | {height} | Z/X orbit, C views, V track, +/- zoom',0)
                last_status=started
        except Exception as error:
            print(f'Camera update retry: {error}',flush=True)
            time.sleep(.2)
        time.sleep(max(0,.05-(time.monotonic()-started)))


if __name__=='__main__':
    main()
