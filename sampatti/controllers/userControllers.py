import html, tempfile, os, re, requests, math, uuid, json
from fastapi import File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import SQLAlchemyError
from .. import models, schemas
from .utility_functions import generate_unique_id, exact_match_case_insensitive, fuzzy_match_score, current_month, previous_month, current_date, current_year, call_sarvam_api, extracted_info_from_llm, send_audio, extracted_info_from_llm, call_sarvam_api, translate_text_sarvam, determine_attendance_period, question_language_audio
from ..controllers import employer_invoice_gen, cashfree_api, uploading_files_to_spaces, whatsapp_message, salary_slip_generation
from sqlalchemy.orm import Session
from pydub import AudioSegment
from datetime import datetime, date
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from PIL import Image
from io import BytesIO
import json
import logging

load_dotenv()
openai_api_key = os.environ.get('OPENAI_API_KEY')
google_api_key = os.environ.get('GOOGLE_API_KEY')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sarvam_api_key = os.environ.get('SARVAM_API_KEY')
# creating the employer
def create_employer(request : schemas.Employer, db: Session):

    employerNumber = request.employerNumber

    employer = db.query(models.Employer).filter(models.Employer.employerNumber == employerNumber).first()

    if not employer :
        unique_id = generate_unique_id()
        new_user = models.Employer(id= unique_id, employerNumber = employerNumber)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    
    else:
        return employer


# creating a domestic worker
def create_domestic_worker(request : schemas.Domestic_Worker, db: Session):

    unique_id = generate_unique_id()
    new_worker = models.Domestic_Worker(id=unique_id, name = request.name, email = request.email, workerNumber = request.workerNumber, panNumber = request.panNumber, upi_id = request.upi_id, accountNumber = None, ifsc = None, vendorId = None)
    db.add(new_worker)
    db.commit()
    db.refresh(new_worker)
    return new_worker

# creating the worker from account number and customer care number

def create_worker_account_number(request : schemas.Domestic_Worker, db: Session):

    existing_worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == request.workerNumber).first()

    if request.accountNumber == "None":
        request.accountNumber = None
        request.ifsc = None

    elif request.upi_id == "None":
        request.upi_id = None
   
    if not existing_worker:

        unique_id = generate_unique_id()
        new_worker = models.Domestic_Worker(id=unique_id, name = request.name, email = request.email, workerNumber = request.workerNumber, panNumber = request.panNumber, upi_id =request.upi_id, accountNumber = request.accountNumber, ifsc = request.ifsc)

        db.add(new_worker)
        db.commit()
        db.refresh(new_worker)
        return new_worker
    
    else:
        return {"message" : "WORKER_ALREADY_ONBOARDED"}
    

# assigning the vendor id to the worker in the domestic worker table.
def assign_vendor_id(workerNumber : int, vendorId : str, db : Session):

    update_statement = update(models.Domestic_Worker).where(models.Domestic_Worker.workerNumber == workerNumber).values(vendorId = vendorId)
    db.execute(update_statement)
    db.commit()


# creating a relation between employer and worker.
def create_relation(request : schemas.Worker_Employer, db: Session):

    unique_id = generate_unique_id()
    worker_employer_relation = insert(models.worker_employer).values(
        id=unique_id,
        worker_number=request.workerNumber,
        employer_number=request.employerNumber,
        vendor_id=request.vendorId,
        salary_amount=request.salary,
        worker_name=request.worker_name,
        employer_id=request.employer_id,
        worker_id = request.worker_id
    )

    with db.begin():
        db.execute(worker_employer_relation)
    return {
        "MESSAGE" : "SUCCESSFUL"
    }

#deleting the relation
def delete_relation(workerNumber: int, employerNumber: int, db: Session):

    field = delete(models.worker_employer).where(
        models.worker_employer.c.worker_number == workerNumber,
        models.worker_employer.c.employer_number == employerNumber
    )

    with db.begin():
        result = db.execute(field)

    return {"MESSAGE": "Record deleted successfully."}

def create_message_log(request : schemas.Message_log_Schema, db  :Session):

    existing_message = db.query(models.MessageLogSystem).where(models.MessageLogSystem.employerNumber==request.employerNumber).where(models.MessageLogSystem.workerNumber==request.workerNumber).first()

    if not existing_message:

        unique_id = generate_unique_id()
        new_message = models.MessageLogSystem(id = unique_id, employerNumber = request.employerNumber, date=f"{current_date()}", lastMessage=request.lastMessage, workerNumber= request.workerNumber, workerName = request.workerName)
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
        return new_message
    
    else:
        update_statement = update(models.MessageLogSystem).where(models.MessageLogSystem.workerNumber == request.workerNumber).where(models.MessageLogSystem.employerNumber==request.employerNumber).values(lastMessage=request.lastMessage)

        db.execute(update_statement)
        db.commit()


