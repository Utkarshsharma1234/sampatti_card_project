from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import Tool
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
from uuid import uuid4
from typing import Optional
from langchain.tools import StructuredTool
import requests


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


class WorkerEmployerInput(BaseModel):
    worker_number: str
    UPI: Optional[str] = None
    bank_account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    pan_number: str
    salary: int
    employer_number: str  # already known and passed from context

    @root_validator()
    def validate_payment_method(cls, values):
        UPI, bank_account, ifsc = values.get('UPI'), values.get('bank_account_number'), values.get('ifsc_code')
        if not UPI and (not bank_account or not ifsc):
            raise ValueError("Please provide either UPI or both bank account number and IFSC code.")
        if UPI and (bank_account or ifsc):
            raise ValueError("Please provide only one mode of payment: either UPI or bank account details.")
        return values



def onboard_worker_employer( worker_number: int, employer_number: int, pan_number: str, salary : int, UPI: Optional[str] = "", bank_account_number: Optional[str]= "", ifsc_code: Optional[str] = "") -> str:

    bank_passbook_image = "placeholder_passbook.jpg"
    pan_card_image = "placeholder_pan.jpg"

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
        "salary": salary
    }

    url = "https://conv.sampatticards.com/user/ai_agent/onboarding_worker_sheet/create"
    response = requests.post(url, json=data)

    return f"Onboarding completed. Status: {response.status_code}, Response: {response.text}"

worker_onboarding_tool = StructuredTool.from_function(
    func=onboard_worker_employer,
    name="onboard_worker_with_employer",
    description="Onboards a worker under an existing employer by collecting bank/UPI, PAN, and salary info.",
    args_schema=WorkerEmployerInput
)