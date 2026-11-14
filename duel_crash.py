"""Unpowered simulated fall after defeat; confirm surface contact before disarming."""
import time

PLAYER='PlayerDrone'


class CrashFall:
    def __init__(self,client):
        self.client=client
        self.status='none'
        self.started=None
        self.start_z=None
        self.drop_m=0.0
        self.surface=None
        self.ground_samples=0
        self.disarmed=False

    def cut_power(self):
        self.client.moveByMotorPWMsAsync(0,0,0,0,.6,vehicle_name=PLAYER)

    def start(self,position):
        self.status='falling'
        self.started=time.monotonic()
        self.start_z=position.z_val
        self.client.enableApiControl(True,vehicle_name=PLAYER)
        # A normal in-flight disarm can be rejected by SimpleFlight. Explicit
        # zero motor output cancels hover and lets simulated gravity act.
        self.cut_power()

    def update(self,position):
        if self.status=='none' or (self.status=='wrecked' and self.disarmed):
            return
        self.drop_m=max(self.drop_m,position.z_val-self.start_z)
        if not self.disarmed:
            self.cut_power()
        collision=self.client.simGetCollisionInfo(vehicle_name=PLAYER)
        state=self.client.getMultirotorState(vehicle_name=PLAYER)
        velocity=state.kinematics_estimated.linear_velocity
        # AirSim clears has_collided once settled, while retaining the most
        # recent surface normal, impact position, and timestamp.
        known_contact=collision.has_collided or collision.time_stamp>0
        on_surface=(known_contact and collision.normal.z_val<-.6
                    and abs(velocity.z_val)<.5
                    and (position-collision.position).get_length()<1.0)
        self.ground_samples=self.ground_samples+1 if on_surface else 0
        if self.ground_samples>=3:
            self.status='wrecked'
            self.surface=collision.object_name
            if not self.disarmed:
                self.disarmed=bool(self.client.armDisarm(False,vehicle_name=PLAYER))
                if self.disarmed:
                    self.client.enableApiControl(False,vehicle_name=PLAYER)

    def report(self):
        return {'status':self.status,'drop_m':round(self.drop_m,2),
                'surface':self.surface,'disarmed':self.disarmed}
