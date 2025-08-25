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

import logging
import time
from functools import cached_property
from typing import Any, List, Optional

import numpy as np
import rtde_control
import rtde_receive
from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from ..utils import ensure_safe_goal_position
from .config_ur5_follower import UR5FollowerConfig

import lerobot.debug_tools as D

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
        self._calibrated = False

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

        self.configure()
        # TODO: show move to rest position
        if not self.is_calibrated and calibrate:
            self.calibrate()
        print('self.cameras is ',self.cameras)
        for cam_key, cam in self.cameras.items():

            if '1_right'==cam_key:
                print('1_right is ',cam)
                from lerobot.cameras.configs import ColorMode
                from lerobot.cameras.realsense.camera_realsense import RealSenseCamera
                from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
                rs_config = RealSenseCameraConfig(
                serial_number_or_name='f1480368',
                color_mode=ColorMode.RGB,
            )
                cam = RealSenseCamera(rs_config)
            
            elif '2_bottom'==cam_key:
                print('2_bottom is ',cam)
                from lerobot.cameras.configs import ColorMode
                from lerobot.cameras.realsense.camera_realsense import RealSenseCamera
                from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
                rs_config = RealSenseCameraConfig(
                serial_number_or_name='f1420223',
                color_mode=ColorMode.RGB,
            )
                cam = RealSenseCamera(rs_config)
            cam.connect()
            self.cameras[cam_key] = cam

        logger.info(f"{self} connected.")

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def calibrate(self) -> None:
        if self.config.init_pos:
            move_p_tmp= self.move_params.copy()
            move_p_tmp["move_mode"] = "moveit"  # Use moveit mode for calibration
            move_p_tmp["velocity"] = 0.2  # Set a slower velocity for calibration
            move_p_tmp["acceleration"] = 0.2
            self.command_joint_state(np.array(self.config.init_pos, dtype=np.float64),**move_p_tmp)
            self._calibrated = True
            logger.info(f"{self} calibrated with initial position: {self.config.init_pos}")
        else:
            logger.warning(f"{self} is not calibrated, no initial position provided.")

    def configure(self) -> None:
        self.robot.endFreedriveMode()
        self.move_params = {
            "move_mode": self.config.move_mode,  # Options: "servo", "moveit"
            "velocity": 0.2,  # default velocity 1.05 in moveJ
            "acceleration": 0.2,  # default acceleration 1.4 in moveJ
            "dt": 1.0 / 500,  # 2ms
            "lookahead_time": 0.1,
            "gain": 100,
        }
        if self.with_gripper:
            self.move_params.update(
                {
                    "gripper_speed": 255,  # default gripper speed
                    "gripper_force": 200,  # default gripper force
                }
            )

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
            obs_dict[cam_key] = cam.async_read()
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
        with D.timeblock("=get safe goal position"):
            if self.config.max_relative_target is not None:
                present_pos = self.get_joint_state()
                present_pos = {k: v for k, v in zip(self.motors_names, present_pos)}
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
        self.command_joint_state(pos_np,**self.move_params)

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

    def command_joint_state(
        self,
        joint_state: np.ndarray,
        move_mode: str = "servo",
        velocity: Optional[float] = None,
        acceleration: Optional[float] = None,
        dt: Optional[float] = None,
        lookahead_time: Optional[float] = None,
        gain: Optional[int] = None,
        gripper_speed: Optional[int] = None,
        gripper_force: Optional[int] = None,
    ) -> None:
        """Command the leader robot to a given state.

        Args:
            joint_state (np.ndarray): The state to command the leader robot to.
        """
        if self._first_move:
            self.init_pos_protect(joint_state, thr=self.config.init_pos_thr)
            self._first_move = False

        with D.timeblock("=robot move:"):
            robot_joints = joint_state[:6]
            t_start = self.robot.initPeriod()

            # 使用传入参数或默认参数
            velocity = velocity if velocity is not None else self.move_params["velocity"]
            acceleration = acceleration if acceleration is not None else self.move_params["acceleration"]
            dt = dt if dt is not None else self.move_params["dt"]
            lookahead_time = (
                lookahead_time if lookahead_time is not None else self.move_params["lookahead_time"]
            )
            gain = gain if gain is not None else self.move_params["gain"]

            if move_mode == "moveit":
                self.robot.moveJ(robot_joints, velocity, acceleration)
            elif move_mode == "servo":
                self.robot.servoJ(robot_joints, velocity, acceleration, dt, lookahead_time, gain)
            else:
                raise ValueError(f"Unknown move model: {move_mode}. Use 'servo' or 'moveit'.")
            if self.with_gripper:
                gripper_pos = joint_state[-1] * 255
                gripper_speed = gripper_speed if gripper_speed is not None else self.move_params["speed"]
                gripper_force = gripper_force if gripper_force is not None else self.move_params["force"]
                self.gripper.move(gripper_pos, gripper_speed, gripper_force)
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
        self._calibrated = False

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
