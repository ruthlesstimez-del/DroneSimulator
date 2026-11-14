import unittest
import airsim
import numpy as np

from duel_camera import desired_view,local_pose,rotate
from player_control import reclaim_controls


class RespawnClient:
    def __init__(self):
        self.api=False
        self.armed=False
    def enableApiControl(self,value):
        self.api=value
    def armDisarm(self,value):
        self.armed=value
        return True
    def getMultirotorState(self):
        state=airsim.MultirotorState()
        state.landed_state=airsim.LandedState.Flying
        state.kinematics_estimated=airsim.KinematicsState()
        state.kinematics_estimated.position=airsim.Vector3r(0,0,-20)
        return state
    def isApiControlEnabled(self):
        return self.api


class PlayerCameraTests(unittest.TestCase):
    def test_respawn_reclaims_api_and_arming(self):
        client=RespawnClient()
        self.assertTrue(reclaim_controls(client))
        self.assertTrue(client.api)
        self.assertTrue(client.armed)
        client.api=client.armed=False
        self.assertTrue(reclaim_controls(client))

    def test_camera_world_pose_independent_of_drone_heading(self):
        player=airsim.Pose(airsim.Vector3r(20,10,-20),airsim.to_quaternion(0,0,np.pi/2))
        eye=np.array((10,10,-25))
        look=np.array((20,10,-20))
        mount=np.array((.46,0,-.15))
        local=local_pose(player,eye,look,mount)
        world=np.array((20,10,-20))+rotate(player.orientation,
            np.array((local.position.x_val,local.position.y_val,local.position.z_val))+mount)
        self.assertTrue(np.allclose(world,eye,atol=1e-5))
        forward=rotate(player.orientation*local.orientation,np.array((1,0,0)))
        expected=(look-eye)/np.linalg.norm(look-eye)
        self.assertTrue(np.allclose(forward,expected,atol=1e-5))

    def test_enemy_behind_moves_camera_to_opposite_side(self):
        eye,look=desired_view(np.array((0,0,-20)),np.array((-20,0,-20)),0,0,9,0)
        self.assertGreater(eye[0],0)
        self.assertLess(look[0],0)

    def test_top_view_stays_above_both_drones(self):
        eye,look=desired_view(np.array((0,0,-20)),np.array((10,0,-40)),0,0,9,2)
        self.assertLess(eye[2],-40)


if __name__=='__main__':
    unittest.main()
