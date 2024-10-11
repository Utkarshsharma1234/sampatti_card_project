import json
from fastapi import HTTPException
import requests, os
from .. import models
from sqlalchemy.orm import Session

orai_api_key = os.environ.get('ORAI_API_KEY')
orai_namespace = os.environ.get('ORAI_NAMESPACE')

def send_whatsapp_message(cust_name, dw_name, month_year, session_id, receiver_number):
    url = "https://orailap.azurewebsites.net/api/cloud/Dialog"
    headers = {
        "API-KEY": orai_api_key,
        "Content-Type": "application/json"
    }

    data = {
        "template": {
            "namespace": orai_namespace,
            "name": "monthly_salary_link_template",
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": cust_name
                        },
                        {
                            "type": "text",
                            "text": dw_name
                        },
                        {
                            "type": "text",
                            "text": month_year
                        }
                    ]
                },
                {
                    "index": 0,
                    "parameters": [
                        {
                            "type": "text",
                            "text": session_id
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
        "to": receiver_number,
        "type": "template"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print(f"Message sent successfully, Worker name : {dw_name}, Employer name : {cust_name}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")



def employer_invoice_message(employerNumber, workerName, salary, filename):
    url = "https://orailap.azurewebsites.net/api/cloud/Dialog"
    headers = {
        "API-KEY": orai_api_key,
        "Content-Type": "application/json"
    }

    data = {
        "template": {
            "namespace": orai_namespace,
            "name": "employer_invoice_template",
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
                            "text": workerName
                        },
                        {
                            "type": "text",
                            "text": salary
                        }
                    ]
                },
                {
                    "index": 0,
                    "parameters": [
                        {
                            "type": "text",
                            "text": filename
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
        print(f"Message sent successfully, Worker name : {workerName}, Employer Number : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")



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
    

def send_pdf(receiverNumber : int, mediaId : str, filename : str):

    url = "https://waba-v2.360dialog.io/messages"

    orai_api_key = os.environ.get('ORAI_API_KEY')

    print("entered sending pdf")
    payload = json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": f"{receiverNumber}",
            "type": "document",
            "document": {
                "id": f"{mediaId}",
                "filename": f"{filename}"
            }
    })
    
    headers = {
    'Content-Type': 'application/json',
    'D360-API-KEY': orai_api_key
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)