import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from ..controllers import utility_functions, cashfree_api, userControllers
from sqlalchemy.orm import Session
from .. import schemas
from .utility_functions import current_date
from .. import models
from .utility_functions import generate_unique_id
#from .onboarding_tasks import run_tasks_till_add_vendor, run_tasks_after_vendor_addition

# Load environment variables from .env file
load_dotenv()

# Function to upload data to Google Sheets
def upload_data_to_google_sheets():
    # Connect to SQLite database

    static_dir = os.path.join(os.getcwd())
    db_path = os.path.join(static_dir, "sampatti.db")  # Adjust the path to your SQLite database
    print(f"The db path is : {db_path}")
    conn = sqlite3.connect(db_path)

    # Query data from SQLite table (adjust table name and columns as per your database structure)
    query = "SELECT * FROM Talk_To_Agent"
    df = pd.read_sql_query(query, conn)

    # Close database connection
    conn.close()

    # Authenticate Google Sheets API
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path:
        raise ValueError("The environment variable 'GOOGLE_APPLICATION_CREDENTIALS' is not set.")
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)


    sheet_title = 'Talk_To_Agent_Sheet'
    try:
        spreadsheet = client.open(sheet_title)
        sheet = spreadsheet.sheet1
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(sheet_title)
        sheet = spreadsheet.sheet1

    team_emails = ['utkarsh@sampatticard.in', 'nusrathmuskan962@gmail.com', 'vrashali@sampatticard.in']

    # Share the entire spreadsheet with multiple team members
    for email in team_emails:
        spreadsheet.share(email, perm_type='user', role='writer')


    # Clear existing data in Google Sheet
    sheet.clear()

    # Update Google Sheet with new data
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

    print(f"Data uploaded to Google Sheets successfully. Shareable link: {sheet.url}")


def get_client():

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    return client

sheet_title = "OpsTeamWorkerDetailsSheet"
main_sheet = "OnboardingWorkerDetails"

all_columns = [
    "id", "bank_account_name_cashfree", "pan_card_name_cashfree", "worker_number", "employer_number", "UPI", "bank_account_number", "ifsc_code", "PAN_number", "bank_passbook_image", "pan_card_image", "bank_account_validation", "pan_card_validation", "cashfree_vendor_add_status", "vendorId", "confirmation_message", "salary", "date_of_onboarding", "referral_code"
]

def create_worker_details_onboarding(worker_number: int, employer_number : int, UPI: str, bank_account_number: str, ifsc_code: str, pan_number: str, bank_passbook_image: str, pan_card_image: str, salary : int, referral_code : str = ""):
    date = current_date()
    # Input row dictionary
    input_data = {
        "id": utility_functions.generate_unique_id(length=16),
        "worker_number": worker_number,
        "employer_number" : employer_number,
        "UPI": UPI,
        "bank_account_number": bank_account_number,
        "ifsc_code": ifsc_code,
        "PAN_number": pan_number,
        "bank_passbook_image": bank_passbook_image,
        "pan_card_image": pan_card_image,
        "salary" : salary,
        "date_of_onboarding" : f"{date}",
        "referral_code" : referral_code
    }


    # Setup Google Sheets credentials
    client = get_client()
    team_emails = ['utkarsh@sampatticard.in', 'nusrathmuskan962@gmail.com', 'vrashali@sampatticard.in', 'om@sampatticard.in', 'nusrath@sampatticard.in']

    try:
        spreadsheet = client.open(sheet_title)
        sheet = spreadsheet.sheet1
        print("Sheet exists. Checking headers...")

        existing_headers = sheet.row_values(1)

        if existing_headers == all_columns:
            # Exact match: append new row
            row = [input_data.get(col, "") for col in all_columns]
            sheet.append_row(row)
            print("Exact column match. Row appended.")
        else:
            print("Column mismatch. Adjusting headers and restoring data...")

            # Fetch existing data
            all_data = sheet.get_all_values()
            existing_data = all_data[1:]  # Exclude headers

            # Map old column positions
            old_columns = existing_headers
            old_data_dicts = []
            for row in existing_data:
                data_dict = {col: row[i] if i < len(row) else "" for i, col in enumerate(old_columns)}
                old_data_dicts.append(data_dict)

            # Backup old rows into new structure
            padded_data = []
            for data_dict in old_data_dicts:
                padded_row = [data_dict.get(col, "") for col in all_columns]
                padded_data.append(padded_row)

            # Add the new row too
            new_row = [input_data.get(col, "") for col in all_columns]
            padded_data.append(new_row)

            # Clear and rewrite everything
            sheet.clear()
            sheet.update([all_columns] + padded_data)

            print("Headers updated. Previous and new data restored.")

    except gspread.SpreadsheetNotFound:
        print("Sheet not found. Creating new sheet...")
        spreadsheet = client.create(sheet_title)
        sheet = spreadsheet.sheet1
        sheet.update([all_columns])
        row = [input_data.get(col, "") for col in all_columns]
        sheet.append_row(row)
        for email in team_emails:
            spreadsheet.share(email, perm_type='user', role='writer')
        print("Sheet created and first row added.")

    print(f"Sheet URL: {spreadsheet.url}")

    #run_tasks_till_add_vendor()

    return spreadsheet.url