def update_worker(oldNumber : int, newNumber : int, db : Session):

    update_statement = update(models.Domestic_Worker).where(models.Domestic_Worker.workerNumber == oldNumber).values(workerNumber=newNumber)

    db.execute(update_statement)
    db.commit()


def insert_salary(request : schemas.Salary, db : Session):

    workerNumber = request.workerNumber
    employerNumber = request.employerNumber
    salary = request.salary_amount

    update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == workerNumber).where(models.worker_employer.c.employer_number == employerNumber).values(salary_amount=salary)

    db.execute(update_statement)
    db.commit()

    return {"salary credited successfully."}


def create_talk_to_agent_employer(request : schemas.talkToAgent, db:Session):

    existing_entity = db.query(models.TalkToAgentEmployer).where(models.TalkToAgentEmployer.employerNumber== request.employerNumber).where(models.TalkToAgentEmployer.workerNumber == request.workerNumber).first()

    if not existing_entity:
        new_user = models.TalkToAgentEmployer(id = generate_unique_id(), date = current_date(), employerNumber = request.employerNumber, workerNumber = request.workerNumber, worker_bank_name = request.worker_bank_name, worker_pan_name = request.worker_pan_name, vpa = request.vpa, issue = request.issue)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    
    else:
        update_statement = update(models.TalkToAgentEmployer).where(models.TalkToAgentEmployer.workerNumber == request.workerNumber).where(models.TalkToAgentEmployer.employerNumber==request.employerNumber).values(date = current_date(), employerNumber = request.employerNumber, workerNumber = request.workerNumber, worker_bank_name = request.worker_bank_name, worker_pan_name = request.worker_pan_name, vpa = request.vpa, issue = request.issue)

        db.execute(update_statement)
        db.commit()
    
def check_existence(employerNumber : int, workerNumber : int, db : Session):

    field = db.query(models.worker_employer).where(models.worker_employer.c.worker_number == workerNumber).where(models.worker_employer.c.employer_number == employerNumber).first()

    if not field:
        return {"message" : "VALID"}
    else : 
        return {"message" : "INVALID"}
    

def check_worker(workerNumber : int, db : Session):

    field = db.query(models.Domestic_Worker).where(models.Domestic_Worker.workerNumber == workerNumber).first()

    if not field :
        return {"message" : "INVALID"}

    else:
        if field.accountNumber is None:
            return {
                "id" : field.id,
                "VPA" : field.upi_id,
                "PAN" : field.panNumber,
                "NAME" : field.name,
                "VENDORID" : field.vendorId
            }

        else:
            return {
                "id" : field.id,
                "NAME" : field.name,
                "ACCOUNT_NUMBER" : field.accountNumber,
                "IFSC" : field.ifsc,
                "PAN" : field.panNumber,
                "VENDORID" : field.vendorId
            } 

def check_names(pan_name : str,vpa_name : str):
    str1 = pan_name.lower()
    str2 = vpa_name.lower()

    exact_match = exact_match_case_insensitive(str1, str2)
    fuzzy_score = fuzzy_match_score(str1, str2)

    print(f"At least one exact match (case insensitive): {exact_match}")
    print(f"Fuzzy match score: {fuzzy_score}")

    if(exact_match == True and fuzzy_score*100 >= 40):
        return {"message" : "VALID"}
    
    else:
        return {"message" : "INVALID"}


def number_regex(numberString : str):

    pattern = r'\+91[\s-]*|\D'

    cleaned_text = re.sub(pattern, '', numberString)

    if len(cleaned_text) >= 10:
        return {"mobileNumber" : int(cleaned_text[-10:])}
    
    return {"mobileNumber" : "INVALID"}


def extract_salary(salary_amount : str):

    match = re.search(r'\d+', salary_amount)
    if match:
        return {"extracted_salary" : int(match.group())}
    
    return {"extracted_salary" : "INVALID"}


def copy_employer_message(db : Session):

    messages = db.query(models.MessageLogSystem).all()

    for entity in messages:

        if entity.lastMessage == "COMPLETED":
            continue
        new_user = models.TalkToAgentEmployer(id = generate_unique_id(), date = current_date(), employerNumber = entity.employerNumber, workerNumber = entity.workerNumber, worker_bank_name = entity.workerName, worker_pan_name = "None", vpa = "None", issue = f"FLOW NOT COMPLETED. LAST MESSAGE - {entity.lastMessage}")
        db.add(new_user)
        db.commit()
        db.refresh(new_user)


