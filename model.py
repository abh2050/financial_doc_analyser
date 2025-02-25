# Add this check before initializing the model
import google.generativeai as genai
import os
# Check if the environment variable is set
if "GEMINI_API_KEY" not in os.environ:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
# Initialize the Generative AI client
# This will use the API key from the environment variable
genai.configure(
    api_key=os.getenv
        ("GEMINI_API_KEY"),
        # api_version="v1"  # Explicitly use stable API version
    )


# Initialize model with correct name
model = genai.GenerativeModel('gemini-pro')  # Official model name
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
# Should show: models/gemini-pro