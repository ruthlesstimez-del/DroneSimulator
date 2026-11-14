"""Arcade-only camera game: virtual hits remove individual AirSim scene actors."""
import ast
import math
from pathlib import Path
import random
import re
import time

import airsim
import cv2
import numpy as np

TITLE = 'AirSim Arcade - click to fire'
DISPLAY = (1024, 576)
TARGETS = re.compile(
    r'building|apartment|tower|office|house|shop|tree|palm|bench|crate|barrel|'
    r'bin|fence|saloon|sedan|hatchback|coupe|suv|bus|lamp|streetsign', re.I)
BUILDINGS = re.compile(r'building|apartment|tower|office|house|shop', re.I)


def decode(response):
    return cv2.imdecode(np.frombuffer(response.image_data_uint8, np.uint8), cv2.IMREAD_COLOR)


class Arcade:
    def __init__(self, client, camera='0', external=False):
        self.client = client
        self.camera = camera
        self.external = external
        self.health = {}
        self.score = 0
        self.destroyed = 0
        self.shots = 0
        self.message = 'Click a building or prop to fire. Reload City to restore objects.'
        self.last_shot = -10.0
        self.last_hit = False
        self.aim = (0.5, 0.5)
        self.pending = None
        self.pitch = 0.0
        self.palette = {}
        for line in (Path(__file__).parent / 'segmentation_colors.txt').read_text().splitlines():
            index, rgb = line.split('\t', 1)
            self.palette[int(index)] = tuple(reversed(ast.literal_eval(rgb)))
        client.simAddDetectionFilterMeshName(camera, airsim.ImageType.Scene, '*', external=external)
        client.simSetDetectionFilterRadius(camera, airsim.ImageType.Scene, 20000, external=external)

    def image(self, kind=airsim.ImageType.Scene):
        response = self.client.simGetImages([airsim.ImageRequest(self.camera, kind, False, True)], external=self.external)[0]
        frame = decode(response)
        if frame is None:
            raise RuntimeError('Drone camera returned no image')
        return frame

    def actor_at(self, x, y, width, height):
        """Use two temporary stencil colors to identify the actual visible actor.

        A bounding box alone could select a building behind a nearer object.
        Both color changes must appear at the exact clicked pixel before a hit
        is accepted. Original segmentation IDs are restored after each probe.
        """
        detections = self.client.simGetDetections(self.camera, airsim.ImageType.Scene, external=self.external)
        candidates = []
        for detection in detections:
            box = detection.box2D
            if (TARGETS.search(detection.name)
                    and box.min.x_val <= x <= box.max.x_val
                    and box.min.y_val <= y <= box.max.y_val):
                candidates.append(detection)
        candidates.sort(key=lambda d: d.relative_pose.position.get_length())
        # Usually one existing segmentation color identifies the visible actor.
        # Only ambiguous ID collisions need the slower temporary-color probes.
        if not candidates:
            return None
        mask = self.image(airsim.ImageType.Segmentation)
        px = min(mask.shape[1] - 1, round(x * mask.shape[1] / width))
        py = min(mask.shape[0] - 1, round(y * mask.shape[0] / height))
        color = tuple(int(v) for v in mask[py, px])
        matches = [d for d in candidates if self.palette.get(
            self.client.simGetSegmentationObjectID(d.name.lower())) == color]
        if len(matches) == 1:
            return matches[0].name
        candidates = matches
        for detection in candidates:
            name = detection.name
            original = self.client.simGetSegmentationObjectID(name.lower())
            if original < 0:
                continue
            matched = True
            try:
                for stencil in (254, 253):
                    if not self.client.simSetSegmentationObjectID(name, stencil):
                        matched = False
                        break
                    time.sleep(0.08)
                    # Allow one capture for the updated stencil to reach rendering.
                    self.image(airsim.ImageType.Segmentation)
                    mask = self.image(airsim.ImageType.Segmentation)
                    px = min(mask.shape[1] - 1, round(x * mask.shape[1] / width))
                    py = min(mask.shape[0] - 1, round(y * mask.shape[0] / height))
                    if tuple(int(v) for v in mask[py, px]) != self.palette[stencil]:
                        matched = False
                        break
            finally:
                self.client.simSetSegmentationObjectID(name, original)
            if matched:
                return name
        return None

    def impact_effect(self, x, y, width, height, destroyed):
        response = self.client.simGetImages([
            airsim.ImageRequest(self.camera, airsim.ImageType.DepthPlanar, True, False)], external=self.external)[0]
        if not response.image_data_float:
            return
        depth = np.asarray(response.image_data_float).reshape(response.height, response.width)
        px = min(response.width - 1, round(x * response.width / width))
        py = min(response.height - 1, round(y * response.height / height))
        distance = float(depth[py, px])
        if not math.isfinite(distance) or not 0 < distance < 200:
            return
        camera = self.client.simGetCameraInfo(self.camera, external=self.external)
        focal = response.width / (2 * math.tan(math.radians(camera.fov) / 2))
        local = airsim.Vector3r(distance, (px - response.width / 2) * distance / focal,
                               (py - response.height / 2) * distance / focal)
        q = camera.pose.orientation
        q = q / q.get_length()
        rotated = q * airsim.Quaternionr(local.x_val, local.y_val, local.z_val, 0) * q.conjugate()
        point = camera.pose.position + airsim.Vector3r(rotated.x_val, rotated.y_val, rotated.z_val)
        origin = self.client.simGetVehiclePose().position if self.external else camera.pose.position
        self.client.simPlotLineList([origin, point], [1, 0.8, 0.1, 1], 4, 0.2)
        rays = []
        radius = 4 if destroyed else 0.8
        for _ in range(6):
            offset = airsim.Vector3r(*(random.uniform(-radius, radius) for _ in range(3)))
            rays.extend([point, point + offset])
        self.client.simPlotLineList(rays, [1, 0.3, 0.05, 1], 8 if destroyed else 3, 1.0)

    def damage(self, actor):
        maximum = 3 if BUILDINGS.search(actor) else 1
        remaining = self.health.get(actor, maximum) - 1
        if remaining > 0:
            self.health[actor] = remaining
            self.message = f'HIT: {actor} | {remaining}/{maximum} HP'
            return False
        if not self.client.simDestroyObject(actor):
            self.message = f'{actor}: this map object could not be removed'
            return False
        # Destruction is queued by Unreal; confirm disappearance before scoring.
        for _ in range(10):
            if math.isnan(self.client.simGetObjectPose(actor).position.x_val):
                self.health.pop(actor, None)
                self.destroyed += 1
                self.score += 300 if maximum == 3 else 100
                self.message = f'DESTROYED: {actor}  +{300 if maximum == 3 else 100}'
                return True
            time.sleep(0.05)
        self.message = f'{actor}: removal not confirmed'
        return False

    def fire(self, x, y, width, height, confirmed_actor=None):
        now = time.monotonic()
        if now - self.last_shot < 0.3:
            return
        self.last_shot = now
        self.shots += 1
        actor = confirmed_actor if confirmed_actor is not None else self.actor_at(x, y, width, height)
        self.last_hit = actor is not None
        if actor:
            # Draw effects before removal so depth still belongs to the hit surface.
            self.impact_effect(x, y, width, height, self.health.get(actor, 3 if BUILDINGS.search(actor) else 1) == 1)
            self.damage(actor)
        else:
            self.message = 'MISS / scenery: aim at a visible building, tree, vehicle, or prop'
        print(self.message, flush=True)

    def mouse(self, event, x, y, flags, userdata):
        self.aim = (max(0, min(1, x / DISPLAY[0])), max(0, min(1, y / DISPLAY[1])))
        if event == cv2.EVENT_LBUTTONDOWN and 56 <= y < DISPLAY[1] - 35:
            self.pending = self.aim

    def run(self):
        cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(TITLE, self.mouse)
        try:
            while True:
                image = self.image()
                h, w = image.shape[:2]
                if self.pending is not None:
                    aim = self.pending
                    self.pending = None
                    self.fire(min(w - 1, round(aim[0] * w)), min(h - 1, round(aim[1] * h)), w, h)
                frame = cv2.resize(image, DISPLAY)
                cx, cy = round(self.aim[0] * DISPLAY[0]), round(self.aim[1] * DISPLAY[1])
                recent = time.monotonic() - self.last_shot < 0.3
                color = (0, 80, 255) if recent and self.last_hit else (80, 255, 120)
                cv2.circle(frame, (cx, cy), 12, color, 1)
                cv2.line(frame, (cx - 22, cy), (cx - 5, cy), color, 2)
                cv2.line(frame, (cx + 5, cy), (cx + 22, cy), color, 2)
                cv2.line(frame, (cx, cy - 22), (cx, cy - 5), color, 2)
                cv2.line(frame, (cx, cy + 5), (cx, cy + 22), color, 2)
                if recent:
                    cv2.line(frame, (DISPLAY[0] // 2, DISPLAY[1] - 1), (cx, cy), (0, 210, 255), 3)
                    cv2.circle(frame, (cx, cy), 20, (0, 150, 255), 2)
                cv2.rectangle(frame, (0, 0), (DISPLAY[0], 56), (20, 20, 20), -1)
                cv2.putText(frame, f'ARCADE  |  SCORE {self.score}  |  DESTROYED {self.destroyed}  |  SHOTS {self.shots}',
                            (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 1)
                cv2.putText(frame, 'Click: fire | T: takeoff | WASD: fly | R/F: altitude | Q/E: turn | I/K: aim up/down | L: land',
                            (15, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (230, 230, 230), 1)
                cv2.rectangle(frame, (0, DISPLAY[1] - 35), DISPLAY, (20, 20, 20), -1)
                cv2.putText(frame, self.message[:115], (15, DISPLAY[1] - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1)
                cv2.imshow(TITLE, frame)
                key = cv2.waitKey(20) & 0xFF
                if key == 27 or cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key in (ord('i'), ord('k')):
                    self.pitch = max(-60, min(60, self.pitch + (5 if key == ord('i') else -5)))
                    self.client.simSetCameraPose('0', airsim.Pose(airsim.Vector3r(0.5, 0, 0),
                        airsim.to_quaternion(math.radians(self.pitch), 0, 0)))
        finally:
            self.client.simClearDetectionMeshNames('0', airsim.ImageType.Scene)
            cv2.destroyAllWindows()


def main():
    client = airsim.MultirotorClient(timeout_value=30)
    client.confirmConnection()
    print('Arcade mode: scene-object removal is temporary. Reload City to restore buildings.', flush=True)
    Arcade(client).run()


if __name__ == '__main__':
    main()
