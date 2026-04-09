from langchain.chat_models import init_chat_model
import os
from dotenv import load_dotenv

load_dotenv()

JUDGE_MODEL = init_chat_model(
        model="gemini-2.5-flash-lite",
        model_provider="google_genai",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )
RESEARCHER_MODEL = init_chat_model(
        model="gemini-2.5-flash-lite",
        model_provider="google_genai",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )
WRITER_MODEL = init_chat_model(
        model="gemini-2.5-flash-lite",
        model_provider="google_genai",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )