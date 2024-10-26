from datetime import datetime
from fastapi import HTTPException
import json, uuid, requests, os
from cashfree_pg.api_client import Cashfree
from cashfree_verification.api_client import Cashfree as Cashfree_Verification
from cashfree_verification.models.upi_mobile_request_schema import UpiMobileRequestSchema
from cashfree_verification.models.pan_advance_request_schema import PanAdvanceRequestSchema
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.api_client import Cashfree
from cashfree_pg.models.customer_details import CustomerDetails
from .. import models
from .whatsapp_message import send_whatsapp_message
from .utility_functions import generate_unique_id
from sqlalchemy.orm import Session
from sqlalchemy import update
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import update
from .. import schemas

load_dotenv()
verification_id= os.environ.get('CASHFREE_VERIFICATION_ID')
verification_secret = os.environ.get('CASHFREE_VERIFICATION_SECRET')

pg_id = os.environ.get('CASHFREE_PG_ID')
pg_secret = os.environ.get('CASHFREE_PG_SECRET')

orai_api_key = os.environ.get('ORAI_API_KEY')
orai_namespace = os.environ.get('ORAI_NAMESPACE')


def fetch_vpa(workerNumber : int):
    Cashfree_Verification.XClientId = verification_id
    Cashfree_Verification.XClientSecret = verification_secret
    Cashfree_Verification.XEnvironment = Cashfree_Verification.XProduction
    uuid_value = uuid.uuid4().hex
    
    user_info = UpiMobileRequestSchema(mobile_number= f"{workerNumber}", verification_id = uuid_value)

    api_response = None
    try:
        api_response = Cashfree_Verification().vrs_upi_mobile_verification(user_info, None)
        if not api_response or not api_response.data:
            raise HTTPException(status_code=400, detail="Bad request: No response from API")
        
    except Exception as e:
        # Log the exception and raise a 400 HTTP exception with the error message
        print(e)
        raise HTTPException(status_code=400, detail=f"Bad request: No response from API")
    
    response = dict(api_response.data)
    return response


def fetch_multiple_vpa(workerNumber : int):
    
    uuid_val = generate_unique_id()
    url = "https://api.cashfree.com/verification/upi/mobile"

    payload = {
        "verification_id": uuid_val,
        "mobile_number": f"{workerNumber}",
        "additional_vpas": True
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-client-id": verification_id,
        "x-client-secret": verification_secret
    }

    response = requests.post(url, json=payload, headers=headers)

    print(response.text)
    response_data = json.loads(response.text)
    vpa = response_data.get('vpa')
    additional_vpas = response_data.get('additional_vpas')
    name_at_bank = response_data.get('name_at_bank')
    if name_at_bank is None:
        name_at_bank = "INVALID"
    if additional_vpas is None:
        additional_vpas = []
    additional_vpas.append(vpa)

    multiple_vpa = []
    for vpa in additional_vpas:
        record = {
            "text": vpa,
            "postback": f"data_vpa_upi_id={vpa}"
        }
        multiple_vpa.append(record)
    
    return {
        "name_at_bank" : name_at_bank,
        "vpa_array" : multiple_vpa
    }


# adding a vendor to the cashfree dashboard.

def add_a_vendor(request : schemas.Vendor, db: Session):

    if request.vpa == "None":
        request.vpa = None

    elif request.accountNumber == "None":
        request.accountNumber = None

    uuid_value = uuid.uuid4().hex
    payload = {
    "vendor_id": uuid_value,
    "status": "ACTIVE",
    "name": request.name,
    "email": "johndoe@gmail.com",
    "phone": f"{request.workerNumber}",
    "verify_account": True,
    "dashboard_access": False,
    "schedule_option": 1,
    "kyc_details": {
        "account_type": "INDIVIDUAL",
        "business_type": "Education",
        "pan": request.pan
    }
}
    
    if request.vpa:
        payload["upi"] = {
            "vpa": request.vpa,
            "account_holder": request.name
        }


    elif request.accountNumber:
        payload["bank"] = {
            "account_number": request.accountNumber,
            "account_holder": request.name,
            "ifsc": request.ifsc
        }

    print(payload)
    headers = {
        "X-Client-Id" : pg_id,
        "X-Client-Secret" : pg_secret,
        "Content-Type" : "application/json",
        "x-api-version" : "2023-08-01"
    }

    url = "https://api.cashfree.com/pg/easy-split/vendors"

    response = requests.post(url, json=payload, headers=headers)

    response_data = json.loads(response.text)
    vendorId = response_data.get('vendor_id')
    return {
        "VENDOR_ID" : vendorId
    }


#checking the activation of the vendor

def check_vendor_status(vendorId):

    url = f"https://api.cashfree.com/pg/easy-split/vendors/{vendorId}"

    payload = {}
    headers = {
        'x-client-id': pg_id,
        'x-client-secret': pg_secret,
        'x-api-version': '2022-09-01',
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers, json=payload)
    response_data = json.loads(response.text)
    status = response_data.get('status')
    print(response_data)
    return {
        "STATUS" : status,
        "VENDOR_ID" : vendorId
    }


# fetching the UTR No.

