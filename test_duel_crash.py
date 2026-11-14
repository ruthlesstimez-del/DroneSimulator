import unittest
import airsim
from duel_crash import CrashFall,PLAYER


class CrashClient:
    def __init__(self):
        self.motors=[]
        self.armed=True
        self.api=True
        self.collision=airsim.CollisionInfo()
        self.state=airsim.MultirotorState()
        self.state.kinematics_estimated=airsim.KinematicsState()
        self.state.kinematics_estimated.linear_velocity=airsim.Vector3r(0,0,0)
    def enableApiControl(self,value,vehicle_name=''):
        self.api=value
    def moveByMotorPWMsAsync(self,*values,vehicle_name=''):
        self.motors.append((vehicle_name,values))
    def simGetCollisionInfo(self,vehicle_name=''):
        return self.collision
    def getMultirotorState(self,vehicle_name=''):
        return self.state
    def armDisarm(self,value,vehicle_name=''):
        self.armed=value
        return True


class CrashTests(unittest.TestCase):
    def test_power_is_cut_in_air_without_waiting_for_disarm(self):
        client=CrashClient()
        crash=CrashFall(client)
        crash.start(airsim.Vector3r(0,0,-20))
        self.assertEqual(client.motors[-1][0],PLAYER)
        self.assertEqual(client.motors[-1][1][:4],(0,0,0,0))
        self.assertEqual(crash.status,'falling')

    def test_old_ground_collision_cannot_confirm_an_airborne_wreck(self):
        client=CrashClient()
        client.collision.has_collided=True
        client.collision.normal=airsim.Vector3r(0,0,-1)
        client.collision.position=airsim.Vector3r(0,0,0)
        crash=CrashFall(client)
        crash.start(airsim.Vector3r(0,0,-20))
        for _ in range(5):
            crash.update(airsim.Vector3r(0,0,-20))
        self.assertEqual(crash.status,'falling')
        self.assertTrue(client.armed)

    def test_ground_contact_confirms_drop_then_releases_control(self):
        client=CrashClient()
        crash=CrashFall(client)
        crash.start(airsim.Vector3r(0,0,-20))
        client.collision.has_collided=True
        client.collision.normal=airsim.Vector3r(0,0,-1)
        client.collision.position=airsim.Vector3r(0,0,0)
        client.collision.object_name='Ground'
        for _ in range(3):
            crash.update(airsim.Vector3r(0,0,0))
        self.assertEqual(crash.status,'wrecked')
        self.assertEqual(crash.drop_m,20)
        self.assertFalse(client.armed)
        self.assertFalse(client.api)

    def test_settled_collision_flag_can_clear_without_losing_ground_contact(self):
        client=CrashClient()
        crash=CrashFall(client)
        crash.start(airsim.Vector3r(0,0,-20))
        client.collision.has_collided=False
        client.collision.time_stamp=123
        client.collision.normal=airsim.Vector3r(0,0,-1)
        client.collision.position=airsim.Vector3r(0,0,0)
        for _ in range(3):
            crash.update(airsim.Vector3r(0,0,0))
        self.assertEqual(crash.status,'wrecked')
        self.assertTrue(crash.disarmed)


if __name__=='__main__':
    unittest.main()
