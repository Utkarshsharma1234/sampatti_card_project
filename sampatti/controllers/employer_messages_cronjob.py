import requests

def main():

    url = "https://conv.sampatticards.com/user/copy_employer_message" 
    response = requests.get(url)
    if response.status_code == 200:
        print("Request successful:", response.json())
    else:
        print("Request failed:", response.status_code)

if __name__ == "__main__":
    main()