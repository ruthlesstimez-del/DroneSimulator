"""Small finite navigation/target-practice environment for tabular Q-learning."""
from collections import deque

import numpy as np

MOVES = ((1, 0), (0, 1), (-1, 0), (0, -1))
ACTIONS = ('north', 'east', 'south', 'west', 'turn_left', 'turn_right', 'fire')
GAMMA = 0.97


def reachable(blocked, start):
    distances = {tuple(start): 0}
    pending = deque([tuple(start)])
    while pending:
        cell = pending.popleft()
        for dx, dy in MOVES:
            other = cell[0] + dx, cell[1] + dy
            if (0 <= other[0] < blocked.shape[0] and 0 <= other[1] < blocked.shape[1]
                    and not blocked[other] and other not in distances):
                distances[other] = distances[cell] + 1
                pending.append(other)
    return distances


class TargetTask:
    def __init__(self, blocked, station, heading):
        self.blocked = np.asarray(blocked, dtype=bool)
        self.station = tuple(station)
        self.heading = int(heading)
        self.starts = list(reachable(self.blocked, self.station))

    def potential(self, state):
        x, y, heading = state
        distance = abs(x - self.station[0]) + abs(y - self.station[1])
        turn_distance = min((heading - self.heading) % 4, (self.heading - heading) % 4)
        return -2.0 * distance - (0.8 * turn_distance if distance == 0 else 0)

    def step(self, state, action):
        x, y, heading = state
        next_state = state
        reward, terminal, success, collision = -0.2, False, False, False
        if action < 4:
            dx, dy = MOVES[action]
            nx, ny = x + dx, y + dy
            if (0 <= nx < self.blocked.shape[0] and 0 <= ny < self.blocked.shape[1]
                    and not self.blocked[nx, ny]):
                next_state = (nx, ny, heading)
            else:
                reward, collision = -12.0, True
        elif action in (4, 5):
            next_state = (x, y, (heading + (-1 if action == 4 else 1)) % 4)
        elif action == 6:
            success = (x, y) == self.station and heading == self.heading
            reward, terminal = (100.0, True) if success else (-10.0, False)
        else:
            raise ValueError('Unknown action')
        reward += GAMMA * (0 if terminal else self.potential(next_state)) - self.potential(state)
        return next_state, reward, terminal, {'success': success, 'collision': collision}

    def sample_start(self, rng):
        x, y = self.starts[int(rng.integers(len(self.starts)))]
        return x, y, int(rng.integers(4))


def evaluate(task, q, episodes=200, seed=9001):
    rng = np.random.default_rng(seed)
    successes = collisions = 0
    lengths = []
    for _ in range(episodes):
        state = task.sample_start(rng)
        for step in range(120):
            state, _, done, info = task.step(state, int(np.argmax(q[state])))
            collisions += int(info['collision'])
            if done:
                successes += int(info['success'])
                lengths.append(step + 1)
                break
    return {'episodes': episodes, 'successes': successes, 'success_rate': successes / episodes,
            'collision_actions': collisions, 'mean_success_steps': float(np.mean(lengths)) if lengths else None}
