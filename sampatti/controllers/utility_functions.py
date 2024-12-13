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


load_dotenv()
groq_key= os.environ.get('GROQ_API_KEY')
sarvam_api_key = os.environ.get('SARVAM_API_KEY')

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

def llm_template():

    template = """
    Extract the following information from the user's text:
    1. Cash Advance amount
    2. Monthly repayment amount
    3. Bonus (if applicable)

    Return the information in a structured JSON format:
    {{
        "Cash_Advance": "<cash advance amount>",
        "Repayment_Monthly": "<monthly repayment amount>",
        "Bonus": "<bonus amount>"
    }}

    Examples:

    - "Cash advance five thousand, bonus two thousand, and monthly repayment three thousand."
    Returns:
    {{
        "Cash_Advance": "5000",
        "Repayment_Monthly": "3000",
        "Bonus": "2000"
    }}

    - "The cash advance I am giving is five thousand rupees, the monthly repayment I will take from the worker is two thousand rupees, and the bonus I am giving is one thousand rupees."
    Returns:
    {{
        "Cash_Advance": "5000",
        "Repayment_Monthly": "2000",
        "Bonus": "1000"
    }}

    - "I am giving my worker ten thousand rupees in advance this month and I want to every month, I want to take back a thousand rupees and also give him this month's bonus, and that is two thousand rupees. The bonus I want to give him is two thousand rupees."

    Returns:
    {{
        "Cash_Advance": "10000",
        "Repayment_Monthly": "1000",
        "Bonus": "2000"
    }}

    User Input: {user_input}
    ### VALID JSON (NO PREAMBLE):
    """

    return template


def llm_template2():
    template = """You are an intelligent assistant helping to extract precise financial and attendance information for an employee cash advance record.

Instructions:
1. Carefully analyze the entire user input
2. Extract all relevant financial and attendance details
3. If any information is missing, use reasonable defaults
4. Be flexible in understanding variations of input

Current Context:
- Current Date: {current_date}
- Current Month: {current_month} {current_year}
- Previous Month: {previous_month} {previous_year}
- Previous Record: {previous_record}
- days in previous month: {previous_month_days}

Input Text: {user_input}
employer_number: {employer_number}

Extract the following information with smart interpretation:
- Cash Advance Amount: Look for any mention of cash advance, advance, loan, or financial support
- Monthly Repayment Amount: Find the planned monthly repayment
- Bonus: Identify any bonus or additional payment
- Attendance: Calculate days present or if days absent then subtract from number of days in previous month.
- Repayment Start Month: Determine when repayment begins

Extraction Rules:
- Use integers for all monetary and attendance values
- If no bonus mentioned, use 0
- If attendance not specified, default to days present in previous month.
- For Repayment_Start_Month:
  * IMPORTANT: Current date is {current_date}
  * If not specified, use next month from current date
  * If user mentions a specific month (e.g., "March", "June"):
    - Compare with current month {current_month}
    - If mentioned month comes after {current_month} in calendar, use {current_year}
    - If mentioned month comes before or equals {current_month}, use {current_year} + 1
  * Always format as 'YYYY-MM'
  * Double-check: For March mentioned in {current_month} {current_year}, it should be '2025-03'
- If user says add/subtract/take back, then add/subtract/take back the amount from previous cash advance, bonus and monthly repayment
- If user says worker was on leave/absent/sick/not working for n days, then subtract n days from previous month
- if employer is coming first time this month, then use 0 for all previous fields
- If same employee is mentioned again, then use previous fields values wherever there is empty field

Return ONLY a valid JSON in this format:
{{
    "Cash_Advance": <cash advance amount as integer>,
    "Repayment_Monthly": <monthly repayment amount as integer>,
    "Bonus": <bonus amount as integer>,
    "Attendance": <number of days present as integer>,
    "Repayment_Start_Month": <start month as 'YYYY-MM'>
}}

Respond with the JSON ONLY. NO additional text!"""
    return template

# def get_previous_record(db: Session, employer_number: int):
#     latest_record = (
#         db.query(CashAdvanceRecord)
#         .join(Employee)
#         .filter(Employee.employer_number == employer_number, CashAdvanceRecord.is_active == True)
#         .order_by(CashAdvanceRecord.created_at.desc())
#         .first()
#     )
    
