import html, tempfile, os, re, requests, math, uuid, json
from fastapi import File, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import SQLAlchemyError
from .. import models, schemas
from ..database import get_db
from ..controllers import employer_invoice_gen, cashfree_api, uploading_files_to_spaces, whatsapp_message, salary_slip_generation, employment_contract_gen
from .utility_functions import generate_unique_id, exact_match_case_insensitive, fuzzy_match_score, current_month, previous_month, current_date, current_year, call_sarvam_api, extracted_info_from_llm, send_audio, send_audio_sarvam, extracted_info_from_llm, call_sarvam_api, translate_text_sarvam, determine_attendance_period, question_language_audio, systemattic_survey_message, transcribe_audio_from_file_path, get_main_transcript, generate_referral_code #extract_transcript_from_json_file
from ..controllers import employer_invoice_gen, cashfree_api, uploading_files_to_spaces, whatsapp_message, salary_slip_generation
from .cashfree_api import fetch_payment_details, create_cashfree_beneficiary, transfer_cashback_amount
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
sarvam_api_key = os.environ.get('SARVAM_API_KEY')


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

    if request.upi_id == "None":
        request.upi_id = None
 
    elif request.accountNumber == "None":
        request.accountNumber = None
        request.ifsc = None
 
    existing_worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == request.workerNumber).first()

    if existing_worker :
        print("worker already exists")
        return existing_worker

    unique_id = generate_unique_id()
    new_worker = models.Domestic_Worker(id=unique_id, name = request.name, email = request.email, workerNumber = request.workerNumber, panNumber = request.panNumber, upi_id = request.upi_id, accountNumber = request.accountNumber, ifsc = request.ifsc, vendorId = request.vendorId)
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
    

def get_worker_id(workerNumber : int, db : Session):

    worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == workerNumber).first()

    if worker:
        return {
            "workerId" : f"{worker.id}"
        }
    
    else:
        return {
            "workerId" : f"{generate_unique_id(16)}"
        }

# creating a relation between employer and worker.
def create_relation(request : schemas.Worker_Employer, db: Session, date_of_onboarding = current_date()):

    unique_id = generate_unique_id()

    employer_id = db.query(models.Employer).filter(models.Employer.employerNumber == request.employerNumber).first().id

    worker_id = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == request.workerNumber).first().id

    worker_employer_relation = insert(models.worker_employer).values(
        id=unique_id,
        worker_number=request.workerNumber,
        employer_number=request.employerNumber,
        vendor_id=request.vendorId,
        salary_amount=request.salary,
        worker_name=request.worker_name,
        employer_id=employer_id,
        worker_id = worker_id,
        date_of_onboarding = date_of_onboarding
    )

    db.execute(worker_employer_relation)
    db.commit()
    return {
        "MESSAGE" : "SUCCESSFUL"
    }

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

    worker = db.query(models.Domestic_Worker).where(models.Domestic_Worker.workerNumber == workerNumber).first()

    if not worker :
        return {"error" : "Worker not found."}

    else:
        return worker


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

    print("Order Note:", order_note)
    print("Order Info Bonus:", order_note["bonus"])
    print("Order Info Deduction:", order_note["deduction"])
    print("Order Info Salary:", order_note["salary"])
    print("Order Info Cash Advance:", order_note["cashAdvance"])
    print("Order Info Repayment:", order_note["repayment"])
    employer_invoice_gen.employer_invoice_generation(transaction.employer_number, transaction.worker_number, transaction.employer_id, transaction.worker_id, order_note["salary"], order_note["cashAdvance"], order_note["bonus"], order_note["repayment"], order_note["attendance"], order_info["order_amount"], order_note["deduction"], db)

    print("generated employer invoice")

    employer_invoice_name = f"{transaction.employer_number}_INV_{transaction.worker_number}_{month}_{year}.pdf"
    object_name = f"employerInvoices/{employer_invoice_name}"
    
    static_dir = os.path.join(os.getcwd(), 'invoices')
    filePath = os.path.join(static_dir, f"{transaction.employer_id}_INV_{transaction.worker_id}_{month}_{year}.pdf")

    print(f"the pdf path is : {filePath}")
    uploading_files_to_spaces.upload_file_to_spaces(filePath, object_name)

    print("uploaded")
    print("Order Info: ", order_info)
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

    print("Order Note:", order_note)

    update_salary_mgmt = update(models.SalaryManagementRecords).where(
        models.SalaryManagementRecords.order_id == orderId
    ).values(
        payment_status="SUCCESS"
    )
    db.execute(update_salary_mgmt)
    
    new_entry = models.SalaryDetails(id = generate_unique_id(), employerNumber = employerNumber, worker_id = item.worker_id, employer_id = item.employer_id, totalAmount = order_info["order_amount"], salary = order_note["salary"], bonus = order_note["bonus"], cashAdvance = order_note["cashAdvance"], repayment = order_note["repayment"], attendance = order_note["attendance"], month = month, year = year, order_id = orderId, deduction= order_note["deduction"])

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    if order_note["cashAdvance"] > 0 or order_note["repayment"] > 0:
        # First, update the payment status for the current order
        update_cash_advance_order = update(models.CashAdvanceManagement).where(
            models.CashAdvanceManagement.order_id == orderId
        ).values(
            payment_status="SUCCESS"
        )
        db.execute(update_cash_advance_order)
        db.commit()

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

