import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Employer, Domestic_Worker, SalaryDetails, worker_employer
from sqlalchemy import Integer, String, func, desc

def draw_header(c, w, h, employer_id, employer_phone, total_workers):
    
    flat_logo = os.path.join(os.getcwd(), 'logos/flat_logo.jpg')
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.078, 0.33, 0.45)
    c.drawImage(flat_logo, w-110, h-45, width=100, height=45)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w/2, h-60, "Propublica Finance and Investment Services Pvt. Ltd.")
    
    c.setFont("Helvetica", 10)
    c.drawCentredString(w/2, h-75, "CIN : 20369785412547852")
    c.drawCentredString(w/2, h-90, "Udyam Registration Number : UDYAM-5689-120356")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w/2, h-110, "Salary Payment Report")
    
    c.setFont("Helvetica", 10)
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
    
    y=115
    c.setFont("Helvetica", 10)
    issued = f"Salary Slip issued on : {date} for the month of {month} {year}"
    x = 30
    y -= 25
    c.drawString(x, y, issued)
    x = 30
    c.setFont("Helvetica", 8)
    
    footer_y = 90
    
    note = """NOTE: This is a digitally issued salary record of your previous Months."""

    footer_y -= 20
    lines = note.split('\n')
    for line in lines:
        c.drawString(x+30, footer_y, line)
        footer_y -= 15

    declaration = """Declaration: The transaction trail is verified with an employment agreement between the employer and the employee basis which the 
salary record is issued. Propublica Finance and Investment Services Pvt. Ltd. is not the employer for the worker for whom salary record is generated."""
    
    # Draw logos and text
    circular_logo = os.path.join(os.getcwd(), 'logos/circular_logo.png')
    c.drawImage(circular_logo, 15, footer_y-10, 30, 30)
    
    lines = declaration.split('\n')
    for line in lines:
        c.drawString(x+30, footer_y, line)
        footer_y -= 10
    
    c.setFont("Helvetica", 10)
    c.rect(0, 0, w, 30, fill=True)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(x+20, 12.5, "Phone : +91 86603 52558")
    c.drawString(x+170, 12.5, "website : www.sampatticard.in          support : vrashali@sampatticard.in")

