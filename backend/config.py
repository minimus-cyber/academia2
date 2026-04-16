import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DB_PATH = "../db/academia.db"
PORT = 8083
ACADEMIA_VERSION = "2.0"

MODEL_TRANSLATION_INPUT = "groq/llama-3.1-8b-instant"
MODEL_SENIOR = "groq/llama-3.3-70b-versatile"
MODEL_COORD_1 = "openrouter/nousresearch/hermes-3-llama-3.1-405b:free"
MODEL_COORD_2 = "openrouter/openai/gpt-oss-120b:free"
MODEL_RESEARCHER_1 = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
MODEL_RESEARCHER_2 = "openrouter/google/gemma-3-27b-it:free"
MODEL_RESEARCHER_3 = "openrouter/qwen/qwen3-30b-a3b:free"
MODEL_STUDENT_1 = "github/Phi-4-mini-instruct"
MODEL_STUDENT_2 = "github/Meta-Llama-3.1-8B-Instruct"
MODEL_TRANSLATION_FINAL = "groq/llama-3.3-70b-versatile"

CONSTITUTION_CONSTRAINTS = """
Academia Intermundia operates under these inviolable founding constraints:
1. EMPIRICISM: Every claim must be verifiable or falsifiable through observation or experiment.
2. IMMANENTISM: No transcendent entities or supernatural forces may be invoked as explanations.
3. ADVANCEMENT: Every work must contribute measurably to the progress of knowledge.
4. SELF-FINANCING: Studies must be real, concrete, and produce results that can be valued and sold through the Professor's resources.
"""
