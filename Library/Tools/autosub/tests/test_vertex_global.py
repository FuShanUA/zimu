
import sys
import os
import vertexai

# Add common directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = os.path.join(os.path.dirname(os.path.dirname(CURRENT_DIR)), "common")
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

from llm_utils import LLMProvider, LLMClient

def test_vertex_global():
    # Set credentials
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/shanfu/.config/gcloud/application_default_credentials.json"
    project = "gen-lang-client-0991632900"
    location = "global"
    model_name = "gemini-3.1-pro-preview"
    
    print(f"Testing Vertex AI with location='{location}' and model='{model_name}'...")
    try:
        vertexai.init(project=project, location=location)
        from vertexai.generative_models import GenerativeModel
        model = GenerativeModel(model_name)
        response = model.generate_content("Ping")
        print(f"✅ Success! Response: {response.text}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_vertex_global()
