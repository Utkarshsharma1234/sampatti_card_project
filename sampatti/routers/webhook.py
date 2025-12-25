import json, os
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import onboarding_agent, userControllers, survey_agent, onboarding_tasks
from dotenv import load_dotenv
from ..controllers import whatsapp_message, super_agent
from .. import models
from ..controllers.userControllers import generate_unique_id

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
        userControllers.process_employer_cashback_for_first_payment(employerNumber=customer_phone, payload=payload, db=db)
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
        message_id = data["entry"][0]["changes"][0]["value"]["messages"][0]["id"]

        contacts = value.get("contacts", [])
        employerNumber = contacts[0].get("wa_id") if contacts else None

        messages = value.get("messages", [])
        message = messages[0] if messages else {}
        message_type = message.get("type")
        
        media_id = None
        if message_type and message_type in ["image", "audio", "video", "document", "sticker"]:
            media_content = message.get(message_type, {})
            media_id = media_content.get("id") if isinstance(media_content, dict) else None

        print(f"Message type: {message_type}, EmployerNumber: {employerNumber}, Media Id: {media_id}")
        
        # url = "https://orailap.azurewebsites.net/api/cloud/Dialog"
        # headers = {
        #     "API-KEY": orai_api_key,
        #     "Content-Type": "application/json"
        # }
        # payload = {
        #     "messaging_product": "whatsapp",
        #     "status": "read",
        #     "message_id": message_id,
        #     "typing_indicator": {
        #         "type": "text"
        #     }
        # }
        
        # resp = requests.post(url, headers=headers, json=payload, timeout=10)
        # if resp.status_code == 200:
        #     print("✅ Typing indicator sent successfully!")
        # else:
        #     print(f"❌ Failed: {resp.status_code} → {resp.text}")
        
        # if employerNumber == "918197266977":
        #     ngrok_url = "https://delicate-cheaply-serval.ngrok-free.app/webhook"
        #     try:
        #         ngrok_response = requests.post(ngrok_url, headers=headers, data=formatted_json)
        #         print(f"Forwarded to ngrok. Status: {ngrok_response.status_code}")
        #     except Exception as e:
        #         print(f"Error forwarding to ngrok: {e}")
        #     # Return early to skip super_agent processing
        #     return
                

        if employerNumber == "919731011117":
            if message_type == "text":
                query = message.get("text", {}).get("body")
                survey_agent.queryExecutor(employerNumber, message_type, query, media_id)
                return
            elif message_type == "audio":
                query = message.get("audio", {}).get("id")
                survey_agent.queryExecutor(employerNumber, message_type, query, media_id)
                return

        # Forward to staging     
        if employerNumber == "917738877765":
            staging_url = "https://staging.sampatticard.in/api/whatsapp/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=formatted_json)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")   
                print(f"Response: {staging_response.text}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        elif employerNumber == "916378639230":
            #https://7rshr4vz-8000.inc1.devtunnels.ms/
            staging_url = "https://7rshr4vz-8000.inc1.devtunnels.ms/api/whatsapp/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=formatted_json)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")   
                print(f"Response: {staging_response.text}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        elif employerNumber == "919080682466" or employerNumber == "918197266977" or employerNumber == "917015645195":
            #https://b93x4t5q-8000.inc1.devtunnels.ms/
            staging_url = "https://staging.sampatticard.in/api/whatsapp/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=formatted_json)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")
                print("response: ", staging_response.text)
                print(f"Response: {staging_response}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        elif employerNumber == "917665292549" or employerNumber == "919922724713" or employerNumber == "917742422603" or employerNumber == "917022878346":
            #https://b93x4t5q-8000.inc1.devtunnels.ms/
            staging_url = "https://staging.sampatticard.in/api/whatsapp/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=formatted_json)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")
                print("response: ", staging_response.text)
                print(f"Response: {staging_response}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        elif employerNumber == "918208804525" :
            #https://gcvdr8fw-8000.inc1.devtunnels.ms/
            staging_url = "https://gcvdr8fw-8000.inc1.devtunnels.ms/api/whatsapp/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=formatted_json)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")   
                print(f"Response: {staging_response.text}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        if not message_type:
            print("None message type")

        elif message_type == "text":
            query = message.get("text", {}).get("body")
            super_agent.super_agent_query(employerNumber, message_type, query, "", data)

        elif message_type == "audio":
            query = message.get("audio", {}).get("id")
            super_agent.super_agent_query(employerNumber, message_type, query, media_id, data)
            
        elif message_type == "image":
            query = message.get("image", {}).get("id")
            super_agent.super_agent_query(employerNumber, message_type, query, media_id, data)

        elif message_type == "button":
            #print("Button message received, but button text extraction is currently disabled.")
            query = data["entry"][0]["changes"][0]["value"]["messages"][0]["button"]["text"]
            print("Button message received.")
            super_agent.super_agent_query(employerNumber, message_type, query, media_id, data)

        elif message_type == "contacts":
            numb = data["entry"][0]["changes"][0]["value"]["messages"][0]["contacts"][0]["phones"][0]["wa_id"]
            print("Extracted the Contact Number from the Button: ", numb)
            super_agent.super_agent_query(employerNumber, "text", numb, "", data)

        else:
            super_agent.super_agent_query(employerNumber, "text", "Hi", media_id, data)

    except Exception as e:
        print(f"Error in background processing of orai webhook: {e}")
        
        
@router.post("/cashfree_vendor_status")
async def cashfree_vendor_status(request: Request, db: Session = Depends(get_db)):
    try:

        payload = await request.json()
        print("Webhook payload received:", payload)

        data = payload.get('data', {})
        vendor_id = data.get('merchant_vendor_id')
        updated_status = data.get('updated_status')
        phone = data.get('phone')
        name = data.get('name')
        account_number = data.get('account_number')
        ifsc = data.get('ifsc')
        vpa = data.get('vpa')
        pan_status = data.get('document_status', {}).get('PAN')
        event_type = payload.get('type')

        print(f"Vendor ID: {vendor_id}")
        print(f"Updated Status: {updated_status}")
        print(f"Phone: {phone}")
        print(f"Name: {name}")
        print(f"Account Number: {account_number}")
        print(f"IFSC: {ifsc}")
        print(f"VPA: {vpa}")
        print(f"PAN Status: {pan_status}")
        print(f"Event Type: {event_type}")
        
        if phone == "9080682466":
            staging_url = "https://gcvdr8fw-8000.inc1.devtunnels.ms/api/cashfree/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                staging_response = requests.post(staging_url, headers=headers, data=payload)
                print(f"Forwarded to staging server. Status: {staging_response.status_code}")   
                print(f"Response: {staging_response.text}")
            except Exception as e:
                print(f"Error forwarding to staging: {e}")
            return
        
        staging_url = "https://staging.sampatticard.in/api/cashfree/webhook"
        headers = {"Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(staging_url, json=payload, headers=headers)
            print(f"Forwarded to staging. Status={resp.status_code}, Body={resp.text}")
        except Exception as forward_err:
            # Don’t fail your main webhook if staging is down;
            # just log it.
            print(f"Failed to forward webhook to staging: {forward_err}")
        
        if phone == "6378639230" or phone == "9080682466":
            print("Entered if statement for 6378639230 or 9080682466 for vendor status webhook")
            #https://gcvdr8fw-8000.inc1.devtunnels.ms/
            staging_url = "https://gcvdr8fw-8000.inc1.devtunnels.ms/api/cashfree/webhook"
            headers = {
                'Content-Type': 'application/json'
            }
            return
        
        number = 6378639230
        text_message = ""
        if updated_status == "ACTIVE":
            onboarding_tasks.run_tasks_after_vendor_addition()
            text_message = f"Hello {name} {phone} {vpa} {account_number} {ifsc} {pan_status},The vendor has been added successfully."
        elif updated_status == "BANK_VALIDATION_FAILED":
            whatsapp_message.display_user_message_on_xbotic(phone, "Bank validation failed. Please check the details and try again.")
        else:
            print(f"Vendor status is {updated_status}, skipping post-addition tasks.")
            text_message = f"Hello {name} {phone} {vpa} {account_number} {ifsc} {pan_status},There is an issue with vendor addition. Status: {updated_status}"

        message = whatsapp_message.twilio_send_text_message(f"+91{number}", text_message)
        print(message.sid)
        return {
            "status": "success"
        }

    except Exception as e:
        print(f"Error handling webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")
    

@router.post("/settlement_status")
async def payment_settlement_issued(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
        print("Webhook payload received:", payload)
        userControllers.update_settlement_status_to_worker(payload=payload, db=db)
        return {
            "status": "success"
        }

    except Exception as e:
        print(f"Error handling webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")