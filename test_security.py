# Test file to verify gitleaks is working
# This should be caught by our secret detection

# Fake OpenAI API key (this should trigger gitleaks)
OPENAI_API_KEY = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyzABCDEFGH"


def test_function():
    return "testing"
