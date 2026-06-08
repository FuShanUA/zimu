
import sys
import os

# Add common directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "common")
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

from llm_utils import LLMProvider, LLMClient

def test_gemini_list():
    client = LLMClient()
    provider = LLMProvider.GEMINI
    print(f"Listing models for {provider.value}...")
    models = client.list_models_by_provider(provider)
    print(f"Models: {models}")

if __name__ == "__main__":
    test_gemini_list()