def generate_salary_records_all_worker(employerNumber: int, db: Session):
    # Create output directory
    static_dir = os.path.join(os.getcwd(), 'Salary Report')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    pdf_path = os.path.join(static_dir, f"salary_record_{employerNumber}.pdf")
    
    try:
        # Query employer
        employer = db.query(Employer).filter(Employer.employerNumber == employerNumber).first()
        print("Employer: ", employer)
        print("Employer ID: ", employer.id)
        if not employer:
            print(f"No employer found with id: {employer.id}")
            return
        
        # Query all workers linked to employer
        workers_query = (
            db.query(
                Domestic_Worker,
                worker_employer.c.date_of_onboarding
            )
            .join(worker_employer, worker_employer.c.worker_id == Domestic_Worker.id)
            .filter(worker_employer.c.employer_id == employer.id)
            .all()
        )
        
        print("Workers Query Result: ", workers_query)
        print("Workers Query Result: ", len(workers_query))
        
        workers = []
        for worker, onboarding_date in workers_query:
            workers.append({
                'worker_id': worker.id,
                'name': worker.name,
                'worker_number': worker.workerNumber,
                'date_of_onboarding': onboarding_date
            })
        
        total_workers = len(workers)
        
        w, h = A4
        c = canvas.Canvas(pdf_path, pagesize=A4)
        
        current_y = draw_header(c, w, h, f"{employer.id}", employer.employerNumber, total_workers)
        
        table_style = [
            ('TEXTCOLOR', (0,0), (-1,-1), colors.Color(0.078, 0.33, 0.45)),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),    # HEADER bold
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),  # TOTAL row bold
            ('BACKGROUND', (0,0), (-1,0), colors.white),
            ('TEXTCOLOR', (0,0), (-1,0), colors.Color(0.078, 0.33, 0.45)),
            ('GRID', (0,0), (-1,-1), 1, colors.Color(0.078, 0.33, 0.45))
        ]
        
        i = 1
        for worker_index, worker in enumerate(workers):
            # Query salary details by worker_id and employer_id
            salary_records = (
                db.query(
                    (func.rtrim(SalaryDetails.month) + ' ' + func.cast(SalaryDetails.year, String)).label('Month'),
                    SalaryDetails.salary,
                    SalaryDetails.cashAdvance.label('Month_Cash_Advance'),
                    SalaryDetails.repayment.label('Month_Repayment'),
                    SalaryDetails.bonus.label('Month_bonus'),
                    SalaryDetails.deduction.label('Month_Deduction'),
                    SalaryDetails.attendance.label('Month_attendance'),
                    SalaryDetails.totalAmount.label('Salary_Paid')
                )
                .filter(
                    SalaryDetails.worker_id == worker['worker_id'],
                    SalaryDetails.employer_id == employer.id
                ).all()
            )
            
            print("Salary Records: ", salary_records)

            # Sort salary records by Month (first element of tuple)
            try:
                salary_records = sorted(
                    salary_records,
                    key=lambda x: datetime.strptime(x[0], "%B %Y"),
                    reverse=True
            )
            except ValueError as e:
                print(f"Error parsing dates in salary records: {e}")
                # Handle malformed date formats if necessary
                salary_records = salary_records  # Fallback to unsorted records

            print("Sorted Salary Records: ", salary_records)
            
            
            table_data = [
                ["Sr. No.", "Month", "Salary", "Bonus", "Deduction",
                 "Advance", "Repayment", "Attendance", "Salary Paid"]
            ]

            total_bonus = 0
            total_cash_advance = 0
            total_repayment = 0
            total_salary_paid = 0
            total_deductions = 0
            
            if salary_records:
                for record_index, record in enumerate(salary_records, 1):
                    Month, Month_salary, Month_Cash_Advance, Month_Repayment, Month_bonus, Month_Deduction, Month_attendance, Salary_Paid = record
                    
                    # Null handling
                    Month_bonus = Month_bonus or 0
                    Month_Deduction = Month_Deduction or 0
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
                        Month_Deduction,
                        Month_Cash_Advance, 
                        Month_Repayment,
                        Month_attendance,
                        Salary_Paid
                    ])
                    
                    total_bonus += Month_bonus
                    total_deductions += Month_Deduction
                    total_cash_advance += Month_Cash_Advance
                    total_repayment += Month_Repayment
                    total_salary_paid += Salary_Paid
            
            # Add total row
            table_data.append([
                "Total", "", "", 
                total_bonus, 
                total_deductions,
                total_cash_advance, 
                total_repayment, 
                "", 
                total_salary_paid
            ])
            
            col_widths = [40, 80, 60,60, 60, 60, 60, 60, 60]
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle(table_style))
            
            table.wrapOn(c, w-60, h)
            table_height = table._height
            
            if current_y - table_height < 50:
                c.showPage()
                current_y = h - 50
                if worker_index == 1:
                    current_y = draw_header(c, w, h, f"{employer.id}", employer.employerNumber, total_workers)
            
            worker_details = f"{i}. Name of the worker: {worker['name']} || Worker Number: {worker['worker_number']} || Date of onboarding: {worker['date_of_onboarding']}"
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(0.078, 0.33, 0.45)
            
            c.drawString(30, current_y, worker_details)
            current_y -= 10
            
            table.drawOn(c, 30, current_y - table_height)
            current_y -= table_height + 20
            i += 1
        
        if current_y < h - 50:
            draw_footer(c, w, h)
        
        c.save()
        
        print(f"Salary report generated: {pdf_path}")
        return pdf_path
    
    except Exception as e:
        print(f"An error occurred: {e}")



