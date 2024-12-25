import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Employer, Domestic_Worker, SalaryDetails, worker_employer
from sqlalchemy import Integer, String, func, desc, cast


def draw_header(c, w, h, employer_id, employer_phone, total_workers):
    
    flat_logo = os.path.join(os.getcwd(), 'logos/flat_logo.jpg')
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
    circular_logo = os.path.join(os.getcwd(), 'logos/circular_logo.png')
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

def generate_salary_records_all_worker(employerNumber: int):
    # Create output directory
    static_dir = os.path.join(os.getcwd(), 'Salary Report')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    pdf_path = os.path.join(static_dir, f"salary_record_{employerNumber}.pdf")
    
    try:
        db = SessionLocal()
        
        # Query employer
        employer = db.query(Employer).filter(Employer.employerNumber == employerNumber).first()
        
        if not employer:
            print(f"No employer found with employer number: {employerNumber}")
            return
            
        # Query workers with their onboarding dates
        workers_query = (
            db.query(
                Domestic_Worker,
                worker_employer.c.date_of_onboarding
            )
            .join(worker_employer)
            .filter(worker_employer.c.employer_number == employerNumber)
        )
        
        workers = []
        for worker, onboarding_date in workers_query:
            workers.append({
                'worker_id': worker.id,
                'name': worker.name,
                'email': worker.email,
                'worker_number': worker.workerNumber,  # Store as worker_number
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
        
        current_y = draw_header(c, w, h, f"{employer.id}", employerNumber, total_workers)
        
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
        
        i = 1
        for worker_index, worker in enumerate(workers):
            # Query salary details using worker_number
            salary_records = (
                db.query(
                    (func.rtrim(SalaryDetails.month) + ' ' + func.cast(SalaryDetails.year, String)).label('Month'),
                    SalaryDetails.salary,
                    SalaryDetails.cashAdvance.label('Month_Cash_Advance'),
                    SalaryDetails.repayment.label('Month_Repayment'),
                    SalaryDetails.bonus.label('Month_bonus'),
                    SalaryDetails.attendance.label('Month_attendance'),
                    SalaryDetails.totalAmount.label('Salary_Paid')
                )
                .filter(
                    SalaryDetails.worker_id == worker['worker_id'],  # Use worker_number
                    SalaryDetails.employerNumber == employerNumber
                )
                .order_by(SalaryDetails.year.desc(), cast(SalaryDetails.month, Integer).desc()) 
                .all()
            )
            
            # Prepare table data
            table_data = [
                ["Sr. No.", "Month", "Month Salary", "Month Bonus",
                 "Cash Advance", "Month Repayment", "Month Attendance", "Salary Paid"]
            ]

            total_bonus = 0
            total_cash_advance = 0
            total_repayment = 0
            total_salary_paid = 0

            if salary_records:
                for record_index, record in enumerate(salary_records, 1):
                    Month, Month_salary, Month_Cash_Advance, Month_Repayment, Month_bonus, Month_attendance, Salary_Paid = record
                    
                    # Convert None values to 0
                    Month_bonus = Month_bonus or 0
                    Month_Cash_Advance = Month_Cash_Advance or 0
                    Month_Repayment = Month_Repayment or 0
                    Month_attendance = Month_attendance or 0
                    Salary_Paid = Salary_Paid or 0
                    Month_salary = Month_salary or 0
                    
                    table_data.append([
                        record_index, 
                        Month.strip() if Month else "",  # Handle None Month
                        Month_salary, 
                        Month_bonus, 
                        Month_Cash_Advance, 
                        Month_Repayment,
                        Month_attendance,
                        Salary_Paid
                    ])
                    
                    total_bonus += Month_bonus
                    total_cash_advance += Month_Cash_Advance
                    total_repayment += Month_Repayment
                    total_salary_paid += Salary_Paid

            # Add total row
            table_data.append([
                "Total", "", "", 
                total_bonus, 
                total_cash_advance, 
                total_repayment, 
                "",  # No total for attendance
                total_salary_paid
            ])

            col_widths = [50, 70, 70, 70, 70, 70, 70, 70]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle(table_style))
            
            table.wrapOn(c, w-60, h)
            table_height = table._height
            
            if current_y - table_height < 50:
                c.showPage()
                current_y = h - 50
                if worker_index == 1:
                    current_y = draw_header(c, w, h, f"{employer.id}", employerNumber, total_workers)
                    
            worker_details = f"{i}. Name of the worker: {worker['name']}   ||  Worker ID: {worker['worker_id']}    ||    Date of onboarding: {worker['date_of_onboarding']}"
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)
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
        raise  # Add this to see the full error traceback
    finally:
        db.close()


def generate_salary_records(employerNumber: int, workerName: str):
    # Create output directory
    static_dir = os.path.join(os.getcwd(), 'Salary Report')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    pdf_path = os.path.join(static_dir, f"salary_record_of_{workerName}.pdf")
    
    try:
        db = SessionLocal()
        
        # Query employer
        employer = db.query(Employer).filter(Employer.employerNumber == employerNumber).first()
        
        if not employer:
            print(f"No employer found with employer number: {employerNumber}")
            return
            
        # Query specific worker with their onboarding date
        worker_query = (
            db.query(
                Domestic_Worker,
                worker_employer.c.date_of_onboarding
            )
            .join(worker_employer)
            .filter(
                worker_employer.c.employer_number == employerNumber,
                Domestic_Worker.name == workerName
            )
            .first()
        )
        
        if not worker_query:
            print(f"No worker found with name {workerName} for employer number {employerNumber}")
            return
            
        worker, onboarding_date = worker_query
        worker_info = {
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
        }
        
        w, h = A4
        c = canvas.Canvas(pdf_path, pagesize=A4)
        
        current_y = draw_header(c, w, h, f"{employer.id}", employerNumber, 1)  # total_workers is 1 since we're generating for specific worker
        
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
        
        # Query salary details for the specific worker
        salary_records = (
            db.query(
                (func.rtrim(SalaryDetails.month) + ' ' + func.cast(SalaryDetails.year, String)).label('Month'),
                SalaryDetails.salary,
                SalaryDetails.cashAdvance.label('Month_Cash_Advance'),
                SalaryDetails.repayment.label('Month_Repayment'),
                SalaryDetails.bonus.label('Month_bonus'),
                SalaryDetails.attendance.label('Month_attendance'),
                SalaryDetails.totalAmount.label('Salary_Paid')
            )
            .filter(
                SalaryDetails.worker_id == worker.id,
                SalaryDetails.employerNumber == employerNumber
            )
            .order_by(SalaryDetails.year.desc(), cast(SalaryDetails.month, Integer).desc()) 
            .all()
        )
        
        # Prepare table data
        table_data = [
            ["Sr. No.", "Month", "Month Salary", "Month Bonus",
             "Cash Advance", "Month Repayment", "Month Attendance", "Salary Paid"]
        ]

        total_bonus = 0
        total_cash_advance = 0
        total_repayment = 0
        total_salary_paid = 0

        if salary_records:
            for record_index, record in enumerate(salary_records, 1):
                Month, Month_salary, Month_Cash_Advance, Month_Repayment, Month_bonus, Month_attendance, Salary_Paid = record
                
                # Convert None values to 0
                Month_bonus = Month_bonus or 0
                Month_Cash_Advance = Month_Cash_Advance or 0
                Month_Repayment = Month_Repayment or 0
                Month_attendance = Month_attendance or 0
                Salary_Paid = Salary_Paid or 0
                Month_salary = Month_salary or 0
                
                table_data.append([
                    record_index, 
                    Month.strip() if Month else "",
                    Month_salary, 
                    Month_bonus, 
                    Month_Cash_Advance, 
                    Month_Repayment,
                    Month_attendance,
                    Salary_Paid
                ])
                
                total_bonus += Month_bonus
                total_cash_advance += Month_Cash_Advance
                total_repayment += Month_Repayment
                total_salary_paid += Salary_Paid

        # Add total row
        table_data.append([
            "Total", "", "", 
            total_bonus, 
            total_cash_advance, 
            total_repayment, 
            "",  # No total for attendance
            total_salary_paid
        ])

        col_widths = [50, 70, 70, 70, 70, 70, 70, 70]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle(table_style))
        
        table.wrapOn(c, w-60, h)
        table_height = table._height
        
        worker_details = f"Name of the worker: {worker_info['name']}   ||  Worker ID: {worker_info['worker_id']}    ||    Date of onboarding: {worker_info['date_of_onboarding']}"
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(30, current_y, worker_details)
        current_y -= 10
        
        table.drawOn(c, 30, current_y - table_height)
        current_y -= table_height + 20
        
        draw_footer(c, w, h)
        c.save()
        
        return pdf_path
        
    except Exception as e:
        print(f"An error occurred: {e}")
        raise
    finally:
        db.close()