import requests

api_key = "sk-239e9cf2fd5d416eac0ce39492d7619d"
url = "https://ws-ml5w5d25c5b4vqpd.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

payload = {
    "model": "wan2.6-t2i",
    "input": {
        "messages": [
            {
                "role": "user",
                "content": [{"text": "A cute cat sitting on a chair"}]
            }
        ]
    },
    "parameters": {"n": 1, "size": "1024*1024"}
}

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

resp = requests.post(url, headers=headers, json=payload)
print(resp.status_code)
print(resp.json())
