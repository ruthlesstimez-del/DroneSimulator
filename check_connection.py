"""Check the simulator API and sensor configuration without moving the drone."""
import airsim

client = airsim.MultirotorClient(timeout_value=10)
client.confirmConnection()
print("Vehicles:", client.listVehicles())
print("Position:", client.getMultirotorState().kinematics_estimated.position)
lidar = client.getLidarData(lidar_name="Lidar1")
print("LiDAR timestamp:", lidar.time_stamp)
print("LiDAR points:", len(lidar.point_cloud) // 3)
