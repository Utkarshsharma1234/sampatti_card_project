import calendar
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
from .utility_functions import generate_unique_id, current_month, current_date, current_year, previous_month
from sqlalchemy.orm import Session
from sqlalchemy import update
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import func
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

def add_a_vendor(request : schemas.Vendor):

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

    try:

        url = f"https://api.cashfree.com/pg/easy-split/vendors/{vendorId}"

        payload = {}
        headers = {
            'x-client-id': pg_id,
            'x-client-secret': pg_secret,
            'x-api-version': '2022-09-01',
            'Content-Type': 'application/json'
        }

        response = requests.get(url, headers=headers, data=payload)
        response_data = json.loads(response.text)
        print(response_data)
        return response_data
    
    except Exception as e:
        print(f"Error checking vendor status: {e}")

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
        print("Response Data: ",response_data)
        if response_data and len(response_data) > 0:
            bank_ref_no = response_data[0].get('bank_reference')
            print("Bank Reference Number: ",bank_ref_no)
            return bank_ref_no
        else:
            print(f"No payment data found for order_id: {order_id}")
            return None
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None


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
    return response_data
    
# pan verification

def pan_verification(pan : str, name : str):
    Cashfree_Verification.XClientId = verification_id
    Cashfree_Verification.XClientSecret = verification_secret
    Cashfree_Verification.XEnvironment = Cashfree_Verification.XProduction
    uuid_val = uuid.uuid4().hex

    pan_schema = PanAdvanceRequestSchema(pan=pan, verification_id=uuid_val, name=name)

    try:
        api_response = Cashfree_Verification().vrs_pan_advance_verification(pan_schema, None)
        # print(api_response.data)
        response = dict(api_response.data)
        return response
    except Exception as e:
        print(e)
        pass


# payment link generation

def payment_link_generation(db : Session):
    Cashfree.XClientId = pg_id
    Cashfree.XClientSecret = pg_secret
    Cashfree.XEnvironment = Cashfree.XProduction
    x_api_version = "2023-08-01"

    cr_month = current_month()
    cr_year = current_year()
    
    month_to_number = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9,
        "October": 10, "November": 11, "December": 12,
        "sampatti" : 20
    }

    payment_ids = []
    total_relations = db.query(models.worker_employer).all()
    
    for item in total_relations:

        if item.employer_number == 917015645195 or item.employer_number == 919731011117 or item.employer_number == 917022878346:
            continue
        
        else:
            dummy_number = item.employer_number
            actual_number = int(str(dummy_number)[2:])
            
            customerDetails = CustomerDetails(customer_id= f"{item.worker_number}", customer_phone= f"{actual_number}")

            total_salary = item.salary_amount
            number_of_month_days = calendar.monthrange(cr_year, datetime.now().month)[1]

            note = {'salary' : item.salary_amount, 'cashAdvance' : 0, 'bonus' : 0, 'repayment' : 0, 'deduction' : 0, 'attendance' : number_of_month_days,
            'repaymentStartMonth': "September",
            'repaymentStartYear': 2025,
            'frequency': 1}

            order_splits = [
                {
                    "vendor_id": f"{item.vendor_id}",
                    "amount": total_salary
                }
            ]
            note_string = json.dumps(note)
            createOrderRequest = CreateOrderRequest(order_amount = total_salary, order_currency="INR", customer_details=customerDetails, order_note=note_string, order_splits=order_splits)
            try:
                api_response = Cashfree().PGCreateOrder(x_api_version, createOrderRequest, None, None)
                response = dict(api_response.data)
                payment_session_id = response["payment_session_id"]

                send_whatsapp_message(employerNumber=item.employer_number, worker_name=item.worker_name, param3=f"{cr_month} {cr_year}", link_param=payment_session_id, template_name="payment_link_adjust_salary")

                update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == item.worker_number, models.worker_employer.c.employer_number == item.employer_number).values(order_id= response["order_id"])

                db.execute(update_statement)
                db.commit()
                payment_ids.append(payment_session_id)


            except Exception as e:
                print(e)

    return payment_ids


# creating dynamic payment links

