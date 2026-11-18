import json
import urllib.request
import urllib.error

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "qwen3:8b"


def generate_response(messages):

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))

            return {
                "success": True,
                "reply": result["message"]["content"]
            }

    except urllib.error.URLError as error:
        return {
            "success": False,
            "error": f"Ollama connection failed: {error}"
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }