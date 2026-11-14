"""First simulator flight: take off, hover, and land without horizontal travel."""
import airsim
import time


def main():
    client = airsim.MultirotorClient(timeout_value=30)
    client.confirmConnection()
    client.enableApiControl(True)
    armed = False
    try:
        if not client.armDisarm(True):
            raise RuntimeError("Simulator refused to arm")
        armed = True
        print("Taking off...")
        client.takeoffAsync(timeout_sec=20).join()
        client.hoverAsync().join()
        state = client.getMultirotorState()
        print("Position:", state.kinematics_estimated.position)
        lidar = client.getLidarData(lidar_name="Lidar1")
        print("LiDAR points:", len(lidar.point_cloud) // 3)
        print("Landing...")
    finally:
        if armed:
            client.landAsync(timeout_sec=30).join()
            time.sleep(3)
            state = client.getMultirotorState()
            collision = client.simGetCollisionInfo()
            velocity = state.kinematics_estimated.linear_velocity
            position = state.kinematics_estimated.position
            # SimpleFlight can keep reporting Flying while resting on the ground.
            # Only use contact fallback near the starting ground, at rest, and
            # where the reported collision position matches the current position.
            ground_contact = (
                collision.has_collided
                and collision.normal.z_val < -0.7
                and position.z_val >= 0
                and (position - collision.position).get_length() < 0.15
                and velocity.get_length() < 0.1
            )
            if state.landed_state == airsim.LandedState.Landed or ground_contact:
                if not client.armDisarm(False):
                    raise RuntimeError("Simulator refused to disarm")
                client.enableApiControl(False)
                print("Ground contact confirmed; disarmed and released control.")
            else:
                client.hoverAsync().join()
                print("Landing was not confirmed; hovering with API control retained.")


if __name__ == "__main__":
    main()
