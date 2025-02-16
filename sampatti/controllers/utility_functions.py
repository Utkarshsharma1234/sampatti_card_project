import shutil
import json, os, uuid, random, string,  difflib, re, requests, base64
from fastapi import File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi.responses import FileResponse, JSONResponse
from gtts import gTTS
from langchain_groq import ChatGroq
from langchain import LLMChain, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableSequence
from fastapi import BackgroundTasks
from ..controllers import whatsapp_message
from sqlalchemy.orm import Session
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain_community.chat_models import ChatOpenAI
from .. import models
from pydub import AudioSegment
import subprocess

load_dotenv()
groq_key= os.environ.get('GROQ_API_KEY')
sarvam_api_key = os.environ.get('SARVAM_API_KEY')
openai_api_key = os.environ.get('OPENAI_API_KEY')

def amount_to_words(amount: float) -> str:
    # Define word representations for numbers 0 to 19
    units = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", 
             "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", 
             "seventeen", "eighteen", "nineteen"]
    
    # Define word representations for tens
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    
    # Define word representations for powers of 10
    scales = ["", "thousand", "million", "billion", "trillion"]
    
    # Helper function to convert a three-digit number to words
    def three_digits_to_words(num):
        hundred = num // 100
        ten = (num % 100) // 10
        unit = num % 10
        
        words = ""
        
        if hundred:
            words += units[hundred] + " hundred "
            
        if ten > 1:
            words += tens[ten] + " "
            words += units[unit]
        elif ten == 1:
            words += units[10 * ten + unit]
        elif unit:
            words += units[unit]
            
        return words.strip()
    
    # Main function logic
    if amount == 0:
        return "zero"
    
    words = ""
    num_parts = []
    
    # Split the amount into groups of three digits
    while amount:
        num_parts.append(int(amount % 1000))
        amount //= 1000
    
    # Convert each group of three digits to words and concatenate them
    for i, num in enumerate(num_parts):
        if num:
            words = three_digits_to_words(num) + " " + scales[i] + " " + words
    
    return words.strip()


def generate_unique_id(length=8):

    unique_id = uuid.uuid4().hex
    letters_only = ''.join([char for char in unique_id if char.isalpha()])[:length]
    if len(letters_only) < length:
        letters_only += ''.join(random.choices(string.ascii_letters, k=length - len(letters_only)))
    return letters_only


def fuzzy_match_score(str1, str2):
    return difflib.SequenceMatcher(None, str1, str2).ratio()


def exact_match_case_insensitive(str1, str2):
    words1 = set(re.findall(r'\b\w+\b', str1.lower()))
    words2 = set(re.findall(r'\b\w+\b', str2.lower()))
    return not words1.isdisjoint(words2)

def extract_date(date_str : str):

    month, year = date_str.split('_')

    month = month.capitalize()

    year = int(year)

    return {
        "month" : month,
        "year" : year
    }

def previous_month():
    first_day_of_current_month = datetime.now().replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    ps_month = last_day_of_previous_month.strftime("%B")
    return ps_month

def current_month():
    return datetime.now().strftime("%B")

def current_year():

    year = datetime.now().year
    return year

def current_date():

    date = datetime.now().date()
    return date



def current_month_days():
    next_month = (datetime.now().replace(day=1) + timedelta(days=31)).replace(day=1)
    return (next_month - timedelta(days=1)).day

def previous_month_days():
    current_month_first = datetime.now().replace(day=1)
    last_day_of_previous_month = current_month_first - timedelta(days=1)
    return last_day_of_previous_month.day

def determine_attendance_period(current_day):
    """
    Determine whether to use previous month or current month's days for attendance
    """
    total_current_month_days = current_month_days()
    
    # If it's near the end of the month (last 3 days), use current month's days
    if current_day >= total_current_month_days - 2:
        return total_current_month_days
    # If it's at the beginning of the month (first 3 days), use previous month's days
    elif current_day <= 15:
        return previous_month_days()
    # Otherwise, default to current month's days
    else:
        return total_current_month_days