def add_vendor_to_cashfree():
    # Define the scope and credentials

    client = get_client()
    sheet = client.open(sheet_title).sheet1
    records = sheet.get_all_records()

    # Iterate over each record starting from row 2 (1-indexed)
    for idx, row in enumerate(records, start=2):
        vendor_id = row.get("vendorId", "").strip()

        # Skip if vendorId already exists
        if vendor_id:
            continue

        # Extract data
        vpa = row.get("UPI", "").strip()
        worker_number = row.get("worker_number", "")
        employer_number = row.get("employer_number", "")
        bank_worker_name = row.get("bank_account_name_cashfree", "").strip()
        pan_worker_name = row.get("pan_card_name_cashfree", "").strip()
        pan_number = row.get("PAN_number", "").strip()
        account_number = row.get("bank_account_number", "")
        ifsc_code = row.get("ifsc_code", "").strip()
        bank_account_validation = row.get("bank_account_validation", "").strip()
        pan_card_validation = row.get("pan_card_validation", "").strip()

        # Validate essential fields
        if not pan_number:
            print(f"Skipping row {idx}: Missing PAN")
            continue

        if not (account_number or vpa):
            print(f"Skipping row {idx}: Missing both account number and VPA")
            continue
        
        if pan_card_validation != "VALID":
            continue

        if not vpa and bank_account_validation != "VALID":
            continue
        
        if not bank_worker_name:
            bank_worker_name = pan_worker_name

        vendor = schemas.Vendor(
            vpa = vpa if vpa else "None",
            workerNumber=int(worker_number),
            name=pan_worker_name,
            pan=pan_number,
            accountNumber=f"{account_number}" if account_number else "None",
            ifsc=ifsc_code if account_number else "None",
            employerNumber=int(employer_number)
        )

        print(vendor)
        response = cashfree_api.add_a_vendor(vendor)
        new_vendor_id = response.get("VENDOR_ID")
        if new_vendor_id:
            sheet.update_cell(idx, get_column_index(sheet, "vendorId"), new_vendor_id)
            print(f"Updated row {idx} with vendorId: {new_vendor_id}")
        else:
            print(f"Failed to get vendorId for row {idx}")

