import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input="Reply with exactly: API test successful."
)
print(response.output_text)