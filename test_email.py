import requests

# Google Apps Script URL for email notifications
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzOA_BkwPcKwTJQooGWISHUnPu6st1gSpf-Ov7RBA2_CrPxb2PRyhA_jckdZTmeYzd9Kw/exec"

# Sample data for testing initial save
test_payload_initial = {
    "type": "initial",
    "data": {
        'cpf': '12345678900',
        'requester_name': 'Test Requester',
        'driver_name': 'Test Driver',
        'date': '2023-10-01 10:00:00',
        'initial_km': '10000',
        'departure_time': '10:00',
        'origin': 'Test Origin',
        'initial_tank_level': '50',
        'destination': 'Test Destination',
        'car_status': 'Good',
        'observations': 'Test observations',
        'status': 'initial'
    }
}

# Sample data for testing final save
test_payload_final = {
    "type": "final",
    "data": {
        'cpf': '12345678900',
        'requester_name': 'Test Requester',
        'driver_name': 'Test Driver',
        'date': '2023-10-01 10:00:00',
        'initial_km': '10000',
        'departure_time': '10:00',
        'origin': 'Test Origin',
        'initial_tank_level': '50',
        'destination': 'Test Destination',
        'car_status': 'Good',
        'final_km': '10100',
        'arrival_time': '12:00',
        'final_tank_level': '40',
        'observations': 'Test final observations',
        'status': 'complete'
    }
}

def test_email(payload, test_type):
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        print(f"Test {test_type} - Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        if response.status_code == 200:
            print(f"Email test for {test_type} successful!")
        else:
            print(f"Email test for {test_type} failed!")
    except Exception as e:
        print(f"Error testing {test_type} email: {e}")

if __name__ == "__main__":
    print("Testing initial save email...")
    test_email(test_payload_initial, "initial")
    print("\nTesting final save email...")
    test_email(test_payload_final, "final")