def llm_template():
    current_day = datetime.now().day
    attendance_period = determine_attendance_period(current_day)

    template = """You are an intelligent assistant helping to extract precise financial and attendance information for an employee cash advance record.

Input Text: {user_input}
employer_number: {employer_number}
existing record: {context} 

Instructions:
1. Carefully analyze the entire user input.
2. Extract all relevant financial and attendance details.
3. Always compare with the existing record and accordingly give the value.
4. currentCashAdvance is the cash advance we will make changes in this field according to the user wants.
5. If any information is missing, use existing record.
6. Be flexible in understanding variations of input.
7. Always include all fields in the result for all cases.
8. don't include current cash cash unless it is mentioned by the user.
9. Analyze the key word properly make changes according to the user wants if user wantes to changes the salary then make changes in the salary field according to the user wants.


Extraction and Update Rules:
- Focus on extracting or modifying specific fields mentioned in the input.
- Always analyze the entire input to ensure all relevant fields are considered.
- If there is not any mention of cash advance then make current cash advance it as 0.
- If your wants to change the salary then make changes in salary field according to the user wants.
- If only one field is discussed, keep other fields from existing record and give them updated information in final output.
- If input suggests adding/changing amount, then add or change according to the existing record field.
- If no specific amount given, use existing record's value.
- Validate and adjust values logically don't give random value.
- use existing record and update the existing record according to the user wants and only change the field which user wants rest keep as it existing record.

Specific Field Extraction:
- currentCashAdvance: 
  * Look for cash advance, advance, loan, or financial support amounts
  * Make change only if there is mention any cash advance, advance, loan, or financial support amounts.
  * don't take any unnecessary values into if unless cash advance or related term mentioned in the {user_input}
  * take the value for the currentCashAdvance from the existing record if no cash advance is mentioned in the {user_input}

- Monthly Repayment: Find planned monthly repayment amount
- Bonus: Identify any bonus or additional payment
  * Take the bonus amount from the existing record and then if the user asks to change the bonus amount then change it or if he wants to add more amount into bonus do the necessary steps from the {user_input}.

- Attendance: 
  * If attendance is mentioned in the {user_input} then return the value from the user input.
  * If nothing related to attendance is specified in the {user_input} take the Attendance value from the existing record.
  * If it is mentioned that the worker was on leave for let's say 7 days then take the attendance as {attendance_period} - 7.
  * If user says worker was present for full month or present for all days or was not on leave or attendance is 100 percent or anything similar to this statemet then make attendance as {attendance_period}.
  * it should not be 0 anytime.


- For Repayment_Start_Month:
  * If user mentions a specific month (e.g., "March", "June"):
    - Set the value of Repayment_Start_Month to the value which user mentions and then return in the response.
  * If user says next month then set the Repayment_Start_Month to the next month calculated from the {current_month}.
  * If user does not mention the month in the {user_input} then take the Repayment_Start_Month from the existing record and return.

- For Repayment_Start_Year:
  * If the user mentions a specific year like (2025, 2026, "january 2025", "march 2026"):
    - Set the value of Repayment_Start_Year to the value which the user mentions and then return in the response.
  * If user does not mentions anythiing related to the year then set the value of Repayment_Start_Year to 0. 
   
- For detailsFlag:
  * If the {user_input} is containing information which says mean that the details which are provided are correct then just make the detailsFlag to be 1 otherwise let it 0.
  * for e.g., If {user_input} says "yes" or it says "yes, correct details" or it says "all details are correct" or it says "yes, all the provided details are correct." or similar stuff then make the detailsFlag to be 1 otherwise let it be 0 only. 
  
- For nameOfWorker:
  * If user mentions a name then take it from the {user_input} but if not then take it from the existing record.
  * for e.g. If user says that, please pay a cash advance of 20000 with a monthly repayment of 5000 to utkarsh sharma then extract the nameOfWorker as "utkarsh sharma".
  * for e.g. If user says that, pay om a advance amount of 40000 to with a monthly repayment of 10000 then take nameOfWorker as "om".
  * for e.g. If user says that, i want to give vrashali a bonus of 70000 and attendance of 25 then take the nameOfWorker as "vrashali".
  * for e.g If user says that, Please change the salary of utkarsh to 12000 rupees, then take the nameOfWorker as "utkarsh".

- For salary:
  * If user mentions the salary then take the salary amount from the {user_input} and if not mentioned then take the salary amount from the existing record.
  * It should never be 0.
  * check if user has world similar to word salary or monthly payment or simailar.

Key Processing Instructions:
- Use integers for monetary and attendance values.
- If no specific value mentioned, preserve existing record's value.

- Ensure final values are reasonable and consistent
- For partial updates, only modify mentioned fields
- Always include all fields in the result for all cases.
- don't make change in the Cash_Advance unless it is necessary change in the currentCashAdvance.

Return ONLY a valid JSON focusing on fields mentioned or changed:
{{
    "currentCashAdvance": <cash advance amount as integer>
    "monthlyRepayment": <monthly repayment amount as integer>,
    "Bonus": <bonus amount as integer>,
    "Attendance": <number of days present as integer>,
    "Repayment_Start_Month": <start month as 'Month' in capitalized form>,
    "Repayment_Start_Year": <integer in the form of yyyy>,
    "detailsFlag" : <0 or 1 as an integer>,
    "nameofWorker" : <name of the worker string always in lowercase.>,
    "salary" : <salary amount as an integer>
}}


examples:
user input = "i wanted to change the repayment amount, wanted to add 500 to the repayment and add 2222 bonus."
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record + 500,
    "Bonus": 2222,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": existing record,
    "Repayment_Start_Year": existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "sampatti",
    "salary" : existing record
}}   

user input = "Add 1000 bonus and worker was on leave for 7 days"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": 1000,
    "Attendance": {attendance_period}-7,
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "sampatti",
    "salary" : existing record
}}

user input = "Worker needs 5000 cash advance and repayment monthly should be 1000."
{{
    "currentCashAdvance": 5000,
    "Repayment_Monthly": 1000,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "sampatti",
    "salary" : existing record
}}


user input = "yes correct details"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 1,
    "nameofWorker" : "sampatti",
    "salary" : existing record
}}

user input = "please pay a cash advance of 20000 with a monthly repayment of 5000 to utkarsh sharma"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "utkarsh sharma",
    "salary" : existing record
}}

user input = "i want to give vrashali a bonus of 70000 and attendance of 25"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "vrashali",
    "salary" : existing record
}}

user input = "pay om a advance amount of 40000 to with a monthly repayment of 10000"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "om",
    "salary" : existing record
}}

user input = "the salary of utkarsh from this month is 15000"
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "utkarsh",
    "salary" : 15000
}}

user input = I wanted to deduct 2000 from salary and wanted to give only 3500 instead of 5500 this month only.
{{
    "currentCashAdvance": take value from the existing record,
    "Repayment_Monthly": take value from the existing record,
    "Bonus": take value from the existing record,
    "Attendance": {attendance_period}
    "Repayment_Start_Month": take value from the existing record,
    "Repayment_Start_Year": take value from the existing record,
    "detailsFlag" : 0,
    "nameofWorker" : "sampatti",
    "salary" : 3500
}}

Respond with the JSON ONLY. NO additional text!"""

    return template



