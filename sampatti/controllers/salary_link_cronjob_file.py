import requests
# from sampatti.routers.auth import get_auth_headers

def main():
    url = "https://conv.sampatticards.com/cashfree/payment_link" 
    response = requests.get(url)
    if response.status_code == 200:
        print("Request successful:", response.json())
    else:
        print("Request failed:", response.status_code)

if __name__ == "__main__":
    main()
