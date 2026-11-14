import unittest
from unittest.mock import patch

import airsim
import numpy as np

from duel_game import AI, PLAYER, Duel
from duel_learning import MOVES, index, transition
from vehicle_client import VehicleClient
from radar_sensor import RadarSensor


class FakeClient:
    def __init__(self):
        self.disarmed=[]
        self.motor_commands=[]
    def enableApiControl(self,value,vehicle_name=''):
        pass
    def moveByMotorPWMsAsync(self,*values,vehicle_name=''):
        self.motor_commands.append((vehicle_name,values))
    def getMultirotorState(self,vehicle_name=''):
        return vehicle_name
    def listVehicles(self):
        return [AI,PLAYER]
    def hoverAsync(self,vehicle_name=''):
        return None
    def armDisarm(self,armed,vehicle_name=''):
        if not armed:
            self.disarmed.append(vehicle_name)
        return True
    def simPrintLogMessage(self,*args):
        pass
    def simPlotLineList(self,*args,**kwargs):
        pass
    def simGetCollisionInfo(self,vehicle_name=''):
        return airsim.CollisionInfo()


class DuelTests(unittest.TestCase):
    def test_vehicle_binding_targets_player_and_preserves_world_apis(self):
        client=VehicleClient(FakeClient(),PLAYER)
        self.assertEqual(client.getMultirotorState(),PLAYER)
        self.assertEqual(client.listVehicles(),[AI,PLAYER])

    def test_abstract_tag_requires_proximity(self):
        rng=np.random.default_rng(1)
        self.assertFalse(transition(np.array((4,4,2)),6,rng,moving=False)[2])
        self.assertTrue(transition(np.array((1,0,0)),6,rng,moving=False)[2])

    def game(self,visible):
        client=FakeClient()
        policy=np.zeros((9,9,5,7))
        policy[...,6]=1
        game=Duel(client,policy)
        game.phase='active'
        game.positions=lambda:{AI:airsim.Vector3r(0,0,-20),PLAYER:airsim.Vector3r(4,0,-20)}
        game.clear_view=lambda distance:visible
        game.publish=lambda positions=None:None
        return game,client

    def test_three_virtual_hits_disable_only_player(self):
        game,client=self.game(True)
        for moment in (0,2,4):
            with patch('duel_game.time.monotonic',return_value=moment):
                game.tick()
        self.assertEqual(game.health,0)
        self.assertEqual(game.phase,'defeated')
        self.assertEqual(game.crash.status,'falling')
        self.assertEqual(client.motor_commands[-1][0],PLAYER)
        self.assertEqual(client.motor_commands[-1][1][:4],(0,0,0,0))

    def test_obstructed_view_prevents_virtual_damage(self):
        game,client=self.game(False)
        game.tick()
        self.assertEqual(game.health,3)
        self.assertEqual(client.disarmed,[])

    def test_no_radar_contact_prevents_pursuit_and_damage(self):
        game,client=self.game(True)
        game.radar=RadarSensor(range_m=1,noise_m=0)
        game.tick()
        self.assertEqual(game.health,3)
        self.assertEqual(client.disarmed,[])
        self.assertTrue(np.array_equal(game.velocity,np.zeros(3)))

    def test_ai_waits_while_player_is_outside_game_window(self):
        game,client=self.game(True)
        game.waiting_for_focus=True
        game.tick()
        self.assertEqual(game.health,3)
        self.assertEqual(client.disarmed,[])


if __name__=='__main__':
    unittest.main()
