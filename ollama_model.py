import requests

def test_qwen(prompt):
    url = "http://192.168.1.22:11434/api/generate"  # your Mac Mini IP

    data = {
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    result = test_qwen("Explain AI agents in simple terms")
    print("Response:\n", result)