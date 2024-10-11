from fastapi import APIRouter, FastAPI, Request, HTTPException
import json

router = APIRouter(
    prefix="/webhook",
    tags=['webhook']
)

# Define the webhook route
@router.post("/cashfree")
async def cashfree_webhook(request: Request):
    try:
        # Receive and parse the JSON body
        payload = await request.json()
        
        # Log the received payload (for debugging)
        print("Webhook payload received:", payload)
        
        customer_id = payload['data']['customer_details'].get('customer_id')
        customer_phone = payload['data']['customer_details'].get('customer_phone')
        order_id = payload['data']['order'].get('order_id')
        bank_reference = payload['data']['payment'].get('bank_reference')
        payment_status = payload['data']['payment'].get('payment_status')

        # Print the extracted details for debugging
        print(f"Customer ID: {customer_id}")
        print(f"Customer Phone: {customer_phone}")
        print(f"Order ID: {order_id}")
        print(f"Bank Reference: {bank_reference}")
        print(f"Payment Status: {payment_status}")

        if payment_status == "SUCCESS":
            print(f"Payment successful for order: {order_id}")
            
        return {"status": "success"}
    
    except Exception as e:
        print(f"Error handling webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")

