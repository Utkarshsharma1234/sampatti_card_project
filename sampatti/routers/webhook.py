from datetime import datetime
import json, os
from fastapi import APIRouter, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import userControllers
from dotenv import load_dotenv
from ..controllers import ai_agents, whatsapp_message
from ..controllers.utility_functions import call_sarvam_api
from ..controllers.agent import queryExecutor

load_dotenv()
orai_api_key = os.environ.get('ORAI_API_KEY')

router = APIRouter(
    prefix="/webhook",
    tags=['webhook']
)

# Define the webhook route
@router.post("/cashfree")
async def cashfree_webhook(request: Request, db : Session = Depends(get_db)):
    try:
        payload = await request.json()
        
        print("Webhook payload received:", payload)
        
        customer_id = payload['data']['customer_details'].get('customer_id')
        customer_phone = payload['data']['customer_details'].get('customer_phone')
        order_id = payload['data']['order'].get('order_id')
        bank_reference = payload['data']['payment'].get('bank_reference')
        payment_status = payload['data']['payment'].get('payment_status')

        if payment_status != "SUCCESS":
            return {"status" : f"{payment_status}"}
        
        print(f"Customer ID: {customer_id}")
        print(f"Customer Phone: {customer_phone}")
        print(f"Order ID: {order_id}")
        print(f"Bank Reference: {bank_reference}")
        print(f"Payment Status: {payment_status}")

        customer_phone = f"91{customer_phone}"
        userControllers.send_employer_invoice(employerNumber=customer_phone, orderId=order_id, db=db)
        userControllers.update_salary_details(employerNumber=customer_phone, orderId=order_id, db=db)
        return {"status": "success"}
    
    except Exception as e:
        print(f"Error handling webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")
    

@router.post("/orai")
async def orai_webhook(request: Request, db : Session = Depends(get_db)):
    try:    

        print("webhook received")
        data = await request.json()
        formatted_json = json.dumps(data, indent=2)
        print("formatted_json: ", formatted_json)
        message_type = data["entry"][0]["changes"][0]["value"]["messages"][0]["type"]
        print("message_type: ", message_type)
        if message_type == "text":
            url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"
            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.request("POST", url, headers=headers, data=formatted_json)
            print("webhook sent to orai.")
            
        elif message_type == "audio":
            media_id = data["entry"][0]["changes"][0]["value"]["messages"][0]["audio"]["id"]
            print("media_id: ", media_id)
            url = f"https://waba-v2.360dialog.io/{media_id}"
            headers = {
                'D360-API-KEY': orai_api_key,
                'Content-Type': 'application/json'
            }

            response = requests.request("GET", url, headers=headers)
            print("response: ", response)
            if response.status_code == 200:
            # Get the audio content as binary data
                audio_content = response.content
                content_type = response.headers.get('content-type', '').lower()
                if 'audio/mpeg' in content_type or 'mp3' in content_type:
                    file_extension = '.mp3'
                elif 'audio/wav' in content_type:
                    file_extension = '.wav'
                elif 'audio/ogg' in content_type:
                    file_extension = '.ogg'
                else:
                    file_extension = '.mp3' 
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"audio_{media_id}"
                save_directory = "downloaded_audio"  # Change this to your desired folder
                save_path = os.path.join(save_directory, filename)
                os.makedirs(save_directory, exist_ok=True)
                with open(save_path, 'wb') as audio_file:
                    audio_file.write(audio_content)
                print(f"Audio file saved successfully: {save_path}")
                print(f"File size: {len(audio_content)} bytes")

                result = call_sarvam_api(save_path)
                transcript = result["transcript"]
                user_language = result["language_code"]
                print("Transcript: ",transcript)
                print("User Language: ",user_language)
                
                employerNumber = data["entry"][0]["changes"][0]["contacts"][0]["wa_id"]
                print("Employer Number: ",employerNumber)
                
                url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"
                headers = {
                    'Content-Type': 'application/json'
                }

                response = requests.request("POST", url, headers=headers, data=formatted_json)
                print("webhook response: ", response)

                print("webhook sent to orai.")

                text = queryExecutor(employerNumber, transcript)
                print("Response from queryExecutor: ", text)
                
                url = "https://conv.sampatticards.com/user/send_audio_message"
                payload = {
                    "text": text,
                    "user_language": user_language,
                    "employerNumber": employerNumber
                }
                response = requests.post(url, params=payload)
                response.raise_for_status()
                data = response.json()
                print("Audio message sent successfully:", data)
                print("Process Complete!!!")
                

                
        print("Webhook Completed Successfully")

    except Exception as e:
        print(f"Error in handling the webhook from orai : {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")
