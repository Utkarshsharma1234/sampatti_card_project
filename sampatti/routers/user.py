import os, uuid
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from .. import schemas, models
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import onboarding_agent, rag_funcs, userControllers
from ..controllers import employment_contract_gen, salary_summary_gen, cash_advance_agent, super_agent
from datetime import datetime, timedelta
from ..controllers import whatsapp_message, talk_to_agent_excel_file, uploading_files_to_spaces
from ..controllers import utility_functions, rag_funcs, onboarding_tasks, cash_advance_management
from pydantic import BaseModel
from typing import Optional


router = APIRouter(
    prefix="/user",
    tags=['users']
)

current_date = datetime.now().date()
first_day_of_current_month = datetime.now().replace(day=1)
last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
previous_month = last_day_of_previous_month.strftime("%B")
current_year = datetime.now().year


class WorkerOnboardingRequest(BaseModel):
    worker_number: int
    employer_number: int
    UPI: Optional[str] = ""
    bank_account_number: Optional[str] = ""
    ifsc_code: Optional[str] = ""
    pan_number: str
    bank_passbook_image: Optional[str] = ""
    pan_card_image: Optional[str] = ""
    salary: int
    referral_code : Optional[str] = ""

@router.get("/download_salary_slip")
def download_worker_salary_slip(workerNumber : int, month : str, year : int, db : Session = Depends(get_db)):
    return userControllers.download_worker_salary_slip(workerNumber, month, year, db)

@router.post("/employer/create")
def create_employer(request : schemas.Employer, db : Session = Depends(get_db)):
    return userControllers.create_employer(request, db)

@router.post('/domestic_worker/create')
def create_domestic_worker(request : schemas.Domestic_Worker, db: Session = Depends(get_db)):
    return userControllers.create_domestic_worker(request, db)

@router.post('/domestic_worker/create/account_number')
def create_worker_account_number(request : schemas.Domestic_Worker, db: Session = Depends(get_db)):
    return userControllers.create_worker_account_number(request,db)

@router.post('/create_relation')
def create_relation(request : schemas.Worker_Employer, db : Session = Depends(get_db)):
    return userControllers.create_relation(request, db)

@router.get("/check_existence")
def check_existence(employerNumber : int, workerNumber : int, db : Session = Depends(get_db)):
    return userControllers.check_existence(employerNumber, workerNumber,db)

@router.get("/worker_details")
def get_worker_id(workerNumber : int, db : Session = Depends(get_db)):
    return userControllers.get_worker_id(workerNumber, db)

@router.get("/check_worker")
def check_worker(workerNumber : int, db : Session = Depends(get_db)):
    return userControllers.check_worker(workerNumber, db)

@router.get("/get_number")
def number_regex(numberString : str):
    return userControllers.number_regex(numberString)

@router.get("/extract_salary")
def extract_salary(salary_amount : str):
    return userControllers.extract_salary(salary_amount)

@router.post('/talk_to_agent/create')
def create_talk_to_agent_employer(request : schemas.talkToAgent, db : Session = Depends(get_db)):
    return userControllers.create_talk_to_agent_employer(request, db)

@router.post("/salary")
def insert_salary(request : schemas.Salary, db : Session = Depends(get_db)):
    return userControllers.insert_salary(request, db)

@router.post("/send_worker_salary_slips")
def send_worker_salary_slips(db : Session = Depends(get_db)):
    return userControllers.send_worker_salary_slips(db)

@router.put("/update_salary")
def update_worker_salary(employerNumber : int, workerName : str, salary : int, db : Session = Depends(get_db)):
    return userControllers.update_worker_salary(employerNumber, workerName, salary, db)

@router.get("/send_employer_invoice")
def send_employer_invoice(employerNumber : int, orderId : str, db : Session = Depends(get_db)):
    return userControllers.send_employer_invoice(employerNumber, orderId, db)
    
@router.get('/salary_payment_reminder')
def salary_payment_reminder(db : Session = Depends(get_db)):
    return userControllers.salary_payment_reminder(db)

@router.get("/send_greetings")
def send_greetings_message(db : Session = Depends(get_db)):
    return userControllers.send_greetings(db)

@router.get('/generate_talk_to_agent_sheet')
def generate_sheet():
    return talk_to_agent_excel_file.upload_data_to_google_sheets()

@router.post("/salary_details")
def create_salary_details(employerNumber : int, orderId : str, db : Session = Depends(get_db)):
    return userControllers.update_salary_details(employerNumber, orderId, db)

