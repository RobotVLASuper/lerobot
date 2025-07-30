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

from dataclasses import dataclass

from ..configs import CameraConfig, ColorMode


@CameraConfig.register_subclass("basler")
@dataclass
class BaslerCameraConfig(CameraConfig):
    camera_idx: int = 0
    color_mode: ColorMode = ColorMode.RGB
    warmup_s: int = 1

    def __post_init__(self):
        # FIXME: here should be a config parameter
        self.height = 400  # 1200
        self.width = 640  # 1920
        self.channels = 3
        self.fps = 20
