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
from ..models import CashAdvanceManagement, worker_employer, SalaryDetails



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
    """Store cash advance data in CashAdvanceManagement table."""
    db = next(get_db())
    try:
        # Create new cash advance record
        cash_advance_record = CashAdvanceManagement(
            id=str(uuid.uuid4().hex),
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
        db.commit()
        
        return {
            "success": True,
            "message": "Cash advance data stored successfully",
            "record_id": cash_advance_record.id
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
            
        db.commit()
        
        return {
            "success": True,
            "message": "Cash advance record updated successfully",
            "record_id": existing_record.id,
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
    year: int = None
) -> dict:
    """Update bonus/deduction in SalaryDetails table for a specific month/year."""
    db = next(get_db())
    try:
        current_date = datetime.now()
        target_month = month or current_date.month
        target_year = year or current_date.year
        
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
            
            db.commit()
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
            db.commit()
            action = "created"
        
        return {
            "success": True,
            "message": f"Salary details {action} successfully",
            "month": target_month,
            "year": target_year,
            "bonus": bonus,
            "deduction": deduction
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
    chat_id: str = ""
) -> dict:
    """Store data in both CashAdvanceManagement and SalaryDetails tables."""
    db = next(get_db())
    try:
        results = []
        
        # Store cash advance data if provided
        if cash_advance_data:
            cash_advance_record = CashAdvanceManagement(
                id=str(uuid.uuid4().hex),
                worker_id=worker_id,
                employer_id=employer_id,
                cashAdvance=cash_advance_data.get('cashAdvance', 0),
                repaymentAmount=cash_advance_data.get('repaymentAmount', 0),
                repaymentStartMonth=cash_advance_data.get('repaymentStartMonth', 0),
                repaymentStartYear=cash_advance_data.get('repaymentStartYear', 0),
                frequency=cash_advance_data.get('frequency', 1),
                chatId=chat_id
            )
            db.add(cash_advance_record)
            results.append("Cash advance data stored")
        
        # Store salary data if provided
        if salary_data:
            current_date = datetime.now()
            target_month = salary_data.get('month', current_date.month)
            target_year = salary_data.get('year', current_date.year)
            
            # Check if record exists
            existing_salary = db.query(SalaryDetails).filter(
                SalaryDetails.worker_id == worker_id,
                SalaryDetails.employer_id == employer_id,
                SalaryDetails.month == target_month,
                SalaryDetails.year == target_year
            ).first()
            
            if existing_salary:
                if salary_data.get('bonus') is not None:
                    existing_salary.bonus = salary_data['bonus']
                if salary_data.get('deduction') is not None:
                    existing_salary.deduction = salary_data['deduction']
                results.append("Salary details updated")
            else:
                new_salary_detail = SalaryDetails(
                    id=str(uuid.uuid4().hex),
                    worker_id=worker_id,
                    employer_id=employer_id,
                    month=target_month,
                    year=target_year,
                    bonus=salary_data.get('bonus', 0),
                    deduction=salary_data.get('deduction', 0)
                )
                db.add(new_salary_detail)
                results.append("Salary details created")
        
        db.commit()
        
        return {
            "success": True,
            "message": "Data stored successfully",
            "actions": results
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

def mark_advance_as_paid_func(
    worker_id: str,
    employer_id: str,
    amount_paid: int
) -> dict:
    """Mark cash advance as already paid - store with 0 repayment."""
    db = next(get_db())
    try:
        # Create record showing advance was paid
        paid_advance_record = CashAdvanceManagement(
            id=str(uuid.uuid4().hex),
            worker_id=worker_id,
            employer_id=employer_id,
            cashAdvance=amount_paid,
            repaymentAmount=0,  # 0 because already paid
            repaymentStartMonth=0,
            repaymentStartYear=0,
            frequency=0,
            chatId=f"paid_advance_{int(time.time())}"
        )
        
        db.add(paid_advance_record)
        db.commit()
        
        return {
            "success": True,
            "message": f"₹{amount_paid} marked as paid advance",
            "record_id": paid_advance_record.id
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
        
        if response.status_code == 200:
            return {
                "success": True,
                "message": "Payment link generated and sent successfully",
                "response": response.json()
            }
        else:
            return {
                "success": False,
                "error": f"API call failed with status:####{response.text}####: {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        print(f"Error generating payment link: {e}")
        return {
            "success": False,
            "error": str(e)
        }
        response = requests.get(url, params=payload)
        
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

def update_salary_func(employer_number: int, worker_name: str, new_salary: int) -> dict:
    try:
        # API endpoint
        url = "https://conv.sampatticards.com/user/update_salary"
        
        # Parameters for the API call
        params = {
            "employerNumber": employer_number,
            "workerName": worker_name,
            "salary": new_salary
        }
        
        # Make the API call
        response = requests.put(url, params=params)
        
        if response.status_code == 200:
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
        return {
            "success": False,
            "message": f"Error updating salary: {str(e)}",
            "error": str(e)
        }

# Create the tool
update_salary_tool = StructuredTool.from_function(
    func=update_salary_func,
    name="update_salary_tool",
    description="Update worker salary using API call. Use this when user wants to change only the salary amount.",
)

# Create structured tools
get_worker_by_name_and_employer_tool = StructuredTool.from_function(
    func=get_worker_by_name_and_employer_func,
    name="get_worker_by_name_and_employer",
    description="Find worker details by name and employer number from worker_employer table. Returns worker information if found."
)

store_cash_advance_data_tool = StructuredTool.from_function(
    func=store_cash_advance_data_func,
    name="store_cash_advance_data",
    description="Store complete cash advance data in CashAdvanceManagement table after all details are confirmed."
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

update_salary_details_func_tool = StructuredTool.from_function(
    func=update_salary_details_func,
    name="update_salary_details",
    description="Update salary details for a worker."
)

store_combined_data_func_tool = StructuredTool.from_function(
    func=store_combined_data_func,
    name="store_combined_data",
    description="Store combined data for cash advance and salary details."
)

mark_advance_as_paid_func_tool = StructuredTool.from_function(
    func=mark_advance_as_paid_func,
    name="mark_advance_as_paid",
    description="Mark cash advance as already paid - store with 0 repayment."
)

generate_payment_link_func_tool = StructuredTool.from_function(
    func=generate_payment_link_func,
    name="generate_payment_link",
    description="Generate payment link by calling the cash advance API."
)