def fetch_bank_ref(order_id):

    url = f"https://api.cashfree.com/pg/orders/{order_id}/payments"

    headers = {
        "accept": "application/json",
        "x-api-version": "2023-08-01",
        "x-client-id": pg_id,
        "x-client-secret": pg_secret
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        response_data = json.loads(response.text)
        bank_ref_no = response_data[0].get('bank_reference')
        print(bank_ref_no)
        return bank_ref_no
    else:
        print(f"Error: {response.status_code}, {response.text}")


# checking the order status
def check_order_status(order_id):

    url = f"https://api.cashfree.com/pg/orders/{order_id}"


    headers = {
        "x-client-id": pg_id,
        "x-client-secret": pg_secret,
        "x-api-version" : "2023-08-01"
    }

    response = requests.get(url, headers=headers)
    response_data = json.loads(response.text)
    order_status = response_data.get('order_status')
    return order_status
    
# pan verification

def pan_verification(pan : str, name : str):
    Cashfree_Verification.XClientId = verification_id
    Cashfree_Verification.XClientSecret = verification_secret
    Cashfree_Verification.XEnvironment = Cashfree_Verification.XProduction
    uuid_val = uuid.uuid4().hex

    pan_schema = PanAdvanceRequestSchema(pan=pan, verification_id=uuid_val, name=name)

    api_response = None
    try:
        api_response = Cashfree_Verification().vrs_pan_advance_verification(pan_schema, None)
        # print(api_response.data)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=f"Bad request: No response from API")
    
    response = dict(api_response.data)
    return response


# payment link generation

def payment_link_generation(db : Session):
    Cashfree.XClientId = pg_id
    Cashfree.XClientSecret = pg_secret
    Cashfree.XEnvironment = Cashfree.XProduction
    x_api_version = "2023-08-01"

    current_month = datetime.now().strftime("%B")
    current_year = datetime.now().year

    payment_ids = []
    total_workers = db.query(models.worker_employer).all()
    
    for item in total_workers:

        if item.employer_number != 916378639230:
            continue
        dummy_number = item.employer_number
        actual_number = int(str(dummy_number)[2:])
        
        customerDetails = CustomerDetails(customer_id= f"{item.worker_number}", customer_phone= f"{actual_number}")
        createOrderRequest = CreateOrderRequest(order_amount = item.salary_amount, order_currency="INR", customer_details=customerDetails)
        try:
            api_response = Cashfree().PGCreateOrder(x_api_version, createOrderRequest, None, None)
            # print(api_response.data)
        except Exception as e:
            print(e)

        response = dict(api_response.data)
        payment_session_id = response["payment_session_id"]

        send_whatsapp_message(employerNumber=item.employer_number, worker_name=item.worker_name, param3=f"{current_month} {current_year}", link_param=payment_session_id, template_name="employer_salary_payment")

        update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == item.worker_number, models.worker_employer.c.employer_number == item.employer_number).values(order_id= response["order_id"])

        db.execute(update_statement)
        db.commit()
        payment_ids.append(payment_session_id)

    return payment_ids


# creating dynamic payment links

def dynamic_payment_link(employerNumber : int, workerNumber : int, bonus : int, db : Session):

    Cashfree.XClientId = pg_id
    Cashfree.XClientSecret = pg_secret
    Cashfree.XEnvironment = Cashfree.XProduction
    x_api_version = "2023-08-01"

    current_month = datetime.now().strftime("%B")
    current_year = datetime.now().year

    entry = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == workerNumber, models.worker_employer.c.employer_number == employerNumber).first()

    existing_bonus_entry = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employerNumber == employerNumber, models.CashAdvanceManagement.worker_id == entry.worker_id).first()
   
    if existing_bonus_entry is None:

        new_entry = models.CashAdvanceManagement(id=generate_unique_id(), employerNumber= employerNumber, worker_id = entry.worker_id, employer_id = entry.employer_id, bonus = bonus)
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)

    else:
        update_statement = update(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employerNumber == employerNumber, models.CashAdvanceManagement.worker_id == entry.worker_id).values(bonus=bonus)

        db.execute(update_statement)
        db.commit()

    actual_number = int(str(employerNumber)[2:])
    total_salary = entry.salary_amount + bonus
    customerDetails = CustomerDetails(customer_id= f"{workerNumber}", customer_phone= f"{actual_number}")
    createOrderRequest = CreateOrderRequest(order_amount = total_salary, order_currency="INR", customer_details=customerDetails)
    try:
        api_response = Cashfree().PGCreateOrder(x_api_version, createOrderRequest, None, None)
        # print(api_response.data)
    except Exception as e:
        print(e)

    response = dict(api_response.data)
    payment_session_id = response["payment_session_id"]

    send_whatsapp_message(employerNumber=employerNumber, worker_name=entry.worker_name, param3=f"{current_month} {current_year}", link_param=payment_session_id, template_name="revised_salary_link_template")

    update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == workerNumber, models.worker_employer.c.employer_number == employerNumber).values(order_id= response["order_id"])

    db.execute(update_statement)
    db.commit()


# settle the unsettled balance on cashfree to the worker's account.

def unsettled_balance(db : Session):

    
    headers = {
        'x-client-id': pg_id,
        'x-client-secret': pg_secret,
        'Content-Type': 'application/json'
    }

    total_workers = db.query(models.worker_employer).all()
    for transaction in total_workers:
        
        status = check_order_status(order_id=transaction.order_id)
        bonus = 0
        existing_bonus_entry = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employerNumber==transaction.employer_number, models.CashAdvanceManagement.worker_id==transaction.worker_id).first()

        if existing_bonus_entry is not None:
            bonus += existing_bonus_entry.bonus
        
        total_salary = transaction.salary_amount + bonus
        if(status == "PAID"):

            url = f'https://api.cashfree.com/api/v2/easy-split/orders/{transaction.order_id}/split'

            data = {
                "split": [
                    {
                        "vendorId": transaction.vendor_id,
                        "amount" : total_salary,
                        "percentage" : None
                    }
                ],
                "splitType" : "ORDER_AMOUNT"
            }

            json_data = json.dumps(data)
            response = requests.post(url, headers=headers, data=json_data)

            print(response.text)

        else:
            continue

