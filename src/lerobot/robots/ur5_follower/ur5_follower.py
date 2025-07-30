#!/usr/bin/env python
from lerobot.utils.rje import rjhaha

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

import logging
import time
from functools import cached_property
from typing import Any, List

import numpy as np
import rtde_control
import rtde_receive
from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from ..utils import ensure_safe_goal_position
from .config_ur5_follower import UR5FollowerConfig

logger = logging.getLogger(__name__)


class UR5Follower(Robot):
    config_class = UR5FollowerConfig
    name = "ur5_follower"

    def __init__(self, config: UR5FollowerConfig):
        super().__init__(config)
        self.config = config
        self.cameras = make_cameras_from_configs(config.cameras)
        self.robot = rtde_control.RTDEControlInterface(config.robot_ip)
        self.r_inter = rtde_receive.RTDEReceiveInterface(config.robot_ip)
        self.with_gripper = config.with_gripper
        self.motors_names = ("q0", "q1", "q2", "q3", "q4", "q5")
        if self.with_gripper:
            from gello.robots.robotiq_gripper import RobotiqGripper

            self.gripper = RobotiqGripper()
            self.gripper.connect(hostname=config.robot_ip, port=config.gripper_port)
            self.motors_names = ("q0", "q1", "q2", "q3", "q4", "q5", "gripper")

        self._first_move = True

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {motor: float for motor in self.motors_names}

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        if self.with_gripper:
            return (
                self.robot.isConnected()
                and self.gripper.is_active()
                and self.r_inter.isConnected()
                and all(cam.is_connected for cam in self.cameras.values())
            )

        else:
            return (
                self.robot.isConnected()
                and self.r_inter.isConnected()
                and all(cam.is_connected for cam in self.cameras.values())
            )

    def connect(self, calibrate: bool = True) -> None:
        """
        We assume that at connection time, arm is in a rest position,
        and torque can be safely disabled to run calibration.
        """
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")
        self._first_move = True

        if not self.robot.isConnected():
            self.robot.reconnect()
        if not self.r_inter.isConnected():
            self.r_inter.reconnect()
        if self.with_gripper:
            self.gripper.connect(hostname=self.config.robot_ip, port=self.config.gripper_port)
            self.gripper.activate(auto_calibrate=True)
        # TODO: show move to rest position
        if not self.is_calibrated and calibrate:
            self.calibrate()

        for cam in self.cameras.values():
            cam.connect()

        self.configure()
        logger.info(f"{self} connected.")

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        self.robot.endFreedriveMode()
        self.velocity = 0.5  # default velocity 1.05 in moveJ
        self.acceleration = 0.5  # default acceleration 1.4  in moveJ
        self.dt = 1.0 / 500  # 2ms
        self.lookahead_time = 0.2
        self.gain = 100
        if self.with_gripper:
            self.gripper_speed = 255  # default gripper speed
            self.gripper_force = 100  # default gripper force

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # Read arm position
        start = time.perf_counter()
        joint = self.get_joint_state()
        obs_dict = {k: v for k, v in zip(self.motors_names, joint)}
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read state: {dt_ms:.1f}ms")

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.read()
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Command arm to move to a target joint configuration.

        The relative action magnitude may be clipped depending on the configuration parameter
        `max_relative_target`. In this case, the action sent differs from original action.
        Thus, this function always returns the action actually sent.

        Raises:
            RobotDeviceNotConnectedError: if robot is not connected.

        Returns:
            the action sent to the motors, potentially clipped.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # goal_pos = {key.removesuffix(".pos"): val for key, val in action.items() if key.endswith(".pos")}
        goal_pos = action

        # Cap goal position when too far away from present position.
        # /!\ Slower fps expected due to reading from the follower.
        if self.config.max_relative_target is not None:
            present_pos = self.get_observation()
            goal_present_pos = {
                key: (g_pos, present_pos[key]) for key, g_pos in goal_pos.items() if key != "gripper"
            }
            goal_pos = ensure_safe_goal_position(goal_present_pos, self.config.max_relative_target)
            if self.with_gripper:
                # Ensure gripper position is within bounds
                if "gripper" in action:
                    goal_pos["gripper"] = np.clip(action["gripper"], 0.0, 1.0)
                else:
                    raise ValueError("Gripper position must be provided when using a gripper.")

        # Send goal position to the arm
        pos_np = np.array([goal_pos[x] for x in self.motors_names], dtype=np.float32)
        self.command_joint_state(pos_np)

        return goal_pos

    def init_pos_protect(self, joint_state: np.ndarray, thr: float = 0.2):
        robot_joints = self.r_inter.getActualQ()
        if self.with_gripper:
            gripper_pos = self.gripper.get_current_position()
            assert 0 <= gripper_pos <= 255, "Gripper position must be between 0 and 255"
            gripper_pos = gripper_pos / 255.0
            current_joint_state = np.append(robot_joints, gripper_pos)
        else:
            current_joint_state = robot_joints
        if np.max(np.abs(current_joint_state - joint_state)) > thr:
            print(f"goal_pos: {joint_state}")
            print(f"current joints: {current_joint_state}")
            raise ValueError(
                "initial condition diverges, make sure the leader position looks like the follower position."
            )

    def command_joint_state(self, joint_state: np.ndarray) -> None:
        """Command the leader robot to a given state.

        Args:
            joint_state (np.ndarray): The state to command the leader robot to.
        """
        if self._first_move:
            self.init_pos_protect(joint_state,thr=self.config.init_pos_thr)
            self._first_move = False

        robot_joints = joint_state[:6]
        t_start = self.robot.initPeriod()
        self.robot.servoJ(
            robot_joints, self.velocity, self.acceleration, self.dt, self.lookahead_time, self.gain
        )
        if self.with_gripper:
            gripper_pos = joint_state[-1] * 255
            self.gripper.move(gripper_pos, self.gripper_speed,self.gripper_force)
        self.robot.waitPeriod(t_start)

    def disconnect(self):
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        self.robot.disconnect()
        self.r_inter.disconnect()
        self.gripper.disconnect()
        for cam in self.cameras.values():
            cam.disconnect()

        self._first_move = True

        logger.info(f"{self} disconnected.")

    def get_joint_state(self) -> List[float]:
        """Get the current state of the follower robot.

        Returns:
            T: The current state of the follower robot.
        """
        robot_joints = self.r_inter.getActualQ()
        if self.with_gripper:
            gripper_pos = self.gripper.get_current_position()
            assert 0 <= gripper_pos <= 255, "Gripper position must be between 0 and 255"
            gripper_pos = gripper_pos / 255.0
            pos = np.append(robot_joints, gripper_pos)
        else:
            pos = robot_joints
        return pos.tolist()
