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


def employer_invoice_generation(employerNumber, workerNumber, employerId, workerId, db:Session) :

    current_date = datetime.now().date()
    first_day_of_current_month = datetime.now().replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    previous_month = last_day_of_previous_month.strftime("%B")
    current_year = datetime.now().year

    static_dir = os.path.join(os.getcwd(), 'invoices')
    pdf_path = os.path.join(static_dir, f"{employerId}_INV_{workerId}_{previous_month}_{current_year}.pdf")

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
    size = len("Employer Invoice")
    c.drawString(w/2-size*5, y, "Employer Invoice") 

    c.setFont("Times-Roman", 10)

    y -= 50
    c.drawString(x, y, f"Employer Id : EMP-{employerId}")

    y -= 20
    c.drawString(x, y, f"Employer Phone Number : {employerNumber}")

    receipt_data = []
    receipt_data.append(["Sr. No.", "Worker Name", "Worker Number", "Reference", "Salary"])

    rows = 0

    transaction = db.query(models.worker_employer).filter(models.worker_employer.c.employer_number == employerNumber).filter(models.worker_employer.c.worker_number == workerNumber).first()
    
    ct = 1
    order_id = transaction.order_id
    bank_ref_no = fetch_bank_ref(order_id=order_id)
    print("the utr no is : " + bank_ref_no)
    workerName = transaction.worker_name

    single_row = [ct, f"{workerName}", f"{workerNumber}", bank_ref_no, transaction.salary_amount]
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

    c.setFont("Times-Roman", 10)
    issued = f"Payment Invoice issued on : {current_date} for the month of {previous_month} {current_year}"
    y -= 25
    c.drawString(x, y, text=issued)

    c.setFont("Helvetica-Bold", 10)
    y -= 30
          
    note = """NOTE : This is a digitally issued payment invoice and does not require attestation.
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
employee basis which the payment invoice is issued. Propublica Finance and Investment Services Pvt. Ltd. is not the 
employer for the worker for whom salary record is generated."""

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