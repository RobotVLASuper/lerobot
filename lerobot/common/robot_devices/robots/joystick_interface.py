import time
import multiprocessing
import numpy as np
import inputs
from typing import Tuple
from dataclasses import dataclass
from enum import Enum


class ControllerType(Enum):
    PS5 = "ps5"
    XBOX = "xbox"

@dataclass
class ControllerConfig:
    resolution: dict
    scale: dict

class JoystickInterface:
    """
    This class provides an interface to the Joystick/Gamepad.
    It continuously reads the joystick state and provides
    a "get_action" method to get the latest action and button state.
    """

    CONTROLLER_CONFIGS = {
        ControllerType.PS5: ControllerConfig(
            # PS5 controller joystick values have 8 bit resolution [0, 255]
            resolution={
                'ABS_X': 2**8,
                'ABS_Y': 2**8,
                'ABS_RX': 2**8,
                'ABS_RY': 2**8,
                'ABS_Z': 2**8,
                'ABS_RZ': 2**8,
                'ABS_HAT0X': 1.0,
            },
            scale={
                'ABS_X': 0.4,
                'ABS_Y': 0.4,
                'ABS_RX': 0.5,
                'ABS_RY': 0.5,
                'ABS_Z': 0.8,
                'ABS_RZ': 1.2,
                'ABS_HAT0X': 0.5,
            }
        ),
        ControllerType.XBOX: ControllerConfig(
            # XBOX controller joystick values have 16 bit resolution [0, 65535]
            resolution={
                'ABS_X': 2**16,
                'ABS_Y': 2**16,
                'ABS_RX': 2**16,
                'ABS_RY': 2**16,
                'ABS_Z': 2**8,
                'ABS_RZ': 2**8,
                'ABS_HAT0X': 1.0,
            },
            scale={
                'ABS_X': -0.01,
                'ABS_Y': -0.005,
                'ABS_RX': 0.015,
                'ABS_RY': 0.015,
                'ABS_Z': 0.0025,
                'ABS_RZ': 0.0025,
                'ABS_HAT0X': 0.03,
            }
        ),
    }

    def __init__(self, controller_type=ControllerType.XBOX):
        self.controller_type = controller_type
        self.controller_config = self.CONTROLLER_CONFIGS[controller_type]

        # Manager to handle shared state between processes
        self.manager = multiprocessing.Manager()
        self.latest_data = self.manager.dict()
        self.latest_data["action"] = [0.0] * 6
        self.latest_data["buttons"] = [False, False, False, False, False, False]

        # Start a process to continuously read Joystick state
        self._process = multiprocessing.Process(target=self._read_joystick)
        self._process.daemon = True
        self._process.start()


    def _read_joystick(self):
        """Add a try-except to prevent thread crashes"""
        action = [0.0] * 6
        buttons = [False, False, False, False, False, False]
        
        while True:
            try:
                # Get fresh events
                events = inputs.get_gamepad()
          
                # Process events
                for event in events:
                    if event.code in self.controller_config.resolution:
                        # Calculate relative changes based on the axis
                        # Normalize the joystick input values to range [-1, 1] expected by the environment
                        resolution = self.controller_config.resolution[event.code]
                        if self.controller_type == ControllerType.PS5:
                            normalized_value = (event.state - (resolution / 2)) / (resolution / 2)
                        else:
                            normalized_value = event.state / (resolution / 2)
                        scaled_value = normalized_value * self.controller_config.scale[event.code]

                        if event.code == 'ABS_Y':
                            action[0] = scaled_value
                        elif event.code == 'ABS_X':
                            action[1] = scaled_value
                        elif event.code == 'ABS_RZ':
                            action[2] = scaled_value
                        elif event.code == 'ABS_Z':
                            # Flip sign so this will go in the down direction
                            action[2] = -scaled_value
                        elif event.code == 'ABS_RX':
                            action[3] = scaled_value
                        elif event.code == 'ABS_RY':
                            action[4] = scaled_value
                        elif event.code == 'ABS_HAT0X':
                            action[5] = scaled_value
                        
                    # Handle button events
                    elif event.code == 'BTN_TL':
                        buttons[0] = bool(event.state)
                    elif event.code == 'BTN_TR':
                        buttons[1] = bool(event.state)
                    # Go back to home, B button on xbox controller
                    elif event.code == 'BTN_EAST': 
                        buttons[2] = bool(event.state)
                     # Indicate recording is starting, X button on xbox controller
                    elif event.code == 'BTN_NORTH':
                        buttons[3] = bool(event.state)
                    # Start intervention, A button on xbox controller
                    elif event.code == 'BTN_SOUTH':
                        buttons[4] = bool(event.state)
                    # E-Stop, Y button on xbox controller
                    elif event.code == 'BTN_WEST':
                        buttons[5] = bool(event.state)

                # Update the shared state
                self.latest_data["action"] = action
                self.latest_data["buttons"] = buttons
                
            except inputs.UnpluggedError:
                print("No controller found. Retrying...")
                time.sleep(1)

    def get_action(self):
        """Returns the latest action and button state from the Joystick."""
        action = self.latest_data["action"]
        buttons = self.latest_data["buttons"]
        return np.array(action), buttons
    
    def close(self):
        """Close the joystick interface and cleanup resources."""
        try:
            if hasattr(self, '_process') and self._process is not None:
                import signal
                self._process.terminate()
                self._process.join()
                self._process = None
        except (ImportError, AttributeError):
            # Fallback if signal module is not available
            if hasattr(self, '_process') and self._process is not None:
                self._process.kill()
                self._process.join()
                self._process = None


class JoystickIntervention():
    def __init__(self, controller_type=ControllerType.XBOX, gripper_enabled=True):
        self.gripper_enabled = gripper_enabled
        self.expert = JoystickInterface(controller_type=controller_type)
        self.left, self.right, self.home, self.intervention_start, self.success, self.estop = False, False, False, False, False, False

    def action(self) -> np.ndarray:
        """
        Output:
        - action: joystick action if nonezero; else, policy action
        """
        deadzone = 0.003

        expert_a, buttons = self.expert.get_action()
        self.left, self.right, self.home, self.intervention_start, self.success, self.estop = tuple(buttons)
        # import logging
        # logging.info(f"success on joystick: {self.success}")

        for i, a in enumerate(expert_a):
            if abs(a) <= deadzone:
                expert_a[i] = 0.0
        if abs(expert_a[0]) >= 0.003 and expert_a[1] >= 0.003 and expert_a[1] <= 0.005:
            expert_a[1] = 0.0
        expert_a[3:6] /= 2

        if self.gripper_enabled:
            if self.left: # close gripper
                gripper_action = [0.0]
            elif self.right: # open gripper
                gripper_action = [0.08]
            else:
                gripper_action = [0.0]
            expert_a = np.concatenate((expert_a, gripper_action), axis=0)
        
        return expert_a

    def get_intervention_start(self) -> bool:
        _, buttons = self.expert.get_action()
        _, _, _, self.intervention_start, self.success, self.estop = tuple(buttons)
        return self.intervention_start, self.success, self.estop
    
    def close(self):
        self.expert.close()