def extracted_info_from_llm(user_input: str, employer_number: str, context: dict):
    # Validate employer_number
    if not employer_number:
        raise ValueError("Employer number is required")

    # Get or create employer record
    llm = ChatGroq(
        temperature=0,
        groq_api_key=groq_key,
        model_name="llama-3.3-70b-specdec"
    )
    
    current_date = datetime.now().date()
    current_day = datetime.now().day
    attendance_period = determine_attendance_period(current_day)

    template = llm_template()

    # Include context in the prompt
    prompt = PromptTemplate(input_variables=["user_input", "current_date", "current_month", "current_year", 
                                             "previous_month", "previous_year", "employer_number", 
                                             "attendance_period", "current_day", "context"], 
                             template=template)
    
    llm_chain = LLMChain(prompt=prompt, llm=llm)

    response = llm_chain.run({
        "user_input": user_input,
        "current_date": current_date,
        "current_month": current_month(),
        "current_year": current_year(),
        "previous_month": previous_month(),
        "previous_year": current_year(),
        "employer_number": employer_number,
        "attendance_period": attendance_period,
        "current_day": current_day,
        "context": context  # Pass the context to the LLM
    })
    
    cleaned_response = response.replace('```json', '').replace('```', '').strip()

    print(f"The response from LLM is: {response}")
    print(f"The response from LLM is: {cleaned_response}")

    try:
        extracted_info = json.loads(cleaned_response)
        return extracted_info
    
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Raw response: {response}")
        print(f"Cleaned response: {cleaned_response}")
        return None
    
def call_sarvam_api(file_path):

    url = "https://api.sarvam.ai/speech-to-text-translate"
    headers = {
        "api-subscription-key": sarvam_api_key
    }

    with open(file_path, 'rb') as file:
        files = { "file": (os.path.basename(file_path), file, "audio/wav")}
        response = requests.post(url, headers=headers, files=files)


    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error from Sarvam API: {response.text}")
    return response.json()




