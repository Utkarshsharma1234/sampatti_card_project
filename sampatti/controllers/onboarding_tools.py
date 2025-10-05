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
from . import userControllers
from ..controllers import onboarding_tasks, talk_to_agent_excel_file


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


class ConfirmWorkerInput(BaseModel):
    worker_number: int
    employer_number: int
    salary: int
    referral_code: Optional[str] = None



def onboard_worker_employer( worker_number: int, employer_number: int, pan_number: str, salary : int, UPI: Optional[str] = "", bank_account_number: Optional[str]= "", ifsc_code: Optional[str] = "", referral_code: Optional[str] = "") -> str:

    bank_passbook_image = "NA"
    pan_card_image = "NA"

    worker_number = int(worker_number)
    employer_number = int(employer_number)
    
    # Validation: Prevent employer from onboarding themselves as worker
    # Remove +91 prefix from employer_number for comparison
    employer_without_prefix = str(employer_number)
    if employer_without_prefix.startswith('91'):
        employer_without_prefix = employer_without_prefix[2:]
    
    if str(worker_number) == employer_without_prefix:
        return "Error: You cannot onboard yourself as a worker. Please provide a different worker number."

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
    
    if response.status_code == 200:
        onboarding_tasks.run_tasks_till_add_vendor()
        print("Onboarding task intialized!!!")

    return f"Onboarding for worker has been initiated and we will get back to you when the process is complete. Status: {response.status_code}, Response: {response.text}"


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


def get_worker_details(workerNumber : int, employer_number: int):
    """
    Fetches worker details from the database using the worker number.
    Returns a dictionary with worker details or an error message.
    """    
    # Validation: Prevent employer from onboarding themselves as worker
    # Remove +91 prefix from employer_number for comparison
    employer_without_prefix = str(employer_number)
    if employer_without_prefix.startswith('91'):
        employer_without_prefix = employer_without_prefix[2:]
    
    if str(workerNumber) == employer_without_prefix:
        return "Error: You cannot onboard yourself as a worker. Please provide a different worker number."
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

# Updated Pydantic model for the tool
class ProcessReferralCodeInput(BaseModel):
    employer_number: int
    referral_code: str
    worker_number: Optional[int] = None
    salary: Optional[int] = None

