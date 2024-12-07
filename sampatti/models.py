from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from .database import Base

worker_employer = Table('worker_employer', Base.metadata,
    Column('id', String),
    Column('worker_number', ForeignKey('Domestic_Worker.workerNumber'), primary_key=True),
    Column('employer_number', ForeignKey('Employer.employerNumber'), primary_key=True),
    Column('salary_amount', Integer, default=0),
    Column('order_id', String, default=''),
    Column('status', String, default=''),
    Column('vendor_id', String, default=''),
    Column('worker_name', String, default=''),
    Column('employer_id', String, default=''),
    Column('worker_id', String, default = '')
)   


class Domestic_Worker(Base):

    __tablename__ = "Domestic_Worker"
    id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String, nullable=True)
    workerNumber = Column(Integer)
    panNumber = Column(String)
    upi_id = Column(String, nullable=True)
    accountNumber = Column(String, nullable=True)
    ifsc = Column(String, nullable=True)
    vendorId = Column(String, nullable=True)
    employers = relationship("Employer", secondary="worker_employer", back_populates='workers') 


class Employer(Base):
    __tablename__ = "Employer"
    id = Column(String, primary_key=True)
    employerNumber = Column(Integer)
    workers = relationship("Domestic_Worker", secondary="worker_employer",back_populates='employers')

class TalkToAgentEmployer(Base):
    __tablename__ = "Talk_To_Agent"
    id = Column(String, primary_key=True)   
    date = Column(String)
    employerNumber = Column(Integer)
    workerNumber = Column(Integer, default=0)
    worker_bank_name = Column(String)
    worker_pan_name = Column(String)
    vpa = Column(String)
    issue = Column(String)


class MessageLogSystem(Base):
    __tablename__ = "Message_Log_System"
    id = Column(String, primary_key=True)   
    employerNumber = Column(Integer)
    workerNumber = Column(Integer, default=0)
    workerName = Column(String)
    lastMessage = Column(String)
    date = Column(String)

class SalaryDetails(Base):
    __tablename__ = "SalaryDetails"
    id = Column(String, primary_key=True)   
    employerNumber = Column(Integer)
    worker_id = Column(Integer, default=0)
    employer_id = Column(String)
    salary = Column(Integer)
    bonus = Column(Integer)
    order_id=Column(String)

class CashAdvanceManagement(Base):
    __tablename__ = "CashAdvanceManagement"
    id = Column(String, primary_key=True)   
    employerNumber = Column(Integer)
    worker_id = Column(Integer, default=0)
    employer_id = Column(String)
    bonus = Column(Integer)
    cashAdvance = Column(Integer, default = 0)
    monthlyRepayment = Column(Integer, default=0)

class CashAdvanceRecords(Base):
    __tablename__ = "CashAdvanceRecords"
    id = Column(String, primary_key=True)
    employerNumber = Column(Integer)
    worker_id = Column(Integer, default=0)
    employer_id = Column(String)
    typeOfAmount = Column(String)
    amount = Column(Integer)
    dateIssuedOn = Column(String)

class RepaymentRecords(Base):
    __tablename__ = "RepaymentRecords"
    id = Column(String, primary_key=True)
    employerNumber = Column(Integer)
    worker_id = Column(Integer, default=0)
    employer_id = Column(String)
    cashAdvance = Column(String)
    monthlyRepaymentAmount = Column(Integer)
    dateStartedOn = Column(String)
    dateEndingOn = Column(String)
    
    

    
#this new tables are created accordingly change it accordingly

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    employer_number = Column(Integer, unique=True, index=True)
    name = Column(String)
    department = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cash_advances = relationship("CashAdvanceRecord", back_populates="employee")
    
class CashAdvanceRecord(Base):
    __tablename__ = "cash_advance_records"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    current_cash_advance = Column(Integer)
    current_monthly_repayment = Column(Integer)
    remaining_balance = Column(Integer)
    bonus = Column(Integer)
    attendance = Column(Integer)
    repayment_start_month = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    employee = relationship("Employee", back_populates="cash_advances")