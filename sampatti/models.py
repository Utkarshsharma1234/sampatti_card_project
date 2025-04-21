import datetime
from sqlalchemy import Column, Integer, String, Date, ForeignKey, Table
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
    Column('worker_id', String, default = ''),
    Column('date_of_onboarding', String, default=''),
    Column('monthly_leaves', Integer, default=0)
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
    worker_id = Column(String)
    employer_id = Column(String)
    totalAmount = Column(Integer)
    salary = Column(Integer)
    bonus = Column(Integer)
    cashAdvance = Column(Integer)
    repayment = Column(Integer)
    attendance = Column(Integer)
    month = Column(String)
    year = Column(Integer)
    order_id=Column(String)


class SalaryRecords(Base):
    __tablename__ = "SalaryRecords"
    id = Column(String, primary_key=True)
    worker_id = Column(String)
    employer_id = Column(String)
    currentSalary = Column(Integer, default=0)
    modifiedSalary = Column(Integer, default=0)
    dateIssuedOn = Column(String)


class AttendanceRecords(Base):
    __tablename__ = "AttendanceRecords"
    id = Column(String, primary_key=True)
    worker_id = Column(String)
    employer_id = Column(String)
    month = Column(String)
    year = Column(Integer)
    date_of_leave = Column(Integer)


class Survey(Base):
    __tablename__ = "SurveyDetails"
    id = Column(Integer, primary_key=True)
    surveyTitle = Column(String, nullable=False)
    description = Column(String)
    startDate = Column(String)
    endDate = Column(String)

class QuestionBank(Base):
    __tablename__ = "QuestionBank"
    id = Column(Integer, primary_key=True)
    questionText = Column(String)
    surveyId = Column(Integer, ForeignKey('SurveyDetails.id'))
    questionType = Column(String)

class Responses(Base):
    __tablename__ = "Responses"
    id = Column(String, primary_key=True)
    responseText = Column(String, nullable=False)
    workerId = Column(String, ForeignKey('Domestic_Worker.id'))
    respondentId = Column(String)
    questionId = Column(Integer, ForeignKey('QuestionBank.id'))
    surveyId = Column(Integer, ForeignKey('SurveyDetails.id'))
    timestamp = Column(String)
    
class AttendanceRecord(Base):
    __tablename__ = "Attendance_Records"
    uuid = Column(String, primary_key=True)
    worker_id = Column(String, nullable=False)
    employer_id = Column(String, nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    date_of_leave = Column(Date, nullable=False)
    
    
class cashAdvance(Base):
    __tablename__ = "CashAdvanceRecord"
    advance_id = Column(String, primary_key=True)
    worker_id = Column(String, ForeignKey("Domestic_Worker.id"))
    employer_id = Column(String, ForeignKey("Employer.id"))
    monthly_salary = Column(Integer)
    cash_advance = Column(Integer)
    repayment_amount = Column(Integer)
    repayment_start_month = Column(Integer)
    repayment_start_year = Column(Integer)
    current_date = Column(String)  # <--- PROBABLY THIS
    frequency = Column(Integer)
    bonus = Column(Integer)
    deduction = Column(Integer)
    payment_status = Column(String, default='Pending')


    repayments = relationship("CashAdvanceRepaymentLog", back_populates="advance")


class CashAdvanceRepaymentLog(Base):
    __tablename__ = "CashAdvanceRepaymentLog"    #managment
    id = Column(String, primary_key=True, index=True)
    advance_id = Column(String, ForeignKey('CashAdvanceRecord.advance_id'), nullable=False)  # Fixed here
    worker_id = Column(String)
    employer_id = Column(String)
    repayment_start_month = Column(Integer)
    repayment_start_year = Column(Integer)
    repayment_month = Column(Integer)
    repayment_year = Column(Integer)
    scheduled_repayment_amount = Column(Integer)
    actual_repayment_amount = Column(Integer)
    remaining_advance = Column(Integer)
    payment_status = Column(String, default='Pending')
    frequency = Column(Integer, default=1)  # 1, 2, 3, 6, or 0 #add this

    advance = relationship("cashAdvance", back_populates="repayments")