def process_referral_code(employer_number: int, referral_code: Optional[str] = None, worker_number: Optional[int] = None, salary: Optional[int] = None) -> dict:
    """
    Process referral code and optionally add worker to employer if worker already exists.
    
    Args:
        employer_number: Employer's phone number
        referral_code: Referral code to validate
        worker_number: Optional - Worker's phone number (if worker exists in DB)
        salary: Optional - Worker's salary (if worker exists in DB)
    """
    try:
        print(f"Starting referral processing for employer {employer_number} with code {referral_code}")
        
        db = next(get_db())

        # STEP 1: Validate referral code
        referring_employer = db.query(models.Employer).where(
            models.Employer.referralCode == referral_code
        ).first()

        referred_employer = db.query(models.Employer).where(
            models.Employer.employerNumber == employer_number
        ).first()

        if not referring_employer:
            return {
                "success": False,
                "message": "Invalid referral code",
                "can_continue": False,
                "step_failed": "validation"
            }
        
        # Check if referral code already used
        referral_mapping = db.query(models.EmployerReferralMapping).where(
            models.EmployerReferralMapping.referralCode == referral_code, 
            models.EmployerReferralMapping.employerReferring == referring_employer.id, 
            models.EmployerReferralMapping.employerReferred == referred_employer.id
        ).first()

        if referral_mapping:
            return {
                "success": False,
                "message": "You have already used this referral code",
                "can_continue": False,
                "step_failed": "validation"
            }

        # Create referral mapping
        new_referral = models.EmployerReferralMapping(
            id=generate_unique_id(length=16),
            employerReferring=referring_employer.id,
            employerReferred=referred_employer.id,
            referralCode=referral_code.strip(),
            referralStatus="ACTIVE",
            dateReferredOn=current_date(),
            cashbackAmount=150,  # Fixed cashback amount
            cashbackStatus="PENDING"
        )
        
        db.add(new_referral)
        db.commit()
        db.refresh(new_referral)

        # STEP 2: If worker details provided, add worker to employer
        if worker_number and salary:
            # Validation: Prevent employer from onboarding themselves
            employer_number_str = str(employer_number)
            worker_number_str = str(worker_number)
            
            if employer_number_str.startswith('91') and len(employer_number_str) > 10:
                employer_number_cleaned = employer_number_str[2:]
            else:
                employer_number_cleaned = employer_number_str
                
            if employer_number_cleaned == worker_number_str:
                return {
                    "success": True,
                    "referral_verified": True,
                    "worker_added": False,
                    "message": "Referral Code has been Verified. However, you cannot onboard yourself as a worker."
                }
            
            # Get worker details
            worker = db.query(models.Domestic_Worker).filter(
                models.Domestic_Worker.workerNumber == worker_number
            ).first()
            
            if not worker:
                return {
                    "success": True,
                    "referral_verified": True,
                    "worker_added": False,
                    "message": "Referral Code has been Verified. Worker not found in database."
                }
            
            # Check if worker-employer relationship already exists
            existing_relation = db.query(models.worker_employer).filter(
                models.worker_employer.c.worker_number == worker_number,
                models.worker_employer.c.employer_number == employer_number
            ).first()
            
            if existing_relation:
                return {
                    "success": True,
                    "referral_verified": True,
                    "worker_added": False,
                    "message": "Referral Code has been Verified. Worker is already associated with this employer."
                }
            
            # Create worker-employer relationship
            relation_id = generate_unique_id(length=8)
            
            insert_stmt = models.worker_employer.insert().values(
                id=relation_id,
                worker_number=worker_number,
                employer_number=employer_number,
                salary_amount=salary,
                vendor_id=worker.vendorId,
                worker_name=worker.name,
                employer_id=referred_employer.id,
                worker_id=worker.id,
                date_of_onboarding=current_date(),
                referralCode=referral_code
            )
            
            db.execute(insert_stmt)
            db.commit()
            
            # Generate employment contract
            try:
                userControllers.generate_employment_contract(
                    employerNumber=employer_number,
                    workerNumber=worker_number,
                    upi=worker.upi_id or "",
                    accountNumber=worker.accountNumber or "",
                    ifsc=worker.ifsc or "",
                    panNumber=worker.panNumber,
                    name=worker.name,
                    salary=salary,
                    db=db
                )
                
                return {
                    "success": True,
                    "referral_verified": True,
                    "worker_added": True,
                    "message": f"✅ Great News! Your Worker Referral Code is Verified!\n🎊 Worker {worker.name} has been successfully onboarded.\n\nWhat happens next:\nStep 1: Make your first payment\nStep 2: Receive YOUR referral code\nStep 3: Start earning ₹150 for every friend you refer!"
                }
                
            except Exception as contract_error:
                return {
                    "success": True,
                    "referral_verified": True,
                    "worker_added": True,
                    "message": f"✅ Referral Code Verified and Worker {worker.name} added successfully. However, there was an issue generating the contract: {str(contract_error)}"
                }
        
        # If only referral code provided (no worker details)
        return {
            "success": True,
            "referral_verified": True,
            "worker_added": False,
            "message": "✅ Great News! Your Worker Referral Code is Verified!\n🎊 What happens next:\nStep 1: Make your first payment\nStep 2: Receive YOUR referral code\nStep 3: Start earning ₹150 for every friend you refer!"
        }
        
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"Error processing referral code: {str(e)}"
        }
    finally:
        db.close()


