from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import Tool
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
import uuid, re
from typing import Optional
from langchain.tools import StructuredTool
import requests, os, tempfile
from pydub import AudioSegment
from urllib.parse import urlparse
from .utility_functions import transcribe_audio_from_file_path, get_main_transcript, call_sarvam_api, generate_unique_id, current_date
from ..database import get_db_session, get_db
from sqlalchemy.orm import Session
from ..models import CashAdvanceManagement, worker_employer
from fastapi import Depends
from .. import models
from .main_tool import add_employer


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

search = DuckDuckGoSearchRun()
search_tool = Tool(
    name="searchWeb",
    func=search.run,
    description="Search the web for information",
)

api_wrapper = WikipediaAPIWrapper(top_k_results=5, doc_content_chars_max=100)
wiki_tool = WikipediaQueryRun(api_wrapper=api_wrapper)

# Pydantic models for structured output
class CashAdvanceData(BaseModel):
    worker_id: str = ""
    employer_id: str = ""
    cashAdvance: int = -1
    repaymentAmount: int = -1
    repaymentStartMonth: int = -1
    repaymentStartYear: int = -1
    frequency: int = -1

class AgentResponse(BaseModel):
    updated_data: CashAdvanceData
    readyToConfirm: int = 0
    ai_message: str


class WorkerEmployerInput(BaseModel):
    worker_number: str
    UPI: Optional[str] = None
    bank_account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    pan_number: str
    salary: int
    employer_number: str  # already known and passed from context
    referral_code: Optional[str] = None  # Optional referral code

    @root_validator()
    def validate_payment_method(cls, values):
        UPI, bank_account, ifsc = values.get('UPI'), values.get('bank_account_number'), values.get('ifsc_code')
        if not UPI and (not bank_account or not ifsc):
            raise ValueError("Please provide either UPI or both bank account number and IFSC code.")
        if UPI and (bank_account or ifsc):
            raise ValueError("Please provide only one mode of payment: either UPI or bank account details.")
        return values



def onboard_worker_employer( worker_number: int, employer_number: int, pan_number: str, salary : int, UPI: Optional[str] = "", bank_account_number: Optional[str]= "", ifsc_code: Optional[str] = "", referral_code: Optional[str] = "") -> str:

    bank_passbook_image = "NA"
    pan_card_image = "NA"

    worker_number = int(worker_number)
    employer_number = int(employer_number)

    data = {
        "worker_number": worker_number,
        "employer_number": employer_number,
        "UPI": UPI or "",
        "bank_account_number": bank_account_number or "",
        "ifsc_code": ifsc_code or "",
        "pan_number": pan_number,
        "bank_passbook_image": bank_passbook_image,
        "pan_card_image": pan_card_image,
        "salary": salary,
        "referral_code": referral_code or ""
    }

    url = "https://conv.sampatticards.com/user/ai_agent/onboarding_worker_sheet/create"
    response = requests.post(url, json=data)

    return f"Onboarding completed. Status: {response.status_code}, Response: {response.text}"


def transcribe_audio(mediaId: str):
    """
    Given a mediaId, calls the first API to get audio info, then fetches the audio file from another endpoint,
    saves it to audio_files/{mediaId}_audio.mp3, and returns the file path or a success message.
    """

    orai_api_key = os.environ.get("ORAI_API_KEY")  

    headers = {
        "D360-API-KEY": orai_api_key
    }

    response_1 = requests.get(f"https://waba-v2.360dialog.io/{mediaId}", headers=headers)

    if response_1.status_code != 200:
        return f"Failed to get audio info: {response_1.status_code} {response_1.text}"

    audio_info = response_1.json()
    audio_url = audio_info.get("url")
    if not audio_url or "whatsapp" not in audio_url:
        return f"Audio URL not found or does not contain 'whatsapp' in API response."
    
    whatsapp_index = audio_url.find("whatsapp")
    whatsapp_path = audio_url[whatsapp_index:]

    response_2 = requests.get(f"https://waba-v2.360dialog.io/{whatsapp_path}", headers=headers, stream=True)
    if response_2.status_code != 200:
        return f"Failed to download audio: {response_2.status_code} {response_2.text}"

    output_dir = 'audio_files'
    os.makedirs(output_dir, exist_ok=True)

    temp_path = ""
    wav_path = os.path.join(output_dir, f"{mediaId}_audio.wav")

    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(response_2.content)
        temp_path = temp.name

    print(f"Downloaded temporary file: {temp_path}")

    # Step 2: Convert to WAV format
    audio = AudioSegment.from_file(temp_path)
    audio.export(wav_path, format="wav")

    print(f"Converted to WAV and saved at: {wav_path}")

    result = call_sarvam_api(wav_path)
    transcript = result["transcript"]
    user_language = result["language_code"]
    print("Transcript: ",transcript)
    print("User Language: ",user_language)

    return transcript, user_language


