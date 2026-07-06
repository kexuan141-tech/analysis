import json
import os

import requests

from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("XUNFEI_APP_ID")
API_KEY = os.getenv("XUNFEI_API_KEY")
API_SECRET = os.getenv("XUNFEI_API_SECRET")
API_PASSWORD = os.getenv("XUNFEI_API_PASSWORD")

def test_text_only():
    results = []
    results.append("=" * 60)
    results.append("测试1: 纯文本请求")
    results.append("=" * 60)
    
    url = "https://spark-api-open.xf-yun.com/x2/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_PASSWORD or (API_SECRET + ':' + API_KEY)}",
        "Content-Type": "application/json"
    }
    
    test_model_names = ["spark-x", "Spark-X2", "x2", "4.0Ultra", "spark-x2", "SparkX2"]
    
    for model_name in test_model_names:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "你好，请问你是谁？"}],
            "temperature": 0.7,
            "max_tokens": 512
        }
        
        results.append(f"\n尝试模型: {model_name}")
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False)
            data = response.json()
            
            if response.status_code == 200 and not data.get("error"):
                content = data["choices"][0]["message"]["content"]
                results.append(f"✅ 成功! 响应: {content[:100]}")
                return model_name, data, "\n".join(results)
            else:
                error_msg = data.get("error", {}).get("message", str(data))
                results.append(f"❌ 失败: HTTP {response.status_code}, 错误: {error_msg[:200]}")
        except Exception as e:
            results.append(f"❌ 异常: {str(e)[:100]}")
    
    return None, None, "\n".join(results)

def main():
    results = []
    results.append("\n" + "=" * 60)
    results.append("讯飞Spark X2 API 调试测试")
    results.append("=" * 60)
    
    model_name, response_data, test_results = test_text_only()
    results.append(test_results)
    
    if model_name:
        results.append(f"\n🎉 找到正确的模型名称: {model_name}")
        results.append(f"完整响应: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
    else:
        results.append("\n❌ 所有模型名称都测试失败，请检查API密钥或联系讯飞客服")
    
    output = "\n".join(results)
    
    with open("f:/三下乡/情绪手账/test_result.txt", "w", encoding="utf-8") as f:
        f.write(output)
    
    print(output)

if __name__ == "__main__":
    main()
