import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import Employer, Domestic_Worker, SalaryDetails, worker_employer
from sqlalchemy import func, String

def draw_header(c, w, h, employer_id, employer_phone, total_workers):
    
    flat_logo = os.path.join(os.getcwd(), 'flat_logo.jpg')
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.078, 0.33, 0.45)
    c.drawImage(flat_logo, w-120, h-40, width=120, height=45)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w/2, h-60, "Propublica Finance and Investment Services Pvt. Ltd.")
    
    c.setFont("Helvetica", 10)
    c.drawCentredString(w/2, h-75, "CIN : 20369785412547852")
    c.drawCentredString(w/2, h-90, "Udyam Registration Number : UDYAM-5689-120356")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w/2, h-110, "Salary Payment Report")
    
    c.setFont("Times-Roman", 10)
    y = h - 140
    c.drawString(30, y, f"Employer Id : {employer_id}")
    y -= 20
    c.drawString(30, y, f"Employer Phone Number : {employer_phone}")
    y -= 20
    c.drawString(30, y, f"Total Workers : {total_workers}")
    
    return y - 30


def draw_footer(c, w, h):
    
    date = datetime.now().strftime("%d-%m-%Y")
    month = datetime.now().strftime("%B")
    year = datetime.now().strftime("%Y")
    
    y=130
    c.setFont("Helvetica-Bold", 8)
    issued = f"Salary Slip issued on : {date} for the month of {month} {year}"
    x = 30
    y -= 25
    c.drawString(x, y, issued)
    x = 30
    c.setFont("Helvetica", 8)
    
    footer_y = 100
    
    note = """NOTE: This is a digitally issued salary record of your previous Months."""

    footer_y -= 10
    lines = note.split('\n')
    for line in lines:
        c.drawString(x+20, footer_y, line)
        footer_y -= 15

    declaration = """Declaration: The transaction trail is verified with an employment agreement between the 
employer and the employee basis which the salary record is issued. Propublica Finance and Investment 
Services Pvt. Ltd. is not the employer for the worker for whom salary record is generated."""
    
    # Draw logos and text
    circular_logo = os.path.join(os.getcwd(), 'circular_logo.png')
    c.drawImage(circular_logo, 15, footer_y-20, 30, 30)
    
    lines = declaration.split('\n')
    for line in lines:
        c.drawString(x+20, footer_y, line)
        footer_y -= 10
    
    c.setFont("Helvetica", 10)
    c.rect(0, 0, w, 30, fill=True)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(x+20, 12.5, "Phone : +91 86603 52558")
    c.drawString(x+170, 12.5, "website : www.sampatticard.in          support : vrashali@sampatticard.in")

def generate_salary_records(employerNumber: int, n: int):
    # Create output directory
    static_dir = os.path.join(os.getcwd(), 'delete_folder')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    pdf_path = os.path.join(static_dir, f"salary_record_{n}_months.pdf")
    
    try:
        # Replace SQLite connection with SQLAlchemy session
        db = SessionLocal()
        
        # Replace employer query
        employer = db.query(Employer).filter(Employer.employerNumber == employerNumber).first()
        
        if not employer:
            print(f"No employer found with employer number: {employerNumber}")
            return
        
        Id = employer.id

        # Replace workers query
        workers_query = (
            db.query(Domestic_Worker, worker_employer.c.date_of_onboarding)
            .join(worker_employer)
            .filter(worker_employer.c.employer_number == employerNumber)
            .all()
        )

        workers = []
        for worker, onboarding_date in workers_query:
            workers.append({
                'worker_id': worker.id,
                'name': worker.name,
                'email': worker.email,
                'worker_number': worker.workerNumber,
                'pan_number': worker.panNumber,
                'upi_id': worker.upi_id,
                'account_number': worker.accountNumber,
                'ifsc': worker.ifsc,
                'vendor_id': worker.vendorId,
                'date_of_onboarding': onboarding_date
            })

        total_workers = len(workers)
        
        w, h = A4
        c = canvas.Canvas(pdf_path, pagesize=A4)
        
        current_y = draw_header(c, w, h, f"{Id}", employerNumber, total_workers)
        
        table_style = [
            ('TEXTCOLOR', (0,0), (-1,-1), colors.Color(0.078, 0.33, 0.45)),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('FONTNAME', (0, -1), (0, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]
        i=1
        for worker_index, worker in enumerate(workers):
            
            # Replace salary query
            salary_records = (
                db.query(
                    (SalaryDetails.month + ' ' + func.cast(SalaryDetails.year, String)).label('Month'),
                    worker_employer.c.salary_amount.label('Monthly_Salary'),
                    SalaryDetails.cashAdvance,
                    SalaryDetails.repayment,
                    SalaryDetails.bonus,
                    SalaryDetails.attendance,
                    SalaryDetails.salary.label('Salary_Paid')
                )
                .join(
                    worker_employer,
                    (worker_employer.c.worker_number == SalaryDetails.worker_id) &
                    (worker_employer.c.employer_number == SalaryDetails.employerNumber)
                )
                .filter(
                    SalaryDetails.worker_id == worker['worker_number'],
                    SalaryDetails.employerNumber == employerNumber
                )
                .order_by(SalaryDetails.year.desc(), SalaryDetails.month.desc())
                .limit(n)
                .all()
            )

            # Prepare table data
            table_data = [
                ["Sr. No.", "Month", "Month Salary", "Cash Advance", "Repayment","Bonus", "Attendance", "Salary Paid"]
            ]

            for record_index, record in enumerate(salary_records, 1):
                Month, Monthly_Salary, Month_Cash_Advance, Month_Repayment, Month_bonus, Attendance, Salary_Paid = record
                table_data.append([
                    record_index, 
                    Month, 
                    Monthly_Salary,  # From worker_employer table
                    Month_Cash_Advance, 
                    Month_Repayment,
                    Month_bonus,
                    Attendance,
                    Salary_Paid      # From SalaryDetails table
                ])
                
            bonus_index = 5
            cash_advance_index = 3
            repayment_index = 4 
            salary_paid_index = 7
            total_bonus = 0
            total_cash_advance = 0
            total_repayment = 0
            total_salary_paid = 0

            for row in table_data[1:]:
                total_bonus += row[bonus_index]
                total_cash_advance += row[cash_advance_index]
                total_repayment += row[repayment_index]
                total_salary_paid += row[salary_paid_index]

            last_row = ["Total", "", "", total_cash_advance, total_repayment, total_bonus, "", total_salary_paid]
            
            table_data.append(last_row)

            table_style.append(('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'))

# table_data me worker_id ke hisab se sab record store kar dena 
            col_widths = [50, 70, 70, 70, 70, 70, 70, 70]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle(table_style))
            
            table.wrapOn(c, w-60, h)
            table_height = table._height
            if current_y - table_height < 50:
                c.showPage()
                current_y = h - 50
                if worker_index == 1:
                    current_y = draw_header(c, w, h, f"{Id}", employerNumber, total_workers)
#change date of onboarding for worker 
            worker_details = f"{i}. Name of the worker: {worker['name']}   ||  Worker ID: {worker['worker_id']}    ||    Date of onboarding: {worker['date_of_onboarding']}"
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0.078, 0.33, 0.45)
            c.drawString(30, current_y, worker_details)
            current_y -= 10
            
            
            table.drawOn(c, 30, current_y - table_height)
            current_y -= table_height + 20

            i += 1
        if current_y < h - 50:
            draw_footer(c, w, h)
        
        c.save()
        
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

