import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"

def ask_ai(question):

    payload = {
        "model": "qwen3:8b",
        "messages": [
            {
                "role": "system",
                "content": """
                You are an AI assistant for a college management system.
                You understand Hindi and English.
                Give clear and helpful answers.
                """
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=180) as response:

        result = json.loads(response.read().decode("utf-8"))

        return result["message"]["content"]


if __name__ == "__main__":

    question = input("You: ")

    answer = ask_ai(question)

    print("\nAI:", answer)