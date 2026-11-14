"""Lightweight colored world labels for the two simulated game drones."""
import time

import airsim

ROLES=(('Drone1','AI Drone',[1.0,.18,.12,1.0]),
       ('PlayerDrone','HumanDrone',[.2,1.0,.35,1.0]))


def draw_labels(client):
    for vehicle,label,color in ROLES:
        position=client.simGetObjectPose(vehicle).position
        if position.containsNan():
            continue
        client.simPlotStrings([label],[position+airsim.Vector3r(0,0,-1.4)],
                              scale=1.5,color_rgba=color,duration=.28)


def main():
    client=airsim.MultirotorClient(timeout_value=5)
    client.confirmConnection()
    print('World labels active: red AI Drone, green HumanDrone.',flush=True)
    while True:
        started=time.monotonic()
        try:
            draw_labels(client)
        except Exception as error:
            print(f'World-label connection ended: {error}',flush=True)
            break
        time.sleep(max(0,.2-(time.monotonic()-started)))


if __name__=='__main__':
    main()
