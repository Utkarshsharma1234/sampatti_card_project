import json
from fastapi import Body, HTTPException
import requests, os
from dotenv import load_dotenv
import os
from twilio.rest import Client
from sampatti.models import Employer

load_dotenv()
orai_api_key = os.environ.get('ORAI_API_KEY')
orai_namespace = os.environ.get('ORAI_NAMESPACE')
twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
twilio_whatsapp_number = os.environ.get("TWILIO_WHATSAPP_NUMBER")
#authourization_message = os.environ.get('ORAI_AUTHERIZATION_MESSEGE')
authorization_message = os.environ.get('ORAI_AUTHORIZATION_MESSAGE')

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
                        }
                    ]
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
        print(f"Message sent successfully, Employer name : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")


def send_v2v_message(employerNumber, text, template_name):
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
                            "text": text
                        }
                    ]
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
    

def generate_audio_media_id(path : str, folder : str):

    url = "https://waba-v2.360dialog.io/media"

    file_path = os.path.join(os.getcwd(), folder, path)
    print("entering into media id for the ogg file.")
    print(file_path)

    payload = {'messaging_product': 'whatsapp'}
    files=[
        ('file',('output.ogg',open(file_path,'rb'),'audio/opus'))
    ]
    headers = {
        'D360-API-KEY': orai_api_key,
        'Accept': 'application/json'
    }
    try:
        response = requests.post(url, headers=headers, data=payload, files=files)
        return response.json()
    except Exception as e:
        print(f"Exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Generating the audio media Id.")


def send_whatsapp_audio(audio_media_id : str, employerNumber : int):

    url = "https://waba-v2.360dialog.io/messages"

    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": f"{employerNumber}",
        "type": "audio",
        "audio": {
            "id" : f"{audio_media_id}"
        }
    })

    headers = {
    'D360-API-KEY': orai_api_key,
    'Content-Type': 'application/json'
    }

    response = requests.post(url, headers=headers, data=payload)

    print(response.text)


def send_intro_video(employerNumber,template_name):

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
                            "type": "video",
                            "video": {
                                "link": "https://sampattifilstorage.sgp1.digitaloceanspaces.com/sampatti_card_video_reduced%20(1).mp4"
                            }
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


def send_message_user(employer_number, body: str):

    url = "https://waba-v2.360dialog.io/messages"

    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": employer_number,
        "type": "text",
        "text": {
            "body": body
        }
    })

    headers = {
        'D360-API-KEY': orai_api_key,
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)
    
    
def display_user_message_on_xbotic(employee_number, text: str):

    # API endpoint
    url = "https://api-xbotic.cbots.live/bot-api/v2.0/customer/71029/bot/732e12160d6e4598/flow/B9DA9D396B2343AFBF5E33420107E9B6"
    
    # Headers
    headers = {
        'Authorization': authorization_message,  # Use the authorization message from .env
        'Content-Type': 'application/json'
    }
    
    # Payload
    data = json.dumps({
        "user.channel": "whatsapp",
        "user.phone_no": employee_number,
        "random_text": text
    })
    
    try:
        # Make the POST request
        response = requests.post(url, headers=headers, data=data)
        print("Response:", response.text)
        print("Status Code:", response.status_code)

        # Check if request was successful
        response.raise_for_status()
        
        # Return the response as JSON
        return {
            'success': True,
            'status_code': response.status_code,
            'data': response.json() if response.content else None
        }
        
    except requests.exceptions.RequestException as e:
        # Handle any request errors
        return {
            'success': False,
            'error': str(e),
            'status_code': response.status_code if 'response' in locals() else None
        }


def send_referral_message_to_employer(employerNumber, template_name, referral_code):

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
                            "text": referral_code
                        }
                    ]
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
        print(f"Message sent successfully, Employer name : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")


def twilio_send_text_message(mobileNumber, body):

    client = Client(twilio_account_sid, twilio_auth_token)
    message = client.messages.create(
        to=mobileNumber,
        from_=twilio_whatsapp_number,
        body=body
    )
    return message.sid


def send_greetings_with_image(employerNumber,template_name):

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
                                "link": "https://bb.branding-element.com/prod/118331/118331-21092025_190144-navratra_stapana.png"
                            }
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
        
        
def send_message_to_referring_employer(employerNumber, template_name, referral_code, referred_employer, upi_id):

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
                            "text": referral_code
                        },
                        {
                            "type": "text",
                            "text": referred_employer
                        },
                        {
                            "type": "text",
                            "text": upi_id
                        }
                    ]
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


def send_template_message(employerNumber,template_name):
    url = "https://orailap.azurewebsites.net/api/cloud/Dialog"

    headers = {
        "API-KEY": orai_api_key,
        "Content-Type": "application/json"
    }

    data = {
        "template": {
            "namespace": orai_namespace,
            "name": template_name,
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
        print(f"Message sent successfully, Employer name : {employerNumber}")
    else:
        print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")