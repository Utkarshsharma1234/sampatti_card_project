import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
