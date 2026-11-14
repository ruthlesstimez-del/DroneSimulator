"""Respawn control handoff and supervision for the human-controlled game drone."""
from pathlib import Path
import subprocess
import sys

import airsim


def reclaim_controls(client):
    client.enableApiControl(True)
    if not client.armDisarm(True):
        return False
    state=client.getMultirotorState()
    airborne=(state.landed_state==airsim.LandedState.Flying or
              state.kinematics_estimated.position.z_val < -1)
    return bool(client.isApiControlEnabled() and airborne)


class PlayerControlSupervisor:
    def __init__(self,folder):
        self.folder=folder
        self.process=None
        self.log=None

    def ensure_running(self):
        if self.process is not None and self.process.poll() is None:
            return
        if self.log is None:
            self.log=(self.folder/'player_control.log').open('a',encoding='utf-8')
        root=Path(__file__).resolve().parent
        self.process=subprocess.Popen([sys.executable,'-u',str(root/'manual_control.py'),
            '--vehicle','PlayerDrone','--no-shooting'],cwd=str(root),
            stdout=self.log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
