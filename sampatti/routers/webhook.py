import json, os
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import onboarding_agent, userControllers
from dotenv import load_dotenv
from ..controllers import whatsapp_message, super_agent

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
async def orai_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()

        # Immediately start background processing
        background_tasks.add_task(process_orai_webhook, data)

        # Immediate response
        return {"status": "received"}

    except Exception as e:
        print(f"Error in initial webhook handling: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")


def process_orai_webhook(data: dict):
    try:
        formatted_json = json.dumps(data, indent=2)
        formatted_json_oneline = json.dumps(data, separators=(',', ':'))

        print(f"Webhook payload: {formatted_json_oneline}")

        url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"
        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.post(url, headers=headers, data=formatted_json)

        entry = data.get("entry", [])[0] if data.get("entry") else {}
        changes = entry.get("changes", [])[0] if entry.get("changes") else {}
        value = changes.get("value", {})

        contacts = value.get("contacts", [])
        employerNumber = contacts[0].get("wa_id") if contacts else None

        messages = value.get("messages", [])
        message = messages[0] if messages else {}
        message_type = message.get("type")
        
        # Safely extract media_id - only for media message types
        media_id = None
        if message_type and message_type in ["image", "audio", "video", "document", "sticker"]:
            media_content = message.get(message_type, {})
            media_id = media_content.get("id") if isinstance(media_content, dict) else None

        print(f"Message type: {message_type}, EmployerNumber: {employerNumber}, Media Id: {media_id}")

        # Forward to ngrok for specific number
        if employerNumber == "918197266977":
            ngrok_url = "https://delicate-cheaply-serval.ngrok-free.app/webhook"
            try: 
                ngrok_response = requests.post(ngrok_url, headers=headers, data=formatted_json) 
                print(f"Forwarded to ngrok. Status: {ngrok_response.status_code}")
            except Exception as e:
                print(f"Error forwarding to ngrok: {e}")
            # Return early to skip super_agent processing
            return

        if not message_type:
            print("None message type")

        elif message_type == "text":
            query = message.get("text", {}).get("body")
            super_agent.super_agent_query(employerNumber, message_type, query, "", formatted_json)

        elif message_type == "audio":
            query = message.get("audio", {}).get("id")
            super_agent.super_agent_query(employerNumber, message_type, query, media_id, formatted_json)

        elif message_type == "button":
            query = data["entry"][0]["changes"][0]["value"]["messages"][0]["button"]["text"]
            super_agent.super_agent_query(employerNumber, "text", query, "", formatted_json)

        elif message_type == "contacts":
            numb = data["entry"][0]["changes"][0]["value"]["messages"][0]["contacts"][0]["phones"][0]["wa_id"]
            print("Extracted the Contact Number from the Button: ", numb)
            super_agent.super_agent_query(employerNumber, "text", numb, "", formatted_json)

        else:
            super_agent.super_agent_query(employerNumber, "text", "Hi", media_id, formatted_json)

    except Exception as e:
        print(f"Error in background processing of orai webhook: {e}")