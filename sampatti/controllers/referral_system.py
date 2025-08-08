"""
Comprehensive Referral System Implementation
Based on the workflow diagram provided by the user
"""

import os
import requests
import random
import string
from datetime import datetime
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from .utility_functions import current_date, generate_unique_id
from . import whatsapp_message, cashfree_api
import random
import string 


class ReferralSystemManager:
    """
    Main class to handle all referral system operations
    """
    
    def __init__(self):
        self.cashback_amount = 150  # Fixed cashback amount in rupees
        # Cashfree API configuration
        self.cashfree_base_url = "https://api.cashfree.com/payout"
        self.cashfree_client_id = os.getenv("CASHFREE_VERIFICATION_ID")
        self.cashfree_client_secret = os.getenv("CASHFREE_VERIFICATION_SECRET")
        self.cashfree_headers = {
            "Content-Type": "application/json",
            "x-api-version": "2024-01-01",
            "x-client-id": self.cashfree_client_id,
            "x-client-secret": self.cashfree_client_secret
        }
    
    def generate_referral_code(self, employer_number: int) -> str:
        """
        Generate a unique referral code for an employer
        Format: EMP{employer_number}_{random_string}
        """
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"EMP{employer_number}_{random_suffix}"
    
    def check_first_payment_status(self, employer_number: int, db: Session) -> dict:
        """
        Check if employer has made their first payment
        Step 2 from the diagram: Check in salary details table
        """
        try:
            # Check if employer exists and has FirstPaymentDone flag
            employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == employer_number
            ).first()
            
            if not employer:
                return {"status": "not_found", "message": "Employer not found"}
            
            # Check if first payment is already done
            if employer.FirstPaymentDone:
                return {
                    "status": "already_done", 
                    "message": "First payment already completed",
                    "employer_id": employer.id
                }
            
            # Check salary details for any payment
            salary_details = db.query(models.SalaryDetails).filter(
                models.SalaryDetails.employerNumber == employer_number
            ).last()
            
            if salary_details and salary_details.order_id:
                # Check payment status via Cashfree
                payment_status = cashfree_api.check_order_status(salary_details.order_id)
                if payment_status.get("order_status") == "PAID":
                    return {
                        "status": "first_payment_done",
                        "message": "First payment completed",
                        "employer_id": employer.id,
                        "order_id": salary_details.order_id
                    }
            
            return {
                "status": "no_payment",
                "message": "No payment made yet",
                "employer_id": employer.id
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Error checking payment status: {str(e)}"}
    
    def extract_upi_and_generate_referral_code(self, employer_number: int, db: Session) -> dict:
        """
        Step 3-4 from diagram: Extract UPI ID and generate referral code
        """
        try:
            employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == employer_number
            ).first()
            
            if not employer:
                return {"status": "error", "message": "Employer not found"}
            
            # Check if referral code already exists
            if employer.referralCode and employer.referralCode.strip():
                return {
                    "status": "already_exists",
                    "message": "Referral code already exists",
                    "referral_code": employer.referralCode,
                    "upi_id": employer.upiId
                }
            
            # Generate new referral code
            referral_code = self.generate_referral_code(employer_number)
            
            # Update employer with referral code
            employer.referralCode = referral_code
            db.commit()
            db.refresh(employer)
            
            return {
                "status": "success",
                "message": "Referral code generated successfully",
                "referral_code": referral_code,
                "upi_id": employer.upiId,
                "employer_id": employer.id
            }
            
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": f"Error generating referral code: {str(e)}"}
    
    def send_referral_code_to_employer(self, employer_number: int, referral_code: str) -> dict:
        """
        Step 5 from diagram: Send referral code to employer via WhatsApp
        """
        try:
            message = f"""🎉 Congratulations! Your referral code is ready!

Your Referral Code: *{referral_code}*

Share this code with friends and family to earn ₹{self.cashback_amount} cashback for each successful referral!

How it works:
1. Share your referral code with others
2. When they onboard their first worker using your code and make their first payment
3. You earn ₹{self.cashback_amount} cashback!

Start sharing and earning today! 💰"""

            # Send WhatsApp message (assuming you have a generic message function)
            # You may need to create a specific template for this
            whatsapp_message.send_message_user(
                employer_number, 
                message
            )
            
            return {
                "status": "success",
                "message": "Referral code sent successfully",
                "referral_code": referral_code
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Error sending referral code: {str(e)}"}
    
    def create_cashfree_beneficiary(self, employer_number: int, employer_upi_id: str) -> dict:
        """
        Create beneficiary on Cashfree for cashback payments
        """
        try:
            db = next(get_db())
            employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == employer_number
            ).first()
            
            if not employer:
                return {"status": "error", "message": f"Employer with number {employer_number} not found"}
                
            beneficiary_id = employer.id
            
            payload = {
                "beneficiary_id": beneficiary_id,
                "beneficiary_name": "Sampatti Card User",
                "beneficiary_instrument_details": {
                    "vpa": employer_upi_id if employer_upi_id else "",
                },
                "beneficiary_contact_details": {
                    "beneficiary_email": "sample@sampatticard.in",
                    "beneficiary_phone": f"{employer_number}",
                    "beneficiary_country_code": "+91"
                }
            }
            
            response = requests.post(
                f"{self.cashfree_base_url}/beneficiary",
                headers=self.cashfree_headers,
                json=payload
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "beneficiary_id": beneficiary_id,
                    "message": "Beneficiary created successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to create beneficiary: {response.text}"
                }
                
        except Exception as e:
            return {"status": "error", "message": f"Error creating beneficiary: {str(e)}"}
    
    def transfer_cashback_amount(self, beneficiary_id: str, amount: int = None, transfer_mode: str = "upi") -> dict:
        """
        Transfer cashback amount to beneficiary via Cashfree
        
        Args:
            beneficiary_id: The ID of the beneficiary to transfer to
            amount: The amount to transfer (defaults to self.cashback_amount if not provided)
            transfer_mode: Payment mode (default: upi)
            
        Returns:
            Dictionary with transfer result
        """
        try:
            transfer_amount = amount or self.cashback_amount
            transfer_id = f"CASHBACK_{beneficiary_id}_{generate_unique_id()}"
            
            
            payload = {
                "transfer_id": transfer_id,
                "transfer_amount": transfer_amount,
                "beneficiary_details": {
                    "beneficiary_id": beneficiary_id
                },
                "transfer_mode": transfer_mode
            }
            
            response = requests.post(
                f"{self.cashfree_base_url}/transfers",
                headers=self.cashfree_headers,
                json=payload
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "transfer_id": transfer_id,
                    "amount": transfer_amount,
                    "message": "Cashback transferred successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to transfer cashback: {response.text}"
                }
                
        except Exception as e:
            return {"status": "error", "message": f"Error transferring cashback: {str(e)}"}
    
    def process_referral_usage(self, referring_employer_number: int, referred_employer_number: int, referral_code: str, db: Session) -> dict:
        """
        Step 6-8 from diagram: Process when someone uses a referral code
        """
        try:
            # Find referring employer
            referring_employer = db.query(models.Employer).filter(
                models.Employer.referralCode == referral_code
            ).first()
            
            if not referring_employer:
                return {"status": "error", "message": "Invalid referral code"}
            
            # Find or create referred employer
            referred_employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == referred_employer_number
            ).first()
            
            if not referred_employer:
                # Create new employer
                from .main_tool import add_employer
                referred_employer = add_employer(referred_employer_number)
            
            # Check if referral relationship already exists
            existing_referral = db.query(models.EmployerReferralMapping).filter(
                models.EmployerReferralMapping.employerReferring == referring_employer.id,
                models.EmployerReferralMapping.employerReferred == referred_employer.id
            ).first()
            
            if existing_referral:
                return {"status": "already_exists", "message": "Referral relationship already exists"}
            
            # Create referral mapping
            referral_mapping = models.EmployerReferralMapping(
                id=str(uuid.uuid4()),
                employerReferring=referring_employer.id,
                employerReferred=referred_employer.id,
                referralCode=referral_code,
                referralStatus="ACTIVE",
                dateReferredOn=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                cashbackAmount=self.cashback_amount,
                cashbackStatus="PENDING"
            )
            
            db.add(referral_mapping)
            
            # Update referring employer's referral count
            referring_employer.numberofReferral += 1
            
            db.commit()
            db.refresh(referral_mapping)
            
            return {
                "status": "success",
                "message": "Referral processed successfully",
                "referral_mapping_id": referral_mapping.id,
                "referring_employer": referring_employer.employerNumber,
                "referred_employer": referred_employer.employerNumber
            }
            
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": f"Error processing referral: {str(e)}"}
    
    def process_cashback_payment(self, referral_mapping_id: str, db: Session) -> dict:
        """
        Step 9-10 from diagram: Process cashback when referred employer makes first payment
        """
        try:
            # Get referral mapping
            referral_mapping = db.query(models.EmployerReferralMapping).filter(
                models.EmployerReferralMapping.id == referral_mapping_id
            ).first()
            
            if not referral_mapping:
                return {"status": "error", "message": "Referral mapping not found"}
            
            if referral_mapping.cashbackStatus == "PAID":
                return {"status": "already_paid", "message": "Cashback already paid"}
            
            # Get referring employer
            referring_employer = db.query(models.Employer).filter(
                models.Employer.id == referral_mapping.employerReferring
            ).first()
            
            # Get referred employer
            referred_employer = db.query(models.Employer).filter(
                models.Employer.id == referral_mapping.employerReferred
            ).first()
            
            # Check if referred employer has made first payment
            payment_check = self.check_first_payment_status(referred_employer.employerNumber, db)
            
            if payment_check["status"] != "first_payment_done":
                return {"status": "payment_pending", "message": "Referred employer hasn't made first payment yet"}
            
            # Step 1: Create Cashfree beneficiary for referring employer if not exists
            employer_data = {
                "name": f"Employer {referring_employer.employerNumber}",
                "upi_id": referring_employer.upiId or "",
                "phone": referring_employer.employerNumber,
                "email": "support@sampatticard.in"
            }
            
            beneficiary_result = self.create_cashfree_beneficiary(referring_employer.employerNumber, employer_data)
            
            if beneficiary_result["status"] != "success":
                return {"status": "error", "message": f"Failed to create beneficiary: {beneficiary_result['message']}"}
            
            beneficiary_id = beneficiary_result["beneficiary_id"]
            
            # Step 2: Transfer cashback amount via Cashfree
            transfer_result = self.transfer_cashback_amount(beneficiary_id, self.cashback_amount)
            
            if transfer_result["status"] != "success":
                return {"status": "error", "message": f"Failed to transfer cashback: {transfer_result['message']}"}
            
            # Step 3: Update database records after successful transfer
            referral_mapping.cashbackStatus = "PAID"
            referral_mapping.dateReferredOn = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Update referring employer's cashback amount
            referring_employer.cashbackAmountCredited += self.cashback_amount
            
            # Store transfer details for audit
            # You might want to add a field to store transfer_id in the database
            
            db.commit()
            
            # Send cashback notification with transfer details
            self.send_cashback_notification(
                referring_employer.employerNumber, 
                self.cashback_amount,
                transfer_result.get("transfer_id", "")
            )
            
            return {
                "status": "success",
                "message": f"Cashback of ₹{self.cashback_amount} processed successfully",
                "cashback_amount": self.cashback_amount,
                "referring_employer": referring_employer.employerNumber
            }
            
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": f"Error processing cashback: {str(e)}"}
    
    def send_cashback_notification(self, employer_number: int, cashback_amount: int, transfer_id: str = ""):
        """
        Send cashback notification to employer with transfer details
        """
        try:
            transfer_info = f"\n📋 Transfer ID: {transfer_id}" if transfer_id else ""
            
            message = f"""🎉 Great News! You've earned a referral reward!

💰 Cashback Earned: ₹{cashback_amount}
✅ Payment Status: Successfully transferred to your UPI{transfer_info}

Your referral was successful! The cashback amount has been directly transferred to your registered UPI account.

Keep sharing your referral code to earn more rewards! 🚀

Thank you for being part of the Sampatti Card referral program! 💳"""

            whatsapp_message.send_message_user(employer_number, message)
            
        except Exception as e:
            print(f"Error sending cashback notification: {e}")
    
    def get_referral_stats(self, employer_number: int, db: Session) -> dict:
        """
        Get referral statistics for an employer
        """
        try:
            employer = db.query(models.Employer).filter(
                models.Employer.employerNumber == employer_number
            ).first()
            
            if not employer:
                return {"status": "error", "message": "Employer not found"}
            
            # Get referral mappings where this employer is referring
            referrals = db.query(models.EmployerReferralMapping).filter(
                models.EmployerReferralMapping.employerReferring == employer.id
            ).all()
            
            total_referrals = len(referrals)
            paid_cashbacks = len([r for r in referrals if r.cashbackStatus == "PAID"])
            pending_cashbacks = len([r for r in referrals if r.cashbackStatus == "PENDING"])
            
            return {
                "status": "success",
                "referral_code": employer.referralCode,
                "total_referrals": total_referrals,
                "paid_cashbacks": paid_cashbacks,
                "pending_cashbacks": pending_cashbacks,
                "total_cashback_earned": employer.cashbackAmountCredited,
                "referrals": [
                    {
                        "referred_employer": r.employerReferred,
                        "date": r.dateReferredOn,
                        "status": r.cashbackStatus,
                        "amount": r.cashbackAmount
                    } for r in referrals
                ]
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Error getting referral stats: {str(e)}"}


# Main workflow function that orchestrates the entire referral system
def execute_referral_workflow(employer_number: int) -> dict:
    """
    Execute the complete referral workflow as per the diagram
    """
    db = next(get_db())
    referral_manager = ReferralSystemManager()
    
    try:
        # Step 1: Check if employer made first payment
        payment_status = referral_manager.check_first_payment_status(employer_number, db)
        
        if payment_status["status"] == "no_payment":
            return {"status": "waiting", "message": "Waiting for first payment"}
        
        if payment_status["status"] == "error":
            return payment_status
        
        # Step 2-4: Extract UPI and generate referral code
        referral_result = referral_manager.extract_upi_and_generate_referral_code(employer_number, db)
        
        if referral_result["status"] == "error":
            return referral_result
        
        # Step 5: Send referral code to employer
        if referral_result["status"] == "success":
            send_result = referral_manager.send_referral_code_to_employer(
                employer_number, 
                referral_result["referral_code"]
            )
            
            return {
                "status": "success",
                "message": "Referral workflow completed successfully",
                "referral_code": referral_result["referral_code"],
                "send_status": send_result["status"]
            }
        
        return referral_result
        
    except Exception as e:
        return {"status": "error", "message": f"Error in referral workflow: {str(e)}"}
    
    finally:
        db.close()


def process_referral_cashback_workflow(referral_mapping_id: str) -> dict:
    """
    Process cashback when referred employer makes first payment
    """
    db = next(get_db())
    referral_manager = ReferralSystemManager()
    
    try:
        return referral_manager.process_cashback_payment(referral_mapping_id, db)
    finally:
        db.close()


def check_and_process_pending_cashbacks() -> dict:
    """
    Batch process all pending cashbacks
    """
    db = next(get_db())
    referral_manager = ReferralSystemManager()
    
    try:
        # Get all pending referral mappings
        pending_referrals = db.query(models.EmployerReferralMapping).filter(
            models.EmployerReferralMapping.cashbackStatus == "PENDING"
        ).all()
        
        processed_count = 0
        for referral in pending_referrals:
            result = referral_manager.process_cashback_payment(referral.id, db)
            if result["status"] == "success":
                processed_count += 1
        
        return {
            "status": "success",
            "message": f"Processed {processed_count} cashbacks out of {len(pending_referrals)} pending",
            "processed": processed_count,
            "total_pending": len(pending_referrals)
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Error processing pending cashbacks: {str(e)}"}
    
    finally:
        db.close()
