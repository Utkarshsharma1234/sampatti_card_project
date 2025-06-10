import json, os
from fastapi import APIRouter, Depends, Request, HTTPException
import requests
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import userControllers
from dotenv import load_dotenv

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
        payload = await request.json()
        
        print("payload entered")
        print(f"Webhook payload received : {payload}")
        print("payload exit")

        url = "https://xbotic.cbots.live/provider016/webhooks/a0/732e12160d6e4598"

        payload = payload
        headers = {
            'D360-API-KEY': orai_api_key
        }

        response = requests.post(url, headers=headers, json=payload)
        response_data = json.loads(response.text)
        print(response_data)
        return response_data

    except Exception as e:
        print(f"Error in handling the webhook from orai : {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")
