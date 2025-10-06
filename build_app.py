#!/usr/bin/env python3
"""
WatermarkApp macOS打包脚本
使用PyInstaller将水印应用打包为独立的macOS .app文件
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    # 确保在正确的目录中
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("🚀 开始打包水印应用...")
    
    # 清理之前的构建
    build_dirs = ['build', 'dist']
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            print(f"🧹 清理 {dir_name} 目录...")
            shutil.rmtree(dir_name)
    
    # PyInstaller命令
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=WatermarkApp',
        '--windowed',  # 无控制台窗口
        '--onedir',    # 创建单个文件夹
        '--clean',     # 清理临时文件
        '--noconfirm', # 不确认覆盖
        # 图标文件（如果有的话）
        # '--icon=icon.icns',
        # 额外的数据文件
        '--add-data=watermark_config.json:.',
        # 隐藏导入（确保所有依赖都被包含）
        '--hidden-import=PIL._tkinter_finder',
        '--hidden-import=customtkinter',
        '--hidden-import=tkinter',
        '--hidden-import=PIL',
        '--hidden-import=PIL.Image',
        '--hidden-import=PIL.ImageTk',
        '--hidden-import=PIL.ImageFont',
        '--hidden-import=PIL.ImageDraw',
        '--hidden-import=queue',
        '--hidden-import=threading',
        '--hidden-import=json',
        '--hidden-import=os',
        '--collect-all=customtkinter',
        '--collect-all=PIL',
        # 主脚本
        'src/main.py'
    ]
    
    print("📦 执行PyInstaller打包...")
    print(f"命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ PyInstaller执行成功!")
        
        # 检查输出
        app_path = Path('dist/WatermarkApp')
        if app_path.exists():
            print(f"🎉 应用已成功打包到: {app_path.absolute()}")
            
            # 创建DMG镜像（可选）
            create_dmg = input("是否创建DMG安装包? (y/N): ").lower().strip()
            if create_dmg == 'y':
                create_dmg_image()
            
        else:
            print("❌ 打包失败：找不到输出文件")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller执行失败:")
        print(f"返回码: {e.returncode}")
        print(f"错误输出: {e.stderr}")
        return False
    
    print("\n🎊 打包完成!")
    print(f"📁 应用位置: {Path('dist/WatermarkApp').absolute()}")
    print("💡 提示: 双击运行应用，或将其移动到应用程序文件夹")
    
    return True

def create_dmg_image():
    """创建DMG安装包"""
    try:
        print("📀 创建DMG安装包...")
        
        dmg_name = "WatermarkApp-Installer"
        
        # 创建临时DMG
        cmd_create = [
            'hdiutil', 'create', '-ov', '-volname', 'WatermarkApp',
            '-fs', 'HFS+', '-srcfolder', 'dist', f'{dmg_name}.dmg'
        ]
        
        subprocess.run(cmd_create, check=True)
        print(f"✅ DMG安装包已创建: {dmg_name}.dmg")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 创建DMG失败: {e}")
    except FileNotFoundError:
        print("❌ 创建DMG失败: 需要macOS系统和hdiutil工具")

if __name__ == "__main__":
    main()