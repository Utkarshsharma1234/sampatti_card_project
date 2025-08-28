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
from ..models import CashAdvanceManagement, worker_employer, SalaryDetails, SalaryManagementRecords



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
def check_workers_for_employer_func(employer_number: int) -> dict:
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
                },
                "prompt": "Please specify what you want to do:\n- Give bonus (specify amount)\n- Apply deduction (specify amount)\n- Give cash advance (specify amount)\n- Update monthly salary (specify new amount)\n- Other salary-related action"
            }
        else:
            # Multiple workers - ask user to specify worker name
            worker_names = [row.worker_name for row in results if row.worker_name]
            return {
                "status": "multiple_workers",
                "message": f"Found {worker_count} workers linked to employer {employer_number}. Please specify which worker you want to work with.",
                "worker_count": worker_count,
                "worker_names": worker_names,
                "prompt": f"Available workers: {', '.join(worker_names)}\nPlease provide the worker name to proceed further."
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

def get_worker_by_name_and_employer_func(worker_name: str, employer_number: int) -> dict:
    """Find worker details by name and employer number from worker_employer table."""
    db = next(get_db())
    try:
        # Normalize input name for better matching
        norm_input = worker_name.strip().lower()
        
        # Fetch all workers for this employer
        results = db.execute(
            worker_employer.select().where(
                worker_employer.c.employer_number == employer_number
            )
        ).fetchall()
        
        exact_match = None
        partial_matches = []
        
        for row in results:
            db_name = row.worker_name or ""
            norm_db_name = db_name.strip().lower()
            
            if norm_db_name == norm_input:
                exact_match = row
                break
            elif norm_input in norm_db_name or norm_db_name in norm_input:
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

def store_cash_advance_data_func(
    worker_id: str,
    employer_id: str,
    cash_advance: int,
    repayment_amount: int,
    repayment_start_month: int,
    repayment_start_year: int,
    frequency: int,
    chat_id: str
) -> dict:
    """Store cash advance data in CashAdvanceManagement and SalaryManagementRecords tables."""
    db = next(get_db())
    try:
        # Create new cash advance record
        cash_advance_id = str(uuid.uuid4().hex)
        cash_advance_record = CashAdvanceManagement(
            id=cash_advance_id,
            worker_id=worker_id,
            employer_id=employer_id,
            cashAdvance=cash_advance,
            repaymentAmount=repayment_amount,
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,
            chatId=chat_id
        )
        
        db.add(cash_advance_record)
        
        # Try to get current monthly salary
        current_salary = 0
        try:
            # Get the latest salary detail for this worker
            latest_salary = db.query(SalaryDetails).filter(
                SalaryDetails.worker_id == worker_id,
                SalaryDetails.employer_id == employer_id
            ).order_by(SalaryDetails.id.desc()).first()
            
            if latest_salary and latest_salary.salary:
                current_salary = latest_salary.salary
        except Exception as salary_error:
            print(f"Warning: Could not retrieve current salary: {salary_error}")
        
        # Create a new SalaryManagementRecords entry
        salary_management_record_id = str(uuid.uuid4())
        new_salary_management = SalaryManagementRecords(
            id=salary_management_record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_salary,
            modifiedMonthlySalary=current_salary,  # No change to salary
            cashAdvance=cash_advance,
            repaymentAmount=repayment_amount,
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,
            bonus=0,  # No bonus for new cash advance
            deduction=0,  # No deduction for new cash advance
            chatId=chat_id,
            date_issued_on=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        
        db.add(new_salary_management)
        db.commit()
        
        return {
            "success": True,
            "message": "Cash advance data stored successfully",
            "record_id": cash_advance_id,
            "salary_management_record_id": salary_management_record_id
        }
    except Exception as e:
        db.rollback()
        print(f"Error storing cash advance data: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()

def get_existing_cash_advance_func(worker_id: str, employer_id: str) -> dict:
    """Get existing cash advance record for a worker and employer."""
    db = next(get_db())
    try:
        existing_record = db.query(CashAdvanceManagement).filter(
            CashAdvanceManagement.worker_id == worker_id,
            CashAdvanceManagement.employer_id == employer_id
        ).first()

        monthly_salary = db.query(worker_employer).where(
            worker_employer.c.worker_id == worker_id,
            worker_employer.c.employer_id == employer_id
        ).first()
        
        if existing_record:
            return {
                "found": True,
                "record_id": existing_record.id,
                "cashAdvance": existing_record.cashAdvance,
                "repaymentAmount": existing_record.repaymentAmount,
                "repaymentStartMonth": existing_record.repaymentStartMonth,
                "repaymentStartYear": existing_record.repaymentStartYear,
                "frequency": existing_record.frequency,
                "chatId": existing_record.chatId,
                "monthly_salary": monthly_salary.monthly_salary
            }
        else:
            return {"found": False}
            
    except Exception as e:
        print(f"Error getting existing cash advance: {e}")
        return {"found": False, "error": str(e)}
    finally:
        db.close()

def update_cash_advance_data_func(
    record_id: str,
    update_fields: dict
) -> dict:
    """
    Update existing cash advance record with flexible field updates.
    update_fields can contain any combination of:
    - cash_advance: int
    - repayment_amount: int  
    - repayment_start_month: int
    - repayment_start_year: int
    - frequency: int
    """
    db = next(get_db())
    try:
        # Find existing record
        existing_record = db.query(CashAdvanceManagement).filter(
            CashAdvanceManagement.id == record_id
        ).first()
        
        if not existing_record:
            return {"success": False, "error": "Cash advance record not found"}
        
        # Store original values for comparison
        original_data = {
            "cashAdvance": existing_record.cashAdvance,
            "repaymentAmount": existing_record.repaymentAmount,
            "repaymentStartMonth": existing_record.repaymentStartMonth,
            "repaymentStartYear": existing_record.repaymentStartYear,
            "frequency": existing_record.frequency
        }
        
        updated_fields = []
        
        # Update fields dynamically based on what's provided
        if "cash_advance" in update_fields and update_fields["cash_advance"] is not None:
            existing_record.cashAdvance = update_fields["cash_advance"]
            updated_fields.append(f"Cash Advance: ₹{original_data['cashAdvance']} → ₹{update_fields['cash_advance']}")
            
        if "repayment_amount" in update_fields and update_fields["repayment_amount"] is not None:
            existing_record.repaymentAmount = update_fields["repayment_amount"]
            updated_fields.append(f"Repayment Amount: ₹{original_data['repaymentAmount']} → ₹{update_fields['repayment_amount']}")
            
        if "repayment_start_month" in update_fields and update_fields["repayment_start_month"] is not None:
            existing_record.repaymentStartMonth = update_fields["repayment_start_month"]
            updated_fields.append(f"Start Month: {original_data['repaymentStartMonth']} → {update_fields['repayment_start_month']}")
            
        if "repayment_start_year" in update_fields and update_fields["repayment_start_year"] is not None:
            existing_record.repaymentStartYear = update_fields["repayment_start_year"]
            updated_fields.append(f"Start Year: {original_data['repaymentStartYear']} → {update_fields['repayment_start_year']}")
            
        if "frequency" in update_fields and update_fields["frequency"] is not None:
            existing_record.frequency = update_fields["frequency"]
            frequency_map = {1: "Monthly", 2: "Every 2 months", 3: "Quarterly", 6: "Half-yearly", 12: "Yearly"}
            old_freq = frequency_map.get(original_data['frequency'], f"Every {original_data['frequency']} months")
            new_freq = frequency_map.get(update_fields['frequency'], f"Every {update_fields['frequency']} months")
            updated_fields.append(f"Frequency: {old_freq} → {new_freq}")
            
        if not updated_fields:
            return {"success": False, "error": "No valid fields provided for update"}
        
        # Get worker and salary details to store in SalaryManagementRecords
        worker_id = existing_record.worker_id
        employer_id = existing_record.employer_id
        chat_id = existing_record.chatId
        
        # Try to get current monthly salary from SalaryDetails
        current_salary = 0
        try:
            # Get the latest salary detail for this worker
            latest_salary = db.query(SalaryDetails).filter(
                SalaryDetails.worker_id == worker_id,
                SalaryDetails.employer_id == employer_id
            ).order_by(SalaryDetails.id.desc()).first()
            
            if latest_salary and latest_salary.salary:
                current_salary = latest_salary.salary
        except Exception as salary_error:
            print(f"Warning: Could not retrieve current salary: {salary_error}")
        
        # Create a new SalaryManagementRecords entry for the update
        salary_management_record_id = str(uuid.uuid4())
        new_salary_management = SalaryManagementRecords(
            id=salary_management_record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_salary,
            modifiedMonthlySalary=current_salary,  # No change to salary
            cashAdvance=existing_record.cashAdvance,
            repaymentAmount=existing_record.repaymentAmount,
            repaymentStartMonth=existing_record.repaymentStartMonth,
            repaymentStartYear=existing_record.repaymentStartYear,
            frequency=existing_record.frequency,
            bonus=0,  # No bonus for cash advance updates
            deduction=0,  # No deduction for cash advance updates
            chatId=chat_id,
            date_issued_on=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        db.add(new_salary_management)
        db.commit()
        
        return {
            "success": True,
            "message": "Cash advance record updated successfully",
            "record_id": existing_record.id,
            "salary_management_record_id": salary_management_record_id,
            "changes_made": updated_fields,
            "updated_data": {
                "cashAdvance": existing_record.cashAdvance,
                "repaymentAmount": existing_record.repaymentAmount,
                "repaymentStartMonth": existing_record.repaymentStartMonth,
                "repaymentStartYear": existing_record.repaymentStartYear,
                "frequency": existing_record.frequency
            }
        }
    except Exception as e:
        db.rollback()
        print(f"Error updating cash advance data: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


def update_salary_details_func(
    worker_id: str,
    employer_id: str,
    bonus: int = None,
    deduction: int = None,
    month: int = None,
    year: int = None,
    chat_id: str = ""
) -> dict:
    """Update bonus/deduction in SalaryDetails table for a specific month/year."""
    db = next(get_db())
    try:
        current_date = datetime.now()
        target_month = month or current_date.month
        target_year = year or current_date.year
        
        # Get current monthly salary
        current_salary = 0
        try:
            # Get the latest salary detail for this worker
            latest_salary = db.query(SalaryDetails).filter(
                SalaryDetails.worker_id == worker_id,
                SalaryDetails.employer_id == employer_id
            ).order_by(SalaryDetails.id.desc()).first()
            
            if latest_salary and latest_salary.salary:
                current_salary = latest_salary.salary
        except Exception as salary_error:
            print(f"Warning: Could not retrieve current salary: {salary_error}")
        
        # Check if salary details record exists for this month/year
        existing_record = db.query(SalaryDetails).filter(
            SalaryDetails.worker_id == worker_id,
            SalaryDetails.employer_id == employer_id,
            SalaryDetails.month == target_month,
            SalaryDetails.year == target_year
        ).first()
        
        if existing_record:
            # Update existing record
            if bonus is not None:
                existing_record.bonus = bonus
            if deduction is not None:
                existing_record.deduction = deduction
            
            action = "updated"
        else:
            # Create new record
            new_salary_detail = SalaryDetails(
                id=str(uuid.uuid4().hex),
                worker_id=worker_id,
                employer_id=employer_id,
                month=target_month,
                year=target_year,
                bonus=bonus or 0,
                deduction=deduction or 0
            )
            db.add(new_salary_detail)
            action = "created"
        
        # Create a record in SalaryManagementRecords for tracking all changes
        salary_management_record_id = str(uuid.uuid4())
        new_salary_management = SalaryManagementRecords(
            id=salary_management_record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_salary,
            modifiedMonthlySalary=current_salary,  # No change to base salary
            cashAdvance=0,  # No cash advance for bonus/deduction updates
            repaymentAmount=0,  # No repayment for bonus/deduction updates
            repaymentStartMonth=None,
            repaymentStartYear=None,
            frequency=1,
            bonus=bonus or 0,
            deduction=deduction or 0,
            chatId=chat_id,
            date_issued_on=current_date.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        db.add(new_salary_management)
        db.commit()
        
        return {
            "success": True,
            "message": f"Salary details {action} successfully",
            "month": target_month,
            "year": target_year,
            "bonus": bonus,
            "deduction": deduction,
            "salary_management_record_id": salary_management_record_id
        }
    except Exception as e:
        db.rollback()
        print(f"Error updating salary details: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()

def store_combined_data_func(
    worker_id: str,
    employer_id: str,
    cash_advance_data: dict = None,
    salary_data: dict = None,
    chat_id: str = "",
    current_monthly_salary: int = 0
) -> dict:
    """Store data in both CashAdvanceManagement, SalaryDetails, and SalaryManagementRecords tables."""
    db = next(get_db())
    try:
        cash_advance_result = None
        salary_details_result = None
        salary_management_result = None
        
        # Store in CashAdvanceManagement if data provided
        if cash_advance_data:
            cash_advance_record_id = str(uuid.uuid4())
            
            new_cash_advance = CashAdvanceManagement(
                id=cash_advance_record_id,
                worker_id=worker_id,
                employer_id=employer_id,
                cashAdvance=cash_advance_data.get('cash_advance', 0),
                repaymentAmount=cash_advance_data.get('repayment_amount', 0),
                repaymentStartMonth=cash_advance_data.get('repayment_start_month'),
                repaymentStartYear=cash_advance_data.get('repayment_start_year'),
                frequency=cash_advance_data.get('frequency', 1),
                chatId=chat_id
            )
            
            db.add(new_cash_advance)
            cash_advance_result = {
                "success": True,
                "record_id": cash_advance_record_id
            }
        
        # Store in SalaryDetails if data provided
        if salary_data:
            salary_record_id = str(uuid.uuid4())
            current_date = datetime.now()
            
            new_salary_details = SalaryDetails(
                id=salary_record_id,
                employerNumber=salary_data.get('employer_number', 0),
                worker_id=worker_id,
                employer_id=employer_id,
                totalAmount=salary_data.get('total_amount', 0),
                salary=salary_data.get('salary', 0),
                bonus=salary_data.get('bonus', 0),
                cashAdvance=salary_data.get('cash_advance', 0),
                repayment=salary_data.get('repayment', 0),
                attendance=salary_data.get('attendance', 0),
                month=salary_data.get('month', current_date.strftime('%B')),
                year=salary_data.get('year', current_date.year),
                order_id=salary_data.get('order_id', ''),
                deduction=salary_data.get('deduction', 0)
            )
            
            db.add(new_salary_details)
            salary_details_result = {
                "success": True,
                "record_id": salary_record_id
            }
        
        # Store in SalaryManagementRecords with combined data from both sources
        salary_management_record_id = str(uuid.uuid4())
        current_datetime = datetime.now()
        
        # Get cash advance data if provided
        ca_amount = 0
        repayment_amount = 0
        repayment_start_month = None
        repayment_start_year = None
        frequency = 1
        
        if cash_advance_data:
            ca_amount = cash_advance_data.get('cash_advance', 0)
            repayment_amount = cash_advance_data.get('repayment_amount', 0)
            repayment_start_month = cash_advance_data.get('repayment_start_month')
            repayment_start_year = cash_advance_data.get('repayment_start_year')
            frequency = cash_advance_data.get('frequency', 1)
        
        # Get bonus/deduction data if provided
        bonus = 0
        deduction = 0
        
        if salary_data:
            bonus = salary_data.get('bonus', 0)
            deduction = salary_data.get('deduction', 0)
        
        # Create new comprehensive record
        new_salary_management = SalaryManagementRecords(
            id=salary_management_record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_monthly_salary,
            modifiedMonthlySalary=current_monthly_salary, # Default to current salary if no modification
            cashAdvance=ca_amount,
            repaymentAmount=repayment_amount,
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,
            bonus=bonus,
            deduction=deduction,
            chatId=chat_id,
            date_issued_on=current_datetime.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        db.add(new_salary_management)
        salary_management_result = {
            "success": True,
            "record_id": salary_management_record_id
        }
        
        # Commit all changes
        db.commit()
        
        return {
            "cash_advance_result": cash_advance_result,
            "salary_details_result": salary_details_result,
            "salary_management_result": salary_management_result,
            "overall_success": True
        }
    except Exception as e:
        db.rollback()
        print(f"Error storing combined data: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()

def store_salary_management_records_func(
    worker_id: str,
    employer_id: str,
    current_monthly_salary: int,
    modified_monthly_salary: int = None,
    cash_advance: int = 0,
    repayment_amount: int = 0,
    repayment_start_month: int = None,
    repayment_start_year: int = None,
    frequency: int = 1,
    bonus: int = 0,
    deduction: int = 0,
    chat_id: str = ""
) -> dict:
    """Store salary management records in SalaryManagementRecords table."""
    db = next(get_db())
    try:
        # Generate a unique ID for the record
        record_id = str(uuid.uuid4())
        
        # Get current date as string
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Set modified monthly salary to current if not provided
        if modified_monthly_salary is None:
            modified_monthly_salary = current_monthly_salary

        # Create new record
        new_record = SalaryManagementRecords(
            id=record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_monthly_salary,
            modifiedMonthlySalary=modified_monthly_salary,
            cashAdvance=cash_advance,
            repaymentAmount=repayment_amount,
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,
            bonus=bonus,
            deduction=deduction,
            chatId=chat_id,
            date_issued_on=current_date
        )
        
        # Add and commit the record
        db.add(new_record)
        db.commit()
        
        return {
            "success": True,
            "message": "Salary management record stored successfully",
            "record_id": record_id
        }
        
    except Exception as e:
        db.rollback()
        print(f"Error storing salary management record: {e}")
        return {
            "success": False,
            "message": f"Failed to store salary management record: {str(e)}"
        }
    finally:
        db.close()

def mark_advance_as_paid_func(
    worker_id: str,
    employer_id: str,
    total_advance_amount: int,
    amount_remaining: int,
    repayment_amount: int,
    repayment_start_month: int,
    repayment_start_year: int,
    frequency: int,
    chat_id: str = ""
) -> dict:
    """Mark a previously given cash advance and set up repayment details.
    
    Args:
        worker_id: Worker's unique ID
        employer_id: Employer's unique ID
        total_advance_amount: Total cash advance amount originally given
        amount_remaining: Remaining amount to be repaid
        repayment_amount: Monthly repayment amount
        repayment_start_month: Month when repayment starts
        repayment_start_year: Year when repayment starts
        frequency: Repayment frequency (default=1 for monthly)
        chat_id: Chat ID for tracking
    
    Returns:
        Dictionary with success status and record IDs
    """
    db = next(get_db())
    try:
        # Generate unique ID
        advance_id = str(uuid.uuid4().hex)
        chat_record_id = chat_id or f"paid_advance_{employer_id}_{worker_id}"
        
        # Create record showing advance in CashAdvanceManagement
        # This tracks the REMAINING amount that needs to be repaid
        paid_advance_record = CashAdvanceManagement(
            id=advance_id,
            worker_id=worker_id,
            employer_id=employer_id,
            cashAdvance=amount_remaining,  # Remaining amount to be repaid
            repaymentAmount=repayment_amount,
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,  # Using the provided frequency
            chatId=chat_record_id
        )
        
        db.add(paid_advance_record)
        
        # Try to get current monthly salary
        current_salary = 0
        try:
            # Get the latest salary detail for this worker
            latest_salary = db.query(SalaryDetails).filter(
                SalaryDetails.worker_id == worker_id,
                SalaryDetails.employer_id == employer_id
            ).order_by(SalaryDetails.id.desc()).first()
            
            if latest_salary and latest_salary.salary:
                current_salary = latest_salary.salary
        except Exception as salary_error:
            print(f"Warning: Could not retrieve current salary: {salary_error}")
        
        # Create a new SalaryManagementRecords entry
        # This records the TOTAL advance amount given for historical tracking
        salary_management_record_id = str(uuid.uuid4())
        new_salary_management = SalaryManagementRecords(
            id=salary_management_record_id,
            worker_id=worker_id,
            employer_id=employer_id,
            currentMonthlySalary=current_salary,
            modifiedMonthlySalary=current_salary,  # No change to salary
            cashAdvance=total_advance_amount,  # TOTAL advance amount given
            repaymentAmount=repayment_amount,  # Monthly repayment amount
            repaymentStartMonth=repayment_start_month,
            repaymentStartYear=repayment_start_year,
            frequency=frequency,
            bonus=0,  # No bonus for paid advance
            deduction=0,  # No deduction for paid advance
            chatId=chat_record_id,
            date_issued_on=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        db.add(new_salary_management)
        db.commit()
        
        # Calculate how many months it will take to repay
        months_to_repay = 0
        if repayment_amount > 0:
            months_to_repay = (amount_remaining + repayment_amount - 1) // repayment_amount
        
        return {
            "success": True,
            "message": f"₹{total_advance_amount} total cash advance recorded with ₹{amount_remaining} remaining to be repaid",
            "record_id": advance_id,
            "salary_management_record_id": salary_management_record_id,
            "estimated_months_to_repay": months_to_repay
        }
    except Exception as e:
        db.rollback()
        print(f"Error marking advance as paid: {e}")
        return {
            "success": False,
            "error": str(e)
        }
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
) -> dict:
    """Generate payment link by calling the cash advance API."""
    try:
        worker_name = worker_name.lower()

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
            "deduction": deduction
        }
        print("Print Payload: ", payload)
        
        # Make API call
        response = requests.get(url, params=payload)
        print("JSON Response: ", response.json())
        
        if response.status_code == 200:
            return {
                "success": True,
                "message": "Payment link generated and sent successfully",
                "response": response.json()
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
get_worker_by_name_and_employer_tool = StructuredTool.from_function(
    func=get_worker_by_name_and_employer_func,
    name="get_worker_by_name_and_employer",
    description="Find worker details by name and employer number from worker_employer table. Returns worker information if found."
)

store_cash_advance_data_func_tool = StructuredTool.from_function(
    func=store_cash_advance_data_func,
    name="store_cash_advance_data",
    description="Store cash advance data in both CashAdvanceManagement and SalaryManagementRecords tables for comprehensive record tracking."
)

get_existing_cash_advance_tool = StructuredTool.from_function(
    func=get_existing_cash_advance_func,
    name="get_existing_cash_advance",
    description="Get existing cash advance record for a worker and employer. Returns record if found."
)

update_cash_advance_data_func_tool = StructuredTool.from_function(
    func=update_cash_advance_data_func,
    name="update_cash_advance",
    description="Update existing cash advance record with flexible field updates."
)

# Create tool for updating salary details
update_salary_details_func_tool = StructuredTool.from_function(
    func=update_salary_details_func,
    name="update_salary_details_func_tool",
    description="Update bonus/deduction in SalaryDetails table for a specific month/year and store in SalaryManagementRecords"
)

store_combined_data_func_tool = StructuredTool.from_function(
    func=store_combined_data_func,
    name="store_combined_data",
    description="Store combined data for cash advance and salary details."
)

mark_advance_as_paid_func_tool = StructuredTool.from_function(
    func=mark_advance_as_paid_func,
    name="mark_advance_as_paid",
    description="Record a previously given cash advance with both total advance amount and remaining amount to be repaid. Creates records in CashAdvanceManagement (with remaining amount) and SalaryManagementRecords (with total advance amount). Parameters: worker_id, employer_id, total_advance_amount, amount_remaining, repayment_amount, repayment_start_month, repayment_start_year, frequency, chat_id."
)

generate_payment_link_func_tool = StructuredTool.from_function(
    func=generate_payment_link_func,
    name="generate_payment_link",
    description="Generate payment link by calling the cash advance API."
)

store_salary_management_records_tool = StructuredTool.from_function(
    func=store_salary_management_records_func,
    name="store_salary_management_records",
    description="Store complete salary management records in SalaryManagementRecords table with cash advance, repayment, bonus, and deduction details."
)

check_workers_for_employer_tool = StructuredTool.from_function(
    func=check_workers_for_employer_func,
    name="check_workers_for_employer",
    description="Check how many workers are linked to an employer. If single worker, returns worker details and prompts for salary action. If multiple workers, asks user to specify worker name."
)