def translate_text_sarvam(text: str, source_language: str, target_language: str) -> str:

    try:
        url = "https://api.sarvam.ai/translate"

        headers = {
            "api-subscription-key": sarvam_api_key, 
            "Content-Type": "application/json"
        }

        payload = {
            "input": text,
            "source_language_code": source_language,
            "target_language_code": target_language,
            "speaker_gender": "Male",  
            "mode": "formal",          
            "model": "mayura:v1"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            translated_text = response.json().get("translated_text", "")
            return translated_text
        else:
            raise Exception(f"Error from Sarvam translation API: {response.text}")

    except Exception as e:
        print(f"Translation error: {e}")
        return text


def send_audio(output_directory: str, sample_output: str, language: str, employerNumber: int):

    
    try:
        # Using Sarvam API for text-to-speech
        url = "https://api.sarvam.ai/text-to-speech"
        payload = {
                "inputs": [sample_output],
                "target_language_code": language,     #Adjust as per the expected language code
                "speaker": "meera",     #Choose the appropriate speaker if required
                "enable_preprocessing": True,
                "model": "bulbul:v1"
            }
        headers = {
            "api-subscription-key": sarvam_api_key,     #Replace with your valid API key
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        base64_string = response_data["audios"][0] 

        os.makedirs(output_directory, exist_ok=True)

        mp3_file_path = os.path.join(os.getcwd(), output_directory, "output.mp3")
        ogg_file_path = os.path.join(os.getcwd(), output_directory, "output.ogg")

             # Decode the Base64 string to binary data
        audio_data = base64.b64decode(base64_string)

             # Write the binary data to a file
        with open(mp3_file_path, "wb") as audio_file:
            audio_file.write(audio_data)

        print(f"File saved as: {mp3_file_path}")
                #Generate the audio media ID using your existing WhatsApp logic

        
        convert_mp3_to_ogg(mp3_file_path, ogg_file_path)
        mediaIdObj = whatsapp_message.generate_audio_media_id("output.ogg", output_directory)
        audioMediaId = mediaIdObj["id"]
        whatsapp_message.send_whatsapp_audio(audioMediaId, employerNumber)
        return {"MESSAGE": "AUDIO SENT SUCCESSFULLY."}

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with speech service")
    except Exception as e:
        print(f"Error generating audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

def question_language_audio(output_directory: str, sample_output: str, surveyId : int, questionId : int, language: str):

    try:
        # Using Sarvam API for text-to-speech
        url = "https://api.sarvam.ai/text-to-speech"
        payload = {
                "inputs": [sample_output],
                "target_language_code": language,     #Adjust as per the expected language code
                "speaker": "meera",     #Choose the appropriate speaker if required
                "enable_preprocessing": True,
                "model": "bulbul:v1"
            }
        headers = {
            "api-subscription-key": sarvam_api_key,     #Replace with your valid API key
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        base64_string = response_data["audios"][0] 

        os.makedirs(output_directory, exist_ok=True)

        mp3_file_path = os.path.join(os.getcwd(), output_directory, f"{surveyId}_{questionId}_{language}.mp3")
        ogg_file_path = os.path.join(os.getcwd(), output_directory, f"{surveyId}_{questionId}_{language}.ogg")

             # Decode the Base64 string to binary data
        audio_data = base64.b64decode(base64_string)

             # Write the binary data to a file
        with open(mp3_file_path, "wb") as audio_file:
            audio_file.write(audio_data)
        
        convert_mp3_to_ogg(mp3_file_path, ogg_file_path)

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with speech service")
    except Exception as e:
        print(f"Error generating audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
    

def calculate_year_for_month(month_name):
    """
    Takes a month name as input and calculates the year.
    If the month occurs before the current month, return the next year.
    Otherwise, return the current year.

    :param month_name: Name of the month (e.g., "January", "September")
    :return: A tuple (month_name, year)
    """
    # Get the current month and year
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year

    # Convert input month name to a month number
    try:
        input_month = datetime.strptime(month_name, "%B").month
    except ValueError:
        return f"Invalid month name: {month_name}"

    # Determine the year based on the comparison
    if input_month < current_month:
        year = current_year + 1
    else:
        year = current_year

    return year



questions = {
    "1": "Please provide your age?",
    "2": "What is your education?(No formal education, primary education, secondary education, higher secondary education, diploma, graduate, post graduate, other)",
    "3": "what is your monthly household income? (20000/5000/100000/52000 integer value)",
    "4": "Please record your occupation",
    "5": "Number of family members",
    "6": "Do you have a bank account? (Yes/No) ",
    "7": "If Yes, which bank? (State Bank of India, Union Bank of India, Canara Bank, Other)",
    "8": "If No, why don't you have bank account? (Check all that apply) (Lack of documents, No bank nearby, Don't know how to open, Don't need one, Other (specify))" ,
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

# Function to process the response
def get_next_question(respondentId : str, workerId : str, questionId : int, answer : str, surveyId : int, db : Session):
    
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0.7, 
        api_key = openai_api_key
    )

    #Current question
    current_question_text = questions[f"{questionId}"]

    #prompt to process the answer
    prompt_template = PromptTemplate(
        input_variables=["worker_id", "current_question", "answer", "questions"],
        template="""
        Worker ID: {worker_id}
        Current Question: {current_question}
        Worker Answer: {answer}
        Questions ID: {questionId}

        Here is the full list of survey questions:
        {questions}

        1. If the provided answer contains responses for multiple questions, extract and match them to their respective question IDs.
        2. Generate the next most relevant question ID and text based on the provided answers.
        3. If the answer does not match the current question, check if it matches other questions. If it matches other questions, extract the answer and question ID and repeat the question with the question ID only once with respect to {worker_id}.
        4. if the  and answer is yes, then for  save the response accordingly and give it in the extracted answers.
        5. If the user answers "Yes" to a yes/no question, add a corresponding inferred answer to related follow-up questions (e.g., if question 6 is "Yes," save question 8 as "You have a bank account").
        6. If the user answers "No," add a corresponding inferred answer to related follow-up questions (e.g., if question 6 is "No," save question 8 as "You do not have a bank account").
        7. Extract the user's answer and match it to the corresponding question ID.
        8. Generate the next most relevant question based on the provided answer.
        9. Ensure that the response is structured correctly and includes the extracted answers and the next suggested question. 
        10. Generate the next most relevant question based on the provided answer.
        11. when the {questionId}=28 then extract the answer and give next {questionId}=0.
        
        Respond in the following JSON format:
        {{
            "extracted_answers": [
                {{"question_id": "<ID>", "answer": "<Answer>"}},
                ...
            ],
            "next_question": {{"id": "<ID>", "text": "<Text>"}}
        }}
        """
    )

    # Generate the prompt
    questions_list = "\n".join([f"ID {qid}: {text}" for qid, text in questions.items()])
    prompt = prompt_template.format(
        worker_id=workerId,
        current_question=current_question_text,
        answer=answer,
        questions=questions_list,
        questionId=questionId
    )
    # Get LLM response

    print(f"the prompt is : {prompt}")
    response = llm.invoke(prompt)  
    response_text = response.content
    cleaned_response = response_text.replace('```json', '').replace('```', '').strip()

    print(f"the response is : {cleaned_response}")
    # Parse the LLM response
    try:
        print("entering response data.")
        response_data = json.loads(cleaned_response)
        print(response_data)

        extracted_answers = response_data["extracted_answers"]
        next_question = response_data["next_question"]

        print(f"extracted answers : {extracted_answers}")
        print(f"next ques : {next_question}")
        for item in extracted_answers:

            qId = item["question_id"]
            ans = item["answer"]

            new_response_entry = models.Responses(id = generate_unique_id(), responseText = ans, workerId = workerId, questionId = qId, surveyId = surveyId, timestamp = f"{datetime.now()}", respondentId=respondentId)

            db.add(new_response_entry)
            
            db.commit()
            db.refresh(new_response_entry)

        return {
            "id" : int(next_question["id"]),
            "text" : next_question["text"]
        }
    except json.JSONDecodeError as e:
        return {"error": "Failed to parse LLM response", "details": str(e)}
    

def convert_mp3_to_ogg(input_file : str, output_file : str):

    try:
        # Check if ffmpeg is installed
        if not shutil.which("ffmpeg"):
            raise EnvironmentError("ffmpeg is not installed or not in PATH.")

        # Construct ffmpeg command
        command = [
            "ffmpeg",
            "-y",
            "-i", input_file,
            "-ar", "16000",  # Set sample rate to 16kHz
            "-c:a", "libopus",  # Use libopus codec
            output_file
        ]

        # Run the command
        subprocess.run(command, check=True)
        print(f"Conversion successful: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
    except Exception as e:
        print(f"Error: {e}")