def send_employer_invoice(employerNumber : int, orderId : str, db : Session):

    transaction = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.order_id==orderId).first()

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


    order_info = cashfree_api.check_order_status(orderId)
    order_note_string = order_info["order_note"]

    decoded_string = html.unescape(order_note_string)
    order_note = json.loads(decoded_string)

    employer_invoice_gen.employer_invoice_generation(transaction.employer_number, transaction.worker_number, transaction.employer_id, transaction.worker_id, order_note["salary"], order_note["cashAdvance"], order_note["bonus"], order_note["repayment"], order_note["attendance"], order_info["order_amount"], db)

    employer_invoice_name = f"{transaction.employer_number}_INV_{transaction.worker_number}_{month}_{year}.pdf"
    object_name = f"employerInvoices/{employer_invoice_name}"
    
    static_dir = os.path.join(os.getcwd(), 'invoices')
    filePath = os.path.join(static_dir, f"{transaction.employer_id}_INV_{transaction.worker_id}_{month}_{year}.pdf")

    print(f"the pdf path is : {filePath}")
    uploading_files_to_spaces.upload_file_to_spaces(filePath, object_name)

    print("uploaded")
    whatsapp_message.send_whatsapp_message(employerNumber=employerNumber, worker_name=transaction.worker_name, param3=order_info["order_amount"], link_param=employer_invoice_name, template_name="employer_invoice_message")

    print("message")
    update_statement = update(models.worker_employer).where(models.worker_employer.c.employer_number == transaction.employer_number, models.worker_employer.c.order_id == transaction.order_id).values(status="SENT")

    print("sent")
    db.execute(update_statement)
    db.commit()


# making the entry in the salary details table from which employer what amount has been paid and what was the bonus amount in it and what was the main salary amount.

def update_salary_details(employerNumber : int, orderId : str, db : Session):

    item = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.order_id==orderId).first()

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

    order_info = cashfree_api.check_order_status(orderId)
    order_note_string = order_info["order_note"]

    decoded_string = html.unescape(order_note_string)
    order_note = json.loads(decoded_string)

    new_entry = models.SalaryDetails(id = generate_unique_id(), employerNumber = employerNumber, worker_id = item.worker_id, employer_id = item.employer_id, totalAmount = order_info["order_amount"], salary = order_note["salary"], bonus = order_note["bonus"], cashAdvance = order_note["cashAdvance"], repayment = order_note["repayment"], attendance = order_note["attendance"], month = month, year = year, order_id = orderId)

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)


    if order_note["repayment"] > 0:

        existing_cash_advance_entry = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == item.worker_id, models.CashAdvanceManagement.employer_id == item.employer_id).first()


        existing_repayment = existing_cash_advance_entry.monthlyRepayment
        existing_advance = existing_cash_advance_entry.cashAdvance

        cash = existing_advance - order_note["repayment"]
        repayment = existing_repayment
        startMonth = existing_cash_advance_entry.repaymentStartMonth
        startYear = existing_cash_advance_entry.repaymentStartYear

        if cash <= 0:
            cash = 0
            repayment = 0
            startMonth = "sampatti"
            startYear = 0

        update_statement = update(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == item.worker_id, models.CashAdvanceManagement.employer_id == item.employer_id).values(cashAdvance = cash, monthlyRepayment = repayment, repaymentStartMonth = startMonth, repaymentStartYear = startYear)

        db.execute(update_statement)
        db.commit()



def download_worker_salary_slip(workerNumber: int, month : str, year : int, db : Session):

    month = month.capitalize()
    print(month)
    field = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == workerNumber).first()
    if field is None:
        return {
            "Message" : "This worker doesn't exist in the database. Please enter some other worker number."
        }
    
    static_pdf_path = os.path.join(os.getcwd(), 'static', f"{field.id}_SS_{month}_{year}.pdf")
    print(static_pdf_path)

    if os.path.exists(static_pdf_path):
        return FileResponse(static_pdf_path, media_type='application/pdf', filename=f"{workerNumber}_SS_{month}_{year}.pdf")
    
    else:
        return {
            "Message" : "The salary slip for the given worker number doesn't exist for the specified month and year."
        }
        


