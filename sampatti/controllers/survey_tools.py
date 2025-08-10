# survey_tools.py
import uuid
import json
import re
import time
import os
import requests
import tempfile
import glob
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import create_engine, Column, String, ForeignKey, Integer, select, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, Field, root_validator
from langchain.tools import StructuredTool, Tool
import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from ..database import get_db_session, get_db
from .. import models
from .utility_functions import generate_unique_id, current_date, call_sarvam_api
from .whatsapp_message import send_message_user
from pathlib import Path
from sarvamai import SarvamAI
from dotenv import load_dotenv
from json import load
from pydub import AudioSegment
from pathlib import Path
from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("SARVAM_API_KEY")

# Database Models
Base = declarative_base()

class SurveyResponse(Base):
    __tablename__ = 'survey_responses'

    response_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    survey_id = Column(String, ForeignKey('SurveyDetails.id'), nullable=False)
    question_id = Column(String, ForeignKey('QuestionBank.id'), nullable=False)
    user_id = Column(String, index=True)
    user_name = Column(String)  # Name of the person whose survey is being collected
    worker_number = Column(String)  # This will store employer number
    response = Column(String)
    timestamp = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Question Bank
QUESTIONS = {
    "1": "Please provide your age?",
    "2": "What is your education?(No formal education, primary education, secondary education, higher secondary education, diploma, graduate, post graduate, other)",
    "3": "what is your monthly household income? (20000/5000/100000/52000 integer value)",
    "4": "Please record your occupation",
    "5": "Number of family members",
    "6": "Do you have a bank account? (Yes/No)",
    "7": "If Yes, which bank? (State Bank of India, Union Bank of India, Canara Bank, Other)",
    "8": "If No, why don't you have bank account? (Check all that apply) (Lack of documents, No bank nearby, Don't know how to open, Don't need one, Other (specify))",
    "9": "What services do you use at the bank? (Deposits, Withdrawals, Money transfers, Loan payments, Other)",
    "10": "Do you have an ATM card? (Yes/No)",
    "11": "If Yes, how often do you use it? (Several times a week, Weekly, Monthly, Rarely, Never)",
    "12": "Do you use any digital payment methods? (UPI, Mobile banking, Internet banking, None)",
    "13": "If you use digital payments, what do you use them for? (Utility bills, Shopping, Money transfers, Other)",
    "14": "What challenges do you face with digital payments? (Lack of smartphone, Poor internet connectivity, Fear of fraud, Difficulty understanding technology, Other)",
    "15": "Have you ever taken a loan? (Yes/No)",
    "16": "If Yes, from where? (Bank, Microfinance Institution, Self-Help Group, Money lender, Family/Friends, Other)",
    "17": "Purpose of loan(s): (Business, Education, Medical expenses, Housing, Personal needs, Other)",
    "18": "Have you ever been rejected for a loan? (Yes/No)",
    "19": "If Yes, why? (Check all that apply) (Low income, No collateral, Poor credit history, Lack of documents, Other)",
    "20": "Record any information on interest and terms of repayment",
    "21": "Do you save money? (Yes/No)",
    "22": "If Yes, how do you save? (Bank account, Cash at home, Chit funds, Self-Help Groups, Other)",
    "23": "How much can you typically save per month? (Less than ₹500, ₹500 - ₹1,000, ₹1,000 - ₹2,000, More than ₹2,000)",
    "24": "What do you save for? (Emergencies, Children's education, Business, Marriage/festivals, Old age, Other)",
    "25": "Do you have any insurance? (Yes/No)",
    "26": "If Yes, what type? (LIC, Ayushman Bharat, Private Insurance, Other)",
    "27": "If No, why don't you have insurance? (Too expensive, Don't understand insurance, Don't think it's necessary, Never approached by anyone, Other)",
    "28": "Please share any other challenges or suggestions regarding financial services"
}

# Pydantic models for tool inputs
class CreateUserInput(BaseModel):
    user_name: str = Field(description="Name of the person whose survey is being collected")