#     if latest_record:
#         return {
#             "current_cash_advance": latest_record.current_cash_advance,
#             "current_monthly_repayment": latest_record.current_monthly_repayment,
#             "remaining_balance": latest_record.remaining_balance,
#             "bonus": latest_record.bonus,
#             "attendance": latest_record.attendance
#         }
#     return None

# def extract_info_from_llm(user_input: str, employer_number: int, db: Session):
#     # Get previous record
#     previous_record = get_previous_record(db, employer_number)
    
#     # Initialize LLM
#     llm = ChatGroq(
#         temperature=0,
#         groq_api_key=groq_key,
#         model_name="llama-3.1-70b-versatile"
#     )
    
#     # Get current date info - Add explicit current_date parameter
#     current_date = current_date()
#     current_month = current_month()
#     current_year = current_year()
#     previous_month = (current_date.replace(day=1) - timedelta(days=1)).strftime("%B")
#     previous_year = (current_date.replace(day=1) - timedelta(days=1)).year
#     previous_month_days = (current_date.replace(day=1) - timedelta(days=1)).day
    
#     # Calculate next month
#     next_month_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
#     next_month = next_month_date.strftime("%Y-%m")
    
#     # Prepare template with explicit current date information
#     prompt = PromptTemplate(
#         input_variables=["user_input", "current_date", "current_month", "current_year", "previous_month", "previous_year", "previous_month_days", "previous_record", "employer_number"],
#         template=llm_template()
#     )
    
#     # Create the runnable sequence with all required variables
#     chain = RunnableSequence(
#         first=prompt,
#         last=llm
#     ) | JsonOutputParser()

#     try:
#         # Run the chain with explicit current date
#         response = chain.invoke({
#             "employer_number": employer_number,
#             "user_input": user_input,
#             "current_date": current_date.strftime("%Y-%m-%d"),  # Format date explicitly
#             "current_month": current_month,
#             "current_year": current_year,
#             "previous_month": previous_month,
#             "previous_year": previous_year,
#             "previous_month_days": previous_month_days,
#             "previous_record": str(previous_record) if previous_record else "No previous record"
#         })
        
#         # Extracted data is now a Python dictionary
#         extracted_data = response
#         # Validate and set defaults if needed
#         extracted_data['Cash_Advance'] = extracted_data.get('Cash_Advance', 0)
#         extracted_data['Repayment_Monthly'] = extracted_data.get('Repayment_Monthly', 0)
#         extracted_data['Bonus'] = extracted_data.get('Bonus', 0)
#         extracted_data['Attendance'] = extracted_data.get('Attendance', previous_month_days)  # Default to full month
#         extracted_data['Repayment_Start_Month'] = extracted_data.get('Repayment_Start_Month', next_month)
        
#         # Get or create employee
#         employee = db.query(Employee).filter_by(employer_number=employer_number).first()
#         if not employee:
#             employee = Employee(employer_number=employer_number)
#             db.add(employee)
#             db.commit()
#         # Deactivate previous record if exists
#         if previous_record:
#             old_record = (
#                 db.query(CashAdvanceRecord)
#                 .filter_by(employee_id=employee.id, is_active=True)
#                 .first()
#             )
#             if old_record:
#                 old_record.is_active = False
#         # Create new record
#         new_record = CashAdvanceRecord(
#             employee_id=employee.id,
#             current_cash_advance=extracted_data["Cash_Advance"],
#             current_monthly_repayment=extracted_data["Repayment_Monthly"],
#             remaining_balance=extracted_data["Cash_Advance"],
#             bonus=extracted_data["Bonus"],
#             attendance=extracted_data["Attendance"],
#             repayment_start_month=extracted_data["Repayment_Start_Month"],
#             is_active=True
#         )
#         db.add(new_record)
#         db.commit()
        
#         print(f"the response from llm is : {response}")
        
#         return {
#             "previous_record": previous_record,
#             "new_record": extracted_data,
#             "status": "success"
#         }
        
