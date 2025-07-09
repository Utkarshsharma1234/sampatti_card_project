import os
from fastapi import HTTPException
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from textwrap import wrap
from sqlalchemy.orm import Session
from .. import models
from .cashfree_api import check_order_status, fetch_bank_ref
from .utility_functions import current_date, current_month, previous_month, current_year, amount_to_words


def generate_salary_slip(workerNumber, db:Session) :

    worker = db.query(models.Domestic_Worker).filter(models.Domestic_Worker.workerNumber == workerNumber).first()
    
    year = current_year()
    month = current_month()
    date = current_date()

    if month == "January":
        month = "December"
        year -= 1

    else:
        month = previous_month()
        
    if not worker :
        raise HTTPException(status_code=404, detail="The domestic worker is not registered. You must register the worker first.")
    
    static_dir = os.path.join(os.getcwd(), 'static')
    pdf_path = os.path.join(static_dir, f"{worker.id}_SS_{month}_{year}.pdf")

    if not os.path.exists('static'):
        os.makedirs('static')
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
    size = len("Salary Record")
    c.drawString(w/2-size*5, y, "Salary Record") 

    c.setFont("Times-Roman", 10)

    if worker.accountNumber is None or worker.accountNumber == "":
        worker.accountNumber = "NA"

    if worker.upi_id is None or worker.upi_id == "":
        worker.upi_id = "NA"

    if worker.ifsc is None or worker.ifsc == "":
        worker.ifsc = "NA"

        
    worker_data = [
        [f"Name of the Employee : {worker.name}", "PF Number : NA"],
        ["Nature of Work : Domestic Help", f"Account Number : {worker.accountNumber}"],
        ["Bank Name : NA", f"IFSC Code : {worker.ifsc}"],
        ["ESI Number : NA", f"UPI ID : {worker.upi_id}"]
    ]

    worker_style = TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.Color(0.078, 0.33, 0.45)),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 100),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica')
    ])


    worker_table = Table(worker_data)
    worker_table.setStyle(worker_style)
    m,n = worker_table.wrapOn(c,0,0)
    y -= 135
    worker_table.drawOn(c,x, y)

    receipt_data = []
    receipt_data.append(["Sr. No.", "Employer Code", "Mode", "Reference", "Salary", "Variable Pay", "Deductions"])

    rows = 0

    total_transactions = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == workerNumber).all()
    total_amount = 0
    
    ct = 1
    for transaction in total_transactions:
        order_id = transaction.order_id
        if order_id == "sample":
            continue
        order_info = check_order_status(order_id=order_id)
        status = order_info["order_status"]
        order_amount = order_info["order_amount"]
        salary = transaction.salary_amount
        if status == "PAID":

            bank_ref_no = fetch_bank_ref(order_id=order_id)
            employer_id = transaction.employer_id
            variablePay = 0
            deduction = 0

            if order_amount >= salary:
                variablePay = order_amount - salary
            else:
                deduction = salary - order_amount

            single_row = [ct, f"EMP-{employer_id}", "UPI", bank_ref_no, salary, variablePay, deduction]
            receipt_data.append(single_row)
            rows += 1
            ct += 1
            total_amount += order_amount

        else:
            continue

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
    issued = f"Salary Slip issued on : {date} for the month of {month} {year}"
    y -= 25
    c.drawString(x, y, text=issued)

    c.setFont("Helvetica-Bold", 10)
    y -= 30
    salary_in_words = amount_to_words(total_amount)
    c.drawString(x, y, f"Total amount Credited : INR {total_amount}/- Only")
    c.drawString(x, y-20, f"Amount in Words : {salary_in_words} Only")
          

    note = """NOTE : This is a digitally issued salary slip and does not require attestation.
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
employee basis which the salary slip is issued. Propublica Finance and Investment Services Pvt. Ltd. is not the 
employer for the worker for whom salary record is generated."""

    lines = declaration.split('\n')
    for line in lines:
        c.drawString(x+20, y, line)
        y -= 10


    c.setFont("Helvetica", 10)
    c.rect(0,0,w,30, fill=True)
    c.setFillColorRGB(1,1,1)
    c.drawString(x+20, 12.5, "Phone : +91 86603 52558")
    c.drawString(x+ 170, 12.5, "website : www.sampatticard.in          support : support@sampatticard.in")

    c.showPage()
    c.save()