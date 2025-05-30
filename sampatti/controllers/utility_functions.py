import calendar
import shutil
from openai import OpenAI
import json, os, uuid, random, string,  difflib, re, requests, base64
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from langchain import PromptTemplate
from ..controllers import whatsapp_message
from sqlalchemy.orm import Session
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain_community.chat_models import ChatOpenAI
from .. import models
import subprocess
import re

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



def extracted_info_from_llm(user_input: str, worker_id: str, employer_id: str, context: dict):
    try:
        llm = OpenAI(api_key=openai_api_key)  # Ensure API key is loaded correctly
        current_date = datetime.now()
        today = datetime.today()
        current_month = today.month
        current_year = today.year
        print(f"Current Date: {current_date}")


        template = """
You are a helpful assistant managing salary, bonus, deduction, and cash advance details for a worker.

The system provides the following context from the database (if available), which contains the existing cash advance details for the worker. Use this context as the baseline, and update only the fields mentioned in the employer's new input: {context}

### Known Context:
The employer has sent the following message: "{user_input}"

Additional information:
- worker_id: {worker_id}
- employer_id: {employer_id}
- current date: {current_date}
- today: {today}
- current_month: {current_month}
- current_year: {current_year}

---

## YOUR TASK

Extract and return the following structured information as a JSON object. Follow these rules strictly:

### 1. **cash_advance**:
- This should reflect the **remaining cash advance balance** after calculating repayments based on:
    - `repayment_amount`
    - `repayment_start_month` and `repayment_start_year`
    - `frequency`
- **Calculation logic**:
    - If all required repayment values are provided (repayment_amount, start month/year, frequency):
        - Calculate how many **repayment cycles** have occurred up to the current month.
            - A repayment cycle occurs every `frequency` months starting from the repayment start date.
            - Example: If repayment started in December 2024, and frequency is 2 (alternate month), then repayments occur in Feb 2025, Apr 2025, etc.
        - **total_repaid = repayment_amount x number_of_cycles**
        - **remaining_balance = original_advance - total_repaid**
        - Cap remaining_balance at 0 if it becomes negative.
    - If the employer mentions only the cash advance without full repayment info:
        - Do NOT confirm.
        - Ask if they'd like to set up a repayment plan.

### 2. **repayment_amount**:
   - If the user gives a cashAdvance, prompt for:
     - repaymentAmount
     - repaymentStartMonth
     - repaymentStartYear
     - frequency
   - If the user says:
     - “repayment starts next month” → calculate from current date:
       - if May 2025 → month = 6, year = 2025
       - if December → month = 1, year = current_year + 1
     - if month name is given (e.g., “July”) → month = 7
       - if that month is already over this year, assume next year



### 3. **repayment_start_month** and **repayment_start_year**:
- If a month is mentioned (like "December"), map to the corresponding month number (December = 12).
- If the employer does NOT explicitly mention the year, infer it using the following logic:
    - If the mentioned month is **earlier than the current month**, assume **last year**.
    - If the mentioned month is **equal to or after the current month**, assume **this year**.
    - Example: If current month is April (4) and employer says "December," use year = current year - 1.
- If no month is mentioned but repayment_amount is provided, set repayment_start_month to **next month** and repayment_start_year accordingly.
- If repayment_amount is not provided, set repayment_start_month and repayment_start_year to 0.

### 4. **frequency**:
- Determine frequency based on employer's wording:
    - "monthly," "each month," "every month" → 1
    - "alternate month," "every other month," "every two months" → 2
    - "every three months," "quarterly" → 3
    - "every six months," "half-yearly" → 6
    - "every n months" → n (where n is the number of months)
    - "random," "unscheduled," or if not specified → 0
- If repayment_amount is provided but frequency is not mentioned, default frequency to 1 (monthly).

### 5. **Salary**
   - Never change monthly_salary unless the user explicitly says it has changed.
   - If user says “change salary” but doesn’t clearly say if it's permanent:
    - Ask: “Do you want to permanently change the salary, or just for this month?”
    - Until confirmation, do not change salary value. Only compute bonus/deduction if amount change is temporary.
- If user says "permanent change" or "change from this month":
    - Update `monthly_salary` to the new value.
    - Set bonus and deduction to 0.
- If salary change is for this month only:
    - Calculate:
        - deduction = context_salary - new_salary (if less)
        - bonus = new_salary - context_salary (if more)
    - Keep monthly_salary unchanged.

### 6. **bonus*
    - Only apply bonus if the user *explicitly* uses phrases like this:
        - “give bonus ₹X from salary”
        - “extra ₹X”
        - “add salary by ₹X”
        - “give ₹X this month”, bonus = X - monthly_salary
        - more phrases like this for bonus
    - Do *not* infer deduction based on cashAdvance or repayment.
    - Do not auto-calculate deduction as monthly_salary - repaymentAmount.
    - bonus and repayment are separate and should never overlap unless user gives both explicitly.

### 7. **deduction*
    - Only apply deduction if the user *explicitly* uses phrases like this:
        - “deduct ₹X from salary”
        - “take out ₹X”
        - “reduce salary by ₹X”
        - “only give ₹X this month”, deduction = monthly_salary - X
    - If user says that "i have paid X earlier and cut this from salary" or similiar phrases, user your mind to understand phrases, deduction = monthly_salary - X.
    - Do *not* infer deduction based on cashAdvance or repayment.
    - Do not auto-calculate deduction as monthly_salary - repaymentAmount.
    - Deduction and repayment are separate and should never overlap unless user gives both explicitly.


### 8. **confirmation**:
- Set to 1 if user_input clearly confirms the details with phrases like:
    - "yes," "confirmed," "looks good," "okay," "all correct," "sounds good," "all set," or similar affirmatives.
    - Consider variations like "yes, please proceed," or "yeah, that's right."
- Set to 0 if:
    - There is any update, change request, or question.
    - Confirmation is unclear or partial (e.g., "yes, but change repayment to 1500").


### Rules for Updating Fields:





## SCENARIO HANDLING:

- If the employer provides only **cash_advance** without repayment details, respond with a polite question asking if they want to set up a repayment plan.
- If they specify repayment_amount but not frequency, assume monthly (1).
- If conflicting or unclear instructions are given (like "set repayment to 2000 but no repayment"), set unclear fields to 0 and politely ask for clarification.
- If they use timing phrases like "next month," calculate the correct month and year based on current_date.
- If the user mentions only "bonus" or "deduction" without a cash advance, still return those fields properly.
- If the user says change the salary then update the monthly salary and set bonus and deduction to 0 accordingly.
- If the user only wanted to give bonus or deduction then set don't mention the cash advance and repayment unless mentioned by user.
- If user only provide bonus or deduction or monthly salary, then set don't mention the cash advance and repayment unless mentioned by user.

---

## AI MESSAGE RULES (`ai_message`):

Questions to ask in "ai_message":
   - never ask questions which may result in answer as "No".
   - interact with the employer like you are managing the financials of the employer which he gives to his domestic worker and help them as a guide will do, very human-like interaction.
   - treat different pockets pocket1 : (cash advance, repayment amount, repayment startmonth, repayment startyear, frequency), pocket2: bonus, pocket3: deduction, pocket4: salary. if values from one pocket are not complete prompt the user for those values and never mix up these pockets. if user is not talking about any pocket dont prompt for that value.
   - once you feel like the values from one pocket are received inform in a very human like way of all the recorded values which user gave you and make the "readyToConfirm" as 1.
   - when "readyToConfirm" is 1 the ending should be "Shall we lock in the details ?" 

- If only cash advance is given and repayment is missing:
    - "You have provided a cash advance of ₹X, but the repayment amount, frequency, or start month is missing. Could you please specify how you would like the repayment to be scheduled?"
- If only bonus or deduction is given:
    - "I've noted a bonus of ₹X this month. Is that correct?"
- If salary is changed temporarily:
    - "The monthly salary remains unchanged, but I’ve noted a deduction of ₹X for this month based on the updated salary."
- If permanent salary change:
    - "Monthly salary has been updated to ₹X as requested."
- If confirmation = 1:
    - "Thank you for confirming! All the details have been recorded successfully: [summary of all fields]."
    - Please make sure to take the correct values and show the correct context that is being provide by the user before confirming.
- If partial confirmation:
    - "I've updated the repayment to ₹X. Let me know if everything looks correct or if you’d like to make any further changes."
- If unclear:
    - Ask a polite clarifying question.
- Always end with a warm question like:
    - "Does this look correct? If not, please let me know what to update!"

---

## RESPONSE FORMAT (Strict JSON only):

Return ONLY the following JSON object:
{{
    "cash_advance": <integer>,
    "repayment_amount": <integer>,
    "repayment_start_month": <integer>,
    "repayment_start_year": <integer>,
    "frequency": <integer>,
    "bonus": <integer>,
    "deduction": <integer>,
    "monthly_salary": <integer>,
    "ai_message": "<friendly summary message>",
    "confirmation": <integer>
}}
"""




        prompt_template = PromptTemplate(
            input_variables=["user_input", "current_date", "context", "worker_id", "employer_id"],
            template=template
        )

        prompt = prompt_template.format(
            user_input=user_input,
            current_date=current_date,
            today=today,
            current_month=current_month,
            current_year=current_year,
            context=context,
            worker_id=worker_id,
            employer_id=employer_id
        )

        # Send prompt to LLM
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a cash advance and repayment management system assistant that updates JSON fields accurately."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )

        response_text = response.choices[0].message.content.strip()
        print(f"LLM Response Raw: {response_text}")

        cleaned_response = response_text.replace('```json', '').replace('```', '').strip()
        print(f"LLM Response Cleaned: {cleaned_response}")
        
        # Parse JSON
        extracted_info = json.loads(cleaned_response)

        return extracted_info

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Raw response: {response_text}")
        return JSONResponse(content={"error": f"Invalid JSON response from LLM: {str(e)}"}, status_code=500)
    except Exception as e:
        print(f"Unexpected error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

     
def call_sarvam_api(file_path):

    url = "https://api.sarvam.ai/speech-to-text-translate"
    headers = {
        "api-subscription-key": sarvam_api_key
    }

    with open(file_path, 'rb') as file:
        files = { "file": (os.path.basename(file_path), file, "audio/wav")}
        response = requests.post(url, headers=headers, files=files)

    print(response.json())

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
        id = generate_unique_id()

        mp3_file_path = os.path.join(os.getcwd(), output_directory, f"output_{id}.mp3")
        ogg_file_path = os.path.join(os.getcwd(), output_directory, f"output_{id}.ogg")

             # Decode the Base64 string to binary data
        audio_data = base64.b64decode(base64_string)

             # Write the binary data to a file
        with open(mp3_file_path, "wb") as audio_file:
            audio_file.write(audio_data)

        print(f"File saved as: {mp3_file_path}")
                #Generate the audio media ID using your existing WhatsApp logic

        
        convert_mp3_to_ogg(mp3_file_path, ogg_file_path)
        mediaIdObj = whatsapp_message.generate_audio_media_id(f"output_{id}.ogg", output_directory)
        audioMediaId = mediaIdObj["id"]
        whatsapp_message.send_whatsapp_audio(audioMediaId, employerNumber)

        try:
            os.remove(mp3_file_path)
            os.remove(ogg_file_path)
            print(f"Deleted files: {mp3_file_path} and {ogg_file_path}")
        except Exception as delete_error:
            print(f"Error deleting files: {delete_error}")

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



def systemattic_survey_message(worker_number: str, user_name: str, survey_id: int, db: Session) -> dict:
    total_survey_messages = db.query(models.SurveyResponse).filter(
        models.SurveyResponse.worker_number == worker_number,
        models.SurveyResponse.user_name == user_name,
        models.SurveyResponse.survey_id == survey_id
    ).all()

    message = "Here are the answers you provided:\n\n"

    for i, response in enumerate(total_survey_messages, start=1):

        question = db.query(models.QuestionBank).filter(models.QuestionBank.id == response.question_id).first()
        
        if question:
            message += f"{i}. {question.questionText}\n   Answer {i}: {response.response}\n\n"

    return {"confirmation_message": message.strip()}

        
