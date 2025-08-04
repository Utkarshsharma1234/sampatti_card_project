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



def process_referral_code(employer_number: int, referral_code: str) -> dict:
    try:
        print(f"Starting referral processing for employer {employer_number} with code {referral_code}")
        
        # STEP 1: Validate referral code
        db = next(get_db())

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
        
        referral_mapping = db.query(models.EmployerReferralMapping).where(
            models.EmployerReferralMapping.referralCode == referral_code, models.EmployerReferralMapping.employerReferring == referring_employer.id, models.EmployerReferralMapping.employerReferred == referred_employer.id
        ).first()

        if referral_mapping:
            return {
                "success": False,
                "message": "You have already used this referral code",
                "can_continue": False,
                "step_failed": "validation"
            }

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

        return {
            "success": True,
            "message": "Referral has been Verified",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error processing referral code: {str(e)}"
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
