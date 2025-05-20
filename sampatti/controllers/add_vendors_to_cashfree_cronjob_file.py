import requests

def main():

    url = "https://conv.sampatticards.com/user/add_vendors_to_cashfree_from_sheet" 
    response = requests.get(url)
    if response.status_code == 200:
        print("Request successful:", response.json())
    else:
        print("Request failed:", response.status_code)

if __name__ == "__main__":
    main()
