from http.server import BaseHTTPRequestHandler
import json
import sys

class handler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """处理GET请求 - 修复501错误"""
        print(f"=== 收到GET请求: {self.path} ===", file=sys.stderr)
        
        if self.path == '/health' or self.path == '/webhook':
            response = {
                "status": "healthy", 
                "service": "deepseek-processor",
                "message": "服务正常运行中",
                "usage": "请使用POST方法发送数据到/webhook"
            }
            self.send_success_response(response)
        else:
            self.send_error_response(404, {"error": "路径未找到"})
    
    def do_POST(self):
        """处理POST请求"""
        print(f"=== 收到POST请求: {self.path} ===", file=sys.stderr)
        
        if self.path == '/webhook':
            self.handle_webhook()
        else:
            self.send_error_response(404, {"error": "路径未找到"})
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def handle_webhook(self):
        """处理webhook数据"""
        try:
            # 读取请求数据
            content_length = int(self.headers.get('Content-Length', 0))
            print(f"Content-Length: {content_length}", file=sys.stderr)
            
            if content_length == 0:
                self.send_success_response({"error": "请求体为空"})
                return
                
            post_data = self.rfile.read(content_length)
            raw_data = post_data.decode('utf-8')
            print(f"原始请求数据: {raw_data}", file=sys.stderr)
            
            # 解析JSON数据
            data = json.loads(raw_data)
            print(f"解析后的数据: {json.dumps(data, indent=2, ensure_ascii=False)}", file=sys.stderr)
            
            # 处理DeepSeek数据
            processed_data = self.process_deepseek_data(data)
            print(f"处理后的数据: {json.dumps(processed_data, indent=2, ensure_ascii=False)}", file=sys.stderr)
            
            # 返回处理结果
            self.send_success_response(processed_data)
            
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}", file=sys.stderr)
            self.send_error_response(400, {"error": f"JSON解析错误: {str(e)}"})
        except Exception as e:
            print(f"服务器错误: {e}", file=sys.stderr)
            self.send_error_response(500, {"error": f"服务器错误: {str(e)}"})
    
    def process_deepseek_data(self, deepseek_data):
        """处理DeepSeek传输过来的数据"""
        try:
            print("开始处理DeepSeek数据...", file=sys.stderr)
            
            if isinstance(deepseek_data, list) and len(deepseek_data) > 0:
                first_item = deepseek_data[0]
                print(f"第一个数据项: {json.dumps(first_item, ensure_ascii=False)}", file=sys.stderr)
                
                text_content = first_item.get("text", "[]")
                print(f"text字段内容: {text_content}", file=sys.stderr)
                
                # 解析JSON字符串
                news_data = json.loads(text_content)
                print(f"解析text后的数据: {json.dumps(news_data, ensure_ascii=False)}", file=sys.stderr)
                
                # 确保是列表格式
                if isinstance(news_data, list):
                    result = news_data
                else:
                    result = [news_data]
                    
                print(f"最终返回数据条数: {len(result)}", file=sys.stderr)
                return result
            else:
                print("数据格式不符合预期", file=sys.stderr)
                return []
                
        except Exception as e:
            print(f"处理数据时出错: {e}", file=sys.stderr)
            return {"error": f"处理数据时出错: {e}"}
    
    def send_success_response(self, data):
        """发送成功响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        response_json = json.dumps(data, ensure_ascii=False, indent=2)
        print(f"发送响应: {response_json}", file=sys.stderr)
        self.wfile.write(response_json.encode('utf-8'))
    
    def send_error_response(self, code, data):
        """发送错误响应"""
        self.send_response(code)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        response_json = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(response_json.encode('utf-8'))