def create_cash_advance_entry(employerNumber: int, workerName: str, cash_advance: int, repayment_amount: int, repayment_start_month: int, repayment_start_year: int, frequency: int, monthly_salary: int, bonus: int, deduction: int, db: Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    if not worker_employer_relation:
        raise ValueError("No worker-employer relation found.")

    workerId = worker_employer_relation.worker_id
    employerId = worker_employer_relation.employer_id
    datee = date.today().strftime('%Y-%m-%d')

    # Check for existing record
    existing_record = db.query(models.cashAdvance).filter(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId, models.cashAdvance.payment_status == "Created").first()

    if existing_record and existing_record.payment_status == "Created":
        update_stmt = update(models.cashAdvance).where(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId).values(cash_advance=cash_advance, repayment_amount=repayment_amount, repayment_start_month=repayment_start_month, repayment_start_year=repayment_start_year, current_date=datee, frequency=frequency, bonus=bonus, deduction=deduction)
        db.execute(update_stmt)
    else:
        new_entry = models.cashAdvance(advance_id=generate_unique_id(), worker_id=workerId, employer_id=employerId, monthly_salary=monthly_salary, cash_advance=cash_advance, repayment_amount=repayment_amount, repayment_start_month=repayment_start_month, repayment_start_year=repayment_start_year, current_date=datee, frequency=frequency, bonus=bonus, deduction=deduction, payment_status="Created")
        db.add(new_entry)

    db.commit()


# Function to finalize and update cash advance entry (set as "Pending")
def cash_advance_record(employerNumber: int, workerName: str, cash_advance: int, repayment_amount: int, repayment_start_month: int, repayment_start_year: int, frequency: int, monthly_salary: int, bonus: int, deduction: int, db: Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_name == workerName, models.worker_employer.c.employer_number == employerNumber).first()

    if not worker_employer_relation:
        raise ValueError("No worker-employer relation found.")

    workerId = worker_employer_relation.worker_id
    employerId = worker_employer_relation.employer_id

    cash_advance_record = db.query(models.cashAdvance).filter(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId, models.cashAdvance.payment_status == "Created").first()

    if not cash_advance_record:
        raise ValueError("No cash advance record found with status 'Created'.")

    datee = date.today().strftime('%Y-%m-%d')

    update_stmt = update(models.cashAdvance).where(models.cashAdvance.worker_id == workerId, models.cashAdvance.employer_id == employerId, models.cashAdvance.payment_status == "Created").values(
        monthly_salary=monthly_salary,
        cash_advance=cash_advance,
        repayment_amount=repayment_amount,
        repayment_start_month=repayment_start_month,
        repayment_start_year=repayment_start_year,
        current_date=datee,
        frequency=frequency,
        bonus=bonus,
        deduction=deduction,
        payment_status="Pending"
    )
    db.execute(update_stmt)
    db.commit()


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


async def get_transalated_text(file_path: str):

    if not file_path:
        raise HTTPException(status_code=400, detail="File URL is required.")

    output_dir = 'audio/'
    os.makedirs(output_dir, exist_ok=True)

    temp_path = ""
    wav_path = os.path.join(output_dir, "audio.wav")

    try:
        # Step 1: Download the file
        #response = requests.get(file_url)
        #if response.status_code != 200:
        #    raise HTTPException(status_code=400, detail="Failed to download file from the URL.")

        with tempfile.NamedTemporaryFile(delete=False) as temp:
            #temp.write(response.content)
            temp_path = temp.name

        print(f"Downloaded temporary file: {file_path}")

        # Step 2: Convert to WAV format
        audio = AudioSegment.from_file(file_path)
        audio.export(wav_path, format="wav")

        print(f"Converted to WAV and saved at: {wav_path}")

        duration_seconds = len(audio) / 1000.0
        print("Duration Second: ",duration_seconds)
        
        
        if duration_seconds < 28.000:
            result = call_sarvam_api(wav_path)
            transcript = result["transcript"]
            user_language = result["language_code"]
            print("Transcript: ",transcript)
            print("User Language: ",user_language)

            return transcript, user_language
        else:
        # Step 3: Call the transcription function
            await transcribe_audio_from_file_path(wav_path)
            print("await transcribe_audio_from_file_path(wav_path) successfull")
        
            transcript, user_language = get_main_transcript("audio/audio.json")
            print(transcript, user_language)

            return transcript, user_language

    except PermissionError as e:
        return JSONResponse(content={"error": f"Permission error: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        # Cleanup temp files
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as cleanup_err:
            print(f"Cleanup error: {cleanup_err}")


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
        monthly_salary = worker_employer_relation.salary_amount
        
        
        existing_record = db.query(models.cashAdvance).where(models.cashAdvance.worker_id == worker_id, models.cashAdvance.employer_id == employer_id, models.cashAdvance.payment_status == "Created").first()
        print(f"Existing Record: {existing_record}")
        
        context = {
            "cash_advance": existing_record.cash_advance if existing_record else 0,
            "repayment_amount": existing_record.repayment_amount if existing_record else 0,
            "repayment_start_month": existing_record.repayment_start_month if existing_record else 0,
            "repayment_start_year": existing_record.repayment_start_year if existing_record else 0,
            "frequency": existing_record.frequency if existing_record else 0,
            "bonus": existing_record.bonus if existing_record else 0,
            "deduction": existing_record.deduction if existing_record else 0,
            "monthly_salary": existing_record.monthly_salary if existing_record else worker_employer_relation.salary_amount,
            "payment_status": existing_record.payment_status if existing_record else "Created",
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
    


def send_audio_message(text : str, user_language : str, employerNumber : int):

    static_dir = "audio_files"
    print(f"user_language in send_audio_message: {user_language}")
    if user_language == "en-IN" or user_language is None or user_language == "en":
        return send_audio(text, employerNumber)
        #return send_audio_sarvam(text, employerNumber, "en-IN")
    else:
        translated_text = translate_text_sarvam(text, "en-IN", user_language)
        return send_audio(translated_text, employerNumber)
        #return send_audio_sarvam(translated_text, employerNumber, user_language)


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


def generate_user_id() -> str:
    return str(uuid.uuid4())

PROMPT_TEMPLATE = """
You are a smart assistant helping to fill a survey based on user responses in natural language (e.g., WhatsApp messages).

There are 28 questions in the survey.

Your goal:
1. Extract answers from the user input and match them with existing questions.
2. Apply logic rules to handle dependent questions (see rules below).
3. don't include user name in the question and answer.
4. Return ALL questions — if not answered or not applicable, set response = null.

---

## Dependency Rules:

1. If Q6 = "Yes":
   - Q7 must be answered.
   - Q8 = "User has a bank account."
2. If Q6 = "No":
   - Q7 = null
   - Answer Q8

3. If Q10 = "Yes":
   - Q11 must be answered.
4. If Q10 = "No":
   - Q11 = null

5. If Q12 ≠ "None":
   - Q13 and Q14 must be answered.
6. If Q12 = "None":
   - Q13 and Q14 = null

7. If Q15 = "Yes":
   - Answer Q16, Q17, Q18, Q20
8. If Q15 = "No":
   - Q16, Q17, Q20 = null

9. If Q18 = "Yes":
   - Answer Q19
10. If Q18 = "No":
    - Q19 = null

11. If Q21 = "Yes":
    - Answer Q22, Q23, Q24
12. If Q21 = "No":
    - Q22, Q23, Q24 = null

13. If Q25 = "Yes":
    - Answer Q26, Q27 = null
14. If Q25 = "No":
    - Q26 = null, Answer Q27

---

## Output Format (JSON only):

[
  {{
    "question_id": "6",
    "question_text": "Do you have a bank account?",
    "response": "Yes"
  }},
  {{
    "question_id": "7",
    "question_text": "If Yes, which bank?",
    "response": "State Bank of India"
  }},
  {{
    "question_id": "8",
    "question_text": "If No, why don't you have a bank account?",
    "response": "User has a bank account."
  }},
  ...
]

---

## Notes:
- If the user gives additional information not tied to a known question, create an entry with `"question_id": "extra_1"` and an appropriate `"question_text"`.
- Return exactly 28 questions with responses (or nulls) + any extras.
- Output only valid JSON. No explanation. No extra text. No markdown.

---

## Questions:
{question_context}

## Existing Answers:
{existing_answers}

## User Message:
"{user_input}"

---
"""


def process_survey_input(user_name: str, worker_number: str, user_input: str, survey_id: int, db: Session):
    existing_entry = db.query(models.SurveyResponse).filter_by(
        user_name=user_name,
        worker_number=worker_number,
        survey_id=survey_id
    ).first()

    if existing_entry:
        user_id = existing_entry.user_id  # reuse existing
    else:
        user_id = generate_user_id()  

    llm = OpenAI(api_key=openai_api_key)

    # Load survey
    survey = db.query(models.Survey).filter_by(id=survey_id).first()
    if not survey:
        return{
            "error": f"Survey with id {survey_id} not found."
        }

    # Load all questions for this survey
    questions = db.query(models.QuestionBank).filter_by(surveyId=survey_id).all()
    question_map = {str(q.id): q.questionText for q in questions}
    question_context = "\n".join([f"- ({qid}) {qtext}" for qid, qtext in question_map.items()])
    print(question_context)

    # Load previous responses
    previous_responses = db.query(models.SurveyResponse).filter_by(
        user_id=user_id,
        survey_id=survey_id
    ).all()
    previous_map = {str(r.question_id): r.response for r in previous_responses}
    existing_answers = "\n".join([
        f"- ({qid}) {question_map.get(qid, 'Unknown')} = {resp}"
        for qid, resp in previous_map.items()
    ]) or "None yet"

    # Build LLM prompt
    prompt = PROMPT_TEMPLATE.format(
        survey_id=survey_id,
        user_id=user_id,
        user_name=user_name,
        worker_number=worker_number,
        question_context=question_context,
        existing_answers=existing_answers,
        user_input=user_input
    )

    try:
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2
        )

        response_text = response.choices[0].message.content.strip()
        cleaned_response = response_text.replace('```json', '').replace('```', '').strip()

        structured_data = json.loads(cleaned_response)
    except Exception as e:
        return {"error": f"LLM failed or returned bad JSON: {str(e)}"}

    answers_received = {}
    clarification_needed = None

    for item in structured_data:
        qid = item.get("question_id")
        qtext = item.get("question_text")
        answer = item.get("response")

        if not qid or not qtext:
            continue

        # Handle clarification
        if answer is None and "clarification_needed" in item:
            clarification_needed = item["clarification_needed"]
            continue

        # Handle extra questions
        if qid.startswith("extra_"):
            new_question = models.QuestionBank(questionText=qtext, surveyId=survey_id, questionType="text")
            db.add(new_question)
            db.commit()
            qid = str(new_question.id)
            question_map[qid] = qtext

        question_id = int(qid)

        # Update or insert response
        existing = db.query(models.SurveyResponse).filter_by(
            user_id=user_id,
            survey_id=survey_id,
            question_id=question_id
        ).first()

        if existing:
            existing.response = answer
            existing.timestamp = str(datetime.now())
        else:
            db.add(models.SurveyResponse(
                response_id=str(uuid.uuid4()),
                survey_id=survey_id,
                question_id=question_id,
                user_id=user_id,
                user_name=user_name,
                worker_number=worker_number,
                response=answer,
                timestamp=str(datetime.now())
            ))

        answers_received[str(question_id)] = answer

    db.commit()

    # Build full response list
    output = []
    for qid, qtext in question_map.items():
        output.append({
            "question_id": qid,
            "question_text": qtext,
            "response": answers_received.get(qid) or previous_map.get(qid) or None
        })

    formatted_summary = systemattic_survey_message(worker_number, user_name, survey_id, db)

    return {
        "status": "success",
        "user_id": user_id,
        "worker_number": worker_number,
        "responses": output,
        "formatted_summary": formatted_summary,
        "clarification_needed": clarification_needed
    }

def generate_employment_contract(employerNumber: int, workerNumber : int, upi : str, accountNumber : str, ifsc : str, panNumber: str, name : str, salary : int, db : Session):

    contract_schema = schemas.Contract(
        employerNumber = employerNumber,
        workerNumber = workerNumber,
        upi = upi,
        accountNumber = accountNumber,
        ifsc = ifsc,
        name = name,
        salary = salary,
        panNumber=panNumber
    )

    employment_contract_gen.create_employment_record_pdf(contract_schema, db)

    employment_contract_name = f"{employerNumber}_ER_{workerNumber}.pdf"
    object_name = f"employmentRecords/{employment_contract_name}"
    
    static_dir = os.path.join(os.getcwd(), 'contracts')

    field = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == workerNumber , models.worker_employer.c.employer_number == employerNumber).first()

    filePath = os.path.join(static_dir, f"{field.id}_ER.pdf")

    print(f"the pdf path is : {filePath}")
    uploading_files_to_spaces.upload_file_to_spaces(filePath, object_name)

    print("uploaded the employment contract.")

    whatsapp_message.send_whatsapp_message(employerNumber=employerNumber, worker_name=name, param3= workerNumber, link_param = employment_contract_name, template_name="successful_worker_onboarding")

    print("Employment Contract sent successfully.")


def is_employer_present(employer_number: str, db: Session) -> bool:
    
    stmt = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employer_number)
    result = db.execute(stmt).first()
    print(f"Result of employer presence check: {result}")
    return result is not None


def send_referral_code_to_employer_and_create_beneficiary(employer_number: int, referral_code: str, upiId : str, db: Session) -> dict:
    try:
        message1 = f"""🎉 Your Referral Code is Ready!

Your referral code is live! 🎉

Referral Code: *{referral_code}*

Here's the deal. Share this. Friends get their workers on Sampatti for verified salary slips + benefits like affordable credit, insurance etc. You get ₹150.

Simple math! 💰

Plus you're literally helping workers build financial futures. Win-win energy right there.

Ready? Forwarding the perfect message next! 🚀
            """
            
        message2 = f"""So. I started using Sampatti for my house help.

Game changer! 🔥

She gets real salary slips now. Building Social Security. The confidence boost? Unreal.

Your worker deserves this too, no?

My code: *{referral_code}*

Try it: https://wa.me/919880081292?text=Hi

Let's upgrade this whole thing! ✨
        """

        employer = db.query(models.Employer).filter(models.Employer.employerNumber == employer_number).first()
        beneficiary_id = employer.beneficiaryId

        whatsapp_message.send_message_user(
            employer_number, 
            message1
        )
        whatsapp_message.send_message_user(
            employer_number, 
            message2
        )

        print("Beneficiary in Process")
        if beneficiary_id is None or beneficiary_id == "":
            create_cashfree_beneficiary(employer_number=employer_number, upi_id=upiId, db=db)
            print("Beneficiary Created")
        else:
            print("Beneficiary Already Present")
            
        return {
            "status": "success",
            "message": "Referral code sent successfully",
            "referral_code": referral_code
        }
            
    except Exception as e:
        return {"status": "error", "message": f"Error sending referral code: {str(e)}"}

def send_message_to_referring_employee(employer_number: int, referral_code: str, employerNumber: int):
    message = f"""
        🎉 Great News! Your Referral Worked!

        Your referral code *{referral_code}* was just used by {employerNumber}! 

        ✅ *Cashback Alert*: ₹150 has been credited to your account!

        You're making a real difference! By sharing Sampatti, you're helping domestic workers:
        • Get verified salary slips
        • Build their financial identity
        • Access banking services
        • Become financially independent

        *Keep the momentum going!* 🚀
        Share your code *{referral_code}* with more friends and employers. 

        Every referral = ₹150 for you + A brighter future for a domestic worker 💪

        Together, let's empower more workers and build a financially inclusive society!
    """

    whatsapp_message.send_message_user(
        employer_number, message
    )


def process_employer_cashback_for_first_payment(employerNumber: int, payload: dict, db: Session):
    """
    Process payment webhook and update employer/referral details according to the flow:
    1. Extract payment data from webhook
    2. Check if payment is successful
    3. Find employer and check if it's first payment
    4. Update employer record with payment details
    5. Check for referral mapping
    6. Process cashback for referring employer
    7. Generate new referral code for paying employer
    """
    try:
        # Extract payment data from webhook
        order_data = payload['data']['order']
        payment_data = payload['data']['payment']
        customer_data = payload['data']['customer_details']
        
        order_id = order_data.get('order_id')
        payment_amount = payment_data.get('payment_amount', 0)
        payment_status = payment_data.get('payment_status')
        upi_id = payment_data['payment_method']['upi'].get('upi_id') if 'upi' in payment_data.get('payment_method', {}) else None
        payment_time = payment_data.get('payment_time')
        bank_reference = payment_data.get('bank_reference')
        
        print(f"Processing payment for employer: {employerNumber}")
        print(f"Order ID: {order_id}")
        print(f"Payment Amount: {payment_amount}")
        print(f"Payment Status: {payment_status}")
        print(f"UPI ID: {upi_id}")
        

        referred_employer = db.query(models.Employer).filter(
            models.Employer.employerNumber == employerNumber
        ).first()

        print(f"Referred employer: {referred_employer}")
        

        # Check if first payment
        if referred_employer.FirstPaymentDone:
            # Not first payment - update total payment amount and exit
            referred_employer.totalPaymentAmount += int(payment_amount)
            db.commit()
            db.refresh(referred_employer)
            return {
                "status": "success", 
                "message": "Payment recorded but not first payment - no referral processing"
            }
        
        print("First payment processing")


        # Generate new referral code for this employer
        new_referral_code = generate_referral_code()
        while db.query(models.Employer).filter(models.Employer.referralCode == new_referral_code).first():
            new_referral_code = generate_referral_code()

        # First payment processing
        # Update employer record with payment details
        print("New referral code generated: ", new_referral_code)
        referred_employer.referralCode = new_referral_code
        referred_employer.FirstPaymentDone = True
        referred_employer.upiId = upi_id or ''
        referred_employer.totalPaymentAmount += int(payment_amount)
        send_referral_code_to_employer_and_create_beneficiary(employerNumber, new_referral_code, upi_id, db)
        
        # Check whether this worker was onboarded using some referral code or not.
        worker_employer_record = db.query(models.worker_employer).filter(
            models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.order_id == order_id
        ).first()

        if not worker_employer_record or not worker_employer_record.referralCode:
            # No referral code - skip referral processing
            db.commit()
            db.refresh(referred_employer)
            return {
                "status": "success",
                "message": "First payment processed. No referral code found.",
                "new_referral_code": new_referral_code
            }
        
        # Has referral code - process referral
        referral_code_used = worker_employer_record.referralCode
        
        # Find referring employer
        referring_employer = db.query(models.Employer).filter(
            models.Employer.referralCode == referral_code_used
        ).first()

        print("Referring employer: ", referring_employer)
        # Process cashback for referring employer
        CASHBACK_AMOUNT = 1  # Fixed cashback amount
        referring_employer.cashbackAmountCredited += CASHBACK_AMOUNT
        referring_employer.numberofReferral += 1

        print("Cashback Amount: ", CASHBACK_AMOUNT)
        
        # Create or update referral mapping
        existing_mapping = db.query(models.EmployerReferralMapping).filter(
            models.EmployerReferralMapping.employerReferring == referring_employer.id,
            models.EmployerReferralMapping.employerReferred == referred_employer.id
        ).first()

        print("Existing mapping: ", existing_mapping)
        
        if not existing_mapping:
            # Create new referral mapping
            new_mapping = models.EmployerReferralMapping(
                id=str(uuid.uuid4()),
                employerReferring=referring_employer.id,
                employerReferred=referred_employer.id,
                referralCode=referral_code_used,
                referralStatus='COMPLETED',
                dateReferredOn=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                cashbackAmount=CASHBACK_AMOUNT,
                cashbackStatus='COMPLETED'  # Can be updated later when cashback is actually credited
            )
            db.add(new_mapping)
        else:
            # Update existing mapping
            existing_mapping.referralStatus = 'COMPLETED'
            existing_mapping.cashbackAmount = CASHBACK_AMOUNT
            existing_mapping.cashbackStatus = 'COMPLETED'
        
        print("Referring employer total referrals: ", referring_employer.numberofReferral)
        print("Existing Mapping")

        # Commit all changes
        db.commit()
        db.refresh(referred_employer)
        db.refresh(referring_employer)

        transfer_cashback_amount(beneficiary_id=referring_employer.beneficiaryId, amount=CASHBACK_AMOUNT, transfer_mode="upi")
        
        referring_employee_number = referring_employer.employerNumber
        referral_code = referring_employer.referralCode
        send_message_to_referring_employee(referring_employee_number, referral_code, employerNumber)

        print("Cashback Processed")

        
        return {
            "status": "success",
            "message": "First payment and referral processed successfully",
            "employer_id": referred_employer.id,
            "new_referral_code": new_referral_code,
            "referring_employer_id": referring_employer.id,
            "cashback_amount": CASHBACK_AMOUNT,
            "referring_employer_total_referrals": referring_employer.numberofReferral
        }
        
    except Exception as e:
        print(f"Error in update_employer_details: {str(e)}")
        db.rollback()
        return {
            "status": "error",
            "message": f"Error processing employer update: {str(e)}"
        }
    

def generate_and_send_referral_code_to_employers(db : Session) :
     
    total_employers = db.query(models.Employer).all()

    for employer in total_employers:

        if not employer.FirstPaymentDone:
            continue

        # Generate a new referral code
        new_referral_code = str(uuid.uuid4())

        # Update the employer record with the new referral code
        employer.referralCode = new_referral_code
        db.commit()
        db.refresh(employer)

        # Send the referral code to the employer
        send_referral_code_to_employer_and_create_beneficiary(employer.employerNumber, new_referral_code, employer.upiId, db)
