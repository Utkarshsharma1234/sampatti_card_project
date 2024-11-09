import json, os, uuid, random, string,  difflib, re, requests
from fastapi import File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi.responses import FileResponse, JSONResponse
from gtts import gTTS
from langchain_groq import ChatGroq
from langchain import LLMChain, PromptTemplate
from fastapi import BackgroundTasks



load_dotenv()
groq_key= os.environ.get('GROQ_API_KEY')

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


def extracted_info_from_llm(user_input : str):
    llm = ChatGroq(
        temperature=0,
        groq_api_key= groq_key,
        model_name="llama-3.1-70b-versatile"
    )
    
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
    User Input: {user_input}
    ### VALID JSON (NO PREAMBLE):
    """

    prompt = PromptTemplate(input_variables=["user_input"], template=template)
    llm_chain = LLMChain(prompt=prompt, llm=llm)

    response = llm_chain.run({
        "user_input": user_input  # Input the text containing the information
    })

    # Use regex to extract the JSON part from the response
    json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)

    extracted_info = {}
    if json_match:
        json_str = json_match.group(1)
        
        # Load the JSON string into a Python dictionary
        try:
            extracted_info = json.loads(json_str)
            return extracted_info
        except json.JSONDecodeError:
            print("Failed to decode JSON:", json_str)
    else:
        print("No JSON found in the response.")

def call_sarvam_api(file_path):
    # Sarvam API URL
    url = "https://api.sarvam.ai/speech-to-text-translate"

    # Headers for the API
    headers = {
        "api-subscription-key": "3f3f7553-a322-4b7e-a4db-b13fbb93f529"
    }

    # Open the audio file and prepare it for sending
    with open(file_path, 'rb') as file:
        # Prepare the file as a tuple: (filename, file content, content type)
        files = {
            "file": (os.path.basename(file_path), file, "audio/wav")  # Adjust content type if needed
        }

        # Send the POST request with the file and headers
        response = requests.post(url, headers=headers, files=files)

    # Check if the API call was successful
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error from Sarvam API: {response.text}")

    # Return the JSON response
    return response.json()

def translate_text_sarvam(text: str, source_language: str, target_language: str) -> str:

    try:
        # Sarvam translation API URL
        url = "https://api.sarvam.ai/translate"

        # Headers for the API request
        headers = {
            "api-subscription-key": "3f3f7553-a322-4b7e-a4db-b13fbb93f529",  # Replace with your actual API key
            "Content-Type": "application/json"
        }

        # Request body for the API
        payload = {
            "input": text,
            "source_language_code": source_language,
            "target_language_code": target_language,
            "speaker_gender": "Male",  # Example value; change if needed
            "mode": "formal",            # Assuming "text" mode; change if needed
            "model": "mayura:v1"
        }

        # Make the POST request to the Sarvam translation API
        response = requests.post(url, json=payload, headers=headers)

        # Check if the response was successful
        if response.status_code == 200:
            translated_text = response.json().get("translated_text", "")
            return translated_text
        else:
            raise Exception(f"Error from Sarvam translation API: {response.text}")

    except Exception as e:
        print(f"Translation error: {e}")
        return text

def send_audio(static_dir : str, filename : str, sample_output : str, language: str, background_tasks : BackgroundTasks):
    try:
        # Generate the audio file using gTTS and save it in the audio_files folder
        audio_file_path = os.path.join(static_dir, f"{filename}_output.mp3")
        tts = gTTS(sample_output, lang=language)
        tts.save(audio_file_path)

        # Add task to delete the file after the response is sent
        background_tasks.add_task(os.remove, audio_file_path)

        # Return the file response
        return FileResponse(path=audio_file_path, media_type="audio/mp3", filename=f"{filename}_output.mp3")

    except Exception as e:
        return JSONResponse(content={"error": f"Failed to generate speech: {e}"}, status_code=500)