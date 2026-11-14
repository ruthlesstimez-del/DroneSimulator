"""Meaningful transition checks before deploying a learned policy."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
from rl_environment import TargetTask, reachable
from rl_project import read_voxels


class TargetTaskTests(unittest.TestCase):
    def setUp(self):
        blocked = np.zeros((5, 5), dtype=bool)
        blocked[2, 2] = True
        self.task = TargetTask(blocked, (3, 3), 1)

    def test_blocked_move_does_not_change_position(self):
        state = (1, 2, 0)
        other, _, done, info = self.task.step(state, 0)
        self.assertEqual(state, other)
        self.assertTrue(info['collision'])
        self.assertFalse(done)

    def test_firing_requires_both_station_and_heading(self):
        self.assertFalse(self.task.step((3, 3, 0), 6)[3]['success'])
        self.assertFalse(self.task.step((3, 2, 1), 6)[3]['success'])
        self.assertTrue(self.task.step((3, 3, 1), 6)[3]['success'])

    def test_turns_wrap_without_translation(self):
        self.assertEqual(self.task.step((1, 1, 0), 4)[0], (1, 1, 3))
        self.assertEqual(self.task.step((1, 1, 3), 5)[0], (1, 1, 0))

    def test_disconnected_cells_are_not_training_starts(self):
        blocked = np.zeros((5, 5), dtype=bool)
        blocked[2, :] = True
        connected = reachable(blocked, (0, 0))
        self.assertNotIn((4, 4), connected)

    def test_airsim_voxel_axes_preserve_known_obstacle_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.binvox'
            path.write_bytes(b'#binvox 1\ndim 2 2 3\ntranslate 0 0 0\nscale 1\ndata\n'
                             + bytes((0, 9, 1, 1, 0, 2)))
            grid = read_voxels(path)
            self.assertEqual(grid.shape, (2, 3, 2))
            self.assertEqual(int(grid.sum()), 1)
            self.assertTrue(grid[1, 2, 0])


if __name__ == '__main__':
    unittest.main()
