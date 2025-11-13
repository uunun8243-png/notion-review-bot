from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """处理所有GET请求"""
        if self.path == '/health':
            self.send_success_response({"status": "healthy", "service": "deepseek-processor"})
        elif self.path == '/webhook':
            self.send_success_response({"message": "请使用POST方法发送数据", "usage": "POST JSON数据到/webhook"})
        else:
            self.send_error_response(404, "页面未找到")
    
    def do_POST(self):
        """处理POST请求"""
        if self.path == '/webhook':
            self.handle_webhook()
        else:
            self.send_error_response(404, "路径未找到")
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_cors_headers()
        self.send_response(200)
        self.end_headers()
    
    def handle_webhook(self):
        """处理webhook数据"""
        try:
            # 读取请求数据
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error_response(400, "请求体为空")
                return
                
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            # 处理DeepSeek数据
            processed_data = self.process_deepseek_data(data)
            
            # 返回成功响应
            self.send_success_response(processed_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"JSON解析错误: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"服务器错误: {str(e)}")
    
    def process_deepseek_data(self, deepseek_data):
        """处理DeepSeek传输过来的数据"""
        try:
            if isinstance(deepseek_data, list) and len(deepseek_data) > 0:
                text_content = deepseek_data[0].get("text", "[]")
                news_data = json.loads(text_content)
                return news_data if isinstance(news_data, list) else [news_data]
            return []
        except Exception as e:
            return {"error": f"处理数据时出错: {e}"}
    
    def send_success_response(self, data):
        """发送成功响应"""
        self.send_response(200)
        self.send_cors_headers()
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        response_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(response_data.encode('utf-8'))
    
    def send_error_response(self, code, message):
        """发送错误响应"""
        self.send_response(code)
        self.send_cors_headers()
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        error_response = {"error": message}
        self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def send_cors_headers(self):
        """设置CORS头"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