@router.post("/cash_advance_entry/create")
def create_cash_advance_entry(employerNumber : int, workerName : str, cash_advance : int, repayment_amount : int, repayment_start_month : int, repayment_start_year : int, frequency : int,  bonus : int, monthly_salary : int, deduction : int, db : Session = Depends(get_db)):
    return userControllers.create_cash_advance_entry(employerNumber, workerName, cash_advance, repayment_amount, repayment_start_month, repayment_start_year, frequency, monthly_salary, bonus, deduction, db)


@router.post("/cash_advance_record/create")
def cash_advance_record(employerNumber : int, workerName : str, cash_advance : int, repayment_amount : int, repayment_start_month : int, repayment_start_year : int, frequency : int, monthly_salary: int, bonus : int, deduction : int, db : Session = Depends(get_db)):
    return userControllers.cash_advance_record(employerNumber, workerName, cash_advance, repayment_amount, repayment_start_month, repayment_start_year, frequency, monthly_salary, bonus, deduction, db)

@router.post("/salary_record/create")
def create_salary_record(employerNumber : int, workerName : str, currentSalary : int, modifiedSalary : int, db : Session = Depends(get_db)):
    return userControllers.create_salary_record(employerNumber, workerName, currentSalary, modifiedSalary, db)

@router.get("/existing_advance_entry")
def check_existing_cash_advance_entry(employerNumber : int, workerNumber : int, db : Session = Depends(get_db)):
    return userControllers.check_existing_cash_advance_entry(employerNumber, workerNumber, db)

@router.get("/extract_date")
def extract_date(date_str : str):
    return utility_functions.extract_date(date_str)

@router.post("/send_audio_message")
def send_audio_message(text : str, user_language : str, employerNumber : int):
    return userControllers.send_audio_message(text, user_language, employerNumber)

@router.get("/get_all_workers")
def find_all_workers(employerNumber : int, db : Session = Depends(get_db)):
    return userControllers.find_all_workers(employerNumber, db)

@router.post('/process_audio')
def process_audio(user_input : str, user_language : str, employerNumber : int, workerName: str, db : Session = Depends(get_db)):
    return userControllers.process_audio(user_input, user_language, employerNumber, workerName, db)

@router.post('/extract_name')
async def extract_name(file_url: str, employerNumber : int): 
    return await userControllers.extract_name(file_url, employerNumber,)

@router.get("/get_next_question")
def get_next_question(respondentId : str, workerId : str, questionId : int, answer : str, surveyId : int, db : Session = Depends(get_db)):
    return utility_functions.get_next_question(respondentId, workerId, questionId, answer, surveyId, db)

@router.get("/get_translated_text")
async def get_transalated_text(file_url: str):
    return await userControllers.get_transalated_text(file_url)

@router.get("/send_question_audio")
def send_question_audio(employerNumber : int, questionId : int, surveyId : int, language : str, db : Session = Depends(get_db)):
    return userControllers.send_question_audio(employerNumber, questionId, surveyId, language, db)

@router.get("/get_languages")
def get_all_languages():
    return userControllers.get_all_languages()

@router.get("/get_respondent_id")
def get_respondent_id():
    return userControllers.get_respondent_id()

@router.get("/get_all_messages")
def create_confirmation_message(workerId : str, respondentId : str, surveyId : int, db : Session = Depends(get_db)):
    return userControllers.create_confirmation_message(workerId, respondentId, surveyId, db)

@router.post("/mark_leave")
def mark_leave(employerNumber : int, workerName : str, leaves : int, db : Session = Depends(get_db)):
    return userControllers.mark_leave(employerNumber, workerName, leaves, db)

@router.get("/calculate_salary_amount")
def calculate_salary_amount(leaves : int, deduction : int, employerNumber : int, workerName : str, db : Session = Depends(get_db)):
    return userControllers.calculate_salary_amount(leaves, deduction, employerNumber, workerName, db)

@router.get("/process_attendance")
def process_attendance_with_llm(employerNumber : int, workerName: str, user_input : str, db : Session = Depends(get_db)):
    return userControllers.process_attendance_with_llm(employerNumber, workerName, user_input, db)

@router.post("/store_attendance")
def add_attendance_records(action: str, dates: str, worker_id: str, employer_id: str, db: Session = Depends(get_db)):
    return userControllers.add_attendance_records(action, dates, worker_id, employer_id, db)

@router.post("/todays_leave")
def mark_leave(employerNumber : int, workerName : str, db: Session = Depends(get_db)):
    return userControllers.mark_leave(employerNumber, workerName, db)   

@router.get("/introduction_video")
def send_introduction_video(employerNumber : int):
    return whatsapp_message.send_intro_video(employerNumber, "send_video_template")

@router.post("/rag_process_query")
def rag_process_query(workerId : str, query : str):
    return rag_funcs.get_response(workerId, query)

