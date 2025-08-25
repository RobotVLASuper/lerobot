# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field
import math

from lerobot.cameras import CameraConfig


from ..config import RobotConfig


@RobotConfig.register_subclass("ur5_follower")
@dataclass
class UR5FollowerConfig(RobotConfig):
    # Port to connect to the arm
    robot_ip: str = "192.168.1.20"
    with_gripper: bool = True
    gripper_port: int = 63352

    disable_torque_on_disconnect: bool = True

    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: float | None = None

    # cameras
    # cameras: dict[str, CameraConfig] = field(
    #     default_factory=lambda: {
    #         "0_top": BaslerCameraConfig(camera_idx=0),
    #         "1_right": BaslerCameraConfig(camera_idx=1),
    #     }
    # )
    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    # Set to `True` for backward compatibility with previous policies/dataset
    use_degrees: bool = False
    init_pos_thr: float = 0.3
    move_mode: str = "servo"  # Options: "servo", "moveit"
    # init_pos: list[float] | None = None
    # OLD init pos
    init_pos: list[float] | None = field(
        default_factory=lambda: [
            0.010746735148131847,
            -1.7625709772109985,
            1.9510701894760132,
            -1.802381157875061,
            -1.6205466985702515,
            -0.015358272939920425,
            0.0117647061124444,
        ]
    )
    # init_pos: list[float] | None = field(
    #     default_factory=lambda: [
    #         -0.10549623170961553,
    #         -1.9308811626830042,
    #         1.964797321950094,
    #         -1.6040007076659144,
    #         -1.5635784308062952,
    #         -0.2269957701312464,
    #         0.0117647061124444,
    #     ]
    # )


@RobotConfig.register_subclass("ur5_follower_end_effector")
@dataclass
class UR5FollowerEndEffectorConfig(UR5FollowerConfig):
    """Configuration for the URFollowerEndEffector robot."""

    # Default bounds for the end-effector position (in meters)
    end_effector_bounds: dict[str, list[float]] = field(
        default_factory=lambda: {
            "min": [-1.0, -1.0, 0.0, -2*math.pi, -2*math.pi, -2*math.pi],  # min x, y, z, roll, pitch, yaw
            "max": [1.0, 1.0, 1.0, 2*math.pi, 2*math.pi, 2*math.pi],  # max x, y, z, roll, pitch, yaw
        }
    )
    delta_effector_bounds: list[float] = field(
        default_factory=lambda: [
            0.15,
            0.15,
            0.15,
            math.pi / 6,
            math.pi / 6,
            math.pi / 6,
        ],  # x, y, z, roll, pitch, yaw
    )
