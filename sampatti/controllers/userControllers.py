import html
import json
import tempfile, os, re, requests
from fastapi import File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete, func, insert,update
from .. import models, schemas
from .utility_functions import generate_unique_id, exact_match_case_insensitive, fuzzy_match_score, current_month, previous_month, current_date, current_year, call_sarvam_api, extracted_info_from_llm, send_audio, extracted_info_from_llm, call_sarvam_api, translate_text_sarvam, determine_attendance_period, calculate_year_for_month
from ..controllers import employer_invoice_gen, cashfree_api, uploading_files_to_spaces, whatsapp_message, salary_slip_generation
from sqlalchemy.orm import Session
from fuzzywuzzy import fuzz
from pydub import AudioSegment


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

        if item.status == "SENT":
            continue
        
        response_data = cashfree_api.check_order_status(order_id=item.order_id)
        order_status = response_data.get("order_status")
        payment_session_id = response_data.get("payment_session_id")

        if order_status == "PAID":
            continue
        
        whatsapp_message.send_whatsapp_message(item.employer_number, item.worker_name, f"{month} {year}", payment_session_id, "salary_payment_reminder")


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


def create_cash_advance_entry(employerNumber : int, employer_id : str, worker_id : str, crrCashAdvance : int, Repayment_Monthly : int, Repayment_Start_Month : str, Repayment_Start_Year : int, Bonus : int, Attendance : int, db : Session):

    existing_record = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == worker_id, models.CashAdvanceManagement.employer_id == employer_id).first()

    if existing_record is not None:

            update_statement = update(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employer_id == employer_id, models.CashAdvanceManagement.worker_id == worker_id).values(monthlyRepayment = Repayment_Monthly, repaymentStartMonth = Repayment_Start_Month, repaymentStartYear = Repayment_Start_Year, currentCashAdvance = crrCashAdvance, attendance = Attendance, bonus = Bonus)
            db.execute(update_statement)
            db.commit()

    else: 
        new_cash_advance_entry = models.CashAdvanceManagement(id = generate_unique_id(), employerNumber = employerNumber, worker_id = worker_id, employer_id = employer_id, cashAdvance = 0, monthlyRepayment = Repayment_Monthly, repaymentStartMonth = Repayment_Start_Month, repaymentStartYear = Repayment_Start_Year, currentCashAdvance = crrCashAdvance, attendance = Attendance, bonus = Bonus)

        db.add(new_cash_advance_entry)
        db.commit()
        db.refresh(new_cash_advance_entry)


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


async def process_audio(file_url: str, employerNumber : int, workerName: str, db : Session):
    if not file_url:
        raise HTTPException(status_code=400, detail="File is not uploaded.")

    results = []
    static_dir = 'audio_files'
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    user_input = ""
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
        user_input = result["transcript"]
        user_language = result["language_code"]
        print(f"the result from the sarvam api is : {result}")

        results.append({
            "filename": os.path.basename(temp_path),
            "transcript": user_input,
            "language_code": user_language
        })

        # Check if there is an existing record for the employer
        worker_employer_relation = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.worker_name== workerName).first()

        if not worker_employer_relation:
            raise ValueError("Worker not found with the given worker number.")

        employer_id = worker_employer_relation.employer_id
        worker_id = worker_employer_relation.worker_id

        existing_record = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.worker_id == worker_id, models.CashAdvanceManagement.employer_id == employer_id).first()
        
        print(f"the existing record is : {existing_record}")
        print(f"groq key : {os.environ.get('GROQ_API_KEY')}")
        # Prepare the context for the LLM based on existing record
        context = {
            "currentCashAdvance": existing_record.currentCashAdvance if existing_record else 0,
            "monthlyRepayment": existing_record.monthlyRepayment if existing_record else 0,
            "Repayment_Start_Month": existing_record.repaymentStartMonth if existing_record else "sampatti",
            "Repayment_Start_Year": 0,
            "Bonus": existing_record.bonus if existing_record else 0,
            "Attendance": existing_record.attendance if existing_record else 50,
            "detailsFlag" : 0,
            "nameofWorker" : workerName,
            "salary" : worker_employer_relation.salary_amount
        }

        # Pass the user input and context to the LLM for extraction
        extracted_info = extracted_info_from_llm(user_input, employerNumber, context)
        print(f"usercontrollers : {extracted_info}")
        

        year = 0
        month_name = extracted_info.get("Repayment_Start_Month")
        given_year = extracted_info.get("Repayment_Start_Year")

        if month_name != "sampatti":

            if given_year == 0:
                year = calculate_year_for_month(month_name)

            else:
                year = given_year

        response = {
            "crrCashAdvance" : extracted_info.get("currentCashAdvance"),
            "Repayment_Monthly" : extracted_info.get("monthlyRepayment"),
            "Repayment_Start_Month" : extracted_info.get("Repayment_Start_Month"),
            "Repayment_Start_Year" : year,
            "Bonus" : extracted_info.get("Bonus"),
            "Attendance" : extracted_info.get("Attendance"),
            "detailsFlag" : extracted_info.get("detailsFlag"),
            "employer_id" : employer_id,
            "worker_id" : worker_id,
            "salary" : extracted_info.get("salary"),
            "user_language" : user_language
        }


        return response

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
            return send_audio(static_dir, outputAudio, "hi-IN",employerNumber)
        else:
            translated_text = translate_text_sarvam(outputAudio, "en-IN", user_language)
            return send_audio(static_dir, translated_text, "en-IN",employerNumber)
    else:

        if user_language == "hi-IN":
            return send_audio(static_dir, missingInformation, "hi-IN",employerNumber)
        else:
            translated_text = translate_text_sarvam(missingInformation, "en-IN", user_language)
            return send_audio(static_dir, translated_text, "en-IN",employerNumber)
        

def update_worker_salary(employer_id : str, worker_id : str, salary : int, db : Session):

    worker_employer_relation = db.query(models.worker_employer).filter(models.worker_employer.c.worker_id == worker_id, models.worker_employer.c.employer_id == employer_id).first()

    if not worker_employer_relation:
        return {
            "MESSAGE" : "No worker with the given name found."
        }
    
    update_statement = update(models.worker_employer).where(models.worker_employer.c.employer_id == employer_id, models.worker_employer.c.worker_id == worker_id).values(salary_amount = salary)
    db.execute(update_statement)
    db.commit()


def send_question_audio(employerNumber : int, question_id : int, user_language : str, db : Session):

    question = db.query(models.QuestionBank).filter(models.QuestionBank.id == question_id).first()
    questionText = question.questionText
    translated_text = translate_text_sarvam(questionText, "en-IN", user_language)
    return send_audio("audio_files", translated_text, user_language ,employerNumber)


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