def send_audio(text: str, employerNumber: int, user_language: str = "en-IN"):
    """
    Sends an audio message by calling the /send_audio_message API endpoint.
    Args:
        text (str): The message text to convert to audio.
        employerNumber (int): The employer's number.
        user_language (str, optional): The language code. Defaults to "en-IN".
    Returns:
        dict: The response from the API.
    """
    url = "https://conv.sampatticards.com/user/send_audio_message"
    payload = {
        "text": text,
        "user_language": user_language,
        "employerNumber": employerNumber
    }
    try:
        response = requests.post(url, params=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def normalize_name(name: str) -> str:
    # Lowercase, strip, remove extra/multiple spaces
    return re.sub(r'\s+', ' ', name.strip().lower())

def get_worker_by_name_and_employer(worker_name: str, employer_number: int) -> dict:
    db = next(get_db())
    """
    Find worker details by name and employer number from worker_employer table.
    Returns worker information if found, empty dict if not found.
    Improved: Robust name matching (normalize, partial match, suggestions)
    """
    try:
        # Fetch all workers for this employer
        results = db.execute(
            worker_employer.select().where(
                worker_employer.c.employer_number == employer_number
            )
        ).fetchall()
        
        norm_input = normalize_name(worker_name)
        exact_match = None
        partial_matches = []
        for row in results:
            db_name = row.worker_name or ""
            norm_db_name = normalize_name(db_name)
            if norm_db_name == norm_input:
                exact_match = row
                break
            elif norm_input in norm_db_name or norm_db_name in norm_input:
                partial_matches.append(row)

        print("Exact Matches:#######: ", exact_match)
        if exact_match:
            return {
                "found": True,
                "worker_id": exact_match.worker_id,
                "employer_id": exact_match.employer_id,
                "worker_name": exact_match.worker_name,
                "salary_amount": exact_match.salary_amount
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
                "note": "Partial match found. Please verify the worker name is correct."
            }
        else:
            # Optionally, suggest available names
            suggestions = [row.worker_name for row in results if row.worker_name]
            return {"found": False, "suggestions": suggestions}
    except Exception as e:
        print(f"Error finding worker: {e}")
        return {"found": False, "error": str(e)}
    finally:
        db.close()


def get_worker_details(workerNumber : int):
    """
    Fetches worker details from the database using the worker number.
    Returns a dictionary with worker details or an error message.
    """
    
    if workerNumber.length == 12:
        workerNumber = workerNumber[2:]
    elif workerNumber.length == 11:
        workerNumber = workerNumber[1:]
    elif workerNumber.length == 10:
        workerNumber = workerNumber
    else:
        return {"error" : "Worker number is invalid."}

    url = "https://conv.sampatticards.com/user/check_worker"
    payload = {
        "workerNumber": workerNumber
    }

    try:
        response = requests.get(url, params=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


# ============================================================================
# SYSTEMATIC REFERRAL PROCESSING TOOLS
# Step-by-step referral validation and processing for onboarding agent
# ============================================================================

def validate_referral_code(referral_code: str) -> dict:
    """
    STEP 1: Validate referral code format and check if referring employer exists
    
    Args:
        referral_code: The referral code to validate
        
    Returns:
        Dictionary with validation result and referring employer info
    """
    db = next(get_db())
    try:
        # Basic format validation
        if not referral_code or len(referral_code.strip()) < 5:
            return {
                "valid": False,
                "message": "Please provide a valid referral code.",
                "can_continue": True
            }
        
        # Find employer by referral code
        referring_employer = db.query(models.Employer).filter(
            models.Employer.referralCode == referral_code.strip()
        ).first()
        
        if not referring_employer:
            return {
                "valid": False,
                "message": "Invalid referral code. Please check and try again.",
                "can_continue": True
            }
        
        return {
            "valid": True,
            "message": "Referral code is valid.",
            "referring_employer": {
                "id": referring_employer.id,
                "employer_number": referring_employer.employerNumber,
                "upi_id": referring_employer.upiId,
                "account_number": referring_employer.accountNumber,
                "ifsc": referring_employer.ifsc
            },
            "can_continue": True
        }
        
    except Exception as e:
        return {
            "valid": False,
            "message": f"Error validating referral code: {str(e)}",
            "can_continue": True
        }
    finally:
        db.close()


def check_employer_first_payment_status(employer_number: int) -> dict:
    """
    STEP 2: Check if current employer has already made their first payment
    
    Args:
        employer_number: The employer number to check
        
    Returns:
        Dictionary with payment status and employer info
    """
    db = next(get_db())
    try:
        # Find employer
        employer = db.query(models.Employer).filter(
            models.Employer.employerNumber == employer_number
        ).first()
        
        if not employer:
            return {
                "status": "new_employer",
                "message": "New employer, can proceed with referral.",
                "first_payment_done": False,
                "can_continue": True
            }
        
        # Check if first payment is already done
        if employer.FirstPaymentDone:
            return {
                "status": "already_paid",
                "message": "This employer is already onboarded with us and has made their first payment. Referral code cannot be applied.",
                "first_payment_done": True,
                "can_continue": False,  # Stop onboarding if already paid
                "employer": employer
            }
        
        # Check salary details for any payment
        salary_details = db.query(models.SalaryDetails).filter(
            models.SalaryDetails.employerNumber == employer_number
        ).first()
        
        if salary_details and salary_details.order_id:
            # Check payment status via Cashfree
            from . import cashfree_api
            payment_status = cashfree_api.check_order_status(salary_details.order_id)
            if payment_status.get("order_status") == "PAID":
                employer.FirstPaymentDone = True
                db.commit()
                return {
                    "status": "already_paid",
                    "message": "This employer is already onboarded with us and has made their first payment. Referral code cannot be applied.",
                    "first_payment_done": True,
                    "can_continue": False,
                    "employer": employer
                }
        
        return {
            "status": "no_payment",
            "message": "Employer exists but no payment made yet. Can proceed with referral.",
            "first_payment_done": False,
            "can_continue": True,
            "employer": employer
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error checking payment status: {str(e)}",
            "first_payment_done": False,
            "can_continue": True
        }
    finally:
        db.close()



def create_referral_mapping(referring_employer_info: dict, referred_employer_number: int, referral_code: str) -> dict:
    """
    STEP 4: Create referral mapping between referring and referred employers
    
    Args:
        referring_employer_info: Information about the referring employer
        referred_employer_number: The employer number being referred
        referral_code: The referral code
        
    Returns:
        Dictionary with referral mapping creation result
    """
    db = next(get_db())
    try:
        # Get referred employer
        referred_employer = db.query(models.Employer).filter(
            models.Employer.employerNumber == referred_employer_number
        ).first()
        
        if not referred_employer:
            return {
                "success": False,
                "message": "Referred employer not found. Please create employer record first."
            }
        
        # Check if referral relationship already exists
        existing_referral = db.query(models.EmployerReferralMapping).filter(
            models.EmployerReferralMapping.employerReferring == referring_employer_info["id"],
            models.EmployerReferralMapping.employerReferred == referred_employer.id
        ).first()
        
        if existing_referral:
            return {
                "success": False,
                "message": "Referral relationship already exists between these employers."
            }
        
        # Create new referral mapping
        new_referral = models.EmployerReferralMapping(
            id=generate_unique_id(length=16),
            employerReferring=referring_employer_info["id"],
            employerReferred=referred_employer.id,
            referralCode=referral_code.strip(),
            referralStatus="ACTIVE",
            dateReferredOn=current_date(),
            cashbackAmount=150,  # Fixed cashback amount
            cashbackStatus="PENDING"
        )
        
        db.add(new_referral)
        
        # Update referring employer's referral count
        referring_employer = db.query(models.Employer).filter(
            models.Employer.id == referring_employer_info["id"]
        ).first()
        
        if referring_employer:
            referring_employer.numberofReferral += 1
        
        db.commit()
        db.refresh(new_referral)
        
        return {
            "success": True,
            "message": f"Referral mapping created successfully. Employer {referring_employer_info['employer_number']} referred employer {referred_employer_number}.",
            "referral_mapping_id": new_referral.id,
            "referring_employer_number": referring_employer_info["employer_number"],
            "referred_employer_number": referred_employer_number
        }
        
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"Error creating referral mapping: {str(e)}"
        }
    finally:
        db.close()


def create_beneficiary_for_referring_employer(referring_employer_info: dict) -> dict:
    """
    STEP 5: Create beneficiary record for the referring employer for future cashback
    
    Args:
        referring_employer_info: Information about the referring employer
        
    Returns:
        Dictionary with beneficiary creation result
    """
    try:
        from .referral_system import ReferralSystemManager
        
        referral_manager = ReferralSystemManager()
        
        # Create beneficiary using referral system manager
        beneficiary_result = referral_manager.create_cashfree_beneficiary(
            referring_employer_info["employer_number"],
            {
                "upi_id": referring_employer_info.get("upi_id"),
                "account_number": referring_employer_info.get("account_number"),
                "ifsc": referring_employer_info.get("ifsc")
            }
        )
        
        return {
            "success": beneficiary_result["status"] == "success",
            "message": f"Beneficiary creation: {beneficiary_result['message']}",
            "beneficiary_result": beneficiary_result
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error creating beneficiary: {str(e)}"
        }


def process_referral_code(employer_number: int, referral_code: str) -> dict:
    """
    MAIN FUNCTION: Complete referral processing workflow
    Orchestrates all the step-by-step functions above
    
    Args:
        employer_number: The employer's phone number who is using the referral code
        referral_code: The referral code provided by the employer
        
    Returns:
        Dictionary with complete processing result
    """
    try:
        print(f"Starting referral processing for employer {employer_number} with code {referral_code}")
        
        # STEP 1: Validate referral code
        validation_result = validate_referral_code(referral_code)
        if not validation_result["valid"]:
            return {
                "success": False,
                "message": validation_result["message"],
                "can_continue": validation_result["can_continue"],
                "step_failed": "validation"
            }
        
        referring_employer_info = validation_result["referring_employer"]
        print(f"Step 1 Complete: Referral code validated for employer {referring_employer_info['employer_number']}")
        
        # STEP 2: Check first payment status
        payment_status = check_employer_first_payment_status(employer_number)
        if payment_status["status"] == "already_paid":
            return {
                "success": False,
                "message": payment_status["message"],
                "can_continue": payment_status["can_continue"],
                "already_onboarded": True,
                "step_failed": "payment_check"
            }
        
        print(f"Step 2 Complete: Payment status checked - {payment_status['status']}")
        
        # NOTE: Step 3 (Employer record creation/update) removed - will be handled after payment confirmation via webhook
        
        # STEP 3: Create referral mapping
        mapping_result = create_referral_mapping(
            referring_employer_info, 
            employer_number, 
            referral_code
        )
        if not mapping_result["success"]:
            return {
                "success": False,
                "message": mapping_result["message"],
                "can_continue": True,
                "step_failed": "referral_mapping"
            }
        
        print(f"Step 3 Complete: Referral mapping created - {mapping_result['referral_mapping_id']}")
        
        # STEP 4: Create beneficiary for referring employer
        beneficiary_result = create_beneficiary_for_referring_employer(referring_employer_info)
        print(f"Step 4 Complete: Beneficiary creation - {beneficiary_result['message']}")
        
        # Return success with all details
        return {
            "success": True,
            "message": f"Referral processed successfully! You will receive cashback once this employer makes their first payment.",
            "can_continue": True,
            "referring_employer_number": referring_employer_info["employer_number"],
            "referred_employer_number": employer_number,
            "referral_mapping_id": mapping_result["referral_mapping_id"],
            "beneficiary_status": beneficiary_result["success"],
            "steps_completed": ["validation", "payment_check", "referral_mapping", "beneficiary_creation"]
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error in referral processing workflow: {str(e)}",
            "can_continue": True,
            "step_failed": "workflow_error"
        }


get_worker_details_tool = StructuredTool.from_function(
    func=get_worker_details,
    name="get_worker_details",
    description="Fetches worker details by worker number."
)

worker_onboarding_tool = StructuredTool.from_function(
    func=onboard_worker_employer,
    name="onboard_worker_with_employer",
    description="Onboards a worker under an existing employer by collecting bank/UPI, PAN, and salary info.",
    args_schema=WorkerEmployerInput
)

transcribe_audio_tool = StructuredTool.from_function(
    func=transcribe_audio,
    name="transcribe_audio_using_mediaID",
    description="Transcribes audio and returns the text."
)


send_audio_tool = StructuredTool.from_function(
    func=send_audio,
    name="send_audio_using_employerNumber",
    description="Sends the audio to the employer using the employer number."
)

get_worker_by_name_and_employer_tool = StructuredTool.from_function(
    func=get_worker_by_name_and_employer,
    name="get_worker_by_name_and_employer",
    description="Find worker details by name and employer number from worker_employer table."
)

process_referral_code_tool = StructuredTool.from_function(
    func=process_referral_code,
    name="process_referral_code",
    description="Process referral code when employer onboards worker. Validates referral code and updates referral mapping."
)

# Import referral system functions
from .referral_system import ReferralSystemManager, execute_referral_workflow

def get_referral_stats_tool_func(employer_number: int) -> dict:
    """
    Get referral statistics for an employer
    """
    db = next(get_db())
    try:
        referral_manager = ReferralSystemManager()
        result = referral_manager.get_referral_stats(employer_number, db)
        return result
    except Exception as e:
        return {"status": "error", "message": f"Error getting referral stats: {str(e)}"}
    finally:
        db.close()

def check_employer_payment_status(employer_number: int) -> dict:
    """
    Check if employer has made first payment
    """
    db = next(get_db())
    try:
        referral_manager = ReferralSystemManager()
        result = referral_manager.check_first_payment_status(employer_number, db)
        return result
    except Exception as e:
        return {"status": "error", "message": f"Error checking payment status: {str(e)}"}
    finally:
        db.close()


get_referral_stats_tool = StructuredTool.from_function(
    func=get_referral_stats_tool_func,
    name="get_referral_stats",
    description="Get referral statistics for an employer including total referrals, cashback earned, etc."
)

check_payment_status_tool = StructuredTool.from_function(
    func=check_employer_payment_status,
    name="check_payment_status",
    description="Check if employer has made their first payment to determine referral code eligibility."
)

# ============================================================================
# STRUCTURED TOOL FUNCTIONS FOR ONBOARDING AGENT
# Individual tools for each step of referral processing
# ============================================================================

validate_referral_code_tool = StructuredTool.from_function(
    func=validate_referral_code,
    name="validate_referral_code",
    description="Step 1: Validate referral code format and check if referring employer exists."
)

def generate_referral_code_func(employer_number: int) -> dict:
    """
    Generate a unique referral code for an employer
    
    Args:
        employer_number: The employer number to generate a referral code for
        
    Returns:
        Dictionary with generated referral code and status
    """
    db = next(get_db())
    try:
        from .referral_system import ReferralSystemManager
        referral_manager = ReferralSystemManager()
        referral_code = referral_manager.generate_referral_code(employer_number)
        
        return {
            "status": "success",
            "referral_code": referral_code,
            "employer_number": employer_number,
            "message": f"Successfully generated referral code {referral_code} for employer {employer_number}"
        }
    except Exception as e:
        return {"status": "error", "message": f"Error generating referral code: {str(e)}"}
    finally:
        db.close()

generate_referral_code_tool = StructuredTool.from_function(
    func=generate_referral_code_func,
    name="generate_referral_code",
    description="Generate a unique referral code for an employer that they can share with others."
)

check_employer_first_payment_status_tool = StructuredTool.from_function(
    func=check_employer_first_payment_status,
    name="check_employer_first_payment_status",
    description="Step 2: Check if current employer has already made their first payment."
)

# Note: create_or_update_employer_record_tool removed as it will be handled after payment confirmation via webhook

create_referral_mapping_tool = StructuredTool.from_function(
    func=create_referral_mapping,
    name="create_referral_mapping",
    description="Step 4: Create referral mapping between referring and referred employers."
)

create_beneficiary_for_referring_employer_tool = StructuredTool.from_function(
    func=create_beneficiary_for_referring_employer,
    name="create_beneficiary_for_referring_employer",
    description="Step 5: Create beneficiary record for the referring employer for future cashback."
)

def transfer_cashback_payment(beneficiary_id: str, amount: int, transfer_mode: str = "upi") -> dict:
    """
    Transfer cashback payment to a beneficiary using Cashfree payout API
    
    Args:
        beneficiary_id: The ID of the beneficiary to transfer to
        amount: The amount to transfer
        transfer_mode: Payment mode (default: upi)
        
    Returns:
        Dictionary with transfer result
    """
    try:
        from .referral_system import ReferralSystemManager
        referral_manager = ReferralSystemManager()
        
        result = referral_manager.transfer_cashback_amount(
            beneficiary_id=beneficiary_id,
            amount=amount,
            transfer_mode=transfer_mode
        )
        
        return result
    except Exception as e:
        return {"status": "error", "message": f"Error transferring payment: {str(e)}"}

transfer_cashback_payment_tool = StructuredTool.from_function(
    func=transfer_cashback_payment,
    name="transfer_cashback_payment",
    description="Transfer cashback payment to a beneficiary using Cashfree payout API."
)
