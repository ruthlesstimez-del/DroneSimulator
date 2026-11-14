"""Abstract arcade pursuit/tag game. No projectiles or real weapon model."""
import json
from pathlib import Path
import time

import numpy as np

FOLDER = Path(__file__).parent / 'duel_artifacts'
LIMITS = np.array((4, 4, 2))
MOVES = np.array(((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)))
SHAPE = (9,9,5,7)


def index(relative):
    return tuple((np.clip(relative,-LIMITS,LIMITS)+LIMITS).astype(int))


def transition(relative, action, rng, moving=True):
    distance = float(np.linalg.norm(relative))
    if action == 6 and distance <= 1:
        return relative.copy(), 50.0 + 2*distance, True
    following = relative.copy()
    penalty = -.3
    if action < 6:
        following -= MOVES[action]
    else:
        penalty -= 8
    if moving and rng.random() < .2:
        following += MOVES[int(rng.integers(6))]
    following = np.clip(following,-LIMITS,LIMITS)
    reward = penalty + 2*distance - .97*2*float(np.linalg.norm(following))
    return following, reward, False


def evaluate(q, seed=901, episodes=200):
    rng = np.random.default_rng(seed)
    successes = 0
    for _ in range(episodes):
        state = np.array([rng.integers(-limit,limit+1) for limit in LIMITS])
        for _ in range(100):
            state, _, done = transition(state,int(q[index(state)].argmax()),rng)
            if done:
                successes += 1
                break
    return {'episodes': episodes,'successes': successes,'success_rate': successes/episodes,
            'scope': 'Abstract relative-grid arcade game with random target moves, not city navigation.'}


def train(episodes=12000, seed=45):
    FOLDER.mkdir(exist_ok=True)
    q = np.zeros(SHAPE,dtype=np.float32)
    baseline = evaluate(q)
    rng = np.random.default_rng(seed)
    start = time.perf_counter()
    for episode in range(episodes):
        state = np.array([rng.integers(-limit,limit+1) for limit in LIMITS])
        epsilon = max(.04,.9*(1-episode/(episodes*.8)))
        for _ in range(100):
            action = int(rng.integers(7)) if rng.random()<epsilon else int(q[index(state)].argmax())
            following,reward,done = transition(state,action,rng)
            entry = index(state)+(action,)
            q[entry] += .2*(reward+(0 if done else .97*float(q[index(following)].max()))-q[entry])
            state=following
            if done:
                break
        if (episode+1)%3000==0:
            print(f'Arcade pursuit training: {episode+1}/{episodes}',flush=True)
    metrics = {'algorithm':'tabular Q-learning','episodes':episodes,'seed':seed,
               'seconds':time.perf_counter()-start,'baseline':baseline,'evaluation':evaluate(q)}
    np.save(FOLDER/'policy.npy',q)
    (FOLDER/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2),flush=True)
    if metrics['evaluation']['success_rate'] < .95:
        raise RuntimeError('Arcade policy did not meet the evaluation threshold')
    return q


if __name__=='__main__':
    train()
