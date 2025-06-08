import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from sqlalchemy.orm import Session
from .. import models
from .. import schemas
from datetime import datetime

def create_employment_record_pdf(request: schemas.Contract, db:Session):
  

    current_time = datetime.now()
    field = db.query(models.worker_employer).filter(models.worker_employer.c.worker_number == request.workerNumber , models.worker_employer.c.employer_number == request.employerNumber).first()
    
    # print(field.worker_number)
    static_dir = os.path.join(os.getcwd(), 'contracts')
    pdf_path = os.path.join(static_dir, f"{field.id}_ER.pdf")

    if not os.path.exists('contracts'):
        os.makedirs('contracts')

    flat_logo = os.path.join(os.getcwd(), 'logos/flat_logo.jpg')
    circular_logo = os.path.join(os.getcwd(), 'logos/circular_logo.png')

    c = canvas.Canvas(pdf_path, pagesize=A4)
    w,h = A4

    y = h-55
    c.drawImage(flat_logo, w-120, y, width=100, height=45)
    x = 40
    y = y - 40
    c.setFont("Helvetica-Bold", 36)
    c.setFillColorRGB(0.078, 0.33, 0.45)
    c.drawString(x, y, "Digital Employment Record")

    # Employer Information
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y-50, F"Reference Number: 0001-{field.id}")
    c.drawString(x, y-75, f"Employer Whatsapp Number: {request.employerNumber}")
    c.drawString(x, y-100, f"Domestic Worker ID: 010-{request.workerNumber}")

    y = y - 150

    # Chat Transcript Title
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Whatsapp Chat:")

    if not request.upi:
        request.upi = "N/A"

    else :
        request.accountNumber = "N/A"
        request.ifsc = "N/A"
    # Chat Transcript
    chat_text = f"""Employer: I'm interested in onboarding my domestic worker for salary slip
issuance.

Sampatti Bot: That's fantastic! We assure you a quick process. Could you please
provide us with the phone number of your domestic worker?

Employer: {request.workerNumber}

Sampatti Bot: Thank you for sharing. We are verifying her account.

Sampatti Bot: We have verified your domestic worker's account details. Please
press "Yes' if the following details are correct:

Name of domestic worker: {request.name}

Bank Details: VPA : {request.upi},  Account Number : {request.accountNumber},  IFSC : {request.ifsc}
PAN Number : {request.panNumber}

Employer: Yes

Sampatti Bot: That's great. Could you please provide us with her monthly salary?

Employer: Her monthly salary is {request.salary}.

Sampatti Bot: Excellent. We will now set up a monthly salary payment process for
you. A reminder and payment link will be sent to you at the end of each month.
Thanks."""        

    c.setFont("Helvetica", 10)
    y = y - 35
    lines = chat_text.split('\n')

    for line in lines:
        c.drawString(x + 20, y, line)
        y -= 15  # Move to the next line

    y = y - 20
    # Timestamp
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, f"Timestamp : {current_time}")

    # Verfication and Signature


    y = y - 50
    c.drawImage(circular_logo, 25, y-30 , 30, 30)
    declaration = """Verified by Sampatti Card
The employment record is digitally created and verified and does not require attestation or physical signature. 
As per Evidence Act, 1872, Section 65B whatsapp messages form electronic evidence and thus contract over whatsapp 
is legally valid. """

    c.setFont("Helvetica", 8)
    declaration_lines = declaration.split('\n')

    for line in declaration_lines:
        c.drawString(x + 30, y, line)
        y -= 15  # Move to the next line

    y = y - 20
    # Company Contact
    c.setFont("Helvetica", 10)
    c.rect(0,0,w,30, fill=True)
    c.setFillColorRGB(1,1,1)
    c.drawString(x, 12.5, "Phone : +91 86603 52558")
    c.drawString(x+ 150, 12.5, "website : www.sampatticard.in          support : support@sampatticard.in")

    c.showPage()
    c.save()
