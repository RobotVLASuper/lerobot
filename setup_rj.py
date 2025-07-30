from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
# 1. 清理之前的构建文件

#rm -rf build/ dist/ *.egg-info/
## 2. 编译扩展模块
#python setup_rj.py build_ext --inplace
## 3. 安装项目（开发模式）
#pip install -e ."""

# 编译指定的模块
extensions = [
    # bomb
    Extension(
        "lerobot.utils.rje",
        ["src/lerobot/utils/rje.py"],
        language="c++",
    ),
    # Pi0 Policy
    Extension(
        "lerobot.policies.pi0.modeling_pi0",
        ["src/lerobot/policies/pi0/modeling_pi0.py"],
        language="c++",
    ),
    Extension(
        "lerobot.policies.pi0.configuration_pi0",
        ["src/lerobot/policies/pi0/configuration_pi0.py"],
        language="c++",
    ),
    Extension(
        "lerobot.policies.pi0.paligemma_with_expert",
        ["src/lerobot/policies/pi0/paligemma_with_expert.py"],
        language="c++",
    ),
    
    # Pi0Fast Policy
    Extension(
        "lerobot.policies.pi0fast.modeling_pi0fast",
        ["src/lerobot/policies/pi0fast/modeling_pi0fast.py"],
        language="c++",
    ),
    
    # SmolVLA Policy
    Extension(
        "lerobot.policies.smolvla.modeling_smolvla",
        ["src/lerobot/policies/smolvla/modeling_smolvla.py"],
        language="c++",
    ),
    Extension(
        "lerobot.policies.smolvla.configuration_smolvla",
        ["src/lerobot/policies/smolvla/configuration_smolvla.py"],
        language="c++",
    ),
    Extension(
        "lerobot.policies.smolvla.smolvlm_with_expert",
        ["src/lerobot/policies/smolvla/smolvlm_with_expert.py"],
        language="c++",
    ),
    
    # Basler Camera
    Extension(
        "lerobot.cameras.basler.camera_basler",
        ["src/lerobot/cameras/basler/camera_basler.py"],
        language="c++",
    ),
    Extension(
        "lerobot.cameras.basler.configuration_basler",
        ["src/lerobot/cameras/basler/configuration_basler.py"],
        language="c++",
    ),
    
    # ur5_follower
    Extension(
        "lerobot.robots.ur5_follower.ur5_follower",
        ["src/lerobot/robots/ur5_follower/ur5_follower.py"],
        language="c++",
    ),
    Extension(
        "lerobot.robots.ur5_follower.configuration_ur5_follower",
        ["src/lerobot/robots/ur5_follower/configuration_ur5_follower.py"],
        language="c++",)
]

setup(
    name="lerobot",
    package_dir={"": "src"},
    packages=find_packages("src"),
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
        annotate=False,
    ),
    zip_safe=False,
)