@router.get("/rag_conversation_history")
def get_conversation_history(workerId : str):
    return rag_funcs.get_conversation_history(workerId)

@router.get("/extract_pan_card")
def extract_pan_card_details(image_url):
    return userControllers.extract_pan_card_details(image_url)

@router.get("/extract_passbook_details")
def extract_passbook_details(image_url):
    return userControllers.extract_passbook_details(image_url)

@router.post("/onboarding_worker_sheet/create")
def create_worker_details_onboarding(worker_number: int, employer_number : int, UPI: str, bank_account_number: str, ifsc_code: str, pan_number: str, bank_passbook_image: str, pan_card_image: str, salary : int):
    return talk_to_agent_excel_file.create_worker_details_onboarding(worker_number, employer_number, UPI, bank_account_number, ifsc_code, pan_number, bank_passbook_image, pan_card_image, salary)




@router.post("/upload_image_to_server")
def upload_image_from_url(image_url: str, object_name: str):
    return uploading_files_to_spaces.upload_image_from_url(image_url, object_name)


@router.get("/survey_model")
def process_survey_input(user_name: str, worker_number: str, user_input: str, survey_id: int, db: Session = Depends(get_db)):
    return userControllers.process_survey_input(user_name, worker_number, user_input, survey_id, db)

@router.post("/generate_employment_contract")
def generate_employment_contract(employerNumber: int, workerNumber : int, upi : str, accountNumber : str, ifsc : str, panNumber: str, name : str, salary : int, db : Session = Depends(get_db)): 
    return userControllers.generate_employment_contract(employerNumber, workerNumber, upi, accountNumber, ifsc, panNumber, name, salary, db)

@router.post("/add_vendors_to_cashfree_from_sheet")
def run_tasks_till_add_vendor():
    return onboarding_tasks.run_tasks_till_add_vendor()


@router.post("/process_vendor_status_from_sheet")
def run_tasks_after_vendor_addition():
    return onboarding_tasks.run_tasks_after_vendor_addition()

@router.get("/get_worker_employer_relation")
def get_worker_employer_relation(employerNumber : int, workerName : str, db : Session = Depends(get_db)):
    
    relation = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name == workerName).first()

    return {"response": dict(relation._mapping) if relation else "INVALID"}

@router.get("/chat_id")
def get_chat_id():
    return {"id" : f"{uuid.uuid4()}"}


@router.post("/process_advance_query")
def process_advance_query(chatId, query, workerId, employerId, db:Session = Depends(get_db)):
    return cash_advance_management.process_advance_query(chatId, query, workerId, employerId, db)

@router.post("/is_worker_onboarded")
def is_employer_present(employer_number: str, db: Session = Depends(get_db)):
    return userControllers.is_employer_present(employer_number, db)

@router.get("/salary_summary_employer")
def generate_salary_records_all_worker(employerNumber: int, db: Session = Depends(get_db)):
    return salary_summary_gen.generate_salary_records_all_worker(employerNumber, db)

@router.get("/salary_summary_employer_worker")
def generate_salary_record(employerNumber: int, workerName: str, db: Session = Depends(get_db)):
    return salary_summary_gen.generate_salary_record(employerNumber, workerName, db)

@router.get("/ai_agents_queryExecutor")
def queryExecutor(employer_number: int, typeofMessage : str, query : str, mediaId : str):
    return onboarding_agent.queryExecutor(employer_number, typeofMessage, query, mediaId)


@router.post("/ai_agent/onboarding_worker_sheet/create")
def worker_onboarding(payload: WorkerOnboardingRequest):
    return talk_to_agent_excel_file.create_worker_details_onboarding(payload.worker_number, payload.employer_number, payload.UPI, payload.bank_account_number, payload.ifsc_code, payload.pan_number, payload.bank_passbook_image, payload.pan_card_image, payload.salary, payload.referral_code)

@router.post("/cash_advance_gage")
def queryE(employer_number: int, typeofMessage: str, query: str, mediaId: str = ""):
    return cash_advance_agent.queryE(employer_number, typeofMessage, query, mediaId)

@router.post("/super_agent")
def super_agent_query(employer_number: int, type_of_message: str, query: str, media_id: str = ""):
    return super_agent.super_agent_query(employer_number, type_of_message, query, media_id)

@router.post("/add_in_employer")
def populate_db(employer_number: int, worker_id: str, db: Session = Depends(get_db)):
    return userControllers.populate_db(employer_number, worker_id, db)


@router.post("/send_referral_code")
def generate_and_send_referral_code_to_employers(db: Session = Depends(get_db)):
    return userControllers.generate_and_send_referral_code_to_employers(db)

