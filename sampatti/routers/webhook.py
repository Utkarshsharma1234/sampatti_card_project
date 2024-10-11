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
        
        # # Extract specific information from the JSON payload
        # # For example, Cashfree sends `order_id`, `payment_status`, `amount`, etc.
        # order_id = payload.get("order_id")
        # payment_status = payload.get("payment_status")
        # amount = payload.get("amount")

        # # Perform your custom logic here based on the received data
        # # For example, you can trigger a script, update a database, etc.
        # if payment_status == "SUCCESS":
        #     print(f"Payment successful for order: {order_id} with amount: {amount}")
        #     # Call your script here, e.g., run some business logic
        # else:
        #     print(f"Payment failed or pending for order: {order_id}")
        
        # # Return a success response back to Cashfree
        # return {"status": "success"}
    
    except Exception as e:
        print(f"Error handling webhook: {e}")
        raise HTTPException(status_code=400, detail="Error processing webhook data")

