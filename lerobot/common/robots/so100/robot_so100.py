#!/usr/bin/env python

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

import json
import logging
import time

import numpy as np

from lerobot.common.cameras.utils import make_cameras_from_configs
from lerobot.common.constants import OBS_IMAGES, OBS_STATE
from lerobot.common.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.common.motors import CalibrationMode, Motor
from lerobot.common.motors.calibration import find_min_max, find_offset, set_calibration
from lerobot.common.motors.feetech import (
    FeetechMotorsBus,
    OperatingMode,
    TorqueMode,
)

from ..robot import Robot
from ..utils import ensure_safe_goal_position
from .configuration_so100 import SO100RobotConfig


class SO100Robot(Robot):
    """
    [SO-100 Follower Arm](https://github.com/TheRobotStudio/SO-ARM100) designed by TheRobotStudio
    """

    config_class = SO100RobotConfig
    name = "so100"

    def __init__(self, config: SO100RobotConfig):
        super().__init__(config)
        self.config = config
        self.robot_type = config.type
        self.logs = {}

        self.arm = FeetechMotorsBus(
            port=self.config.port,
            motors={
                "shoulder_pan": Motor(1, "sts3215", CalibrationMode.RANGE_M100_100),
                "shoulder_lift": Motor(2, "sts3215", CalibrationMode.RANGE_M100_100),
                "elbow_flex": Motor(3, "sts3215", CalibrationMode.RANGE_M100_100),
                "wrist_flex": Motor(4, "sts3215", CalibrationMode.RANGE_M100_100),
                "wrist_roll": Motor(5, "sts3215", CalibrationMode.RANGE_M100_100),
                "gripper": Motor(6, "sts3215", CalibrationMode.RANGE_0_100),
            },
        )
        self.cameras = make_cameras_from_configs(config.cameras)

    @property
    def state_feature(self) -> dict:
        return {
            "dtype": "float32",
            "shape": (len(self.arm),),
            "names": {"motors": list(self.arm.motors)},
        }

    @property
    def action_feature(self) -> dict:
        return self.state_feature

    @property
    def camera_features(self) -> dict[str, dict]:
        cam_ft = {}
        for cam_key, cam in self.cameras.items():
            cam_ft[cam_key] = {
                "shape": (cam.height, cam.width, cam.channels),
                "names": ["height", "width", "channels"],
                "info": None,
            }
        return cam_ft

    def configure(self) -> None:
        for name in self.arm.names:
            # We assume that at connection time, arm is in a rest position,
            # and torque can be safely disabled to run calibration.
            self.arm.write("Torque_Enable", name, TorqueMode.DISABLED.value)
            self.arm.write("Mode", name, OperatingMode.POSITION.value)

            # Set P_Coefficient to lower value to avoid shakiness (Default is 32)
            self.arm.write("P_Coefficient", name, 16)
            # Set I_Coefficient and D_Coefficient to default value 0 and 32
            self.arm.write("I_Coefficient", name, 0)
            self.arm.write("D_Coefficient", name, 32)
            # Set Maximum_Acceleration to 254 to speedup acceleration and deceleration of
            # the motors. Note: this configuration is not in the official STS3215 Memory Table
            self.arm.write("Maximum_Acceleration", name, 254)
            self.arm.write("Acceleration", name, 254)

        if not self.calibration_fpath.exists():
            print("Calibration file not found. Running calibration.")
            self.calibrate()
        else:
            print("Calibration file found. Loading calibration data.")
            set_calibration(self.arm, self.calibration_fpath)

        for name in self.arm.names:
            self.arm.write("Torque_Enable", name, TorqueMode.ENABLED.value)

        logging.info("Torque activated.")

    @property
    def is_connected(self) -> bool:
        # TODO(aliberts): add cam.is_connected for cam in self.cameras
        return self.arm.is_connected

    def connect(self) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(
                "ManipulatorRobot is already connected. Do not run `robot.connect()` twice."
            )

        logging.info("Connecting arm.")
        self.arm.connect()
        self.configure()

        # Check arm can be read
        self.arm.sync_read("Present_Position")

        # Connect the cameras
        for cam in self.cameras.values():
            cam.connect()

    def calibrate(self) -> None:
        print(f"\nRunning calibration of {self.name} robot")

        offsets = find_offset(self.arm)
        min_max = find_min_max(self.arm)

        calibration = {}
        for name in self.arm.names:
            motor_id = self.arm.motors[name].id
            calibration[str(motor_id)] = {
                "name": name,
                "homing_offset": offsets.get(name, 0),
                "drive_mode": 0,
                "min": min_max[name]["min"],
                "max": min_max[name]["max"],
            }

        with open(self.calibration_fpath, "w") as f:
            json.dump(calibration, f, indent=4)
        print("Calibration saved to", self.calibration_fpath)

    def get_observation(self) -> dict[str, np.ndarray]:
        """The returned observations do not have a batch dimension."""
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "ManipulatorRobot is not connected. You need to run `robot.connect()`."
            )

        obs_dict = {}

        # Read arm position
        before_read_t = time.perf_counter()
        obs_dict[OBS_STATE] = self.arm.sync_read("Present_Position")
        self.logs["read_pos_dt_s"] = time.perf_counter() - before_read_t

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            before_camread_t = time.perf_counter()
            obs_dict[f"{OBS_IMAGES}.{cam_key}"] = cam.async_read()
            self.logs[f"read_camera_{cam_key}_dt_s"] = cam.logs["delta_timestamp_s"]
            self.logs[f"async_read_camera_{cam_key}_dt_s"] = time.perf_counter() - before_camread_t

        return obs_dict

    def send_action(self, action: np.ndarray) -> np.ndarray:
        """Command arm to move to a target joint configuration.

        The relative action magnitude may be clipped depending on the configuration parameter
        `max_relative_target`. In this case, the action sent differs from original action.
        Thus, this function always returns the action actually sent.

        Args:
            action (np.ndarray): array containing the goal positions for the motors.

        Raises:
            RobotDeviceNotConnectedError: if robot is not connected.

        Returns:
            np.ndarray: the action sent to the motors, potentially clipped.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "ManipulatorRobot is not connected. You need to run `robot.connect()`."
            )

        goal_pos = action

        # Cap goal position when too far away from present position.
        # /!\ Slower fps expected due to reading from the follower.
        if self.config.max_relative_target is not None:
            present_pos = self.arm.sync_read("Present_Position")
            goal_pos = ensure_safe_goal_position(goal_pos, present_pos, self.config.max_relative_target)

        # Send goal position to the arm
        self.arm.sync_write("Goal_Position", goal_pos.astype(np.int32))

        return goal_pos

    def print_logs(self):
        # TODO(aliberts): move robot-specific logs logic here
        pass

    def disconnect(self):
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "ManipulatorRobot is not connected. You need to run `robot.connect()` before disconnecting."
            )

        self.arm.disconnect()
        for cam in self.cameras.values():
            cam.disconnect()
