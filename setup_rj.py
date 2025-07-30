import os
import glob
from pathlib import Path
from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
import numpy as np
# 1. 清理之前的构建文件
#rm -rf build/ dist/ *.egg-info/
## 2. 编译扩展模块
#python setup_rj.py build_ext --inplace
## 3. 安装项目（开发模式）
#pip install -e ."""


def scan_policy_extensions():
    """
    自动扫描 src/lerobot/policies 目录中的所有 policy 模块，
    并生成对应的 Extension 列表
    """
    extensions = []
    
    # 要排除的文件（非 policy 的框架文件）
    exclude_files = {
        "__init__.py",
        "factory.py", 
        "pretrained.py",
        "normalize.py",
        "utils.py"
    }
    
    # 扫描 policies 目录
    policies_dir = Path("src/lerobot/policies")
    
    if not policies_dir.exists():
        print(f"Warning: {policies_dir} 不存在")
        return extensions
    
    # 遍历所有 policy 子目录
    for policy_dir in policies_dir.iterdir():
        if not policy_dir.is_dir() or policy_dir.name.startswith('.'):
            continue
            
        policy_name = policy_dir.name
        print(f"扫描 policy: {policy_name}")
        
        # 扫描该 policy 目录下的所有 .py 文件
        for py_file in policy_dir.glob("*.py"):
            if py_file.name in exclude_files:
                print(f"  跳过框架文件: {py_file.name}")
                continue
                
            # 构建模块名
            module_name = f"lerobot.policies.{policy_name}.{py_file.stem}"
            file_path = str(py_file)
            
            print(f"  添加模块: {module_name}")
            
            # 根据文件类型设置不同的编译选项
            if "modeling" in py_file.name or "expert" in py_file.name or "extractor" in py_file.name:
                # 复杂的建模文件，需要更多优化
                extension = Extension(
                    module_name,
                    [file_path],
                    language="c++",
                    include_dirs=[np.get_include()],
                    extra_compile_args=["-O2", "-fPIC", "-std=c++11"],
                    extra_link_args=["-shared"],
                    define_macros=[("CYTHON_WITHOUT_ASSERTIONS", "1")],
                )
            else:
                # 配置文件等，使用基本编译选项
                extension = Extension(
                    module_name,
                    [file_path], 
                    language="c++",
                )
            
            extensions.append(extension)
    
    return extensions

def scan_additional_extensions():
    """
    扫描其他需要编译的模块（非 policy）
    """
    extensions = []
    
    # 手动指定的其他模块
    additional_modules = [
        # Utilities
        {
            "module": "lerobot.utils.rje",
            "file": "src/lerobot/utils/rje.py",
            "type": "basic"
        },
        # Basler Camera
        {
            "module": "lerobot.cameras.basler.camera_basler", 
            "file": "src/lerobot/cameras/basler/camera_basler.py",
            "type": "basic"
        },
        {
            "module": "lerobot.cameras.basler.configuration_basler",
            "file": "src/lerobot/cameras/basler/configuration_basler.py", 
            "type": "basic"
        },
        # UR5 Follower
        {
            "module": "lerobot.robots.ur5_follower.ur5_follower",
            "file": "src/lerobot/robots/ur5_follower/ur5_follower.py",
            "type": "basic"
        },
        {
            "module": "lerobot.robots.ur5_follower.config_ur5_follower",
            "file": "src/lerobot/robots/ur5_follower/config_ur5_follower.py",
            "type": "basic"
        },
    ]
    
    for module_info in additional_modules:
        if os.path.exists(module_info["file"]):
            if module_info["type"] == "optimized":
                extension = Extension(
                    module_info["module"],
                    [module_info["file"]],
                    language="c++",
                    include_dirs=[np.get_include()],
                    extra_compile_args=["-O2", "-fPIC", "-std=c++11"],
                    extra_link_args=["-shared"],
                    define_macros=[("CYTHON_WITHOUT_ASSERTIONS", "1")],
                )
            else:  # basic
                extension = Extension(
                    module_info["module"],
                    [module_info["file"]],
                    language="c++",
                )
            extensions.append(extension)
            print(f"添加额外模块: {module_info['module']}")
        else:
            print(f"Warning: 文件不存在 {module_info['file']}")
    
    return extensions

def generate_all_extensions():
    """
    生成所有需要编译的 extensions
    """
    print("开始扫描 policy 模块...")
    policy_extensions = scan_policy_extensions()
    
    print("\n开始扫描其他模块...")
    additional_extensions = scan_additional_extensions()
    
    all_extensions = policy_extensions + additional_extensions
    
    print(f"\n总共找到 {len(all_extensions)} 个模块需要编译:")
    for ext in all_extensions:
        print(f"  - {ext.name}")
    
    return all_extensions

# 使用自动生成的 extensions
extensions = generate_all_extensions()

def cleanup_files():
    """清理原始 py 文件和生成的 cpp 文件"""
    # 收集所有要编译的 py 文件路径
    py_files = []
    for ext in extensions:
        py_files.extend(ext.sources)
    
    # 删除原始 py 文件
    for py_file in py_files:
        if os.path.exists(py_file):
            print(f"删除原始文件: {py_file}")
            os.remove(py_file)
    
    # 删除生成的 cpp 文件
    cpp_patterns = [
        "src/**/*.cpp",
        "src/**/*.c",
        "build/**/*.cpp",
        "build/**/*.c"
    ]
    
    for pattern in cpp_patterns:
        cpp_files = glob.glob(pattern, recursive=True)
        for cpp_file in cpp_files:
            if os.path.exists(cpp_file):
                print(f"删除 cpp 文件: {cpp_file}")
                os.remove(cpp_file)

class CustomBuildExt:
    """自定义构建扩展，在编译后清理文件"""
    def run(self):
        # 先执行正常的编译
        from setuptools.command.build_ext import build_ext
        build_ext_cmd = build_ext(self.distribution)
        build_ext_cmd.inplace = True
        build_ext_cmd.run()
        
        # 编译完成后清理文件
        cleanup_files()

if __name__ == "__main__":
    import sys
    
    # 检查是否是 build_ext --inplace 命令
    if len(sys.argv) >= 3 and sys.argv[1] == "build_ext" and "--inplace" in sys.argv:
        # 先正常编译
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
                    "nonecheck": False,
                    "cdivision": True,
                    "embedsignature": True,
                    "always_allow_keywords": True,
                },
                annotate=False,
                build_dir="build",
            ),
            zip_safe=False,
        )
        
        # 编译完成后清理文件
        print("\n开始清理文件...")
        cleanup_files()
        print("清理完成！")
    else:
        # 正常的 setup
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
                    "nonecheck": False,
                    "cdivision": True,
                    "embedsignature": True,
                    "always_allow_keywords": True,
                },
                annotate=False,
                build_dir="build",
            ),
            zip_safe=False,
        )