class AddSurveyResponseInput(BaseModel):
    user_id: str = Field(description="User ID generated from user name")
    user_name: str = Field(description="Name of the person whose survey is being collected")
    employer_number: str = Field(description="Employer number who is collecting the survey")
    question_id: str = Field(description="Question ID from the question bank")
    response: str = Field(description="User's response to the question")

class BatchSurveyResponseInput(BaseModel):
    user_id: str = Field(description="User ID generated from user name")
    user_name: str = Field(description="Name of the person whose survey is being collected")
    employer_number: str = Field(description="Employer number who is collecting the survey")
    responses: Dict[str, str] = Field(description="Dictionary of question_id: response pairs")

class GetUserResponsesInput(BaseModel):
    user_name: str = Field(description="Name of the user to fetch survey responses")

class UpdateSurveyResponseInput(BaseModel):
    user_id: str = Field(description="User ID")
    employer_number: str = Field(description="Employer number updating the response")
    question_id: str = Field(description="Question ID to update")
    new_response: str = Field(description="New response value")

class CheckUserExistsInput(BaseModel):
    user_name: str = Field(description="Name of the user to check")

# Survey Database Functions
def normalize_name(name: str) -> str:
    """Normalize name for consistent user ID generation"""
    return re.sub(r'\s+', ' ', name.strip().lower())

def generate_user_id_from_name(user_name: str) -> str:
    """Generate a consistent user ID from user name"""
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', normalize_name(user_name))
    name_hash = str(hash(user_name))[-4:]
    return f"user_{clean_name}_{name_hash}"

def create_user_id(user_name: str) -> dict:
    """
    Create a user ID from the user name.
    This doesn't create a database entry, just generates the ID.
    """
    try:
        user_id = generate_user_id_from_name(user_name)
        return {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "message": f"User ID generated: {user_id}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error generating user ID: {str(e)}"
        }

def check_user_exists(user_name: str) -> dict:
    """
    Check if a user has filled surveys before.
    Returns user details and survey statistics.
    """
    db = next(get_db())
    try:
        user_id = generate_user_id_from_name(user_name)
        
        # Query survey responses for this user
        responses = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.user_id == user_id,
            models.SurveyResponse.survey_id == "1"
        ).all()
        
        if responses:
            # Get unique questions answered
            answered_questions = set()
            employers_involved = set()
            latest_timestamp = None
            
            for resp in responses:
                answered_questions.add(resp.question_id)
                if resp.worker_number:  # worker_number stores employer_number
                    employers_involved.add(resp.worker_number)
                if not latest_timestamp or resp.timestamp > latest_timestamp:
                    latest_timestamp = resp.timestamp
            
            return {
                "exists": True,
                "user_id": user_id,
                "user_name": user_name,
                "total_responses": len(responses),
                "questions_answered": len(answered_questions),
                "questions_list": list(answered_questions),
                "collected_by_employers": list(employers_involved),
                "last_updated": latest_timestamp,
                "message": f"User '{user_name}' found with {len(answered_questions)} questions answered"
            }
        else:
            return {
                "exists": False,
                "user_id": user_id,
                "user_name": user_name,
                "message": f"User '{user_name}' not found. This is a new survey respondent."
            }
    except Exception as e:
        return {
            "exists": False,
            "error": str(e),
            "message": f"Error checking user: {str(e)}"
        }
    finally:
        db.close()

