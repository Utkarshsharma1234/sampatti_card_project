from pydantic import BaseModel
from typing import List

class Domestic_Worker(BaseModel):
    name: str
    email : str
    workerNumber:int
    employerNumber : int
    panNumber : str
    upi_id : str
    accountNumber : str
    ifsc : str
    vendorId : str
    class Config:
        from_attributes = True

class Employer(BaseModel):
    employerNumber:int
    class Config:
        from_attributes = True

class Worker_Employer(BaseModel):
    workerNumber : int
    employerNumber : int
    salary : int
    vendorId : str
    worker_name : str
    employer_id : str
    worker_id : str

class Salary(BaseModel):
    workerNumber : int
    employerNumber : int
    salary_amount : int
    class Config:
        from_attributes = True

class Message_log_Schema(BaseModel):
    employerNumber : int
    workerNumber : int
    lastMessage : str
    workerName : str

class talkToAgent(BaseModel):
    employerNumber : int
    workerNumber : int
    worker_bank_name : str
    worker_pan_name : str
    vpa : str
    issue : str

class Dummy_worker(BaseModel):
    name: str
    email : str
    workerNumber:int

class Domestic_Worker_Schema(Dummy_worker):
    employers : List[Employer] = []

class Employer_Schema(Employer):
    workers : List[Dummy_worker] = []

class ShowEmployer(BaseModel):
    name:str
    email:str
    domestic_workers: List[Domestic_Worker] = []
    class Config():
        from_attributes = True


class ShowDomesticWorker(BaseModel):
    name : str
    email: str
    employers : List[Employer] = []
    class Config():
        from_attributes = True

class Login_Employer(BaseModel):
    email: str
    password:str    

class Contract(BaseModel):
    employerNumber: int
    workerNumber : int
    upi : str
    accountNumber : str
    ifsc : str
    name : str
    salary : int

class Vendor(BaseModel):
    vpa : str
    workerNumber : int
    name : str
    pan : str
    accountNumber : str
    ifsc : str
    employerNumber : int