def dynamic_payment_link(employerNumber : int, workerName : str, cashAdvance : int, bonus : int, attendance : int, repayment : int, salary : int, db : Session):

    Cashfree.XClientId = pg_id
    Cashfree.XClientSecret = pg_secret
    Cashfree.XEnvironment = Cashfree.XProduction
    x_api_version = "2023-08-01"

    cr_month = current_month()
    cr_year = current_year()

    total_salary = cashAdvance + bonus + salary - repayment

    item = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    workerId = item.worker_id
    employerId = item.employer_id

    note = {'salary' : salary, 'cashAdvance' : cashAdvance, 'bonus' : bonus, 'repayment' : repayment, 'attendance' : attendance}

    note_string = json.dumps(note)
    actual_number = int(str(employerNumber)[2:])

    customerDetails = CustomerDetails(customer_id= f"{item.worker_number}", customer_phone= f"{actual_number}")
    createOrderRequest = CreateOrderRequest(order_amount = total_salary, order_currency="INR", customer_details=customerDetails, order_note=note_string)
    try:
        api_response = Cashfree().PGCreateOrder(x_api_version, createOrderRequest, None, None)
        # print(api_response.data)
    except Exception as e:
        print(e)

    response = dict(api_response.data)
    payment_session_id = response["payment_session_id"]

    send_whatsapp_message(employerNumber=employerNumber, worker_name=item.worker_name, param3=f"{cr_month} {cr_year}", link_param=payment_session_id, template_name="revised_salary_link_template")

    update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).values(order_id= response["order_id"])

    db.execute(update_statement)
    db.commit()

    existing_cash_advance_entry = db.query(models.CashAdvanceManagement).filter(models.CashAdvanceManagement.worker_id == workerId, models.CashAdvanceManagement.employer_id == employerId).first()

    if existing_cash_advance_entry is None:
        return {"Link sent successfully."}
    
    total_advance = existing_cash_advance_entry.cashAdvance + existing_cash_advance_entry.currentCashAdvance

    update_advance = update(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == workerId, models.CashAdvanceManagement.employer_id == employerId).values(cashAdvance = total_advance, currentCashAdvance = 0, bonus = 0, attendance = None)

    db.execute(update_advance)
    db.commit()


# settle the unsettled balance on cashfree to the worker's account.

def unsettled_balance(db : Session):

    
    headers = {
        'x-client-id': pg_id,
        'x-client-secret': pg_secret,
        'Content-Type': 'application/json'
    }


    total_records = db.query(models.worker_employer).all()

    for transaction in total_records:

        if transaction.order_id == "sample":
            continue
        
        order_info = check_order_status(transaction.order_id)
        totalAmount = order_info["order_amount"]

        url = f'https://api.cashfree.com/api/v2/easy-split/orders/{transaction.order_id}/split'

        data = {
            "split": [
                {
                    "vendorId": transaction.vendor_id,
                    "amount" : totalAmount,
                    "percentage" : None
                }
            ],
            "splitType" : "ORDER_AMOUNT"
        }

        json_data = json.dumps(data)
        response = requests.post(url, headers=headers, data=json_data)
        print(response.text)
    return {
        "message" : "Splits created."
    }

def bank_account_verification(account_number : str, ifsc_code : str):

    url = "https://api.cashfree.com/verification/bank-account/sync"

    payload = {
        "bank_account": f"{account_number}",
        "ifsc": f"{ifsc_code}"
    }

    headers = {
        "x-client-id": verification_id,
        "x-client-secret": verification_secret,
        "Content-Type": "application/json"
    }

    response = requests.request("POST", url, json=payload, headers=headers)

    print(response.text)
    response_data = json.loads(response.text)
    return response_data


def cash_advance_link(
    employerNumber: int,
    workerName: str,
    cash_advance: int,
    repayment_amount: int,
    monthly_salary: int,
    bonus: int,
    deduction: int,
    repayment_start_month: int | None,
    repayment_start_year: int | None,
    frequency: int,
    attendance: int,
    db: Session,
):

    Cashfree.XClientId = pg_id
    Cashfree.XClientSecret = pg_secret
    Cashfree.XEnvironment = Cashfree.XProduction
    x_api_version = "2023-08-01"

    ps_month = previous_month()
    month  = ""
    year = ""

    day_only = current_date().day
    if(abs(31-day_only) >= abs(1-day_only)):
        month = ps_month
        if month == "December":
            year = current_year() - 1

        else:
            year = current_year()

    else:
        month = current_month()
        year = current_year()


    total_salary = cash_advance + bonus + monthly_salary - repayment_amount - deduction

    item = db.query(models.worker_employer).filter(func.lower(models.worker_employer.c.worker_name) == workerName.strip().lower(), models.worker_employer.c.employer_number == employerNumber).first()

    note = {
        'salary': monthly_salary,
        'cashAdvance': cash_advance,
        'bonus': bonus,
        'repayment': repayment_amount,
        'deduction': deduction,
        'attendance': attendance,
        'repaymentStartMonth': repayment_start_month,
        'repaymentStartYear': repayment_start_year,
        'frequency': frequency,
    }

    order_splits = [
        {
            "vendor_id": item.vendor_id,
            "amount": total_salary
        }
    ]
    note_string = json.dumps(note)
    actual_number = int(str(employerNumber)[2:])

    customerDetails = CustomerDetails(customer_id= f"{item.worker_number}", customer_phone= f"{actual_number}")
    createOrderRequest = CreateOrderRequest(order_amount = total_salary, order_currency="INR", customer_details=customerDetails, order_note=note_string, order_splits=order_splits)

    try:
        api_response = Cashfree().PGCreateOrder(x_api_version, createOrderRequest, None, None)
        response = dict(api_response.data)
        payment_session_id = response["payment_session_id"]
        
        # Extract values that are JSON serializable
        clean_response = {
            "cf_order_id": str(response.get("cf_order_id", "")),
            "order_id": str(response.get("order_id", "")),
            "order_amount": float(response.get("order_amount", 0)),
            "order_status": response.get("order_status", ""),
            "payment_session_id": response.get("payment_session_id", ""),
            "order_note": response.get("order_note", ""),
        }

        send_whatsapp_message(employerNumber=employerNumber, worker_name=item.worker_name, param3=f"{month} {year}", link_param=payment_session_id, template_name="revised_salary_link_template")

        update_statement = update(models.worker_employer).where(
            (models.worker_employer.c.worker_name == workerName) &
            (models.worker_employer.c.employer_number == employerNumber)
        ).values(order_id=response["order_id"])
        db.execute(update_statement)
        db.commit()

        print("Order created successfully:", clean_response)
        return clean_response   # ✅ Always return clean JSON dict

    except Exception as e:
        print(e)