def send_worker_salary_slips(db : Session) :

    total_workers = db.query(models.Domestic_Worker).all()

    year = current_year()
    month = current_month()
    ps_month = previous_month()

    if month == "January":
        month = "December"
        year -= 1

    else:
        month = ps_month

    for worker in total_workers:

        salary_slip_generation.generate_salary_slip(worker.workerNumber, db)
        worker_salary_slip_name = f"{worker.workerNumber}_SS_{month}_{year}.pdf"
        object_name = f"salarySlips/{worker_salary_slip_name}"
        
        static_dir = os.path.join(os.getcwd(), 'static')
        filePath = os.path.join(static_dir, f"{worker.id}_SS_{month}_{year}.pdf")

        print(f"the pdf path is : {filePath}")
        uploading_files_to_spaces.upload_file_to_spaces(filePath, object_name)
        # whatsapp_message.worker_salary_slip_message()
        

# send greetings message to the employers
def send_greetings(db : Session):

    total_employers = db.query(models.Employer).all()

    for employer in total_employers:
        whatsapp_message.send_greetings(employer.employerNumber, template_name="salary_adjust_greetings")

    return {
        "MESSAGE" : "Greetings sent successfully."
    }


def salary_payment_reminder(db : Session):

    transactions = db.query(models.worker_employer).all()

    month = current_month()
    year = current_year()
    ps_month = previous_month()

    if(month == "January"):
        month = "December"
        year -= 1

    else:
        month = ps_month

    for item in transactions:

        response_data = cashfree_api.check_order_status(order_id=item.order_id)
        order_status = response_data.get("order_status")

        if order_status == "PAID":
            continue
        
        payment_session_id = response_data.get("payment_session_id")
        whatsapp_message.send_whatsapp_message(item.employer_number, item.worker_name, f"{month} {year}", payment_session_id, "salary_reminder")


def find_all_workers(employerNumber : int, db : Session):

    total_workers = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employerNumber).all()

    multiple_workers = []
    for item in total_workers:
        record = {
            "text": item.worker_name,
            "postback": f"data_nameofWorker={item.worker_name}"
        }
        multiple_workers.append(record)
    
    return {
        "worker_array" : multiple_workers
    }


