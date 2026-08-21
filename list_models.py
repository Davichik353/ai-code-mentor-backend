"""
Diagnostic: list which Gemini models your API key actually has access to.
"""

import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("❌ GOOGLE_API_KEY not found in .env")
    exit(1)

print(f"✅ API key loaded (starts with: {api_key[:12]}...)\n")

client = genai.Client(api_key=api_key)

print("Fetching available models from Google API...\n")

try:
    models = client.models.list()
    found_any = False
    for m in models:
        found_any = True
        actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None)
        print(f"  • {m.name}")
        if actions:
            print(f"      supports: {actions}")

    if not found_any:
        print("⚠️  No models returned — key might not have Generative Language API enabled.")

except Exception as e:
    print(f"❌ Error listing models: {e}")
    print("\nPossible causes:")
    print("  - API key is invalid or restricted")
    print("  - 'Generative Language API' not enabled for this key's project")
    print("  - Regional restriction on your Google account")