def generate_salary_record(employerNumber: int, workerName: str, db: Session):

    output_dir = os.path.join(os.getcwd(), 'Salary Report')
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"salary_record_{employerNumber}_{workerName}.pdf")

    try:
        # Fetch employer
        employer = db.query(Employer).filter(Employer.employerNumber == employerNumber).first()

        if not employer:
            print(f"No employer found with employer number: {employerNumber}")
            return None

        # Fetch worker
        worker = db.query(worker_employer).where(worker_employer.c.employer_number == employerNumber, worker_employer.c.worker_name == workerName).first()
        print("Worker: ", worker)
        
        if not worker:
            print(f"No worker found with name: {workerName}")
            return None

        # Fetch salary records for this worker under this employer
        salary_records = (
                db.query(
                    (func.rtrim(SalaryDetails.month) + ' ' + func.cast(SalaryDetails.year, String)).label('Month'),
                    SalaryDetails.salary,
                    SalaryDetails.cashAdvance.label('Month_Cash_Advance'),
                    SalaryDetails.repayment.label('Month_Repayment'),
                    SalaryDetails.bonus.label('Month_bonus'),
                    SalaryDetails.deduction.label('Month_Deduction'),
                    SalaryDetails.attendance.label('Month_attendance'),
                    SalaryDetails.totalAmount.label('Salary_Paid')
                )
                .filter(
                    SalaryDetails.worker_id == worker.worker_id,
                    SalaryDetails.employerNumber == employerNumber
                ).all()
            )
            
        print("Salary Records: ", salary_records)
        #salary_records.sort(key=lambda r: (r.year, MONTH_ORDER.get(r.month.strip(), 13)), reverse=True)
        #salary_records = sorted(salary_records, key=lambda x: datetime.strptime(x['month'], "%B %Y"), reverse=True)

        # Sort salary records by Month (first element of tuple)
        try:
            salary_records = sorted(
                salary_records,
                key=lambda x: datetime.strptime(x[0], "%B %Y"),
                reverse=True
            )
        except ValueError as e:
            print(f"Error parsing dates in salary records: {e}")
            # Handle malformed date formats if necessary
            salary_records = salary_records  # Fallback to unsorted records
        
        if not salary_records:
            print(f"No salary records found for worker '{workerName}' under employer number: {employerNumber}")
            return None

        w, h = A4
        c = canvas.Canvas(pdf_path, pagesize=A4)
        current_y = draw_header(c, w, h, employer.id, employer.employerNumber, 1)

        table_style = [
            ('TEXTCOLOR', (0,0), (-1,-1), colors.Color(0.078, 0.33, 0.45)),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),    # HEADER bold
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),  # TOTAL row bold
            ('BACKGROUND', (0,0), (-1,0), colors.white),
            ('TEXTCOLOR', (0,0), (-1,0), colors.Color(0.078, 0.33, 0.45)),
            ('GRID', (0,0), (-1,-1), 1, colors.Color(0.078, 0.33, 0.45))
        ]

        table_data = [
                ["Sr. No.", "Month", "Salary", "Bonus", "Deduction",
                 "Advance", "Repayment", "Attendance", "Salary Paid"]
            ]

        total_bonus = 0
        total_cash_advance = 0
        total_repayment = 0
        total_salary_paid = 0
        total_deductions = 0

        for idx, record in enumerate(salary_records, start=1):
            Month, Month_salary, Month_Cash_Advance, Month_Repayment, Month_bonus, Month_Deduction, Month_attendance, Salary_Paid = record

            Month_bonus = Month_bonus or 0
            Month_Deduction = Month_Deduction or 0
            Month_Cash_Advance = Month_Cash_Advance or 0
            Month_Repayment = Month_Repayment or 0
            Month_attendance = Month_attendance or 0
            Salary_Paid = Salary_Paid or 0
            Month_salary = Month_salary or 0

            table_data.append([
                idx, Month.strip() if Month else "", Month_salary, Month_bonus, Month_Deduction,
                Month_Cash_Advance, Month_Repayment, Month_attendance, Salary_Paid
            ])

            total_bonus += Month_bonus
            total_deductions += Month_Deduction
            total_cash_advance += Month_Cash_Advance
            total_repayment += Month_Repayment
            total_salary_paid += Salary_Paid

        table_data.append(["Total", "", "", total_bonus, total_deductions, total_cash_advance, total_repayment, "", total_salary_paid])

        col_widths = [40, 80, 60, 60, 60, 60, 60, 60, 60]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(table_style)

        table.wrapOn(c, w - 60, h)
        table_height = table._height

        if current_y - table_height < 100:
            c.showPage()
            current_y = draw_header(c, w, h, employer.id, employer.employerNumber, workerName, len(salary_records))

        worker_details = f"Worker Name: {worker.worker_name} || Worker Number: {worker.worker_number} || Date of Onboarding: {worker.date_of_onboarding}"
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0.078, 0.33, 0.45)
        c.drawString(30, current_y, worker_details)
        current_y -= 10
        
        table.drawOn(c, 30, current_y - table_height)
        current_y -= table_height + 20

        draw_footer(c, w, h)
        c.save()

        print(f"Salary record generated at: {pdf_path}")
        return pdf_path

    except Exception as e:
        print(f"An error occurred: {e}")
        return None
