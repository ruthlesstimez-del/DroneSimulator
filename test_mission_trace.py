import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from mission_trace import MissionTrace, planned_route


class MissionTraceTests(unittest.TestCase):
    def test_route_uses_world_coordinates_and_stops_before_target(self):
        data = {'blocked': np.zeros((16,16),dtype=int).tolist(), 'station': (9,8),
                'heading': 0, 'center': [10,20,-8], 'cell_size': 2}
        q = np.zeros((16,16,4,7))
        q[8,8,0,0] = 1
        q[9,8,0,6] = 1
        self.assertEqual(planned_route(data,q,(8,8,0)), [[10,20,-8],[12,20,-8]])

    def test_temporary_telemetry_lock_does_not_stop_flight_and_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            trace = object.__new__(MissionTrace)
            trace.path = Path(folder)/'route.json'
            trace.published = 0
            trace.data = {'actual': [[1,2,3,0]], 'status': 'flying'}
            with patch.object(Path,'replace',side_effect=PermissionError('temporarily locked')):
                self.assertFalse(trace.publish())
            self.assertTrue(trace.publish())
            self.assertEqual(json.loads(trace.path.read_text()),trace.data)


if __name__ == '__main__':
    unittest.main()
