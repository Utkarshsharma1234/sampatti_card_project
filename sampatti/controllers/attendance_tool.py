from turtle import mode
from langchain_community.tools import WikipediaQueryRun, DuckDuckGoSearchRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.tools import Tool
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
import uuid, re, json
from typing import Optional
from langchain.tools import StructuredTool
import requests, os, tempfile
from pydub import AudioSegment
from urllib.parse import urlparse

from sampatti.controllers.onboarding_tools import get_worker_details
from .utility_functions import call_sarvam_api
from ..database import get_db_session, get_db
from sqlalchemy.orm import Session
from ..models import CashAdvanceManagement, worker_employer
from fastapi import Depends
from .. import models

def save_to_txt(data: str, filename: str = "research_output.txt"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_text = f"--- Research Output ---\nTimestamp: {timestamp}\n\n{data}\n\n"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(formatted_text)
    
    return f"Data successfully saved to {filename}"

save_tool = Tool(
    name="attendance_file",
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



def get_workers_for_employer(employer_number: int) -> str:

    db = next(get_db())
    try:
        # Query to get all workers for this employer
        workers = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employer_number).all()
        
        if not workers:
            return {
                "success": False,
                "message": "No workers found for this employer number",
                "workers": []
            }
        
        # Convert to list of dictionaries
        worker_list = []
        for worker in workers:
            worker_list.append({
                "worker_id": worker.worker_id,
                "worker_name": worker.worker_name,
                "worker_number": worker.worker_number,
                "employer_id": worker.employer_id,
                "salary_amount": worker.salary_amount,
                "monthly_leaves": worker.monthly_leaves
            })
        
        return {
            "success": True,
            "message": f"Found {len(worker_list)} worker(s)",
            "workers": worker_list
        }
        
    except Exception as e:
        return {    
            "success": False,
            "message": f"Error fetching workers: {str(e)}",
            "workers": []
        }

def manage_attendance_records(action: str, dates: str, worker_id: str, employer_id: str):
    """Core function for managing attendance records"""
    
    db = next(get_db())
    try:
        # Convert comma-separated string into list of trimmed date strings
        date_list = [date.strip() for date in dates.split(",")] if dates else []

        if action == "view":
            # Retrieve attendance records for the worker
            records = db.query(models.AttendanceRecord.date_of_leave).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id
            ).all()

            # Format output
            attendance_dates = [record.date_of_leave.strftime("%Y-%m-%d") for record in records]
            print("Attendance Dates: ", attendance_dates)
            return {
                "status": "success", "data": attendance_dates
            }

        elif action == "add":
            # Convert date strings to date objects
            date_objects = [datetime.strptime(date, "%Y-%m-%d").date() for date in date_list]

            # Extract year and month for filtering
            year_month_tuples = {(d.year, d.month) for d in date_objects}

            # Fetch existing records for given worker & employer
            existing_records = db.query(models.AttendanceRecord.date_of_leave).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id,
                models.AttendanceRecord.year.in_([y for y, m in year_month_tuples]),
                models.AttendanceRecord.month.in_([m for y, m in year_month_tuples]),
            ).all()

            # Convert existing dates to a set for quick lookup
            existing_dates = {record.date_of_leave for record in existing_records}

            # Filter out duplicate dates
            new_dates = [d for d in date_objects if d not in existing_dates]

            if new_dates:
                new_records = [
                    models.AttendanceRecord(
                        uuid=str(uuid.uuid4()),
                        worker_id=worker_id,
                        employer_id=employer_id,
                        month=d.month,
                        year=d.year,
                        date_of_leave=d
                    ) for d in new_dates
                ]
                db.add_all(new_records)
                db.commit()
                return {
                    "status": "success", "message": f"Added {len(new_records)} new attendance records."
                }
            else:
                return {
                    "status": "info", "message": "No new records to add (all dates already exist)."
                }

        elif action == "delete":
            # Convert date strings to date objects
            date_objects = [datetime.strptime(date, "%Y-%m-%d").date() for date in date_list]

            # Find records to delete
            records_to_delete = db.query(models.AttendanceRecord).filter(
                models.AttendanceRecord.worker_id == worker_id,
                models.AttendanceRecord.employer_id == employer_id,
                models.AttendanceRecord.date_of_leave.in_(date_objects)
            ).all()

            if records_to_delete:
                for record in records_to_delete:
                    db.delete(record)
                db.commit()
                return {
                    "status": "success", "message": f"Deleted {len(records_to_delete)} attendance records."
                }
            else:
                return {
                    "status": "info", "message": "No matching records found for deletion."
                }

        else:
            return {
                "status": "error", "message": "Invalid action. Use 'view', 'add', or 'delete'."
            }

    except SQLAlchemyError as e:
        db.rollback()
        return {
            "status": "error", "message": f"Database error: {str(e)}"
        }

    except Exception as e:
        return {
            "status": "error", "message": f"Unexpected error: {str(e)}"
        }


def get_attendance_summary(
    employer_number: str,
    worker_name: Optional[str] = None
) -> str:
    
    db = next(get_db())
    try:
        worker_employer = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employer_number, models.worker_employer.c.worker_name == worker_name).first()

        employer_id = worker_employer.employer_id
        worker_id = worker_employer.worker_id

        print(f"Worker ID: {worker_id} and Employer ID: {employer_id}")

        attendance = db.query(models.AttendanceRecord).where(models.AttendanceRecord.employer_id == employer_id, models.AttendanceRecord.worker_id == worker_id).all()
        print("Attendance: ",attendance)

        return{
            "status": "success", 
            "data": attendance
        }

    except Exception as e:
        return {
            "status": "error", "message": f"Unexpected error: {str(e)}"
        }
        worker_id = worker_employer.worker_id

        attendance = db.query(models.AttendanceRecord).where(models.AttendanceRecord.employer_id == employer_id, models.AttendanceRecord.worker_id == worker_id).all()
        
        return{
            "status": "success", 
            "data": attendance
        }

    except Exception as e:
        return {
            "status": "error", "message": f"Unexpected error: {str(e)}"
        }


get_workers_for_employer_tool = StructuredTool.from_function(
    func=get_workers_for_employer,
    name="get_workers_for_employer",    
    description="Fetches worker details by worker number."
)

manage_attendance_tool = StructuredTool.from_function(
    func=manage_attendance_records,
    name="manage_attendance_records",
    description="Manages attendance records for workers."
)

get_attendance_summary_tool = StructuredTool.from_function(
    func=get_attendance_summary,
    name="get_attendance_summary",
    description="Gets attendance summary for workers."
)
