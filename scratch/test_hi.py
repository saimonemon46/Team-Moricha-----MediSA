import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../fastapi_ai")

from fastapi_ai.workflow import run_question_generation

def test_intent(text):
    print(f"\nTesting: '{text}'")
    result = run_question_generation(text, user_id=1)
    print(f"Is Medical: {result.get('is_medical')}")
    print(f"Message: {result.get('intent_message')}")
    print(f"Questions: {len(result.get('questions', []))} questions generated.")

if __name__ == "__main__":
    test_intent("hi")