def create_cash_advance_entry(employerNumber : int, workerName : str, cash_advance : int, repayment_amount : int, repayment_start_month : int, repayment_start_year : int, frequency : int,  bonus : int, deduction : int, db : Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    workerId = worker_employer_relation.worker_id
    employerId = worker_employer_relation.employer_id
    monthly_salary = worker_employer_relation.salary_amount

    datee = date.today().strftime('%Y-%m-%d')

    existing_record = db.query(models.cashAdvance).where(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId).order_by(models.cashAdvance.current_date.desc()).first()
    
    if existing_record is not None:
        update_statement = update(models.cashAdvance).where(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId).values(cash_advance = cash_advance, repayment_amount = repayment_amount, repayment_start_month = repayment_start_month, repayment_start_year = repayment_start_year, frequency = frequency, bonus = bonus, deduction = deduction, current_date = datee)
        db.execute(update_statement)
        db.commit()
    else:
        new_cash_advance_entry = models.cashAdvance(advance_id = generate_unique_id(), worker_id = workerId, employer_id = employerId, monthly_salary = monthly_salary, cash_advance = cash_advance, repayment_amount = repayment_amount, repayment_start_month = repayment_start_month, repayment_start_year = repayment_start_year, current_date = datee, frequency = frequency, bonus = bonus, deduction = deduction)
        db.add(new_cash_advance_entry)
        db.commit()
        db.refresh(new_cash_advance_entry)

def cash_advance_record(employerNumber : int, workerName : str, cash_advance : int, repayment_amount : int, repayment_start_month : int, repayment_start_year : int, frequency : int,  bonus : int, deduction : int, db : Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    workerId = worker_employer_relation.worker_id
    employerId = worker_employer_relation.employer_id
    
    cash_advance_record = db.query(models.cashAdvance).where(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId).order_by(models.cashAdvance.current_date.desc()).first()
    advance_id = cash_advance_record.advance_id
    
    month = current_month()
    year = current_year()

    new_cash_advance_entry = models.CashAdvanceRepaymentLog(id = generate_unique_id(), advance_id = advance_id, worker_id = workerId, employer_id = employerId, repayment_start_month = repayment_start_month, repayment_start_year = repayment_start_year, repayment_month = repayment_start_month, repayment_year = repayment_start_year, scheduled_repayment_amount = repayment_amount, actual_repayment_amount = 0, remaining_advance = cash_advance, payment_status = "Pending", frequency = frequency)

    db.add(new_cash_advance_entry)
    db.commit()
    db.refresh(new_cash_advance_entry)
    print("new entry created", new_cash_advance_entry)


def create_salary_record(employerNumber : int, workerName : str, currentSalary : int, modifiedSalary : int, db : Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    workerId = worker_employer_relation.worker_id
    employerId = worker_employer_relation.employer_id

    day_only = current_date().day
    month = current_month()
    year = current_year()

    dateIssuedOn = f"{day_only}_{month}_{year}"

    new_salary_record = models.SalaryRecords(id = generate_unique_id(), worker_id = workerId, employer_id = employerId, currentSalary = currentSalary, modifiedSalary = modifiedSalary, dateIssuedOn = dateIssuedOn)

    db.add(new_salary_record)
    db.commit()
    db.refresh(new_salary_record)


async def get_transalated_text(file_url: str):

    if not file_url:
        raise HTTPException(status_code=400, detail="File is not uploaded.")
    
    static_dir = 'audio_files'
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    temp_wav_path = ""

    try:
        # Download the file from the given URL
        response = requests.get(file_url)
        with tempfile.NamedTemporaryFile(dir=static_dir, delete=False) as temp:
            # Write the downloaded content to the temp file
            temp.write(response.content)
            temp_path = temp.name

        print(f"Downloaded temp file: {temp_path}")
        audio = AudioSegment.from_file(temp_path)  # Automatically detects the format
        temp_wav_path = f"{temp_path}.wav"  # Create a new temp path for the wav file
        audio.export(temp_wav_path, format="wav")  # Export the audio as .wav
        print(f"Converted to wav: {temp_wav_path}")

        # Transcribe the audio using Whisper
        result = call_sarvam_api(temp_wav_path)
        return {
            "text" : result["transcript"],
            "user_language" : result["language_code"]
        }

    except PermissionError as e:
        return JSONResponse(content={"error": f"Error saving temporary file: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        # Clean up by deleting the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)


def process_audio(user_input: str, user_language: str, employerNumber: int, workerName: str, db: Session):
    try:
        # Check if there is an existing record for the employer
        worker_employer_relation = db.query(models.worker_employer).where(
            models.worker_employer.c.employer_number == employerNumber,
            models.worker_employer.c.worker_name == workerName
        ).first()
        
        if not worker_employer_relation:
            raise ValueError("Worker not found with the given worker number.")

        employer_id = worker_employer_relation.employer_id
        worker_id = worker_employer_relation.worker_id
        
        
        existing_record = db.query(models.cashAdvance).where(models.cashAdvance.worker_id == worker_id, models.cashAdvance.employer_id == employer_id).order_by(models.cashAdvance.current_date.desc()).first()
        print(f"Existing Record: {existing_record}")
        
        context = {
            "cash_advance": existing_record.cash_advance if existing_record else 0,
            "repayment_amount": existing_record.repayment_amount if existing_record else 0,
            "repayment_start_month": existing_record.repayment_start_month if existing_record else 0,
            "repayment_start_year": existing_record.repayment_start_year if existing_record else 0,
            "frequency": existing_record.frequency if existing_record else 0,
            "bonus": existing_record.bonus if existing_record else 0,
            "deduction": existing_record.deduction if existing_record else 0,
            "monthly_salary": existing_record.monthly_salary if existing_record else 0,
        }
        
        
        # Pass the user input and context to the LLM for extraction
        extracted_info = extracted_info_from_llm(user_input, worker_id, employer_id, context)
        
        if isinstance(extracted_info, JSONResponse):
            return extracted_info

        print(f"usercontrollers: {extracted_info}")
        
        return extracted_info

    except PermissionError as e:
        return JSONResponse(content={"error": f"Error saving temporary file: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    


def send_audio_message(employer_id : str, worker_id : str, user_language : str, employerNumber : int, db : Session):

    new_existing_record = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == worker_id, models.CashAdvanceManagement.employer_id == employer_id).first()

    worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_id == employer_id, models.worker_employer.c.worker_id == worker_id).first()

    static_dir = "audio_files"
    missingInformation = "Please provide the following details."

    if new_existing_record.currentCashAdvance > 0 and new_existing_record.monthlyRepayment == 0:
        missingInformation += "monthly repayment amount."

    if new_existing_record.currentCashAdvance > 0 and new_existing_record.repaymentStartMonth == "sampatti":
        missingInformation += "start date for the repayment."

    if new_existing_record.attendance == 50:
        missingInformation += "attendance for this month."

    
    if missingInformation == "Please provide the following details.":

        outputAudio = f"Please confirm the following details."

        if new_existing_record.currentCashAdvance > 0:
            outputAudio += f"The cash advance amount is {new_existing_record.currentCashAdvance} while the repayment per month is {new_existing_record.monthlyRepayment}. The repayment starts from {new_existing_record.repaymentStartMonth} {new_existing_record.repaymentStartYear}. The salary for your worker is {worker_employer_relation.salary_amount}."

        if new_existing_record.bonus > 0:

            outputAudio += f"The bonus for this month is {new_existing_record.bonus}."


        outputAudio += f"attendance for this month is {new_existing_record.attendance}."

        
        if user_language == "hi-IN":
            translated_text = translate_text_sarvam(outputAudio, "en-IN", user_language)
            return send_audio(static_dir, translated_text, "hi-IN",employerNumber)
        else:
            return send_audio(static_dir, outputAudio, "en-IN",employerNumber)
    else:

        if user_language == "hi-IN":
            translated_text = translate_text_sarvam(missingInformation, "en-IN", user_language)
            return send_audio(static_dir, translated_text, "hi-IN",employerNumber)
        else:
            return send_audio(static_dir, missingInformation, "en-IN",employerNumber)
        

def update_worker_salary(employerNumber : int, workerName : str, salary : int, db : Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name == workerName).first()

    if not worker_employer_relation:
        return {
            "MESSAGE" : "No worker with the given name found."
        }
     
    update_statement = update(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name == workerName).values(salary_amount = salary)
    db.execute(update_statement)
    db.commit()


def get_all_languages():
    
    total_languages = {
    "hi-IN": "Hindi",
    "bn-IN": "Bengali",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "od-IN": "Odia",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "en-IN": "English",
    "gu-IN": "Gujarati"
}
    language_array = []
    for code, language in total_languages.items():
        record = {
            "text": language,
            "postback": f"data_language={code}"
        }
        language_array.append(record)
    
    return {
        "language_array" : language_array
    }

 
def get_respondent_id():

    respondentId = generate_unique_id()
    return {
        "respondentId" : respondentId
    }


def create_confirmation_message(workerId: str, respondentId: str, surveyId: int, db: Session):

    total_survey_messages = db.query(models.Responses).filter(models.Responses.workerId == workerId, models.Responses.respondentId == respondentId, models.Responses.surveyId == surveyId).all()

    message = "Here are the answers you provided:\n\n"

    for i, response in enumerate(total_survey_messages, start=1):

        question = db.query(models.QuestionBank).filter(models.QuestionBank.id == response.questionId).first()
        
        if question:
            message += f"{i}. {question.questionText}\n   Answer {i}: {response.responseText}\n\n"

    print(message)
    return {
        "confirmation_message" : message
    }


def send_question_audio(employerNumber : int, questionId : int, surveyId : int, language : str, db : Session):

    questionPath = os.path.join(os.getcwd(), "questions", f"{surveyId}_{questionId}_{language}.ogg")

    if os.path.exists(questionPath):

        mediaIdObj = whatsapp_message.generate_audio_media_id(f"{surveyId}_{questionId}_{language}.ogg", "questions")
        audioMediaId = mediaIdObj["id"]
        whatsapp_message.send_whatsapp_audio(audioMediaId, employerNumber)
        return {"MESSAGE": "AUDIO SENT SUCCESSFULLY."}
    
    else:

        create_question_audio(surveyId, questionId, language, db)
        mediaIdObj = whatsapp_message.generate_audio_media_id(f"{surveyId}_{questionId}_{language}.ogg", "questions")
        audioMediaId = mediaIdObj["id"]
        whatsapp_message.send_whatsapp_audio(audioMediaId, employerNumber)
        return {"MESSAGE": "AUDIO SENT SUCCESSFULLY."}


def create_question_audio(surveyId : int, questionId : int,  language : str, db : Session):

    question = db.query(models.QuestionBank).filter(models.QuestionBank.surveyId == surveyId, models.QuestionBank.id == questionId).first()
    questionText = question.questionText
    questionId = question.id
    translatedQuestion = translate_text_sarvam(questionText, "en-IN", language)
    question_language_audio("questions", translatedQuestion, surveyId, questionId, language)

    return {
        "Message" : "question generated."
    }
    
def calculate_total_days(year, month):
    """ Calculate the total number of days in the given month of the given year. """
    start_of_month = datetime(year, month, 1)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1)
    else:
        end_of_month = datetime(year, month + 1, 1)
    return (end_of_month - start_of_month).days


def mark_leave(employerNumber : str, workerName : str, leaves : int, db: Session):
    
    worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).first()
    
    current_leaves = worker_employer_relation.monthly_leaves
    new_leaves = current_leaves + leaves

    update_statement = update(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).values(monthly_leaves=new_leaves)

    db.execute(update_statement)
    db.commit()

def calculate_salary_amount(leaves : int, deduction : int, employerNumber : int, workerName : str,db : Session):

    number_of_month_days = determine_attendance_period(current_date().day)
    attendance = number_of_month_days - leaves

    worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).first()

    salary = worker_employer_relation.salary_amount
    newSalary = math.ceil((salary * attendance)/number_of_month_days)
    newSalary -= deduction

    attendanceReturn = "FULL"
    if attendance != number_of_month_days:
        attendanceReturn = f"{attendance} days present of {number_of_month_days} days"

    return {
        "newSalary" : newSalary,
        "attendance" : attendanceReturn,
        "deduction" : deduction
    }


def fetch_attendance_records(db, employer_id, worker_id):
    """Fetch all attendance records of a worker for an employer."""
    records = db.query(models.AttendanceRecord).filter_by(employer_id=employer_id, worker_id=worker_id).all()
    attendance_data = [{"date_of_leave": str(record.date_of_leave)} for record in records]
    return attendance_data


def process_attendance_with_llm(employerNumber : int, workerName: str, user_input : str, db : Session):
    """Extracts existing records, sends them to LLM, and gets structured output."""
    
    worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).first()

    if not worker_employer_relation:
        raise ValueError("Worker not found with the given worker number.")

    employer_id = worker_employer_relation.employer_id
    worker_id = worker_employer_relation.worker_id
    worker_name = worker_employer_relation.worker_name
    
    # Fetch existing attendance records
    attendance_records = fetch_attendance_records(db, employer_id, worker_id)
    
    llm = OpenAI(api_key=openai_api_key)
    current_date = date.today().strftime("%Y-%m-%d")

    # Construct the prompt for the LLM
    prompt_template = f"""
    You are an intelligent attendance manager. Given the following input, process the attendance record update:
    
    - Employer ID: {employer_id}
    - Worker ID: {worker_id}
    - Current Date: {current_date}
    - Existing Attendance Records: {attendance_records}
    - Worker Name: {worker_name}
    - User Input: {user_input}

    Based on the input, determine:
    1. Action: ("view", "add", "delete")
    2. Dates: List of dates in "YYYY-MM-DD" format.
    3. Dates: Provide me the dates in the strings format with coma separated values
    4. AI Message: A natural response for the user, with Worker Name in a readable format and correct format.
    5. AI Message: also provide the total number of days worker was absent in present month previously without including present dates.
    6. AI Message: after add/delete, if user ask question about the attendance of his worker, then give answer in ai_message.
    7. AI Message: if user select view, then given dates which are readble format for example 1st of January 2024, 2nd of January 2024, etc.
    8. AI Message: Make it in more readable format for the user to understand.
    9. AI Message: use worker worker_name in the message with more readable format.
    10. AI Message: if the user is viewing at the end, add If you have any further questions or need to make changes, feel free to let me know.
    
    Respond with a JSON object in the format:
    {{
        "action": "<view/add/delete>",
        "dates": "<comma-separated list of dates>",
        "ai_message": "<response message>"
        "employer_id": "{employer_id}",
        "worker_id": "{worker_id}"
    }}
    """

    # Call OpenAI GPT-4o API
    response =  llm.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_template}],
        temperature=0.5,
    )

    response_text = response.choices[0].message.content.strip()
    cleaned_response = response_text.replace('```json', '').replace('```', '').strip()

    print(f"LLM Response Raw: {response_text}")
    print(f"LLM Response Cleaned: {cleaned_response}")

        # Try parsing JSON
    extracted_info = json.loads(cleaned_response)
    return extracted_info


