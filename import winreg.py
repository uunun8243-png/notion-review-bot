import winreg
import subprocess
import os

def get_installed_software():
    """获取已安装的软件列表"""
    software_list = []
    
    # 检查注册表中的安装程序
    registry_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    ]
    
    for path in registry_paths:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    
                    try:
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        try:
                            install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                        except FileNotFoundError:
                            install_location = "Unknown"
                        
                        try:
                            size = winreg.QueryValueEx(subkey, "EstimatedSize")[0]
                        except FileNotFoundError:
                            size = 0
                            
                        software_list.append({
                            'name': name,
                            'location': install_location,
                            'size_mb': round(size/1024) if size else 0
                        })
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(subkey)
                except WindowsError:
                    pass
            winreg.CloseKey(key)
        except WindowsError:
            pass
    
    return software_list

# 获取软件列表
software = get_installed_software()
print("已安装的软件:")
for app in sorted(software, key=lambda x: x['size_mb'], reverse=True)[:20]:  # 显示前20个最大的
    if app['size_mb'] > 0:
        print(f"{app['name']} - {app['size_mb']} MB")