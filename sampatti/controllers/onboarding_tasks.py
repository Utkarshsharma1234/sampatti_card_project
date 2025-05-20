from ..database import get_db_session
from .talk_to_agent_excel_file  import (
    fetch_pan_bank_details_from_image,
    bank_account_validation_status,
    add_vendor_to_cashfree,
    process_vendor_status,
    create_relations_in_db
)


def run_tasks_till_add_vendor():
    print("Running: fetch_pan_bank_details_from_image")
    fetch_pan_bank_details_from_image()

    print("Running: bank_account_validation_status")
    bank_account_validation_status()

    print("Running: add_vendor_to_cashfree")
    add_vendor_to_cashfree()


def run_tasks_after_vendor_addition():

    with get_db_session() as db:
        print("Running: process_vendor_status")
        process_vendor_status(db)

    with get_db_session() as db:
        print("Running: create_relations_in_db")
        create_relations_in_db(db)