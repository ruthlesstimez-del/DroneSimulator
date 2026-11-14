"""On-demand arcade shots; no camera window or continuous image streaming."""
import queue
import threading

import airsim
from arcade_mode import Arcade


class ArcadeControls:
    def __init__(self):
        self.requests = queue.Queue(maxsize=1)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def fire(self, aim=(0.5, 0.5)):
        if not self.stopping.is_set():
            try:
                self.requests.put_nowait(aim)
            except queue.Full:
                pass

    def run(self):
        client = airsim.MultirotorClient(timeout_value=8)
        game = None
        manager = None
        while not self.stopping.is_set():
            try:
                aim = self.requests.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if game is None:
                    game = Arcade(client, camera='AimProxy', external=True)
                    managers = client.simListSceneObjects('PlayerCameraManager.*')
                    if not managers:
                        raise RuntimeError('Active viewing camera was not found')
                    manager = managers[0]
                pose = client.simGetObjectPose(manager)
                if pose.position.containsNan():
                    raise RuntimeError('Active viewing camera pose is unavailable')
                client.simSetCameraPose('AimProxy', pose, external=True)
                # Let the proxy camera render its new pose before picking a pixel.
                game.image()
                frame = game.image()
                height, width = frame.shape[:2]
                game.fire(min(width-1, max(0, round(aim[0]*width))),
                          min(height-1, max(0, round(aim[1]*height))), width, height)
                client.simPrintLogMessage('Arcade', f'{game.message} | Score {game.score}', 0)
            except Exception as error:
                print(f'Arcade shot failed: {error}', flush=True)
            finally:
                self.requests.task_done()

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=2)
