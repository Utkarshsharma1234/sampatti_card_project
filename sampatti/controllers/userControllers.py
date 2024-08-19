from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import update
import uuid, random, string, hashlib, difflib, json, re
from .. import models
from ..import schemas
from sqlalchemy.orm import Session


# utility functions

def generate_unique_id(length=8):

    unique_id = uuid.uuid4().hex
    letters_only = ''.join([char for char in unique_id if char.isalpha()])[:length]
    if len(letters_only) < length:
        letters_only += ''.join(random.choices(string.ascii_letters, k=length - len(letters_only)))
    return letters_only

def fuzzy_match_score(str1, str2):
    return difflib.SequenceMatcher(None, str1, str2).ratio()


def exact_match_case_insensitive(str1, str2):
    words1 = set(re.findall(r'\b\w+\b', str1.lower()))
    words2 = set(re.findall(r'\b\w+\b', str2.lower()))
    return not words1.isdisjoint(words2)

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
        {"message" : "EMPLOYER_EXISTS"}


# creating a domestic worker
def create_domestic_worker(request : schemas.Domestic_Worker, db: Session):

    employer = db.query(models.Employer).filter(models.Employer.employerNumber == request.employerNumber).first()

    if not employer:
        raise HTTPException(status_code=400, detail="The employer is not registered. You must register the employer first.")

    existing_worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == request.workerNumber).first()
    
    if not existing_worker:
        unique_id = generate_unique_id()
        new_worker = models.Domestic_Worker(id=unique_id, name = request.name, email = request.email, workerNumber = request.workerNumber, panNumber = request.panNumber, upi_id = request.upi_id, accountNumber = None, ifsc = None)
        new_worker.employers.append(employer)
        db.add(new_worker)
        db.commit()
        db.refresh(new_worker)

        unique_id2 = generate_unique_id()
        update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == request.workerNumber).where(models.worker_employer.c.employer_number == employer.employerNumber).values(id=unique_id2)
        db.execute(update_statement)
        db.commit()
        return new_worker
    
    else:
        existing_worker.employers.append(employer)
        db.commit()
        db.refresh(existing_worker)

        unique_id2 = generate_unique_id()
        update_statement = update(models.worker_employer).where(models.worker_employer.c.worker_number == request.workerNumber).where(models.worker_employer.c.employer_number == employer.employerNumber).values(id=unique_id2)
        db.execute(update_statement)
        db.commit()
        return existing_worker


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
    

def create_message_log(request : schemas.Message_log_Schema, db  :Session):

    current_date = datetime.now().date()
    current_time = datetime.now().timestamp()

    existing_message = db.query(models.MessageLogSystem).where(models.MessageLogSystem.employerNumber==request.employerNumber).where(models.MessageLogSystem.workerNumber==request.workerNumber).first()

    if not existing_message:

        unique_id = generate_unique_id()
        new_message = models.MessageLogSystem(id = unique_id, employerNumber = request.employerNumber, date=f"{current_date}", timestamp=f"{current_time}", lastMessage=request.lastMessage, workerNumber= request.workerNumber)
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



def create_talk_to_agent_employer(employerNumber : int, category : str, workerNumber : int, db:Session):

    current_date = datetime.now().date()

    unique_id = generate_unique_id()
    new_user = models.TalkToAgentEmployer(id = unique_id, employerNumber = employerNumber, date=f"{current_date}", category = category, workerNumber=workerNumber)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

    
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
                "VPA" : field.upi_id,
                "PAN" : field.panNumber,
                "NAME" : field.name
            }

        else:
            return {
                "NAME" : field.name,
                "ACCOUNT_NUMBER" : field.accountNumber,
                "IFSC" : field.ifsc,
                "PAN" : field.panNumber
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


def explain_worker(db : Session, workerNumber : int, employerNumber : int):

    current_date = datetime.now().date()
    new_worker = models.ExplainDomesticWorker(id = generate_unique_id(), date = current_date, employerNumber = employerNumber, workerNumber = workerNumber)

    db.add(new_worker)
    db.commit()
    db.refresh(new_worker)

    return {"message" : "Successful"}