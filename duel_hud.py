"""Small game HUD and two-drone minimap; no camera stream."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

FOLDER=Path(__file__).parent/'duel_artifacts'
TITLE='Drone Duel - player green, AI red'


def render(state):
    image=np.full((570,460,3),(27,24,21),np.uint8)
    cv2.putText(image,'DRONE DUEL',(22,35),0,.85,(245,245,245),1,cv2.LINE_AA)
    radar=state.get('radar',{'status':'searching','range_m':80,'contact':None,'sweep_degrees':0})
    cv2.putText(image,f"{state['phase'].upper()} / {radar['status'].upper()}",(22,70),0,.55,(80,220,250),1)
    if state['phase']=='defeated':
        cv2.rectangle(image,(18,45),(443,77),(27,24,21),-1)
        label='FALLING - MOTORS DISABLED' if state.get('crash',{}).get('status')=='falling' else 'CRASHED - F9 TO RESPAWN'
        cv2.putText(image,label,(22,69),0,.59,(80,90,255),1)
    elif state.get('waiting_for_focus'):
        cv2.rectangle(image,(18,45),(443,77),(27,24,21),-1)
        cv2.putText(image,'CLICK CITY WINDOW TO PLAY',(22,69),0,.62,(80,220,250),1)
    for i in range(3):
        cv2.rectangle(image,(22+i*140,88),(150+i*140,110),
                      (80,220,100) if i<state['health'] else (60,60,80),-1)
    measured=radar.get('measured_range_m')
    text='NO RADAR CONTACT' if measured is None else f'CONTACT {measured:.1f} m'
    cv2.putText(image,f"HEALTH {state['health']}/3 | {text}",(22,140),0,.48,(225,225,225),1)
    a=np.array(state['positions']['Drone1'])
    scope=image[165:486,28:433]
    scope[:]=(35,38,30)
    center=(202,160)
    radius=140
    scale=radius/radar['range_m']
    def pixel(point):
        return round(center[0]+(point[1]-a[1])*scale),round(center[1]-(point[0]-a[0])*scale)
    for fraction in (.25,.5,.75,1):
        cv2.circle(scope,center,round(radius*fraction),(65,90,65),1,cv2.LINE_AA)
    cv2.line(scope,(center[0]-radius,center[1]),(center[0]+radius,center[1]),(55,70,55),1)
    cv2.line(scope,(center[0],center[1]-radius),(center[0],center[1]+radius),(55,70,55),1)
    angle=math.radians(radar['sweep_degrees'])
    tip=(round(center[0]+radius*math.sin(angle)),round(center[1]-radius*math.cos(angle)))
    cv2.line(scope,center,tip,(65,170,75),1,cv2.LINE_AA)
    cv2.circle(scope,center,6,(70,90,255),-1,cv2.LINE_AA)
    cv2.putText(scope,'AI Drone',(center[0]+9,center[1]+14),0,.4,(70,90,255),1)
    cv2.putText(scope,'N',(center[0]-5,15),0,.45,(190,210,190),1)
    cv2.putText(scope,f"{radar['range_m']:.0f} m / 360 deg",(10,306),0,.4,(190,210,190),1)
    if radar['contact'] is not None:
        contact=pixel(radar['contact'])
        color=(70,220,255) if radar['status']=='coasting' else (100,245,100)
        cv2.circle(scope,contact,7,color,-1,cv2.LINE_AA)
        cv2.putText(scope,'HumanDrone',(contact[0]+10,contact[1]-10),0,.36,color,1)
        cv2.putText(image,f"Bearing {radar['bearing_degrees']:.0f} deg | age {radar['contact_age']:.1f}s",(22,492),0,.4,(225,225,225),1)
    cv2.putText(image,'F8 start/pause AI | F9 respawn | F10 stop',(22,515),0,.47,(230,230,230),1)
    cv2.putText(image,'WASD fly | arrows altitude | Shift boost',(22,544),0,.47,(230,230,230),1)
    return image


def main():
    cv2.namedWindow(TITLE,cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITLE,460,570)
    while True:
        try:
            state=json.loads((FOLDER/'state.json').read_text())
            image=render(state)
        except (OSError,ValueError,KeyError):
            image=np.zeros((570,460,3),np.uint8)
            cv2.putText(image,'Preparing drone duel...',(25,70),0,.6,(230,230,230),1)
        cv2.imshow(TITLE,image)
        if cv2.waitKey(100)&0xFF==27 or cv2.getWindowProperty(TITLE,cv2.WND_PROP_VISIBLE)<1:
            break
    cv2.destroyAllWindows()


if __name__=='__main__':
    main()
