"""
Quick test examples for AI Code Mentor API
Run: python test_examples.py
"""

import requests
import json

BASE_URL = "http://localhost:8000"

# Example 1: Bad code with issues
BAD_CODE = """
def calculate(x, y):
    result = x + y
    result = x * y
    result = result * 2
    return result

data = [1, 2, 3, 4, 5]
for i in range(len(data)):
    print(data[i])
"""

# Example 2: Good code
GOOD_CODE = """
def calculate(a: int, b: int) -> int:
    \"\"\"Calculate sum and product.\"\"\"
    total = a + b
    product = a * b
    return total + product

numbers = [1, 2, 3, 4, 5]
for num in numbers:
    print(num)
"""

# Example 3: Code with potential security issue
SECURITY_CODE = """
import sqlite3

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchone()
"""

def test_analyze():
    """Test /analyze endpoint"""
    print("=" * 60)
    print("TEST 1: Analyzing code with issues...")
    print("=" * 60)
    
    payload = {
        "code": BAD_CODE,
        "filename": "bad_example.py"
    }
    
    response = requests.post(f"{BASE_URL}/analyze", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Analysis successful!")
        print(f"Score: {result['score']}/100")
        print(f"Summary: {result['summary']}")
        print(f"Critical issues: {len(result['feedback']['critical'])}")
        print(f"Improvements: {len(result['feedback']['improvements'])}")
        print(f"Learning topics: {len(result['feedback']['learning'])}")
        print(f"Good practices: {len(result['feedback']['good'])}")
        
        if result['mentor_hints']:
            print(f"\nMentor Hints:")
            for hint in result['mentor_hints']:
                print(f"  • {hint['hint']}")
        
        return result['id']
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

def test_history(analysis_id):
    """Test /history endpoint"""
    print("\n" + "=" * 60)
    print("TEST 2: Getting analysis history...")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/history?limit=5")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ History retrieved!")
        print(f"Total analyses: {result['total']}")
        
        if result['analyses']:
            print("\nLatest analyses:")
            for analysis in result['analyses'][:3]:
                print(f"  • {analysis['filename']} - Score: {analysis['score']}/100")
    else:
        print(f"❌ Error: {response.status_code}")

def test_get_analysis(analysis_id):
    """Test /analysis/{id} endpoint"""
    if not analysis_id:
        print("\n❌ No analysis ID to test")
        return
    
    print("\n" + "=" * 60)
    print("TEST 3: Getting specific analysis...")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/analysis/{analysis_id}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Analysis retrieved!")
        print(f"File: {result['filename']}")
        print(f"Score: {result['score']}")
    else:
        print(f"❌ Error: {response.status_code}")

def test_stats():
    """Test /stats endpoint"""
    print("\n" + "=" * 60)
    print("TEST 4: Getting statistics...")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/stats")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Stats retrieved!")
        print(f"Total analyses: {result['total_analyses']}")
        print(f"Average score: {result['average_score']}")
        print(f"Best score: {result['best_score']}")
    else:
        print(f"❌ Error: {response.status_code}")

def test_good_code():
    """Test with good code"""
    print("\n" + "=" * 60)
    print("TEST 5: Analyzing good code...")
    print("=" * 60)
    
    payload = {
        "code": GOOD_CODE,
        "filename": "good_example.py"
    }
    
    response = requests.post(f"{BASE_URL}/analyze", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Analysis successful!")
        print(f"Score: {result['score']}/100 (should be high)")
        print(f"Good practices found: {len(result['feedback']['good'])}")
    else:
        print(f"❌ Error: {response.status_code}")

def test_security_code():
    """Test with security issue"""
    print("\n" + "=" * 60)
    print("TEST 6: Analyzing code with security issues...")
    print("=" * 60)
    
    payload = {
        "code": SECURITY_CODE,
        "filename": "security_issue.py"
    }
    
    response = requests.post(f"{BASE_URL}/analyze", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Analysis successful!")
        print(f"Score: {result['score']}/100")
        
        if result['feedback']['critical']:
            print(f"\nCritical issues found:")
            for issue in result['feedback']['critical']:
                print(f"  • {issue.get('issue', 'Unknown issue')}")
    else:
        print(f"❌ Error: {response.status_code}")

if __name__ == "__main__":
    try:
        print("\n🚀 AI Code Mentor API Tests\n")
        
        # Run tests
        analysis_id = test_analyze()
        test_good_code()
        test_security_code()
        test_history(analysis_id)
        test_get_analysis(analysis_id)
        test_stats()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        print("\n📚 Next: Connect React frontend to these endpoints")
        print("📖 Docs: http://localhost:8000/docs")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server.")
        print("Make sure to run: python main.py")
    except Exception as e:
        print(f"❌ Error: {e}")
