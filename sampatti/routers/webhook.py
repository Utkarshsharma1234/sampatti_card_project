import json, os
from fastapi import APIRouter, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import userControllers
from dotenv import load_dotenv
from ..controllers import ai_agents, whatsapp_message

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

        url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"
        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=formatted_json)

        print("webhook sent to orai.")
        entry = data.get("entry", [])[0] if data.get("entry") else {}
        changes = entry.get("changes", [])[0] if entry.get("changes") else {}
        value = changes.get("value", {})

        contacts = value.get("contacts", [])
        employerNumber = contacts[0].get("wa_id") if contacts else None

        messages = value.get("messages", [])
        message = messages[0] if messages else {}
        message_type = message.get("type")
        media_id = message.get(message_type, {}).get("id")

        # print("payload entered")
        # print(f"Webhook payload received : {formatted_json}")
        # print("payload exit")

        print(f"Message type: {message_type}")
        print(f"Employernumber: {employerNumber}")
        print(f"Media Id: {media_id}")

        if not message_type:
            pass

        elif message_type == "text":
            body = message.get("text", {}).get("body")
            # userControllers.send_audio_message(body, "en-IN", employerNumber)
            # whatsapp_message.send_greetings(employerNumber, template_name="salary_adjust_greetings")
            ai_agents.queryExecutor(employerNumber, message_type, body, "")
        
        else:
            media_id = message.get(message_type, {}).get("id")
            # whatsapp_message.send_greetings(employerNumber, template_name="salary_adjust_greetings")
            # userControllers.send_audio_message("Hi this is testing audio which is created for testing the webhook.", "en-IN", employerNumber)
            ai_agents.queryExecutor(employerNumber, message_type, "", media_id)


    except Exception as e:
        print(f"Error in handling the webhook from orai : {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")