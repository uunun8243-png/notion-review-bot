import os
import json

# === 项目根目录 ===
project_root = os.path.abspath("your_project")

# === 目录结构 ===
folders = [
    os.path.join(project_root, "api")
]

files = {
    os.path.join(project_root, "api", "deepseek-processor.py"): "# deepseek-processor\n\n# 这里编写你的处理逻辑\n",
    os.path.join(project_root, "vercel.json"): json.dumps({
        "version": 2,
        "builds": [
            {"src": "api/deepseek-processor.py", "use": "@vercel/python"}
        ],
        "routes": [
            {"src": "/api/(.*)", "dest": "api/deepseek-processor.py"}
        ]
    }, indent=4, ensure_ascii=False),
    os.path.join(project_root, "README.md"): "# DeepSeek Processor API\n\n使用 Vercel 部署的 Python API 示例项目。\n"
}

# === 创建文件夹 ===
for folder in folders:
    os.makedirs(folder, exist_ok=True)
    print(f"📁 创建目录: {folder}")

# === 创建文件 ===
for path, content in files.items():
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 创建文件: {path}")
    else:
        print(f"⚠️ 文件已存在: {path}")

print("\n🎉 项目结构创建完成！")
