import json, os
import tempfile
from fastapi import APIRouter, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import userControllers
from dotenv import load_dotenv
from ..controllers import ai_agents, whatsapp_message
from ..controllers.utility_functions import call_sarvam_api
from ..controllers.agent import queryExecutor
from pydub import AudioSegment

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
            response = response.json()
            print("Response from 360dialog: ", response)

            wb = response["url"]
            extracted_part = wb.split('whatsapp_business')[1]
            extracted_part = 'whatsapp_business' + wb.split('whatsapp_business')[1]
            print("extracted_part: ", extracted_part)

            url = f"https://waba-v2.360dialog.io/{extracted_part}"
            headers = {
                'D360-API-KEY': orai_api_key,
                'Content-Type': 'application/json'
            }

            response_2 = requests.request("GET", url, headers=headers)

            if response_2.status_code != 200:
                return f"Failed to download audio: {response_2.status_code} {response_2.text}"

            output_dir = 'audio_files'
            os.makedirs(output_dir, exist_ok=True)

            temp_path = ""
            wav_path = os.path.join(output_dir, f"{media_id}_audio.wav")

            with tempfile.NamedTemporaryFile(delete=False) as temp:
                temp.write(response_2.content)
                temp_path = temp.name

            print(f"Downloaded temporary file: {temp_path}")

            # Step 2: Convert to WAV format
            audio = AudioSegment.from_file(temp_path)
            audio.export(wav_path, format="wav")

            print(f"Converted to WAV and saved at: {wav_path}")

            result = call_sarvam_api(wav_path)
            transcript = result["transcript"]
            user_language = result["language_code"]
            employer_n =data["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
            print("employer_n: ", employer_n)

            print("Transcript: ",transcript)
            print("User Language: ",user_language)
                
            url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"
            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.request("POST", url, headers=headers, data=formatted_json)
            print("webhook response: ", response)

            print("webhook sent to orai.")

            text = queryExecutor(employer_n, transcript)
            print("Response from queryExecutor: ", text)

            url = "https://conv.sampatticards.com/user/send_audio_message"
            payload = {
                "text": text,
                "user_language": user_language,
                "employerNumber": employer_n
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