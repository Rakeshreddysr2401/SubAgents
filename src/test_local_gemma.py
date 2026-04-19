from openai import OpenAI
import base64
import os


def encode_image(path):
    """Convert local image to base64"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def run_text_query(client, enable_thinking=False):
    """Simple text test"""
    response = client.chat.completions.create(
        model="gemma",
        messages=[
            {"role": "user", "content": "Explain robotics in simple terms"}
        ],
        max_tokens=150,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
    )

    print("\n=== TEXT RESPONSE ===")
    print(response.choices[0].message.content)


def run_image_query(client, image_path, enable_thinking=False):
    """Image + text test"""
    img_base64 = encode_image(image_path)

    response = client.chat.completions.create(
        model="gemma",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What do you see in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=200,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
    )

    print("\n=== IMAGE RESPONSE ===")
    print(response.choices[0].message.content)


def main():
    # 🔥 Change this if using Unsloth instead of manual server
    BASE_URL = "http://localhost:8080/v1"
    # BASE_URL = "http://127.0.0.1:8888/v1"  # <-- if using Unsloth

    client = OpenAI(
        base_url=BASE_URL,
        api_key="not-needed"
    )

    print("🚀 Testing Gemma E2B Local Model")

    # ---- TEXT TEST ----
    run_text_query(client, enable_thinking=False)
    run_text_query(client, enable_thinking=True)

    # ---- IMAGE TEST ----
    image_path = "test.jpg"  # 👈 put any image in same folder

    if os.path.exists(image_path):
        run_image_query(client, image_path, enable_thinking=False)
        run_image_query(client, image_path, enable_thinking=True)
    else:
        print("\n⚠️ No test.jpg found. Skipping image test.")


if __name__ == "__main__":
    main()