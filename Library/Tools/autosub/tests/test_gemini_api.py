
import sys
import os

# Add common directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "common")
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

from llm_utils import LLMProvider, LLMClient

def test_gemini_api():
    client = LLMClient()
    provider = LLMProvider.GEMINI
    model_name = "gemini-3.1-pro-preview"
    
    print(f"Testing {provider.value} with model {model_name}...")
    success, response = client.generate_content_with_provider(
        "Ping",
        provider=provider,
        model_name=model_name,
        fallback=False
    )
    
    if success:
        print(f"✅ Success! Response: {response}")
    else:
        print(f"❌ Failed: {response}")

if __name__ == "__main__":
    test_gemini_api()