#     except Exception as e:
#         print(f"Error processing response: {str(e)}")
#         raise HTTPException(
#             status_code=422,
#             detail=f"Error processing LLM response: {str(e)}"
#         )


# #delete this 
# #Test cases for checking
# test_inputs = [
#     "The worker was present for 22 days. I am giving my worker ten thousand rupees as cash advance this month and I want to take back a thousand rupees and bonus is two thousand rupees.",
#     "I wanted to add 10000 rupees as cash advance and 1000 rupees as monthly repayment.",
#     "The worker was on leave for 2 days. I want to add 10000 rupees as cash advance and 1000 rupees as monthly repayment.",
#     "Worker got a bonus of 5000 and worked for 25 days. Cash advance of 15000 with monthly repayment of 2000.", 
#     "Eight thousand as advance, repayment of five hundred, bonus of one thousand."
#     "I wanted to start monthly repayment from march"
#     "The worker was on leave for 2 days. I want to add 10000 rupees as cash advance and 1000 rupees as monthly repayment.",
# ]

def extracted_info_from_llm(user_input : str):
    llm = ChatGroq(
        temperature=0,
        groq_api_key= groq_key,
        model_name="llama-3.1-70b-versatile"
    )
    
    template = llm_template()

    prompt = PromptTemplate(input_variables=["user_input"], template=template)
    llm_chain = LLMChain(prompt=prompt, llm=llm)

    response = llm_chain.run({
        "user_input": user_input 
    })

    print(f"the response from llm is : {response}")
    try:
        extracted_info = json.loads(response)
        return extracted_info
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
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


# def translate_text_sarvam(text: str, source_language: str, target_language: str) -> str:

#     try:
#         url = "https://api.sarvam.ai/translate"

#         headers = {
#             "api-subscription-key": sarvam_api_key, 
#             "Content-Type": "application/json"
#         }

#         payload = {
#             "input": text,
#             "source_language_code": source_language,
#             "target_language_code": target_language,
#             "speaker_gender": "Male",  
#             "mode": "formal",          
#             "model": "mayura:v1"
#         }

#         response = requests.post(url, json=payload, headers=headers)

#         if response.status_code == 200:
#             translated_text = response.json().get("translated_text", "")
#             return translated_text
#         else:
#             raise Exception(f"Error from Sarvam translation API: {response.text}")

#     except Exception as e:
#         print(f"Translation error: {e}")
#         return text

# def send_audio(output_directory: str, sample_output: str, language: str, background_tasks: BackgroundTasks, employerNumber: int):

#     try:
#         # Using Sarvam API for text-to-speech
#         url = "https://api.sarvam.ai/text-to-speech"
#         payload = {
#             "inputs": [sample_output],
#             "target_language_code": language,  # Adjust as per the expected language code
#             "speaker": "meera",  # Choose the appropriate speaker if required
#             "enable_preprocessing": True,
#             "model": "bulbul:v1"
#         }
#         headers = {
#             "api-subscription-key": sarvam_api_key,  # Replace with your valid API key
#             "Content-Type": "application/json"
#         }

#         response = requests.post(url, json=payload, headers=headers)
#         response_data = response.json()
#         base64_string = response_data["audios"][0] 

#         os.makedirs(output_directory, exist_ok=True)

#         # Decode the Base64 string to binary data
#         audio_data = base64.b64decode(base64_string)

#         # Construct the full file path
#         output_filename = "output.ogg"
#         file_path = os.path.join(output_directory, output_filename)

#         # Write the binary data to a file
#         with open(file_path, "wb") as ogg_file:
#             ogg_file.write(audio_data)

#         print(f"File saved as: {file_path}")
#         # Generate the audio media ID using your existing WhatsApp logic
#         response = whatsapp_message.generate_audio_media_id("output.ogg", output_directory)
#         audio_media_id = response.get('id')
#         print(audio_media_id)

#         # Send the audio using WhatsApp
#         whatsapp_message.send_audio(audio_media_id, employerNumber)

#         return {"MESSAGE": "AUDIO SENT SUCCESSFULLY."}

#     except Exception as e:
#         return JSONResponse(content={"error": f"Failed to generate speech: {e}"}, status_code=500)