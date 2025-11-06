from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import Tool
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
import uuid
from typing import Optional
from langchain.tools import StructuredTool
import requests, os, tempfile, json
import asyncio
from pydub import AudioSegment
from urllib.parse import urlparse
from .utility_functions import call_sarvam_api
from ..database import get_db
from sqlalchemy.orm import Session
from .. import models
from .utility_functions import generate_unique_id
from ..routers.auth import get_auth_headers


def add_employer(employer_number: int):
  
    db = next(get_db())

    employer = db.query(models.Employer).where(models.Employer.employerNumber == employer_number).first()

    if not employer:
        unique_id = generate_unique_id()
        new_user = models.Employer(
            id=unique_id, 
            employerNumber=employer_number,
            referralCode = '',
            accountNumber = '',
            ifsc = '',
            upiId = '',
            cashbackAmountCredited=0,
            FirstPaymentDone=False,
            numberofReferral=0,
            totalPaymentAmount=0
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    
    else:
        return employer


def get_employer_workers_info(employer_number: int):
    """
    Tool to fetch all workers mapped to a given employer number along with details.
    Returns a structured dictionary the AI agent can use to generate responses.
    """

    db = next(get_db())

    # Fetch all mapped workers for the employer
    result = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employer_number).all()

    # Build structured data
    workers_data = []
    for row in result:
        workers_data.append({
            "worker_number": row.worker_number,
            "worker_name": row.worker_name,
            "salary_amount": row.salary_amount,
            "monthly_leaves": row.monthly_leaves,
            "date_of_onboarding": row.date_of_onboarding,
        })

    response = {
        "employer_number": employer_number,
        "total_workers": len(workers_data),
        "workers": workers_data
    }

    return response


def check_employer_exists(employer_number: int) -> bool:
    db = next(get_db())
    employer = db.query(models.Employer).where(models.Employer.employerNumber == employer_number).first()
    
    if employer:
        return True
    return False
    
def check_worker_employer_exists(employer_number: int) -> bool:
    db = next(get_db())
    mapping = db.query(models.worker_employer).where(models.worker_employer.c.employer_number == employer_number).first()
    
    if mapping:
        return True
    return False


def financial_query_response(employerNumber: int, query: str) -> str:
    """
    Tool to handle financial queries related to employers and workers.
    It uses an external API to fetch accurate financial information.
    """
    api_url = "https://conv.sampatticards.com/user/rag_process_query"  # Replace with actual API endpoint
    payload = {"employerNumber" : employerNumber, "query": query}
    
    try:
        response = requests.post(api_url, params=payload, headers=get_auth_headers())
        response.raise_for_status()
        data = response.json()
        print("data : ", response)
        print("data : ", data)
        return data.get("response", "No answer found.")
    except requests.RequestException as e:
        return f"Error fetching financial data: {e}"


add_employer_tool = StructuredTool.from_function(
    func=add_employer,
    name="Add Employer",
    description="Add a new employer to the database."
)

get_employer_workers_info_tool = StructuredTool.from_function(
    func=get_employer_workers_info,
    name="Get Worker information",
    description="Get information about all workers mapped to a specific employer."
)

check_employer_exists_tool = StructuredTool.from_function(
    func=check_employer_exists,
    name="Check Employer Exists",
    description="Check if an employer exists in the database."
)

check_worker_employer_exists_tool = StructuredTool.from_function(
    func=check_worker_employer_exists,
    name="Check Worker-Employer Mapping Exists",
    description="Check if any worker-employer mapping exists for a given employer number."
)

financial_query_tool = StructuredTool.from_function(
    func=financial_query_response,
    name="Financial Query Tool",
    description="Handle financial queries related to employers and workers."
)
    