def process_vendor_status(db : Session):
    # Setup

    client = get_client()
    onboarding_sheet = client.open(sheet_title).sheet1

    records = onboarding_sheet.get_all_records()
    header = onboarding_sheet.row_values(1)
    
    for idx, row in enumerate(records, start=2):  # start=2 for actual sheet row (header is at 1)
        vendorId = row.get("vendorId", "").strip()
        employer_number = row.get("employer_number", "")
        worker_bank_name = row.get("bank_account_name_cashfree", "").strip()
        worker_pan_name = row.get("pan_card_name_cashfree", "").strip()
        worker_number = row.get("worker_number", "")
        PAN_number = row.get("PAN_number", "").strip()
        upi_id = row.get("UPI", "").strip()
        bank_account_number = row.get("bank_account_number", "")
        ifsc_code = row.get("ifsc_code", "").strip()
        salary = row.get("salary", "")
        confirmation_message = row.get("confirmation_message", "").strip()
        referral_code = row.get("referral_code", "").strip()

        if not vendorId:
            print(f"[{idx}] No vendorId found")
            continue

        try:

            if confirmation_message == "SENT":
                continue

            status_response = cashfree_api.check_vendor_status(vendorId)
            pan_remarks = status_response["related_docs"][1]["remarks"]
            remarks = status_response["remarks"]
            final_remarks = f"{remarks} || {pan_remarks}"
            print(final_remarks)

            vendor_status = status_response["status"].upper()

            if vendor_status == "ACTIVE":
                
                update_sheet_cell(onboarding_sheet, idx, "cashfree_vendor_add_status", "ACTIVE")
                
                # Check if worker already exists in Domestic_Worker table
                existing_worker = db.query(models.Domestic_Worker).filter(
                    models.Domestic_Worker.workerNumber == worker_number
                ).first()
                
                if existing_worker:
                    print(f"[{idx}] Worker {worker_number} already exists in database. Using existing worker data.")
                    # Worker already exists, use existing vendorId and worker_id
                    existing_vendor_id = existing_worker.vendorId
                    existing_worker_id = existing_worker.id
                    
                    # Update the sheet with existing vendorId if different
                    if existing_vendor_id and existing_vendor_id != vendorId:
                        update_sheet_cell(onboarding_sheet, idx, "vendorId", existing_vendor_id)
                        print(f"[{idx}] Updated sheet with existing vendorId: {existing_vendor_id}")
                        
                else:
                    # Worker doesn't exist, create new entry in the db
                    if not worker_bank_name:
                        worker_bank_name = worker_pan_name

                    worker = schemas.Domestic_Worker(
                        name = worker_bank_name,
                        email = "sample@sample.com",
                        workerNumber=worker_number,
                        employerNumber = employer_number,
                        panNumber = PAN_number,
                        upi_id = upi_id if upi_id else "None",
                        accountNumber = bank_account_number if bank_account_number else "None",
                        ifsc = ifsc_code if bank_account_number else "None",
                        vendorId = vendorId,
                        referralCode = referral_code
                    )
                
                    userControllers.create_domestic_worker(worker, db)
                    print(f"[{idx}] Created new worker {worker_number} in database.")

            else:
                print(f"[{idx}] Vendor {vendorId} status = {vendor_status}. Updating status in sheet and logging failure.")
                update_sheet_cell(onboarding_sheet, idx, "cashfree_vendor_add_status", f"NOT ACTIVE - {final_remarks}")

        except Exception as e:
            print(f"[{idx}] Error checking status for vendorId {vendorId}: {e}")

def create_relations_in_db(db : Session):

    client = get_client()
    onboarding_sheet = client.open(sheet_title).sheet1
    worker_details_main_sheet = client.open(main_sheet).sheet1

    records = onboarding_sheet.get_all_records()
    header = onboarding_sheet.row_values(1)
    
    for idx, row in enumerate(records, start=2):  # start=2 for actual sheet row (header is at 1)
        vendorId = row.get("vendorId", "").strip()
        employer_number = row.get("employer_number", "")
        worker_name = row.get("bank_account_name_cashfree", "").strip()
        pan_name = row.get("pan_card_name_cashfree", "").strip()
        PAN_number=row.get("PAN_number", "").strip()
        worker_number = row.get("worker_number", "")
        salary = row.get("salary", "")
        vendor_status = row.get("cashfree_vendor_add_status", "")
        upi_id = row.get("UPI", "").strip()
        bank_account_number = row.get("bank_account_number", "")
        ifsc_code = row.get("ifsc_code", "").strip()
        confirmation_message = row.get("confirmation_message", "").strip()
        date_of_onboarding = row.get("date_of_onboarding", "").strip()
        referral_code = row.get("referral_code", "").strip()


        if not worker_name:
            worker_name = pan_name


        if confirmation_message == "SENT":
            continue

        if vendor_status == "ACTIVE":

            try:
                # Get actual worker_id and vendor_id from Domestic_Worker table
                existing_worker = db.query(models.Domestic_Worker).filter(
                    models.Domestic_Worker.workerNumber == worker_number
                ).first()
                
                if existing_worker:
                    actual_worker_id = existing_worker.id
                    actual_vendor_id = existing_worker.vendorId
                    print(f"[{idx}] Using existing worker data - worker_id: {actual_worker_id}, vendor_id: {actual_vendor_id}")
                else:
                    # Fallback to sheet values if worker not found in database
                    actual_worker_id = "worker_id"
                    actual_vendor_id = vendorId
                    print(f"[{idx}] Worker not found in database, using sheet values")
                    
                employer_obj = db.query(models.Employer).filter(
                    models.Employer.employerNumber == employer_number
                ).first()

                if employer_obj:
                    actual_employer_id = employer_obj.id
                    print(f"[{idx}] Using existing employer - employer_id: {actual_employer_id}")
                else:
                    # Create new Employer
                    actual_employer_id = generate_unique_id()
                    new_employer = models.Employer(
                        id=actual_employer_id,
                        employerNumber=employer_number,
                        referralCode=referral_code,
                        cashbackAmountCredited=0,
                        FirstPaymentDone=False,
                        accountNumber='',
                        ifsc='',
                        upiId='',
                        numberofReferral=0,
                        totalPaymentAmount=0,
                        beneficiaryId=''
                    )
                    db.add(new_employer)
                    db.commit()
                    db.refresh(new_employer)
                    print(f"[{idx}] Created new employer - employer_id: {actual_employer_id}")
                
                relation = schemas.Worker_Employer(
                    workerNumber = worker_number,
                    employerNumber = employer_number,
                    salary = salary,
                    vendorId = actual_vendor_id,
                    worker_name = worker_name,
                    employer_id = actual_employer_id,
                    worker_id = actual_worker_id,
                    referralCode = referral_code
                )

                userControllers.create_relation(relation, db, date_of_onboarding)

                if not bank_account_number:
                    bank_account_number="N/A"
                    ifsc_code="N/A"

                if not upi_id:
                    upi_id="N/A"

                userControllers.generate_employment_contract(employer_number, worker_number,upi_id, bank_account_number, ifsc_code, PAN_number, worker_name, salary, db)
                update_sheet_cell(onboarding_sheet, idx, "confirmation_message", "SENT")
                row_values = onboarding_sheet.row_values(idx)
                worker_details_main_sheet.append_row(row_values, value_input_option="USER_ENTERED")
                main_sheet_url = worker_details_main_sheet.url
                print(main_sheet_url)
            except Exception as e:
                print(f"Error creating worker employer relation in db : {e}")
        
        else:
            continue