def add_single_survey_response(
    user_id: str,
    user_name: str,
    employer_number: str,
    question_id: str,
    response: str
) -> dict:
    """
    Add or update a single survey response in the database.
    """
    db = next(get_db())
    try:
        # Check if response already exists
        existing = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.survey_id == "1",
            models.SurveyResponse.user_id == user_id,
            models.SurveyResponse.question_id == question_id
        ).first()
        
        if existing:
            # Update existing response
            existing.response = response
            existing.worker_number = employer_number
            existing.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()
            
            return {
                "success": True,
                "action": "updated",
                "response_id": existing.response_id,
                "message": f"Updated response for question {question_id}"
            }
        else:
            # Create new response
            new_response = models.SurveyResponse(
                response_id=generate_unique_id(length=16),
                survey_id="1",  # Fixed survey ID
                question_id=question_id,
                user_id=user_id,
                user_name=user_name,
                worker_number=employer_number,  # Store employer number here
                response=response,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.add(new_response)
            db.commit()
            
            return {
                "success": True,
                "action": "created",
                "response_id": new_response.response_id,
                "message": f"Added response for question {question_id}"
            }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
            "message": f"Error adding response: {str(e)}"
        }
    finally:
        db.close()

def batch_add_survey_responses(
    user_id: str,
    user_name: str,
    employer_number: str,
    responses: Dict[str, str]
) -> dict:
    """
    Add multiple survey responses at once.
    More efficient for bulk operations.
    """
    db = next(get_db())
    success_count = 0
    update_count = 0
    errors = []
    response_ids = []
    
    try:
        for question_id, response in responses.items():
            try:
                # Check if response exists
                existing = db.query(models.SurveyResponse).filter(
                    models.SurveyResponse.survey_id == "1",
                    models.SurveyResponse.user_id == user_id,
                    models.SurveyResponse.question_id == question_id
                ).first()
                
                if existing:
                    # Update existing
                    existing.response = response
                    existing.worker_number = employer_number
                    existing.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    update_count += 1
                    response_ids.append(existing.response_id)
                else:
                    # Create new
                    new_response = models.SurveyResponse(
                        response_id=generate_unique_id(length=16),
                        survey_id="1",
                        question_id=question_id,
                        user_id=user_id,
                        user_name=user_name,
                        worker_number=employer_number,
                        response=response,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    db.add(new_response)
                    success_count += 1
                    response_ids.append(new_response.response_id)
                    
            except Exception as e:
                errors.append(f"Q{question_id}: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "created": success_count,
            "updated": update_count,
            "total_processed": success_count + update_count,
            "errors": errors,
            "response_ids": response_ids,
            "message": f"Successfully processed {success_count + update_count} responses ({success_count} new, {update_count} updated)"
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
            "message": f"Batch processing error: {str(e)}"
        }
    finally:
        db.close()

def get_user_survey_responses(user_name: str) -> dict:
    """
    Get all survey responses for a user by their name.
    """
    db = next(get_db())
    try:
        user_id = generate_user_id_from_name(user_name)
        
        # Get all responses for this user
        responses = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.user_id == user_id,
            models.SurveyResponse.survey_id == "1"
        ).order_by(models.SurveyResponse.question_id).all()
        
        if responses:
            response_data = []
            employers_involved = set()
            
            for resp in responses:
                response_data.append({
                    "question_id": resp.question_id,
                    "question": QUESTIONS.get(resp.question_id, "Unknown question"),
                    "response": resp.response,
                    "collected_by": resp.worker_number,  # Employer number
                    "timestamp": resp.timestamp,
                    "response_id": resp.response_id
                })
                if resp.worker_number:
                    employers_involved.add(resp.worker_number)
            
            # Group responses by employer
            responses_by_employer = {}
            for resp in response_data:
                employer = resp["collected_by"] or "Unknown"
                if employer not in responses_by_employer:
                    responses_by_employer[employer] = []
                responses_by_employer[employer].append(resp)
            
            return {
                "success": True,
                "user_id": user_id,
                "user_name": user_name,
                "total_responses": len(response_data),
                "responses": response_data,
                "responses_by_employer": responses_by_employer,
                "employers_involved": list(employers_involved),
                "message": f"Found {len(response_data)} responses for {user_name}"
            }
        else:
            return {
                "success": False,
                "user_id": user_id,
                "user_name": user_name,
                "message": f"No survey responses found for {user_name}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error retrieving responses: {str(e)}"
        }
    finally:
        db.close()

