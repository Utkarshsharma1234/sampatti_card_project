import tempfile, whisper, os, re
from fastapi import File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import delete, insert,update
from .. import models, schemas
from .utility_functions import generate_unique_id, exact_match_case_insensitive, fuzzy_match_score, current_month, previous_month, current_date, current_year, send_audio, extracted_info_from_llm
from ..controllers import employer_invoice_gen, cashfree_api, uploading_files_to_spaces, whatsapp_message, salary_slip_generation
from sqlalchemy.orm import Session


model = whisper.load_model("base")

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
        new_worker = models.Domestic_Worker(id=unique_id, name = request.name, email = request.email, workerNumber = request.workerNumber, panNumber = request.panNumber, upi_id =request.upi_id, accountNumber = request.accountNumber, ifsc = request.ifsc, vendor_id = None)

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


    if transaction.status == "SENT":
        return
    
    elif transaction.order_id is None:
        return

    bonus = 0
    existing_bonus_entry = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employerNumber==employerNumber, models.CashAdvanceManagement.worker_id==transaction.worker_id).first()

    if existing_bonus_entry is not None:
        bonus += existing_bonus_entry.bonus

    order_status = cashfree_api.check_order_status(order_id=transaction.order_id)
    if(order_status == "PAID"):
        
        total_salary = transaction.salary_amount + bonus
        employer_invoice_gen.employer_invoice_generation(transaction.employer_number, transaction.worker_number, transaction.employer_id, transaction.worker_id, bonus, db)

        employer_invoice_name = f"{transaction.employer_number}_INV_{transaction.worker_number}_{month}_{year}.pdf"
        object_name = f"employerInvoices/{employer_invoice_name}"
        
        static_dir = os.path.join(os.getcwd(), 'invoices')
        filePath = os.path.join(static_dir, f"{transaction.employer_id}_INV_{transaction.worker_id}_{month}_{year}.pdf")

        print(f"the pdf path is : {filePath}")
        uploading_files_to_spaces.upload_file_to_spaces(filePath, object_name)

        whatsapp_message.send_whatsapp_message(employerNumber=employerNumber, worker_name=transaction.worker_name, param3=total_salary, link_param=employer_invoice_name, template_name="employer_invoice_message")

        update_statement = update(models.worker_employer).where(models.worker_employer.c.employer_number == transaction.employer_number, models.worker_employer.c.order_id == transaction.order_id).values(status="SENT")

        db.execute(update_statement)
        db.commit()
    

# making the entry in the salary details table from which employer what amount has been paid and what was the bonus amount in it and what was the main salary amount.

def update_salary_details(employerNumber : int, orderId : str, db : Session):

    transaction = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employerNumber, models.worker_employer.c.order_id==orderId).first()

    bonus = 0
    existing_bonus_entry = db.query(models.CashAdvanceManagement).where(models.CashAdvanceManagement.employerNumber==employerNumber, models.CashAdvanceManagement.worker_id==transaction.worker_id).first()

    if existing_bonus_entry is not None:
        bonus += existing_bonus_entry.bonus

    new_entry = models.SalaryDetails(id = generate_unique_id(), employerNumber=employerNumber, worker_id=transaction.worker_id, employer_id= transaction.employer_id, salary=transaction.salary_amount, bonus=bonus, order_id=orderId)

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)


def send_worker_salary_slips(db : Session) :

    total_workers = db.query(models.Domestic_Worker).all()

    year = current_year()
    month = current_month()

    if month == "January":
        month = "December"
        year -= 1

    
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
        whatsapp_message.send_greetings(employer.employerNumber, template_name="diwali_greetings")

    return {
        "MESSAGE" : "Greetings sent successfully."
    }

def create_salary_records(workerNumber : int, db : Session):

    total = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number==workerNumber).all()

    for item in total:

        new_entry = models.SalaryDetails(id=generate_unique_id(), employerNumber=item.employer_number, worker_id=item.worker_id, employer_id=item.employer_id, salary=item.salary_amount, order_id=item.order_id)

        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)


async def process_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="File is not uploaded.")

    results = []

    static_dir = 'audio_files'
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    user_input = ""
    try:
        # Use NamedTemporaryFile with delete=False
        with tempfile.NamedTemporaryFile(dir=static_dir, delete=False) as temp:
            # Read the file content
            audio_bytes = await file.read()
            temp.write(audio_bytes)
            temp_path = temp.name  # Store the temporary file path

        # Transcribe the audio using Whisper
        result = whisper.transcribe(audio=temp_path, model=model, fp16=True)

        user_input = result["text"]
        print(result)

        # Append the transcription result
        results.append({
            "filename": file.filename,
            "transcript": user_input
        })

    except PermissionError as e:
        return JSONResponse(content={"error": f"Error saving temporary file: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        # Clean up by deleting the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

    print(results)
    extracted_info = extracted_info_from_llm(user_input)
    cash_advance = extracted_info.get("Cash_Advance")
    bonus = extracted_info.get("Bonus")
    repayment = extracted_info.get("Repayment_Monthly")
    sample_output = f"Please confirm the following details. The cash advance given by you is {cash_advance} and the bonus given by you is {bonus} while the repayment per month is {repayment}"

    return send_audio(static_dir, file.filename, sample_output, background_tasks)
