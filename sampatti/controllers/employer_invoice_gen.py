import os
from fastapi import HTTPException
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .. import models
from .cashfree_api import fetch_bank_ref
from .utility_functions import current_year, current_date, current_month, previous_month


def employer_invoice_generation(employerNumber, workerNumber, employerId, workerId, salary, cashAdvance, bonus, repayment, attendance, order_amount, db:Session) :

    ps_month = previous_month()
    month  = ""
    year = ""

    day_only = current_date().day
    if(abs(31-day_only) >= abs(1-day_only)):
        month = ps_month
        if month == "December":
            year = current_year() - 1

        else:
            year = current_year()

    else:
        month = current_month()
        year = current_year()

    static_dir = os.path.join(os.getcwd(), 'invoices')
    pdf_path = os.path.join(static_dir, f"{employerId}_INV_{workerId}_{month}_{year}.pdf")

    if not os.path.exists('invoices'):
        os.makedirs('invoices')
    w, h = A4
    c = canvas.Canvas(pdf_path, pagesize=A4)
    
    flat_logo = os.path.join(os.getcwd(), 'logos/flat_logo.jpg')
    circular_logo = os.path.join(os.getcwd(), 'logos/circular_logo.png')

    c.setFont("Helvetica-Bold", 18)

    c.setFillColorRGB(0.078, 0.33, 0.45)
    c.drawImage(flat_logo, w-120, h-55, width=100, height=45)
    text = "Propublica Finance and Investment Services Pvt. Ltd."
    size = len(text)
    c.drawString(w/2 - size*4.5, h-80, text=text)

    x = 30
    y = h - 110

    c.setFont("Helvetica", 14)

    cin = "CIN : 20369785412547852"
    udyam = "Udyam Registration Number : UDYAM-5689-120356"

    c.drawString(w/2 - size*3, y, cin)
    y -= 20
    c.drawString(w/2 - size*3, y, udyam)

    y -= 40
    c.setFont("Helvetica-Bold", 14)
    size = len("Salary Payment Receipt")
    c.drawString(w/2-size*5, y, "Salary Payment Receipt") 

    c.setFont("Times-Roman", 10)

    y -= 50
    c.drawString(x, y, f"Employer Id : EMP-{employerId}")

    y -= 20
    c.drawString(x, y, f"Employer Phone Number : {employerNumber}")

    receipt_data = []
    receipt_data.append(["Worker Name", "Worker Number", "Reference", "Salary", "Cash Advance", "Repayment", "Bonus"])

    rows = 0

    transaction = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employerNumber).filter(models.worker_employer.c.worker_number == workerNumber).first()
    
    ct = 1
    order_id = transaction.order_id
    bank_ref_no = fetch_bank_ref(order_id=order_id)
    print(f"the utr no is :  {bank_ref_no}")
    workerName = transaction.worker_name

    single_row = [f"{workerName}", f"{workerNumber}", bank_ref_no, salary, cashAdvance, repayment, bonus]
    receipt_data.append(single_row)
    rows += 1
    ct += 1

    receipt_style = TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.Color(0.078, 0.33, 0.45)),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])

    y = y - rows*25 - 70
    receipt_table = Table(receipt_data)
    receipt_table.setStyle(receipt_style)
    receipt_table.wrapOn(c, 0, 0)
    receipt_table.drawOn(c, x, y)

    c.setFont("Helvetica-Bold", 10)
    
    total_salary = f"Total Amount Paid : {order_amount}"
    y -= 25 
    c.drawString(x,y,text=total_salary)

    attending = f"Attendance of {month} {year} : {attendance}"
    y -= 25
    c.drawString(x,y,text=attending)

    issued = f"Salary Payment Receipt issued on : {current_date()} for the month of {month} {year}"
    y -= 25
    c.drawString(x, y, text=issued)

    c.setFont("Helvetica-Bold", 10)
    y -= 30
          
    note = """NOTE : This is a digitally issued salary payment receipt and does not require attestation.
The money has been debited in the corresponding bank account."""
    lines = note.split('\n')
    c.setFont("Helvetica", 8)

    y = 110
    for line in lines:
        c.drawString(x+20, y, line)
        y -= 10

    y -= 10

    c.drawImage(circular_logo, 15, y-20 , 30, 30)

    declaration = """Declaration : The transaction trail is verified with an employment agreement between the employer and the 
employee basis which the salary payment receipt is issued. Propublica Finance and Investment Services Pvt. Ltd. is not the 
employer for the worker for whom salary payment receipt is generated."""

    lines = declaration.split('\n')
    for line in lines:
        c.drawString(x+20, y, line)
        y -= 10


    c.setFont("Helvetica", 10)
    c.rect(0,0,w,30, fill=True)
    c.setFillColorRGB(1,1,1)
    c.drawString(x+20, 12.5, "Phone : +91 86603 52558")
    c.drawString(x+ 170, 12.5, "website : www.sampatticard.in          support : vrashali@sampatticard.in")

    c.showPage()
    c.save()

    print("invoice generated")