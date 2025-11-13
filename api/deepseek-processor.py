from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # 读取请求数据
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            # 处理数据
            processed_data = self.process_deepseek_data(data)
            
            # 返回响应
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(processed_data).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
    
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
