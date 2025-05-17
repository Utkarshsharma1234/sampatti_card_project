import time
from sampatti.database import get_db_session
from sampatti.controllers.talk_to_agent_excel_file import (
    fetch_pan_bank_details_from_image,
    bank_account_validation_status,
    add_vendor_to_cashfree,
    process_vendor_status,
    create_relations_in_db
)


def run_task_with_delay():
    print("Running: fetch_pan_bank_details_from_image")
    fetch_pan_bank_details_from_image()
    time.sleep(10)  # wait 1 hour

    print("Running: bank_account_validation_status")
    bank_account_validation_status()
    time.sleep(10)

    print("Running: add_vendor_to_cashfree")
    add_vendor_to_cashfree()
    time.sleep(300)

    with get_db_session() as db:
        print("Running: process_vendor_status")
        process_vendor_status(db)
    time.sleep(10)

    with get_db_session() as db:
        print("Running: create_relations_in_db")
        create_relations_in_db(db)

if __name__ == "__main__":
    run_task_with_delay()
