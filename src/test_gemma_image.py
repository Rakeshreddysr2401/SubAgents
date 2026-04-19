from openai import OpenAI
import base64
import os


def encode_image(path):
    """Convert local image to base64"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def extract_text(response):
    """Safely extract response text"""
    choice = response.choices[0]

    if choice.message.content:
        return choice.message.content

    if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
        return str(choice.message.tool_calls)

    return str(response)


def run_image_query(client, image_path, query, enable_thinking=False):
    """Run image + text query"""

    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return

    print(f"\n📸 Using image: {image_path}")
    print(f"🧠 Thinking: {enable_thinking}")

    img_base64 = encode_image(image_path)

    response = client.chat.completions.create(
        model="gemma",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=300,
        temperature=0.7,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
    )

    print("\n=== RESPONSE ===")
    print(extract_text(response))


def main():
    # 🔥 Change if using Unsloth
    BASE_URL = "http://localhost:8080/v1"
    # BASE_URL = "http://127.0.0.1:8888/v1"

    client = OpenAI(
        base_url=BASE_URL,
        api_key="not-needed"
    )

    print("🚀 Testing Image + Query with Gemma")

    # ✅ Your image path (fixed spaces issue automatically handled)
    image_path = "/Users/rakeshreddy/PycharmProjects/SubAgents/src/chotesh photo.jpg"

    # 🔹 Try different queries
    queries = [
        "What do you see in this image?",
        "Describe the person and surroundings",
        "Is there anything important or unusual?",
        "If a robot sees this, what should it do?"
    ]

    # Run tests
    for q in queries:
        print("\n" + "=" * 50)
        print(f"📝 Query: {q}")

        # Fast mode
        run_image_query(client, image_path, q, enable_thinking=False)

        # Reasoning mode
        run_image_query(client, image_path, q, enable_thinking=True)


if __name__ == "__main__":
    main()