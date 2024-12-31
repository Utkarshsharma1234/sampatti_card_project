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


Extraction and Update Rules:
- Focus on extracting or modifying specific fields mentioned in the input.
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
  * If user says attendance is 100 or the attendance 100 percent then take the attendance as {attendance_period}.
  * If not specified use the value from the existing record.
  * If it is mentioned that the worker was on leave for let's say 7 days then take the attendance as {attendance_period} - 7.
  * If user says worker was present for full month or present for all days or was not on leave or attendance is 100 percent or anything like you listen is 100 for attendance or anything similar to this statemet then make attendance as {attendance_period}.
  * it should not be 0 anytime.


- For Repayment_Start_Month:
  * If user mentions a specific month (e.g., "March", "June"):
    - Set the value of Repayment_Start_Month to the value which user mentions and then return in the response.
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
    "Attendance": <number of days present as integer or {attendance_period}>,
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

        output_file_path = os.path.join(os.getcwd(), output_directory, "output.mp3")
             # Decode the Base64 string to binary data
        audio_data = base64.b64decode(base64_string)

             # Write the binary data to a file
        with open(output_file_path, "wb") as audio_file:
            audio_file.write(audio_data)

        print(f"File saved as: {output_file_path}")
                #Generate the audio media ID using your existing WhatsApp logic

        
        mediaIdObj = whatsapp_message.generate_audio_media_id("output.mp3", output_directory)
        audioMediaId = mediaIdObj["id"]
        whatsapp_message.send_whatsapp_audio(audioMediaId, employerNumber)
        return {"MESSAGE": "AUDIO SENT SUCCESSFULLY."}

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with speech service")
    except Exception as e:
        print(f"Error generating audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

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