def confirm_worker_and_add_to_employer(worker_number: int, employer_number: int, salary: int, referral_code: Optional[str]) -> dict:
    """
    Immediately adds worker to employer in worker_employer table and generates employment contract
    when employer confirms the worker details.
    """
    # Validation: Prevent employer from onboarding themselves as worker
    # Remove +91 prefix from employer_number for comparison
    
    try:
        db = next(get_db())
        
        employer_number_str = str(employer_number)
        worker_number_str = str(worker_number)
        
        # Remove 91 prefix if present
        if employer_number_str.startswith('91') and len(employer_number_str) > 10:
            employer_number_cleaned = employer_number_str[2:]
        else:
            employer_number_cleaned = employer_number_str
            
        # Check if employer is trying to onboard themselves
        if employer_number_cleaned == worker_number_str:
            return {
                "success": False,
                "message": "You cannot onboard yourself as a worker"
            }
        
        # Get worker details from database
        worker = db.query(models.Domestic_Worker).filter(
            models.Domestic_Worker.workerNumber == worker_number
        ).first()
        
        if not worker:
            return {
                "success": False,
                "message": "Worker not found in database"
            }
        
        # Get employer details
        employer = db.query(models.Employer).filter(
            models.Employer.employerNumber == employer_number
        ).first()
        
        if not employer:
            employer = models.Employer(
                id=generate_unique_id(length=8),
                employerNumber=employer_number,
            )
            db.add(employer)
            db.commit()
            db.refresh(employer)

            employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == employer_number
            ).first()

        
        # Check if worker-employer relationship already exists
        existing_relation = db.query(models.worker_employer).filter(
            models.worker_employer.c.worker_number == worker_number,
            models.worker_employer.c.employer_number == employer_number
        ).first()
        
        if existing_relation:
            return {
                "success": False,
                "message": "Worker is already associated with this employer"
            }
        
        # Create worker-employer relationship
        relation_id = generate_unique_id(length=8)
        
        # Insert into worker_employer table
        insert_stmt = models.worker_employer.insert().values(
            id=relation_id,
            worker_number=worker_number,
            employer_number=employer_number,
            salary_amount=salary,
            vendor_id=worker.vendorId,
            worker_name=worker.name,
            employer_id=employer.id,
            worker_id=worker.id,
            date_of_onboarding=current_date(),
            referralCode=referral_code or ""
        )
        
        db.execute(insert_stmt)
        db.commit()

        # talk_to_agent_excel_file.create_worker_details_onboarding(
        #     worker_number=worker_number,
        #     employer_number=employer_number,
        #     UPI=worker.upi_id or "",
        #     bank_account_number=worker.accountNumber or "",
        #     ifsc_code=worker.ifsc or "",
        #     pan_number=worker.panNumber,
        #     bank_passbook_image="NA",
        #     pan_card_image="NA",
        #     salary=salary,
        #     referral_code=referral_code or ""
        # )

        # Generate employment contract
        try:
            userControllers.generate_employment_contract(
                employerNumber=employer_number,
                workerNumber=worker_number,
                upi=worker.upi_id or "",
                accountNumber=worker.accountNumber or "",
                ifsc=worker.ifsc or "",
                panNumber=worker.panNumber,
                name=worker.name,
                salary=salary,
                db=db
            )
            
            return {
                "success": True,
                "message": f"Worker {worker.name} has been successfully added to your employment and the employment contract has been generated."
            }
            
        except Exception as contract_error:
            # If contract generation fails, still return success for worker addition
            return {
                "success": True,
                "message": f"Worker {worker.name} has been successfully added to your employment. However, there was an issue generating the contract: {str(contract_error)}"
            }
            
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"Error adding worker to employer: {str(e)}"
        }
    finally:
        db.close()

def employer_details(employer_number: int) -> dict:

    try:
        db = next(get_db())
        employer = db.query(models.Employer).filter(
            models.Employer.employerNumber == employer_number
        ).first()
        
        if not employer:
            return {
                "success": False,
                "error": f"No employer found with employer number: {employer_number}"
            }
        
        # Convert employer object to dictionary
        employer_data = {
            "success": True,
            "data": {
                "id": employer.id,
                "employerNumber": employer.employerNumber,
                "referralCode": employer.referralCode,
                "cashbackAmountCredited": employer.cashbackAmountCredited,
                "firstPaymentDone": employer.FirstPaymentDone,
                "accountNumber": employer.accountNumber,
                "ifsc": employer.ifsc,
                "upiId": employer.upiId,
                "numberOfReferral": employer.numberofReferral,
                "totalPaymentAmount": employer.totalPaymentAmount,
                "beneficiaryId": employer.beneficiaryId
            }
        }
        
        return employer_data
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }
    finally:
        db.close()

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
    description="Process referral code and optionally add worker to employer if worker already exists. Pass worker_number and salary only when confirming an existing worker.",
    args_schema=ProcessReferralCodeInput
)

confirm_worker_and_add_to_employer_tool = StructuredTool.from_function(
    func=confirm_worker_and_add_to_employer,
    name="confirm_worker_and_add_to_employer",
    description="Immediately adds confirmed worker to employer in worker_employer table and generates employment contract.",
    args_schema=ConfirmWorkerInput
)

employer_details_tool = StructuredTool.from_function(
    func=employer_details,
    name="employer_details",
    description="Get employer Deatils from employer Number",   
)