def bank_account_validation_status():

    # Access the sheet
    client = get_client()
    sheet = client.open(sheet_title).sheet1
    header = sheet.row_values(1)
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):
        account_number = row.get("bank_account_number", "")
        ifsc_code = row.get("ifsc_code", "").strip()
        pan_number = row.get("PAN_number", "").strip()
        pan_validation = row.get("pan_card_validation", "").strip()
        bank_account_validation = row.get("bank_account_validation", "").strip()

        # Skip if missing critical info
        if pan_validation != "VALID" and pan_number:

            print(pan_number)
            pan_response = cashfree_api.pan_verification(pan_number, "sample")

            if not pan_response:
                update_sheet_cell(sheet, idx, "pan_card_validation", "NOT FETCHED")
                update_sheet_cell(sheet, idx, "pan_card_name_cashfree", "NOT FETCHED")
            else:
                pan_status = pan_response.get("status")
                name_pan_card = pan_response.get("name_pan_card")
                update_sheet_cell(sheet, idx, "pan_card_validation", pan_status)
                update_sheet_cell(sheet, idx, "pan_card_name_cashfree", name_pan_card)

        if bank_account_validation != "VALID" and account_number:

            print(account_number)
            bank_response = cashfree_api.bank_account_verification(account_number, ifsc_code)
            
            if not bank_response:
                update_sheet_cell(sheet, idx, "bank_account_validation", "NOT FETCHED")
                update_sheet_cell(sheet, idx, "bank_account_name_cashfree", "NOT FETCHED")
                continue
            else:
                bank_status = bank_response.get("account_status")
                name_at_bank = bank_response.get("name_at_bank")
                update_sheet_cell(sheet, idx, "bank_account_validation", bank_status)
                update_sheet_cell(sheet, idx, "bank_account_name_cashfree", name_at_bank)

def fetch_pan_bank_details_from_image():

    # Access the sheet
    client = get_client()
    sheet = client.open(sheet_title).sheet1
    header = sheet.row_values(1)
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):

        bank_passbook_image = row.get("bank_passbook_image", "").strip()
        account_number = row.get("bank_account_number", "")
        pan_card_image = row.get("pan_card_image", "").strip()
        pan_number = row.get("PAN_number", "").strip()
        ifsc_code = row.get("ifsc_code", "").strip()

        if bank_passbook_image:

            if account_number and ifsc_code:
                continue

            bank_response = userControllers.extract_passbook_details(bank_passbook_image)
            response_error = bank_response.get("error")
            if response_error:
                update_sheet_cell(sheet, idx, "bank_account_number", "NA")
                update_sheet_cell(sheet, idx, "ifsc_code", "NA")
            else:
                account_number = bank_response.get("account_number")
                ifsc_code = bank_response.get("ifsc_code")
                update_sheet_cell(sheet, idx, "bank_account_number", account_number)
                update_sheet_cell(sheet, idx, "ifsc_code", ifsc_code)

        if pan_card_image:

            if pan_number: 
                continue
            
            pan_response = userControllers.extract_pan_card_details(pan_card_image)
            response_error = pan_response.get("error")
            if response_error:
                update_sheet_cell(sheet, idx, "PAN_number", "NA")
            else:
                PAN_number = pan_response.get("pan_number")
                update_sheet_cell(sheet, idx, "PAN_number", PAN_number)
 