def update_survey_response(
    user_id: str,
    employer_number: str,
    question_id: str,
    new_response: str
) -> dict:
    """
    Update a specific survey response.
    """
    db = next(get_db())
    try:
        # Find the response
        existing = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.survey_id == "1",
            models.SurveyResponse.user_id == user_id,
            models.SurveyResponse.question_id == question_id
        ).first()
        
        if existing:
            old_response = existing.response
            existing.response = new_response
            existing.worker_number = employer_number  # Update who made the change
            existing.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()
            
            return {
                "success": True,
                "response_id": existing.response_id,
                "old_response": old_response,
                "new_response": new_response,
                "updated_by": employer_number,
                "message": f"Successfully updated response for question {question_id}"
            }
        else:
            return {
                "success": False,
                "message": f"No response found for question {question_id} for this user"
            }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
            "message": f"Error updating response: {str(e)}"
        }
    finally:
        db.close()

def get_audio_duration(file_path):
    """Get audio duration in seconds"""
    audio = AudioSegment.from_file(file_path)
    return len(audio) / 1000.0

def run_sttt_sync(audio_files, output_dir):
    client = SarvamAI(api_subscription_key=API_KEY)

    job = client.speech_to_text_translate_job.create_job(
        model="saaras:v2.5",
        with_diarization=True,
        num_speakers=2,
        prompt="Official meeting"
    )

    print(f"Job created: {job._job_id}")
    job.upload_files(file_paths=audio_files, timeout=600)
    job.start()
    print("Translation started...")
    job.wait_until_complete(poll_interval=5, timeout=600)

    if job.is_failed():
        raise RuntimeError("Translation failed")

    job.download_outputs(output_dir=str(output_dir))
    print(f"Translation completed. Output saved to: {output_dir}")



def translate_audio(mediaId: str):
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

    duration = get_audio_duration(wav_path)
    print(f"Audio duration: {duration:.2f} seconds")

    if duration < 28:
        result = call_sarvam_api(wav_path)
        transcript = result["transcript"]
        user_language = result["language_code"]
        print("Transcript: ",transcript)
        print("User Language: ",user_language)
        return transcript, user_language
    else:
        sttt_output_dir = Path("STT_Results")
    
        try:
            # Run STTT sync with the audio file
            audio_files = [wav_path]
            run_sttt_sync(audio_files, sttt_output_dir)

            print("STTT Sync completed. Output saved to: ", sttt_output_dir)
            
            from json import load
            with open(sttt_output_dir / f"{mediaId}_audio.wav.json", "r") as f:
                data = load(f)
                transcript = data["transcript"]
                user_language = data["language_code"]

            
            print(f"Extracted transcript: {transcript}")
            print(f"Extracted user_language: {user_language}")
            
            # Clean up temporary file
            os.unlink(temp_path)
            
            return transcript, user_language
            
        except Exception as e:
            print(f"Error in STTT sync processing: {str(e)}")
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            return f"Error processing long audio: {str(e)}", None

def get_survey_statistics(user_name: str) -> dict:
    """
    Get detailed statistics about a user's survey responses.
    """
    db = next(get_db())
    try:
        user_id = generate_user_id_from_name(user_name)
        
        # Get all responses
        responses = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.user_id == user_id,
            models.SurveyResponse.survey_id == "1"
        ).all()
        
        if not responses:
            return {
                "success": False,
                "message": f"No survey data found for {user_name}"
            }
        
        # Calculate statistics
        total_questions = len(QUESTIONS)
        answered_questions = set()
        unanswered_questions = []
        responses_by_date = {}
        
        for resp in responses:
            answered_questions.add(resp.question_id)
            date = resp.timestamp.split()[0] if resp.timestamp else "Unknown"
            if date not in responses_by_date:
                responses_by_date[date] = 0
            responses_by_date[date] += 1
        
        # Find unanswered questions
        for q_id in QUESTIONS.keys():
            if q_id not in answered_questions:
                unanswered_questions.append({
                    "question_id": q_id,
                    "question": QUESTIONS[q_id]
                })
        
        completion_percentage = (len(answered_questions) / total_questions) * 100
        
        return {
            "success": True,
            "user_name": user_name,
            "user_id": user_id,
            "total_questions": total_questions,
            "answered_questions": len(answered_questions),
            "unanswered_questions": len(unanswered_questions),
            "completion_percentage": round(completion_percentage, 2),
            "unanswered_details": unanswered_questions,
            "responses_by_date": responses_by_date,
            "message": f"Survey {round(completion_percentage, 2)}% complete"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error calculating statistics: {str(e)}"
        }
    finally:
        db.close()

