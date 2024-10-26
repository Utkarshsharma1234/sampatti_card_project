import json
from fastapi import HTTPException
import requests, os

orai_api_key = os.environ.get('ORAI_API_KEY')
orai_namespace = os.environ.get('ORAI_NAMESPACE')

# send template messages - payment link, invoice message and worker salary slip message

def send_whatsapp_message(employerNumber, worker_name, param3, link_param,template_name):
    url = "https://orailap.azurewebsites.net/api/cloud/Dialog"
    headers = {
        "API-KEY": orai_api_key,
        "Content-Type": "application/json"
    }

    data = {
        "template": {
            "namespace": orai_namespace,
            "name": template_name,
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": employerNumber
                        },
                        {
                            "type": "text",
                            "text": worker_name
                        },
                        {
                            "type": "text",
                            "text": param3
                        }
                    ]
                },
                {
                    "index": 0,
                    "parameters": [
                        {
                            "type": "text",
                            "text": link_param
                        }
                    ],
                    "sub_type": "url",
                    "type": "button"
                }
            ],
            "language": {
                "code": "en_US",
                "policy": "deterministic"
            }
        },
        "messaging_product": "whatsapp",
        "to": employerNumber,
        "type": "template"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print(f"Message sent successfully, Worker name : {worker_name}, Employer name : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")


# send greetings message

def send_greetings(employerNumber,template_name):
    url = "https://orailap.azurewebsites.net/api/cloud/Dialog"
    headers = {
        "API-KEY": orai_api_key,
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": employerNumber,
        "type": "template",
        "template" : {
            "namespace": orai_namespace,
            "language": {
                "code": "en_US",
                "policy": "deterministic"
            },
            "name": template_name,
            "components" : [

                {
                    "type" : "header",
                    "parameters" : [
                        {
                            "type": "image",
                            "image": {
                                "link": "https://sampattifilstorage.sgp1.digitaloceanspaces.com/diwali_image.jpg"
                            }
                        }
                    ]
                },

                {
                    "type" : "body",
                    "parameters" : [
                        {
                            "type": "text",
                            "text": employerNumber
                        }
                    ]
                }
            ]
        }

    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print(f"Message sent successfully, Employer name : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")



# generate media id for the file uploading

def generate_mediaId(path : str, folder : str):
    

    print("the code entered media id")

    url = "https://waba-v2.360dialog.io/media"

    static_pdf_path = os.path.join(os.getcwd(), folder, path)
    print(static_pdf_path)

    if os.path.exists(static_pdf_path):
        headers = {
            "D360-API-KEY": orai_api_key
        }

        data = {
            "messaging_product": "whatsapp"
        }
        files = {
            "file": (path, open(static_pdf_path, "rb"), "application/pdf")
        }

        
        try:
            response = requests.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            return response.json()
        except Exception as e:

            print(f"Exception occurred: {e}")
            raise HTTPException(status_code=500, detail="Generating the media Id.")
    else:
        raise HTTPException(status_code=404, detail="PDF file not found")