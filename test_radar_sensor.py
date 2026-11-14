import unittest
import numpy as np

from radar_sensor import RadarSensor


class RadarTests(unittest.TestCase):
    def sensor(self):
        return RadarSensor(range_m=80,noise_m=0)

    def test_range_and_visibility_gate_detection(self):
        radar=self.sensor()
        self.assertIsNone(radar.update([0,0,0],[81,0,0],True,0))
        self.assertIsNone(radar.update([0,0,0],[40,0,0],False,1))
        self.assertEqual(radar.update([0,0,0],[40,0,0],True,2),[40,0,0])

    def test_scans_do_not_supply_live_truth_between_updates(self):
        radar=self.sensor()
        radar.update([0,0,0],[20,0,0],True,0)
        self.assertEqual(radar.update([0,0,0],[60,0,0],True,.5),[20,0,0])
        self.assertEqual(radar.update([0,0,0],[60,0,0],True,1),[60,0,0])

    def test_lost_contact_expires_instead_of_tracking_hidden_drone(self):
        radar=self.sensor()
        radar.update([0,0,0],[20,0,0],True,0)
        radar.update([0,0,0],[200,0,0],True,1)
        self.assertEqual(radar.report([0,0,0],1)['status'],'coasting')
        self.assertIsNone(radar.update([0,0,0],[200,0,0],True,2))
        self.assertEqual(radar.report([0,0,0],2)['status'],'searching')

    def test_bearing_and_range_include_vertical_displacement(self):
        radar=self.sensor()
        radar.update([0,0,0],[0,30,-40],True,0)
        report=radar.report([0,0,0],0)
        self.assertAlmostEqual(report['measured_range_m'],50)
        self.assertAlmostEqual(report['bearing_degrees'],90)


if __name__=='__main__':
    unittest.main()