def update_sheet_cell(sheet, row_index, column_name, new_value):

    """Helper to update a cell by column name."""
    header = sheet.row_values(1)
    try:
        col_index = header.index(column_name) + 1
        sheet.update_cell(row_index, col_index, new_value)
    except ValueError:
        print(f"Column '{column_name}' not found in sheet.")

def get_column_index(sheet, column_name):
    """Helper to get column index (1-indexed) for a given column name."""
    header = sheet.row_values(1)
    try:
        return header.index(column_name) + 1
    except ValueError:
        raise ValueError(f"Column '{column_name}' not found in sheet header.")
    
    
def create_record_for_existing_worker_sheet(worker_number: int, employer_number : int, worker_name : str, UPI: str, bank_account_number: str, ifsc_code: str, pan_number: str, salary : int, referral_code : str = ""):
    date = current_date()
    
    # Input row dictionary
    input_data = {
        "id": utility_functions.generate_unique_id(length=16),
        "worker_number": worker_number,
        "employer_number" : employer_number,
        "UPI": UPI or "NA",
        "bank_account_number": bank_account_number or "NA",
        "ifsc_code": ifsc_code or "NA",
        "PAN_number": pan_number,
        "bank_passbook_image": "NA",
        "pan_card_image": "NA",
        "salary" : salary,
        "date_of_onboarding" : f"{date}",
        "referral_code" : referral_code,
        "bank_account_validation": "VALID",
        "pan_card_validation": "VALID",
        "cashfree_vendor_add_status": "VALID",
        "bank_account_name_cashfree": worker_name,
        "pan_card_name_cashfree": worker_name, 
    }


    # Setup Google Sheets credentials
    client = get_client()
    team_emails = ['utkarsh@sampatticard.in', 'nusrathmuskan962@gmail.com', 'vrashali@sampatticard.in', 'om@sampatticard.in', 'nusrath@sampatticard.in']

    try:
        spreadsheet = client.open(sheet_title)
        sheet = spreadsheet.sheet1
        print("Sheet exists. Checking headers...")

        existing_headers = sheet.row_values(1)

        if existing_headers == all_columns:
            # Exact match: append new row
            row = [input_data.get(col, "") for col in all_columns]
            sheet.append_row(row)
            print("Exact column match. Row appended.")
        else:
            print("Column mismatch. Adjusting headers and restoring data...")

            # Fetch existing data
            all_data = sheet.get_all_values()
            existing_data = all_data[1:]  # Exclude headers

            # Map old column positions
            old_columns = existing_headers
            old_data_dicts = []
            for row in existing_data:
                data_dict = {col: row[i] if i < len(row) else "" for i, col in enumerate(old_columns)}
                old_data_dicts.append(data_dict)

            # Backup old rows into new structure
            padded_data = []
            for data_dict in old_data_dicts:
                padded_row = [data_dict.get(col, "") for col in all_columns]
                padded_data.append(padded_row)

            # Add the new row too
            new_row = [input_data.get(col, "") for col in all_columns]
            padded_data.append(new_row)

            # Clear and rewrite everything
            sheet.clear()
            sheet.update([all_columns] + padded_data)

            print("Headers updated. Previous and new data restored.")
            

    except gspread.SpreadsheetNotFound:
        print("Sheet not found. Creating new sheet...")
        spreadsheet = client.create(sheet_title)
        sheet = spreadsheet.sheet1
        sheet.update([all_columns])
        row = [input_data.get(col, "") for col in all_columns]
        sheet.append_row(row)
        for email in team_emails:
            spreadsheet.share(email, perm_type='user', role='writer')
        print("Sheet created and first row added.")

    print(f"Sheet URL: {spreadsheet.url}")

    #run_tasks_till_add_vendor()

    return spreadsheet.url
    