# Pydantic model for systematic survey message
class SystematicSurveyMessageInput(BaseModel):
    worker_number: str = Field(description="Worker number (employer number) who collected the survey")
    user_name: str = Field(description="Name of the person whose survey was collected")
    survey_id: str = Field(description="Survey ID (default is '1')")

def systemattic_survey_message(worker_number: str, user_name: str, survey_id: str = "1") -> dict:
    """
    Generate a systematic survey message showing all responses for a user.
    This function formats the survey responses in a clear, numbered format.
    """
    db = next(get_db())
    try:
        total_survey_messages = db.query(models.SurveyResponse).filter(
            models.SurveyResponse.worker_number == worker_number,
            models.SurveyResponse.user_name == user_name,
            models.SurveyResponse.survey_id == survey_id
        ).all()

        if not total_survey_messages:
            return {
                "success": False,
                "confirmation_message": f"No survey responses found for {user_name}"
            }

        message = "Here are the answers you provided:\n\n"

        for i, response in enumerate(total_survey_messages, start=1):
            question = db.query(models.QuestionBank).filter(
                models.QuestionBank.id == response.question_id
            ).first()
            
            if question:
                message += f"{i}. {question.questionText}\n   Answer {i}: {response.response}\n\n"

        send_message_user(user_name, message.strip())
        
        return {
            "success": True,
            "confirmation_message": message.strip()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "confirmation_message": f"Error generating survey message: {str(e)}"
        }
    finally:
        db.close()

# Create LangChain tools
create_user_id_tool = StructuredTool.from_function(
    func=create_user_id,
    name="create_user_id",
    description="Generate a user ID from the user's name",
    args_schema=CreateUserInput
)

check_user_exists_tool = StructuredTool.from_function(
    func=check_user_exists,
    name="check_user_exists",
    description="Check if a user has previously filled surveys and get their statistics",
    args_schema=CheckUserExistsInput
)

add_single_response_tool = StructuredTool.from_function(
    func=add_single_survey_response,
    name="add_single_survey_response",
    description="Add or update a single survey response",
    args_schema=AddSurveyResponseInput
)

batch_add_responses_tool = StructuredTool.from_function(
    func=batch_add_survey_responses,
    name="batch_add_survey_responses",
    description="Add or update multiple survey responses at once",
    args_schema=BatchSurveyResponseInput
)

get_user_responses_tool = StructuredTool.from_function(
    func=get_user_survey_responses,
    name="get_user_survey_responses",
    description="Get all survey responses for a user by their name",
    args_schema=GetUserResponsesInput
)

update_response_tool = StructuredTool.from_function(
    func=update_survey_response,
    name="update_survey_response",
    description="Update a specific survey response",
    args_schema=UpdateSurveyResponseInput
)

get_survey_statistics_tool = StructuredTool.from_function(
    func=get_survey_statistics,
    name="get_survey_statistics",
    description="Get detailed statistics about a user's survey completion"
)

systematic_survey_message_tool = StructuredTool.from_function(
    func=systemattic_survey_message,
    name="systematic_survey_message",
    description="Generate a systematic formatted message showing all survey responses for a user",
    args_schema=SystematicSurveyMessageInput
)

# Additional utility tool
get_question_bank_tool = Tool(
    name="get_question_bank",
    func=lambda _: json.dumps(QUESTIONS, indent=2),
    description="Get all survey questions with their IDs"
)