import subprocess
import winreg
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading

class SoftwareCleaner:
    def __init__(self):
        self.software_to_remove = [
            "Python 3.13.7 Documentation (64-bit)",
            "Python 3.13.7 Test Suite (64-bit)", 
            "Java(TM) SE Development Kit 9.0.1 (64-bit)",
            "Autodesk Material Library 2021",
            "Autodesk Single Sign On Component",
            "Autodesk Genuine Service",
            "Autodesk Material Library Base Resolution Image Library 2021",
            "AutoCAD 2021 Language Pack - Simplified Chinese",
            "ACA & MEP 2021 Object Enabler",
            "Office 16 Click-to-Run Extensibility Component",
            "Intel(R) C++ Redistributables on Intel(R) 64",
            "Care Center Service"
        ]
        
        self.results = []
    
    def uninstall_software(self, software_name):
        """卸载指定软件"""
        try:
            # 方法1: 使用WMIC卸载
            cmd = f'wmic product where "name=\'{software_name}\'" call uninstall /nointeractive'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                return True, f"✓ 成功卸载: {software_name}"
            else:
                # 方法2: 使用MSIEXEC通过产品代码卸载
                product_code = self.get_product_code(software_name)
                if product_code:
                    cmd = f'msiexec /x {product_code} /quiet /norestart'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                    if result.returncode == 0:
                        return True, f"✓ 成功卸载: {software_name}"
                
                return False, f"✗ 无法卸载: {software_name} (可能需要手动卸载)"
                
        except subprocess.TimeoutExpired:
            return False, f"✗ 卸载超时: {software_name}"
        except Exception as e:
            return False, f"✗ 卸载错误: {software_name} - {str(e)}"
    
    def get_product_code(self, software_name):
        """获取软件的产品代码"""
        try:
            # 从注册表查找产品代码
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
                                if name == software_name:
                                    product_code = subkey_name
                                    winreg.CloseKey(subkey)
                                    winreg.CloseKey(key)
                                    return product_code
                            except FileNotFoundError:
                                pass
                            finally:
                                winreg.CloseKey(subkey)
                        except WindowsError:
                            pass
                    winreg.CloseKey(key)
                except WindowsError:
                    pass
        except Exception:
            pass
        
        return None
    
    def run_cleanup(self):
        """运行清理操作"""
        total = len(self.software_to_remove)
        success_count = 0
        
        for i, software in enumerate(self.software_to_remove, 1):
            success, message = self.uninstall_software(software)
            self.results.append(message)
            
            if success:
                success_count += 1
            
            # 更新进度
            if hasattr(self, 'update_progress'):
                self.update_progress(i, total, message)
            
            # 短暂延迟，避免系统过载
            time.sleep(2)
        
        return success_count, total

class CleanupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("C盘立即清理工具")
        self.root.geometry("700x500")
        self.root.resizable(False, False)
        
        self.cleaner = SoftwareCleaner()
        self.setup_ui()
    
    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="C盘立即清理工具", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10))
        
        # 说明文字
        desc_text = "本工具将自动卸载以下可安全删除的软件组件，预计可释放约1GB空间:"
        desc_label = ttk.Label(main_frame, text=desc_text, wraplength=650)
        desc_label.pack(pady=(0, 15))
        
        # 软件列表框架
        list_frame = ttk.LabelFrame(main_frame, text="即将清理的软件", padding="10")
        list_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 软件列表
        software_text = "\n".join([f"• {software}" for software in self.cleaner.software_to_remove])
        software_label = ttk.Label(list_frame, text=software_text, justify=tk.LEFT)
        software_label.pack(anchor=tk.W)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.clean_btn = ttk.Button(button_frame, text="开始清理", command=self.start_cleaning)
        self.clean_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 15))
        
        # 进度标签
        self.progress_label = ttk.Label(main_frame, text="准备就绪")
        self.progress_label.pack(pady=(0, 15))
        
        # 结果框架
        result_frame = ttk.LabelFrame(main_frame, text="清理结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=12)
        self.result_text.pack(fill=tk.BOTH, expand=True)
    
    def start_cleaning(self):
        """开始清理"""
        if not messagebox.askyesno("确认清理", 
                                  "确定要执行清理操作吗？\n\n这将卸载选中的软件组件，操作不可逆。\n建议先关闭其他正在运行的应用程序。"):
            return
        
        self.clean_btn.config(state='disabled')
        self.cleaner.update_progress = self.update_progress
        
        # 在新线程中运行清理
        thread = threading.Thread(target=self.run_cleanup)
        thread.daemon = True
        thread.start()
    
    def update_progress(self, current, total, message):
        """更新进度"""
        self.root.after(0, self._update_progress, current, total, message)
    
    def _update_progress(self, current, total, message):
        """在主线程中更新进度"""
        progress_percent = (current / total) * 100
        self.progress['value'] = progress_percent
        self.progress_label.config(text=f"进度: {current}/{total} - {message}")
        self.result_text.insert(tk.END, f"{message}\n")
        self.result_text.see(tk.END)
        self.result_text.update()
    
    def run_cleanup(self):
        """运行清理操作"""
        try:
            success_count, total = self.cleaner.run_cleanup()
            
            # 显示最终结果
            self.root.after(0, self.show_final_result, success_count, total)
            
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
        finally:
            self.root.after(0, self.cleaning_complete)
    
    def show_final_result(self, success_count, total):
        """显示最终结果"""
        result_text = f"\n清理完成!\n成功卸载: {success_count}/{total} 个软件组件\n"
        result_text += f"预计释放空间: 约 1GB\n\n"
        
        if success_count < total:
            result_text += "部分软件需要手动卸载，请通过控制面板完成。\n"
        
        self.result_text.insert(tk.END, result_text)
        self.result_text.see(tk.END)
    
    def show_error(self, error_msg):
        """显示错误信息"""
        messagebox.showerror("错误", f"清理过程中出现错误:\n{error_msg}")
    
    def cleaning_complete(self):
        """清理完成"""
        self.clean_btn.config(state='normal')
        self.progress_label.config(text="清理完成")

def main():
    root = tk.Tk()
    app = CleanupGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()