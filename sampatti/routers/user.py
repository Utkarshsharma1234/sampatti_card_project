import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
import requests
from .. import schemas, models
from ..database import get_db
from sqlalchemy.orm import Session
from ..controllers import userControllers
from ..controllers import employment_contract_gen
from datetime import datetime, timedelta
from ..controllers import whatsapp_message, talk_to_agent_excel_file


router = APIRouter(
    prefix="/user",
    tags=['users']
)


current_date = datetime.now().date()
first_day_of_current_month = datetime.now().replace(day=1)
last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
previous_month = last_day_of_previous_month.strftime("%B")
current_year = datetime.now().year


@router.post("/employer/create")
def create_employer(request : schemas.Employer, db : Session = Depends(get_db)):
    return userControllers.create_employer(request, db)

@router.post('/domestic_worker/create')
def create_domestic_worker(request : schemas.Domestic_Worker, db: Session = Depends(get_db)):
    return userControllers.create_domestic_worker(request, db)

@router.post('/domestic_worker/create/account_number')
def create_worker_account_number(request : schemas.Domestic_Worker, db: Session = Depends(get_db)):
    return userControllers.create_worker_account_number(request,db)

@router.post('/assign_vendor_id')
def assign_vendor_id(workerNumber : int, vendorId : str, db : Session = Depends(get_db)):
    return userControllers.assign_vendor_id(workerNumber, vendorId, db)

@router.post('/create_relation')
def create_relation(request : schemas.Worker_Employer, db : Session = Depends(get_db)):
    return userControllers.create_relation(request, db)

@router.delete('/delete_relation')
def delete_relation(workerNumber : int, employerNumber : int, db : Session = Depends(get_db)):
    return userControllers.delete_relation(workerNumber, employerNumber,db)

@router.get("/check_existence")
def check_existence(employerNumber : int, workerNumber : int, db : Session = Depends(get_db)):
    return userControllers.check_existence(employerNumber, workerNumber,db)

@router.get("/check_name_matching")
def check_names(pan_name : str, vpa_name : str):
    return userControllers.check_names(pan_name, vpa_name)

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

@router.post('/explain_worker/create')
def explain_worker(employerNumber : int, workerNumber : int , db : Session = Depends(get_db)):
    return userControllers.explain_worker(db, workerNumber, employerNumber)

@router.post('/message_log/create')
def create_message_log(request : schemas.Message_log_Schema, db : Session = Depends(get_db)):
    return userControllers.create_message_log(request, db)

@router.put('/domestic_worker/update')
def update_worker(oldNumber : int, newNumber: int, db : Session = Depends(get_db)):
    return userControllers.update_worker(oldNumber,newNumber, db)

@router.post("/salary")
def insert_salary(request : schemas.Salary, db : Session = Depends(get_db)):
    return userControllers.insert_salary(request, db)

@router.get("/salary_slips")
def salary_slips(db: Session = Depends(get_db)):

    total_workers = db.query(models.Domestic_Worker).all()

    for singleworker in total_workers:
        url = f"https://conv.sampatticards.com/user/generate_salary_slip/{singleworker.workerNumber}" 
        response = requests.get(url)
        if response.status_code == 200:

            content_type = response.headers.get('Content-Type')
            if content_type == 'application/pdf':
                print("Request successful:", singleworker.workerNumber)
        else:
            print("Request failed:", response.status_code)

    return {"message" : "SALARY SLIPS GENERATED"}


@router.get("/generate_salary_slip/{workerNumber}", response_class=FileResponse, name="Generate Salary Slip")
def generate_salary_slip_endpoint(workerNumber : int, db: Session = Depends(get_db)):

    worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == workerNumber).first()
    static_pdf_path = os.path.join(os.getcwd(), 'static', f"{worker.id}_SS_{previous_month}_{current_year}.pdf")
    
    return FileResponse(static_pdf_path, media_type='application/pdf', filename=f"{workerNumber}_SS_{previous_month}_{current_year}.pdf")


@router.get('/get_salary_slip', response_class=FileResponse, name="Get Salary Slip")
def get_salary_slip(workerNumber : int, month : str, year : str, db: Session = Depends(get_db)):

    worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == workerNumber).first()
    static_pdf_path = os.path.join(os.getcwd(), 'static', f"{worker.id}_SS_{month}_{year}.pdf")
    
    return FileResponse(static_pdf_path, media_type='application/pdf', filename=f"{workerNumber}_SS_{month}_{year}.pdf")


@router.post("/contract")
def contract_generation(request : schemas.Contract, db : Session = Depends(get_db)):

    employment_contract_gen.create_employment_record_pdf(request, db)
    field = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == request.workerNumber, models.worker_employer.c.employer_number == request.employerNumber).first()

    static_pdf_path = os.path.join(os.getcwd(), 'contracts', f"{field.id}_ER.pdf")

    return FileResponse(static_pdf_path, media_type='application/pdf', filename=f"{request.workerNumber}_ER_{request.employerNumber}.pdf")


@router.delete("/delete_demo_contract")
def delete_demo_contract(workerNumber : int, employerNumber : int, db: Session = Depends(get_db)):

    field = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == workerNumber, models.worker_employer.c.employer_number == employerNumber).first()

    static_pdf_path = os.path.join(os.getcwd(), 'contracts', f"{field.id}_ER.pdf")
    if(static_pdf_path):
        os.remove(static_pdf_path)
        return {
            "MESSAGE" : "File deleted Successfully."
        }

    else:
        return {
            "MESSAGE" : "No such file exist."
        }
    
    
@router.post("/generate_contract")
def generate_mediaId(workerNumber: int, employerNumber: int, db : Session = Depends(get_db)):

    field = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == workerNumber, models.worker_employer.c.employer_number == employerNumber).first()

    path = f"{field.id}_ER.pdf"
    folder = 'contracts'
    return whatsapp_message.generate_mediaId(path, folder)


@router.get("/send_employer_invoice")
def send_employer_invoice(employerNumber : int, orderId : str, db : Session = Depends(get_db)):
    return userControllers.send_employer_invoice(employerNumber, orderId, db)
    

@router.get('/generate_talk_to_agent_sheet')
def generate_sheet():
    return talk_to_agent_excel_file.upload_data_to_google_sheets()

@router.get('/copy_employer_message')
def copy_employer_message(db : Session = Depends(get_db)):
    return userControllers.copy_employer_message(db)
