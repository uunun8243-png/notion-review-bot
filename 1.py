# -*- coding: utf-8 -*-
"""
扫描 F 盘并删除 .venv 虚拟环境（不动 C 盘）
"""
import os
import shutil

# 指定扫描目录（F 盘）
scan_path = r"F:\"

found = []

# 扫描文件夹
for root, dirs, files in os.walk(scan_path):
    if ".venv" in dirs:
        venv_path = os.path.join(root, ".venv")
        found.append(venv_path)

if not found:
    print("❌ 未找到任何 .venv 文件夹")
else:
    print("✅ 找到以下 .venv 文件夹：")
    for f in found:
        print(f)

    # 确认删除
    confirm = input("是否删除以上所有 .venv 文件夹？(y/n)：")
    if confirm.lower() == "y":
        for f in found:
            try:
                shutil.rmtree(f)
                print(f"✅ 已删除 {f}")
            except Exception as e:
                print(f"❌ 删除失败 {f}: {e}")
    else:
        print("❌ 操作已取消")