def add_attendance_records(action: str, dates: str, worker_id: str, employer_id: str, db: Session):
    try:
        # Convert comma-separated string into list of trimmed date strings
        date_list = [date.strip() for date in dates.split(",")] if dates else []

        if action == "view":
            # Retrieve attendance records for the worker
            records = db.query(models.AttendanceRecord.date_of_leave).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id
            ).all()

            # Format output
            attendance_dates = [record.date_of_leave.strftime("%Y-%m-%d") for record in records]
            return {"status": "success", "data": attendance_dates}

        elif action == "add":
            # Convert date strings to date objects
            date_objects = [datetime.strptime(date, "%Y-%m-%d").date() for date in date_list]

            # Extract year and month for filtering
            year_month_tuples = {(d.year, d.month) for d in date_objects}

            # Fetch existing records for given worker & employer
            existing_records = db.query(models.AttendanceRecord.date_of_leave).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id,
                models.AttendanceRecord.year.in_([y for y, m in year_month_tuples]),
                models.AttendanceRecord.month.in_([m for y, m in year_month_tuples]),
            ).all()

            # Convert existing dates to a set for quick lookup
            existing_dates = {record.date_of_leave for record in existing_records}

            # Filter out duplicate dates
            new_dates = [d for d in date_objects if d not in existing_dates]

            if new_dates:
                new_records = [
                    models.AttendanceRecord(
                        uuid=str(uuid.uuid4()),
                        worker_id=worker_id,
                        employer_id=employer_id,
                        month=d.month,
                        year=d.year,
                        date_of_leave=d
                    ) for d in new_dates
                ]
                db.add_all(new_records)
                db.commit()
                return {"status": "success", "message": f"Added {len(new_records)} new attendance records."}
            else:
                return {"status": "info", "message": "No new records to add (all dates already exist)."}

        elif action == "delete":
            # Convert date strings to date objects
            date_objects = [datetime.strptime(date, "%Y-%m-%d").date() for date in date_list]

            # Find records to delete
            records_to_delete = db.query(models.AttendanceRecord).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id,
                models.AttendanceRecord.date_of_leave.in_(date_objects)
            ).all()

            if records_to_delete:
                for record in records_to_delete:
                    db.delete(record)
                db.commit()
                return {"status": "success", "message": f"Deleted {len(records_to_delete)} attendance records."}
            else:
                return {"status": "info", "message": "No matching records found for deletion."}

        else:
            return {"status": "error", "message": "Invalid action. Use 'view', 'add', or 'delete'."}

    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "error", "message": f"Database error: {str(e)}"}

    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}