def fetch_payment_details(order_id):

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
        print("Response Data: ",response_data)
        return response_data
    else:
        print(f"Error: {response.status_code}, {response.text}")

def create_cashfree_beneficiary(employer_number: int, upi_id: str, db : Session) -> dict:
    """
    Create beneficiary on Cashfree for cashback payments
    """
    try:
        employer = db.query(models.Employer).filter(models.Employer.employerNumber == employer_number).first()
                
        beneficiary_id = "BENEFICIARY_" + str(employer_number) + "_" + generate_unique_id(6)
        
        employer_number_str = str(employer_number)
        phone_number = ""
        if len(employer_number_str) > 10 and employer_number_str.startswith('91'):
            phone_number = employer_number_str[2:]  # Remove first 2 digits (91)
        else:
            phone_number = employer_number_str

        print("Phone Number: ", phone_number)

        
        payload = {
            "beneficiary_id": beneficiary_id,
            "beneficiary_name": "SAMPATTI CARD USER",
            "beneficiary_instrument_details": {
                "vpa": upi_id
            },
            "beneficiary_contact_details": {
                "beneficiary_email": "support@sampatticard.in",
                "beneficiary_phone": phone_number,
                "beneficiary_country_code": "+91"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-version": "2024-01-01",
            "x-client-id": verification_id,
            "x-client-secret": verification_secret
        }

        response = requests.post("https://api.cashfree.com/payout/beneficiary", headers=headers, json=payload)

        print("Create Beneficiary Response: ", response.text)
        if response.status_code == 200:

            print("Beneficiary created successfully.")
            employer.beneficiaryId = str(beneficiary_id)
            db.commit()
            db.refresh(employer)
            
            return {
                "status": "success",
                "beneficiary_id": beneficiary_id,
                "message": "Beneficiary created successfully"
            }
        else:

            print("Failed to create beneficiary.")
            employer.beneficiaryId = "BENEFICIARY_FAILED"
            db.commit()
            db.refresh(employer)
        
            return {
                "status": "error",
                "message": f"Failed to create beneficiary: {response.text}"
            }
                
    except Exception as e:
        return {"status": "error", "message": f"Error creating beneficiary: {str(e)}"}


def transfer_cashback_amount(beneficiary_id: str, amount: int = None, transfer_mode: str = "upi") -> dict:

    try:
        transfer_amount = amount 
        transfer_id = f"C_{beneficiary_id}"
        print("Transfer Amount: ", transfer_amount)
        print("Beneficiary ID: ", beneficiary_id)
            
        payload = {
            "transfer_id": transfer_id,
            "transfer_amount": transfer_amount,
            "beneficiary_details": {
                "beneficiary_id": beneficiary_id
            },
            "transfer_mode": transfer_mode
        }

        header = {
            "Content-Type": "application/json",
            "x-api-version": "2024-01-01",
            "x-client-id": verification_id,
            "x-client-secret": verification_secret
        }
            
        response = requests.post(
            "https://api.cashfree.com/payout/transfers",
            headers=header,
            json=payload
        )
            
        if response.status_code == 200:
            return {
                "status": "success",
                "transfer_id": transfer_id,
                "amount": transfer_amount,
                "message": "Cashback transferred successfully"
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to transfer cashback: {response.text}"
            }
                
    except Exception as e:
        return {"status": "error", "message": f"Error transferring cashback: {str(e)}"}

