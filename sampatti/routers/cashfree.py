import asyncio
from fastapi import APIRouter, Depends
from .. import schemas
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import cashfree_api

router = APIRouter(
    prefix="/cashfree",
    tags=['Cashfree']
)


@router.get("/fetch_vpa/{workerNumber}")
def fetch_vpa(workerNumber : int):
    return cashfree_api.fetch_vpa(workerNumber=workerNumber)

@router.get("/fetch_multiple_vpa/{workerNumber}")
def fetch_multiple_vpa(workerNumber : int):
    return cashfree_api.fetch_multiple_vpa(workerNumber=workerNumber)


@router.get("/payment_link")
def payment_link_generation(db : Session = Depends(get_db)):
    return cashfree_api.payment_link_generation(db)

@router.get("/dynamic_payment_link")
def dynamic_payment_link(employerNumber : int, workerName : str, cashAdvance : int, bonus : int, attendance : int, repayment : int, salary : int, db : Session = Depends(get_db)):
    return cashfree_api.dynamic_payment_link(employerNumber, workerName, cashAdvance, bonus, attendance, repayment, salary, db)

@router.get("/order_status")
def check_order_status(orderId : str):
    return cashfree_api.check_order_status(orderId)

@router.get('/fetch_utr')
def fetch_utr(orderId : str):
    return cashfree_api.fetch_bank_ref(orderId)

@router.get('/vendor_status')
async def check_vendor_status(vendorId : str):

    await asyncio.sleep(10)
    return cashfree_api.check_vendor_status(vendorId)

@router.post("/add_a_vendor")
def add_a_vendor(request : schemas.Vendor):
    return cashfree_api.add_a_vendor(request)

@router.get("/pan_verification")
def pan_verification(pan : str, name : str):
    return cashfree_api.pan_verification(pan, name)


@router.get("/bank_account_verification")
def bank_account_verification(account_number : str, ifsc_code : str):
    return cashfree_api.bank_account_verification(account_number, ifsc_code)
    

@router.get("/unsettled_balance")
def unsettled_balance(db : Session = Depends(get_db)):
    return cashfree_api.unsettled_balance(db)

@router.get("/cash_advance_link")
def cash_advance_link(employerNumber : int, workerName : str, cash_advance : int, repayment_amount : int, repayment_start_month : int, repayment_start_year : int, monthly_salary : int, bonus : int, frequency : int, deduction : int, db : Session = Depends(get_db)):
    return cashfree_api.cash_advance_link(employerNumber, workerName, cash_advance, repayment_amount, repayment_start_month, repayment_start_year, monthly_salary, bonus, frequency, deduction, db)