def mark_leave(employerNumber : int, workerName : str, db: Session):
    
    worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).first()

    if not worker_employer_relation:
        raise ValueError("Worker not found with the given worker number.")

    employer_id = worker_employer_relation.employer_id
    worker_id = worker_employer_relation.worker_id
    
    today = date.today()

    # Create a new attendance record
    attendance_entry = models.AttendanceRecord(
        uuid=str(uuid.uuid4()),
        worker_id=worker_id,
        employer_id=employer_id,
        month=today.month,
        year=today.year,
        date_of_leave=today
    )

    # Add to database
    db.add(attendance_entry)
    db.commit()
    db.refresh(attendance_entry)

    return {"message": "Leave marked successfully", "date": today}


def extract_pan_card_details(image_url):
    try:
        # Download image from URL
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))

        genai.configure(api_key=google_api_key)
        
        # Load Gemini Vision Pro model
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Prompt to extract PAN details
        prompt = """
        This is an Indian PAN card. Extract the following details and return in JSON format:
        - Name
        - Father's Name
        - Date of Birth (DOB)
        - PAN Number

        Example format:
        {
            "name": "RAHUL SHARMA",
            "pan_number": "ABCDE1234F",
            "dob": "12/12/1990",
            "father_name": "RAJESH SHARMA"
        }
        """

        # Send the image and prompt to Gemini
        result = model.generate_content([prompt, image], stream=False)
        raw_output = result.text

        # Try to parse JSON from the model's output
        json_start = raw_output.find("{")
        json_end = raw_output.rfind("}") + 1
        extracted_json = raw_output[json_start:json_end]

        return json.loads(extracted_json)

    except Exception as e:
        return {"error": str(e)}
    

def extract_passbook_details(image_url):
    try:
        # Download image from URL
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))

        genai.configure(api_key=google_api_key)
        
        # Load Gemini Vision model
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Prompt to extract passbook details
        prompt = """
        This is an image of an Indian bank passbook. Extract the following details and return in proper JSON format:
        - Name
        - Account Number
        - IFSC Code
        - Bank Name

        Example format:
        {
            "name": "RAVI KUMAR",
            "account_number": "123456789012",
            "ifsc_code": "SBIN0001234",
            "bank_name": "State Bank of India"
        }
        """

        # Send the image and prompt to Gemini
        result = model.generate_content([prompt, image], stream=False)
        raw_output = result.text

        # Extract JSON from the model's response
        json_start = raw_output.find("{")
        json_end = raw_output.rfind("}") + 1
        extracted_json = raw_output[json_start:json_end]

        return json.loads(extracted_json)

    except Exception as e:
        return {"error": str(e)}
        