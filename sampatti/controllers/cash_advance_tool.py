from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import Tool
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
import uuid
from typing import Optional
from langchain.tools import StructuredTool
import requests, os, tempfile
from pydub import AudioSegment
from urllib.parse import urlparse
from .utility_functions import call_sarvam_api
from ..database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import CashAdvanceManagement, worker_employer, SalaryDetails, SalaryManagementRecords
from .. import models
from datetime import datetime



def save_to_txt(data: str, filename: str = "research_output.txt"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_text = f"--- Research Output ---\nTimestamp: {timestamp}\n\n{data}\n\n"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(formatted_text)
    
    return f"Data successfully saved to {filename}"

save_tool = Tool(
    name="save_text_to_file",
    func=save_to_txt,
    description="Saves structured research data to a text file.",
)


# Pydantic models for structured output
class CashAdvanceData(BaseModel):
    worker_name: str = ""
    worker_id: str = ""
    employer_id: str = ""
    monthly_salary: int = -1
    cashAdvance: int = -1
    repaymentAmount: int = -1
    repaymentStartMonth: int = -1
    repaymentStartYear: int = -1
    frequency: int = -1
    bonus: int = -1
    deduction: int = -1
    chatId: str = ""

class AgentResponse(BaseModel):
    updated_data: CashAdvanceData
    readyToConfirm: int = 0
    ai_message: str

# Tools for the agent
def fetch_all_workers_linked_to_employer(employer_number: int) -> dict:
    """Check how many workers are linked to an employer and return appropriate response."""
    db = next(get_db())
    try:
        # Fetch all workers for this employer
        results = db.execute(
            worker_employer.select().where(
                worker_employer.c.employer_number == employer_number
            )
        ).fetchall()
        
        if not results:
            return {
                "status": "no_workers",
                "message": f"No workers found for employer number {employer_number}",
                "worker_count": 0
            }
        
        worker_count = len(results)
        
        if worker_count == 1:
            # Single worker - return worker details and ask for salary action
            worker = results[0]
            return {
                "status": "single_worker",
                "message": f"Found 1 worker linked to employer {employer_number}. What would you like to do with {worker.worker_name}'s salary?",
                "worker_count": 1,
                "worker_details": {
                    "worker_id": worker.worker_id,
                    "employer_id": worker.employer_id,
                    "worker_name": worker.worker_name,
                    "salary_amount": worker.salary_amount,
                    "worker_number": worker.worker_number
                }
            }
        else:
            # Multiple workers - ask user to specify worker name
            worker_names = [row.worker_name for row in results if row.worker_name]
            return {
                "status": "multiple_workers",
                "message": f"Found {worker_count} workers linked to employer {employer_number}. Please specify which worker you want to work with.",
                "worker_count": worker_count,
                "worker_names": worker_names
            }
            
    except Exception as e:
        print(f"Error checking workers for employer: {e}")
        return {
            "status": "error",
            "message": f"Error checking workers: {str(e)}",
            "worker_count": 0
        }
    finally:
        db.close()

def fetch_worker_employer_relation(worker_name: str, employer_number: int) -> dict:
    """Find worker details by name and employer number from worker_employer table."""
    db = next(get_db())
    try:
        # Normalize input name for better matching
        worker_name_lowercase = worker_name.strip().lower()
        
        # Fetch all workers for this employer
        results = db.execute(
            worker_employer.select().where(
                worker_employer.c.employer_number == employer_number
            )
        ).fetchall()
        
        exact_match = None
        partial_matches = []
        
        for row in results:
            worker_name_db = row.worker_name or ""
            worker_name_db_lowercase = worker_name_db.strip().lower()

            if worker_name_db_lowercase == worker_name_lowercase:
                exact_match = row
                break
            elif worker_name_lowercase in worker_name_db_lowercase or worker_name_db_lowercase in worker_name_lowercase:
                partial_matches.append(row)

        if exact_match:
            return {
                "found": True,
                "worker_id": exact_match.worker_id,
                "employer_id": exact_match.employer_id,
                "worker_name": exact_match.worker_name,
                "salary_amount": exact_match.salary_amount,
                "worker_number": exact_match.worker_number
            }
        elif partial_matches:
            # Return the closest match (first partial)
            row = partial_matches[0]
            return {
                "found": True,
                "worker_id": row.worker_id,
                "employer_id": row.employer_id,
                "worker_name": row.worker_name,
                "salary_amount": row.salary_amount,
                "worker_number": row.worker_number,
                "note": "Partial match found. Please verify the worker name is correct."
            }
        else:
            # Suggest available names
            suggestions = [row.worker_name for row in results if row.worker_name]
            return {"found": False, "suggestions": suggestions[:5]}
            
    except Exception as e:
        print(f"Error finding worker: {e}")
        return {"found": False, "error": str(e)}
    finally:
        db.close()

def fetch_existing_cash_advance_details(worker_id: str, employer_id: str) -> dict:
    """Get existing cash advance record for a worker and employer."""
    db = next(get_db())
    try:
        cash_advance_records = db.query(models.CashAdvanceManagement).filter(
            models.CashAdvanceManagement.worker_id == worker_id,
            models.CashAdvanceManagement.employer_id == employer_id
        ).all()

        worker_employer = db.query(models.worker_employer).filter(
            models.worker_employer.c.worker_id == worker_id,
            models.worker_employer.c.employer_id == employer_id
        ).first()

        print("monthly_salary:", worker_employer.salary_amount)

        total_records = []
        for advance_record in cash_advance_records:
            total_records.append({
                "found": True,
                "record_id": advance_record.id,
                "cashAdvance": advance_record.cashAdvance,
                "repaymentAmount": advance_record.repaymentAmount,
                "repaymentStartMonth": advance_record.repaymentStartMonth,
                "repaymentStartYear": advance_record.repaymentStartYear,
                "frequency": advance_record.frequency,
                "chatId":   advance_record.chatId,
                "monthly_salary": worker_employer.salary_amount,
                "date_issued_on" : advance_record.date_issued_on,
                "payment_status": advance_record.payment_status
            })

        if total_records:
            return {"found": True, "records": total_records}
        else:
            return {"found": False}
            
    except Exception as e:
        print(f"Error getting existing cash advance: {e}")
        return {"found": False, "error": str(e)}
    finally:
        db.close()


def generate_payment_link_func(
    employer_number: int,
    worker_name: str,
    cash_advance: int = 0,
    bonus: int = 0,
    deduction: int = 0,
    repayment: int = 0,
    monthly_salary: int = 0,
    repayment_start_month: int | None = None,
    repayment_start_year: int | None = None,
    frequency: int = 1,
    attendance: int = 31,
) -> dict:
    """Generate payment link by calling the cash advance API.

    IMPORTANT: Do not write to DB before payment. This only creates a Cashfree order
    embedding all details (cash advance, repayment, schedule, bonus, deduction)
    in the order_note for webhook processing after payment.
    """
    try:

        # API endpoint
        url = "https://conv.sampatticards.com/cashfree/cash_advance_link"
        
        # Prepare payload
        payload = {
            "employerNumber": employer_number,
            "workerName": worker_name,
            "cash_advance": cash_advance,
            "repayment_amount": repayment,
            "monthly_salary": monthly_salary,
            "bonus": bonus,
            "deduction": deduction,
            "repayment_start_month": repayment_start_month,
            "repayment_start_year": repayment_start_year,
            "frequency": frequency,
            "attendance": attendance
        }
        # Drop None values to avoid FastAPI parse issues
        payload = {k: v for k, v in payload.items() if v is not None}
        print("Print Payload: ", payload)
        
        # Make API call
        response = requests.get(url, params=payload)
        
        if response.status_code == 200:
            response_data = response.json()
            order_id = response_data.get("order_id")
            order_amount = int(response_data.get("order_amount"))
            
            # Calculate total salary (should match what cash_advance_link calculates)
            total_salary = cash_advance + bonus + monthly_salary - repayment - deduction
            
            print(f"Order Amount & Order ID: {order_amount}, {order_id}")

            if order_id:
                # If order_id is present, store it in the database
                db = next(get_db())
                try:
                    # Get worker and employer details
                    worker_employer = db.query(models.worker_employer).filter(
                        models.worker_employer.c.employer_number == employer_number,
                        func.lower(models.worker_employer.c.worker_name) == worker_name.strip().lower()
                    ).first()
                    
                    if not worker_employer:
                        return {
                            "success": False,
                            "error": "Worker-Employer relationship not found"
                        }
                    
                    # Get current date for date_issued_on
                    current_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Create new salary management record
                    new_salary_management = SalaryManagementRecords(
                        id=str(uuid.uuid4()),
                        worker_id=worker_employer.worker_id,
                        employer_id=worker_employer.employer_id,
                        currentMonthlySalary=monthly_salary,  # Original monthly salary
                        modifiedMonthlySalary=order_amount,  # Total amount to be paid
                        cashAdvance=cash_advance,
                        repaymentAmount=repayment,
                        repaymentStartMonth=repayment_start_month,
                        repaymentStartYear=repayment_start_year,
                        frequency=frequency,
                        bonus=bonus,
                        deduction=deduction,
                        date_issued_on=current_date_str,
                        order_id=order_id,
                        payment_status="pending"  # Initial status is pending
                    )
                    
                    db.add(new_salary_management)
                    
                    # If there's cash advance or repayment, also create CashAdvanceManagement record
                    if cash_advance > 0 or repayment > 0:
                        new_cash_advance_record = CashAdvanceManagement(
                            id=str(uuid.uuid4()),
                            worker_id=worker_employer.worker_id,
                            employer_id=worker_employer.employer_id,
                            cashAdvance=cash_advance,
                            repaymentAmount=repayment,
                            repaymentStartMonth=repayment_start_month,
                            repaymentStartYear=repayment_start_year,
                            frequency=frequency,
                            chatId=None,  # Set this if you have chat context
                            order_id=order_id,
                            payment_status="PENDING",
                            date_issued_on=current_date_str
                        )
                        db.add(new_cash_advance_record)
                        print(f"Cash advance record created with advance: {cash_advance}, repayment: {repayment}")
                    
                    db.commit()
                    print(f"Records saved successfully with order_id: {order_id}")
                    
                except Exception as e:
                    db.rollback()
                    print(f"Error saving records: {e}")
                    return {
                        "success": False,
                        "error": f"Failed to save records: {str(e)}"
                    }
                finally:
                    db.close()

            return {
                "success": True,
                "message": "Payment link generated and sent successfully",
                "order_id": order_id,
                "order_amount": order_amount,
                "total_salary": total_salary,
                "cash_advance": cash_advance,
                "repayment": repayment,
                "response": response_data
            }
        else:
            return {
                "success": False,
                "error": f"API call failed with status {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        print(f"Error generating payment link: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_salary_func(employer_number: int, worker_name: str, new_salary: int, chat_id: str = "") -> dict:
    db = next(get_db())
    try:
        # API endpoint for salary update
        url = "https://conv.sampatticards.com/user/update_salary"
        
        # Parameters for the API call
        params = {
            "employerNumber": employer_number,
            "workerName": worker_name,
            "salary": new_salary
        }
        
        # Try to find worker in database to get IDs
        worker_data = None
        worker_id = None
        employer_id = None
        current_salary = 0
        
        try:
            # Get the worker details using employer number and name
            worker_data = db.query(worker_employer).filter(
                worker_employer.employer_number == employer_number,
                worker_employer.worker_name == worker_name
            ).first()
            
            if worker_data:
                worker_id = worker_data.worker_id
                employer_id = worker_data.employer_id
                
                # Try to get current salary before update
                latest_salary = db.query(SalaryDetails).filter(
                    SalaryDetails.worker_id == worker_id
                ).order_by(SalaryDetails.id.desc()).first()
                
                if latest_salary and latest_salary.salary:
                    current_salary = latest_salary.salary
        except Exception as db_error:
            print(f"Warning: Could not retrieve worker data: {db_error}")
        
        # Make the API call to update salary
        response = requests.put(url, params=params)
        
        if response.status_code == 200:
            # If worker data was found, create a SalaryManagementRecords entry
            if worker_id and employer_id:
                try:
                    # Create a record in SalaryManagementRecords for tracking the salary change
                    salary_management_record_id = str(uuid.uuid4())
                    new_salary_management = SalaryManagementRecords(
                        id=salary_management_record_id,
                        worker_id=worker_id,
                        employer_id=employer_id,
                        currentMonthlySalary=current_salary,
                        modifiedMonthlySalary=new_salary,
                        cashAdvance=0,  # No cash advance for salary updates
                        repaymentAmount=0,  # No repayment for salary updates
                        repaymentStartMonth=None,
                        repaymentStartYear=None,
                        frequency=1,
                        bonus=0,
                        deduction=0,
                        chatId=chat_id,
                        date_issued_on=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    
                    db.add(new_salary_management)
                    db.commit()
                    
                    return {
                        "success": True,
                        "message": f"Salary updated successfully for {worker_name} to ₹{new_salary}",
                        "data": response.json() if response.content else {},
                        "salary_management_record_id": salary_management_record_id
                    }
                except Exception as record_error:
                    print(f"Warning: Could not create salary management record: {record_error}")
            
            return {
                "success": True,
                "message": f"Salary updated successfully for {worker_name} to ₹{new_salary}",
                "data": response.json() if response.content else {}
            }
        else:
            return {
                "success": False,
                "message": f"Failed to update salary. Status code: {response.status_code}",
                "error": response.text
            }
            
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        return {
            "success": False,
            "message": f"Error updating salary: {str(e)}",
            "error": str(e)
        }
    finally:
        if 'db' in locals():
            db.close()

# Create the tool
update_salary_tool = StructuredTool.from_function(
    func=update_salary_func,
    name="update_salary_tool",
    description="Update worker's monthly salary and store the change in SalaryManagementRecords using API call. Use this when user wants to change only the salary amount.",
)

# Create structured tools
fetch_worker_employer_relation_tool = StructuredTool.from_function(
    func=fetch_worker_employer_relation,
    name="fetch_worker_employer_relation",
    description="Find worker employer relation details by worker name and employer number from worker_employer table. Returns relation information if found."
)


fetch_existing_cash_advance_details_tool = StructuredTool.from_function(
    func=fetch_existing_cash_advance_details,
    name="fetch_existing_cash_advance_details",
    description="Get existing cash advance record for a worker and employer according to the payment status of the cash advance. Returns record if found."
)

generate_payment_link_func_tool = StructuredTool.from_function(
    func=generate_payment_link_func,
    name="generate_payment_link",
    description=(
        "Generate payment link (no DB writes). Provide: employer_number, worker_name, "
        "cash_advance, repayment, repayment_start_month, repayment_start_year, frequency, "
        "monthly_salary, bonus, deduction, attendance. The webhook updates DB on payment."
    ),
)


fetch_all_workers_linked_to_employer_tool = StructuredTool.from_function(
    func=fetch_all_workers_linked_to_employer,
    name="fetch_all_workers_linked_to_employer",
    description="Fetch all workers linked to an employer. If single worker, returns worker details and prompts for salary action. If multiple workers, asks user to specify worker name."
)
