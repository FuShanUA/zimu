import sys
import os
CURRENT_DIR = "/Users/shanfu/cc/Library/Tools/autosub"
COMMON_DIR = "/Users/shanfu/cc/Library/Tools/common"
sys.path.append(COMMON_DIR)

from llm_utils import LLMProvider, LLMClient

client = LLMClient()
print(f"ENV_PATH: {os.path.exists('/Users/shanfu/cc/.env')}")
print(f"GEMINI_API_KEY: {client.api_keys.get(LLMProvider.GEMINI) is not None}")
print(f"OPENAI_API_KEY: {client.api_keys.get(LLMProvider.OPENAI) is not None}")

try:
    models = client.list_models_by_provider(LLMProvider.GEMINI)
    print(f"Gemini models count: {len(models)}")
except Exception as e:
    print(f"Gemini error: {e}")
