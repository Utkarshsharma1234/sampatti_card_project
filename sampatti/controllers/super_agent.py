from cgitb import text
import json
import os
import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import chromadb
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.tools import StructuredTool
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from .userControllers import send_audio_message, extract_document_details
from .whatsapp_message import send_v2v_message, send_message_user, display_user_message_on_xbotic, send_template_message
from .onboarding_agent import queryExecutor as onboarding_agent
from .cash_advance_agent import queryE as cash_advance_agent
from .onboarding_tools import transcribe_audio
# Import the employer and worker tools
from .main_tool import add_employer_tool, get_employer_workers_info_tool, check_employer_exists_tool, add_employer, get_employer_workers_info, check_employer_exists, check_worker_employer_exists
# Import attendance agent and tools
from .attendance_agent import queryExecutor as attendance_agent
from .attendance_tool import get_workers_for_employer_tool, manage_attendance_tool, get_attendance_summary_tool



load_dotenv()
print("✅ Successfully imported onboarding_agent")
print("✅ Successfully imported cash_advance_agent")
print("✅ Successfully imported employer and worker tools")
print("✅ Successfully imported attendance_agent and attendance_tools")


# Configuration
openai_api_key = os.environ.get("OPENAI_API_KEY")
openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
llm = ChatOpenAI(
        model="openai/gpt-5", 
        api_key=openrouter_api_key,
        base_url="https://openrouter.ai/api/v1"
)

embedding = OpenAIEmbeddings(api_key=openai_api_key)

class IntentClassification(BaseModel):
    """Pydantic model for intent classification"""
    primary_intent: str  # "onboarding", "cash_advance", "general_conversation", "greeting", "help", "worker_info"
    confidence: float  # 0.0 to 1.0
    keywords_found: list[str]
    requires_specialized_agent: bool
    conversation_context: str
    user_emotional_state: str  # "neutral", "frustrated", "happy", "confused"

class SuperAgentResponse(BaseModel):
    """Pydantic model for super agent response"""
    agent_used: str  # "super_agent", "onboarding_agent", "cash_advance_agent"
    response_text: str
    intent_detected: str
    next_expected_action: str
    conversation_stage: str  # "greeting", "information_gathering", "processing", "completion"

class SuperAgent:
    def __init__(self):
        self.PERSIST_DIR = "../../chroma_db"
        self.vectordb = Chroma(
            persist_directory=self.PERSIST_DIR,
            collection_name="SuperAgentConversations",
            embedding_function=embedding
        )
        
        # Intent keywords for classification - Added worker_info keywords
        self.intent_keywords = {
            "onboarding": [
                "onboard", "add worker", "new worker", "employee details",
                "upi", "bank account", "pan number", "salary", "ifsc", "worker number",
                "add worker", "register worker", "setup worker", "worker information",
                "new employee", "employee setup", "worker registration", "referral code", 
                "cashback amount", "number of referrals", "referral code status"
            ],
            "cash_advance": [
                "cash advance", "advance", "bonus", "deduction", "salary deduction",
                "advance money", "payment link", "repayment", "advance payment",
                "give money", "advance salary", "loan", "pay advance", "advance amount",
                "bonus payment", "deduct salary", "salary payment", "generate link",
                "give bonus", "add bonus", "bonus to worker", "bonus to employee",
                "deduct from salary", "salary cut", "cut salary", "deduct money",
                "payment to worker", "pay worker", "worker payment", "employee payment"
            ],
            "worker_info": [
                "show workers", "list workers", "worker list", "employee list", "my workers",
                "worker status", "worker details", "employee status", "worker info",
                "how many workers", "total workers", "worker count", "employee count",
                "worker salary", "worker leaves", "worker onboarding date", "worker vendor",
                "active workers", "inactive workers", "all workers", "my employees",
                "tell me about workers", "worker information", "employee information",
                "salary of", "what is salary", "worker a", "worker b"
            ],
            "general_conversation": [
                "hello", "hi", "how are you", "what can you do", "help", "thanks",
                "good morning", "good evening", "bye", "goodbye", "thank you",
                "hey", "capabilities", "what do you do"
            ]
        }
        
        # Initialize tools
        self.tools = [
            add_employer_tool,
            get_employer_workers_info_tool,
            get_workers_for_employer_tool,
            manage_attendance_tool,
            get_attendance_summary_tool,
            check_employer_exists_tool
        ]
        
        self.setup_intent_classifier()
        self.setup_tool_agent()
        self.setup_conversation_manager()

    def setup_intent_classifier(self):
        """Setup the intent classification system"""
        intent_parser = PydanticOutputParser(pydantic_object=IntentClassification)
        
        self.intent_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
                You are an intelligent intent classifier for a workplace management system.
                
                Analyze the user's message and classify it into one of these intents:
                1. "onboarding" - Adding new workers, collecting worker details (UPI, bank, PAN, salary, etc.)
                2. "cash_advance" - Cash advances, bonuses, deductions, payment links, salary payments
                3. "worker_info" - Viewing worker lists, worker details, worker status, counts, salary inquiries, etc.
                4. "general_conversation" - Greetings, help requests, general chat
                5. "greeting" - Hello, hi, good morning, etc.
                6. "help" - What can you do, how to use, etc.
                
                Consider conversation history to understand context better.
                
                KEYWORDS FOR CLASSIFICATION:
                Onboarding: {onboarding_keywords}
                Cash Advance: {cash_advance_keywords}
                Worker Info: {worker_info_keywords}
                General: {general_keywords}
                
                Return your analysis in the specified JSON format.
                {format_instructions}
                """,
            ),
            ("system", "Previous conversation context:\n{chat_history}"),
            ("human", "Current message: {user_message}"),
        ]).partial(
            format_instructions=intent_parser.get_format_instructions(),
            onboarding_keywords=", ".join(self.intent_keywords["onboarding"]),
            cash_advance_keywords=", ".join(self.intent_keywords["cash_advance"]),
            worker_info_keywords=", ".join(self.intent_keywords["worker_info"]),
            general_keywords=", ".join(self.intent_keywords["general_conversation"])
        )
        
        self.intent_classifier = self.intent_prompt | llm | intent_parser

    def setup_tool_agent(self):
        """Setup placeholder for tool agent - currently using direct function calls"""
        # Tool agent setup is not currently used as we're calling functions directly
        # Keeping this method for potential future use with LangChain agents
        self.tool_agent = None
        self.tool_executor = None

    def setup_conversation_manager(self):
        """Setup the main conversation management system"""
        response_parser = PydanticOutputParser(pydantic_object=SuperAgentResponse)
        
        self.conversation_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
                You are a Super AI Assistant for worker management. You are the main interface between users and specialized systems.
                
                Today's date: {today}
                Employer Number: {employer_number}
                
                YOUR ROLE:
                1. Handle general conversations naturally and helpfully
                2. Route specialized requests to appropriate agents
                3. Maintain conversation continuity and context
                4. Provide helpful guidance and support
                
                ROUTING DECISIONS:
                - If intent is "onboarding": Route to onboarding specialist
                - If intent is "cash_advance": Route to cash advance specialist
                - If intent is "worker_info": Use internal tools to fetch worker information
                - If intent is "general_conversation", "greeting", "help": Handle yourself
                
                CONVERSATION STAGES:
                1. "greeting" - Initial hello, introductions
                2. "information_gathering" - Collecting details from user
                3. "processing" - Working on user's request
                4. "completion" - Task completed, offering additional help
                
                GENERAL CONVERSATION RESPONSES:
                For greetings: Be warm and welcoming, introduce your capabilities
                For help requests: Explain what you can do clearly
                For thanks: Acknowledge gracefully and offer continued assistance
                For general chat: Be friendly but guide toward productive usage
                GREETING RESPONSE TEMPLATE:
                - When the user says hi, hello, hey, or similar greeting and you haven't already shared your welcome context in this conversation, reply with:
                  "👋 Hi! I’m here to help you manage your domestic worker payments easily.\nHere’s what you can do:\n• 💸 Pay Salary / Advance\n• 📑 View Verified Salary Slip\n• 📊 View Advance payment logs\nJust let me know which one you'd like to do."
                - Keep the wording consistent so the experience feels familiar each time.

                CAPABILITIES TO MENTION:
                ✅ View all your workers and their details
                ✅ Onboard new workers (collect UPI, bank details, PAN, salary info)
                ✅ Manage cash advances and repayments  
                ✅ Handle bonuses and salary deductions
                ✅ Generate salary payment links
                ✅ Track and update worker information
                
                IMPORTANT FACTS:
                - Sampatti currently operates entirely through WhatsApp. There is no separate mobile app (Android or iOS) or downloadable APK.
                - If the user asks for an app, store link, or download URL, clearly explain that everything runs on WhatsApp and reassure them you'll share updates if that changes.
                - Onboarding requires the worker's phone number, PAN card, and either bank account details or a UPI ID. If they don't have those yet, let the user know our support team can help set them up and ask how you can assist.
                - Sampatti Card's mission is to make household staff financially capable by enabling responsible cash advances, secure salary management, and access to future loan or insurance products.
                - we require pan card, bank account or UPI ID for onboarding and these are required for cash advances and salary payments, if worker doesn't have them, support team can help create them. please ask how you can assist if user needs help.

                MANDATORY RESPONSE CHECK:
                - Whenever the user indicates a worker lacks a bank account, PAN card, or UPI ID, clearly state that these are required for onboarding and immediately offer assistance from the support team to get them created.

                RESPONSE GUIDELINES:
                - Always be professional yet friendly
                - Provide clear, actionable guidance
                - Ask clarifying questions when needed
                - Summarize what you're going to do before routing
                - Never leave users confused about next steps
                
                Return your response in the specified JSON format.
                {format_instructions}
                """,
            ),
            ("system", "Conversation History:\n{chat_history}"),
            ("system", "Intent Analysis: {intent_analysis}"),
            ("human", "User Message: {user_message}"),
        ]).partial(format_instructions=response_parser.get_format_instructions())
        
        self.conversation_manager = self.conversation_prompt | llm | response_parser

    def ensure_employer_exists(self, employer_number: int):
        """Ensure employer exists in database, add if not present"""
        try:
            # This will add the employer if not exists, or return existing employer
            result = add_employer(employer_number)
            print(f"EMPLOYER ADDING LOG: {result}")
            print(f"✅ Employer {employer_number} ensured in database")
            return True
        except Exception as e:
            print(f"❌ Error ensuring employer exists: {e}")
            return False
        
    def check_first_time_employer(self, employer_number: int) -> bool:
        try:
            check_result = check_employer_exists(employer_number)
            print(f"EMPLOYER CHECK LOG: {check_result}")
            return check_result
        
        except Exception as e:
            print(f"❌ Error checking if employer exists: {e}")
            return False
    
    def worker_employer_mapping(self, employer_number: int) -> bool:
        try:
            check_result = check_worker_employer_exists(employer_number)
            print(f"WORKER-EMPLOYER MAPPING CHECK LOG: {check_result}")
            return check_result
        
        except Exception as e:
            print(f"❌ Error checking worker-employer mapping: {e}")
            return False

    def check_employer_exists(employer_number: int) -> bool:
        """
        Check if employer exists in the database
        Returns True if employer exists, False otherwise
        """
        try:
            # Try to get employer workers info - this will fail if employer doesn't exist
            result = get_employer_workers_info(employer_number)
            # If we get here without exception, employer exists
            return True
        except Exception as e:
            # If there's an error (likely employer not found), return False
            print(f"Employer {employer_number} not found: {e}")
            return False

    def get_worker_info_response(self, employer_number: int, user_message: str) -> Dict[str, Any]:
        """Fetch worker information and return raw data for the super agent to process"""
        try:
            # First ensure employer exists
            self.ensure_employer_exists(employer_number)
            
            # Direct call to the function to get worker data
            worker_data = get_employer_workers_info(employer_number)
            
            # Return the raw data for the super agent to process
            return {
                "success": True,
                "data": worker_data,
                "error": None
            }
                
        except Exception as e:
            print(f"❌ Error getting worker info: {e}")
            print(f"❌ Error Type: {type(e).__name__}")
            print(f"❌ Error Details: {str(e)}")
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def generate_worker_info_response(self, user_message: str, worker_data: Dict[str, Any], 
                                    chat_history: str, employer_number: int) -> str:
        """Generate a natural language response based on user query and worker data"""
        
        worker_info_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
                You are a helpful workplace management assistant. You have access to worker information 
                and need to respond to the user's query in a natural, conversational way.
                
                Today's date: {today}
                Employer Number: {employer_number}
                
                Worker Data Available:
                {worker_data}
                
                RESPONSE GUIDELINES:
                1. Answer the specific question the user asked
                2. Be conversational and friendly
                3. For Status when status= SENT it means the worker has paid the last salary.
                4. Format dates nicely (e.g., "January 15, 2024" instead of "2024-01-15").
                5. Format currency with commas (e.g., ₹12,000).
                6. If user asks for specific information, focus on that
                7. If user asks generally, provide a comprehensive overview
                8. Always end with a helpful suggestion or question
                9. Monthly leaves is total number of leaves in the current month.
                10. only provide the like this *example* for bullet point don't use **example** like this.
                
                SPECIFIC QUERY HANDLING:
                - "how many workers": Focus on count and status breakdown
                - "worker salaries": Focus on salary information
                - "worker details": Show comprehensive information
                - "specific worker name": Focus on that worker only
                - "salary of worker": Focus on the specific worker's salary
                
                Remember: Be helpful, natural, and answer exactly what the user is asking for.
                """,
            ),
            ("system", "Conversation History:\n{chat_history}"),
            ("human", "User Query: {user_message}"),
        ])
        
        chain = worker_info_prompt | llm
        
        try:
            response = chain.invoke({
                "user_message": user_message,
                "worker_data": json.dumps(worker_data, indent=2),
                "chat_history": chat_history,
                "today": datetime.now().strftime("%B %d, %Y"),
                "employer_number": employer_number
            })
            
            # Extract the content from the response
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)
                
        except Exception as e:
            print(f"❌ Error generating worker info response: {e}")
            # Fallback to a basic response
            if not worker_data["workers"]:
                return (
                    "I checked your records, and it looks like you don't have any workers registered yet. 😊\n\n"
                    "Would you like to onboard your first worker? Just say 'add worker' or 'onboard new worker', "
                    "and I'll guide you through the process step by step!"
                )
            else:
                return (
                    f"You have {worker_data['total_workers']} worker(s) in your system. "
                    f"Would you like me to show you more specific details about them?"
                )

    def store_conversation(self, employer_number: int, message: str, metadata: dict = None):
        """Store conversation in vector database with enhanced metadata"""
        default_metadata = {
            "employerNumber": str(employer_number),
            "timestamp": time.time(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if metadata:
            default_metadata.update(metadata)
            
        self.vectordb.add_texts(
            texts=[message],
            metadatas=[default_metadata]
        )
        # Removed self.vectordb.persist() as it's deprecated in Chroma 0.4.x

    def get_sorted_chat_history(self, employer_number: int, limit: int = 20) -> str:
        """Retrieve recent sorted chat history for an employer"""
        try:
            raw_results = self.vectordb.get(where={"employerNumber": str(employer_number)})

            if not raw_results or not raw_results.get("documents"):
                return ""

            messages = list(zip(raw_results["metadatas"], raw_results["documents"]))
            sorted_messages = sorted(messages, key=lambda x: x[0].get("timestamp", 0))
            
            # Get recent messages only
            recent_messages = sorted_messages[-limit:] if len(sorted_messages) > limit else sorted_messages
            sorted_text = "\n".join(msg for _, msg in recent_messages)

            return sorted_text
        except Exception as e:
            print(f"Error retrieving chat history: {e}")
            return ""

    def classify_intent(self, user_message: str, chat_history: str) -> IntentClassification:
        """Classify user intent using the LLM-based classifier"""
        try:
            result = self.intent_classifier.invoke({
                "user_message": user_message,
                "chat_history": chat_history
            })
            return result
        except Exception as e:
            print(f"Error classifying intent: {e}")
            # Fallback to keyword-based classification
            return self.fallback_intent_classification(user_message)

    def fallback_intent_classification(self, user_message: str) -> IntentClassification:
        """Fallback keyword-based intent classification"""
        message_lower = user_message.lower()
        
        # Check for worker info keywords first (including salary queries)
        worker_info_matches = [kw for kw in self.intent_keywords["worker_info"] if kw in message_lower]
        if worker_info_matches or ("salary" in message_lower and "worker" in message_lower):
            return IntentClassification(
                primary_intent="worker_info",
                confidence=0.9,
                keywords_found=worker_info_matches or ["salary", "worker"],
                requires_specialized_agent=False,  # Handled by super agent's tools
                conversation_context="worker_info_request",
                user_emotional_state="neutral"
            )
        
        # Check for cash advance keywords with higher confidence for clear matches
        cash_advance_matches = [kw for kw in self.intent_keywords["cash_advance"] if kw in message_lower]
        if cash_advance_matches:
            # Higher confidence for specific money-related terms
            confidence = 0.95 if any(term in message_lower for term in ["bonus", "advance", "deduction", "payment"]) else 0.8
            return IntentClassification(
                primary_intent="cash_advance",
                confidence=confidence,
                keywords_found=cash_advance_matches,
                requires_specialized_agent=True,
                conversation_context="cash_advance_related",
                user_emotional_state="neutral"
            )
        
        # Check for onboarding keywords
        onboarding_matches = [kw for kw in self.intent_keywords["onboarding"] if kw in message_lower]
        if onboarding_matches:
            confidence = 0.95 if any(term in message_lower for term in ["add worker", "new worker", "onboard"]) else 0.8
            return IntentClassification(
                primary_intent="onboarding",
                confidence=confidence,
                keywords_found=onboarding_matches,
                requires_specialized_agent=True,
                conversation_context="onboarding_related",
                user_emotional_state="neutral"
            )
        
        # Check for greeting/help keywords
        general_matches = [kw for kw in self.intent_keywords["general_conversation"] if kw in message_lower]
        if any(word in message_lower for word in ["hello", "hi", "hey", "good morning", "good evening"]):
            return IntentClassification(
                primary_intent="greeting",
                confidence=0.9,
                keywords_found=["greeting"],
                requires_specialized_agent=False,
                conversation_context="greeting",
                user_emotional_state="neutral"
            )
        elif any(word in message_lower for word in ["help", "what can you do", "capabilities"]):
            return IntentClassification(
                primary_intent="help",
                confidence=0.9,
                keywords_found=["help_request"],
                requires_specialized_agent=False,
                conversation_context="help_request",
                user_emotional_state="neutral"
            )
        
        # Default to general conversation with low confidence
        return IntentClassification(
            primary_intent="general_conversation",
            confidence=0.5,
            keywords_found=general_matches,
            requires_specialized_agent=False,
            conversation_context="general_chat",
            user_emotional_state="neutral"
        )

    def generate_general_response(self, intent_analysis: IntentClassification, user_message: str, 
                                chat_history: str, employer_number: int) -> SuperAgentResponse:
        """Generate response for general conversation using LLM"""
        try:
            # Convert Pydantic model to dict properly
            intent_dict = {
                "primary_intent": intent_analysis.primary_intent,
                "confidence": intent_analysis.confidence,
                "keywords_found": intent_analysis.keywords_found,
                "requires_specialized_agent": intent_analysis.requires_specialized_agent,
                "conversation_context": intent_analysis.conversation_context,
                "user_emotional_state": intent_analysis.user_emotional_state
            }
            
            result = self.conversation_manager.invoke({
                "user_message": user_message,
                "chat_history": chat_history,
                "intent_analysis": intent_dict,
                "today": datetime.now().strftime("%B %d, %Y"),
                "employer_number": employer_number
            })
            return result
        except Exception as e:
            print(f"Error generating general response: {e}")
            return self.fallback_general_response(intent_analysis, user_message)

    def fallback_general_response(self, intent_analysis: IntentClassification, user_message: str) -> SuperAgentResponse:
        """Fallback response generation"""
        if intent_analysis.primary_intent in ["greeting", "general_conversation"]:
            if any(word in user_message.lower() for word in ["hello", "hi", "hey"]):
                response_text = (
                    "👋 Hi! I’m here to help you manage your domestic worker payments easily.\n"
                    "Here’s what you can do:\n"
                    "• 💸 Pay Salary / Advance\n"
                    "• 📑 View Verified Salary Slip\n"
                    "• 📊 View Advance payment logs\n"
                    "Just let me know which one you'd like to do."
                )

            elif any(word in user_message.lower() for word in ["help", "what can you do"]):
                response_text = """I'm here to help with your domestic worker management needs! Here's what I can assist you with:

🔹 **Worker Onboarding**
   - Add new workers to your system
   - Collect UPI or bank account details
   - Gather PAN numbers and salary information
   
🔹 **Worker Information**
   - View all your workers and their current status
   - Check worker details like salary, leaves, and onboarding dates

🔹 **Cash Advance Management**
   - Process cash advance requests
   - Set up repayment schedules
   - Handle bonuses and salary deductions
   - Generate payment links

🔹 **General Support**
   - Answer questions about the system
   - Guide you through processes
   - Provide status updates

To complete onboarding, I’ll need the worker's phone number, PAN card, and either bank account details or a UPI ID. If she doesn’t have those yet, our customer support team can help create them—just let me know how you'd like us to assist.

Sampatti Card focuses on helping your household staff become financially capable with transparent salary management, responsible advances, and access to future loan or insurance options.

And just so you know: everything runs right here on WhatsApp—there isn't a separate mobile app yet. I'll keep you posted if that changes!

Just tell me what you need help with, and I'll take care of it!"""
            else:
                response_text = "I understand you'd like to chat! While I'm here to help with domestic worker management tasks, feel free to let me know if you need assistance with worker onboarding, viewing your workers, cash advances, or payment processing."
        else:
            response_text = (
                "I'm here to help! Let me know if you want to onboard a worker, review their details, or manage advances. "
                "For onboarding, I'll need their phone number, PAN card, and bank account or UPI ID—"
                "and if they don't have those yet, our support team can help set everything up. "
                "Sampatti Card's goal is to make your staff financially capable with transparent salaries, responsible advances, and future loan or insurance access. "
                "Just let me know if you'd like me to connect you with the team to get started."
            )

        return SuperAgentResponse(
            agent_used="super_agent",
            response_text=response_text,
            intent_detected=intent_analysis.primary_intent,
            next_expected_action="awaiting_user_request",
            conversation_stage="greeting"
        )

    def route_to_specialized_agent(self, intent: str, employer_number: int, 
                                 type_of_message: str, query: str, media_id: str) -> str:
        """Route request to appropriate specialized agent"""
        try:
            if intent == "onboarding":
                print(f"🔄 Routing to Onboarding Agent for employer {employer_number}")
                print(f"📤 Calling: onboarding_agent({employer_number}, '{type_of_message}', '{query}', '{media_id}')")
                
                if onboarding_agent is None:
                    return "Onboarding service is currently unavailable. Please try again later."
                
                # Call the onboarding agent directly
                response = onboarding_agent(employer_number, type_of_message, query, media_id)
                print(f"📥 Onboarding Agent Response: {response}")
                # Robustly extract string from agent response
                if isinstance(response, dict):
                    # Try common keys for message
                    for key in ["output", "result", "ai_message", "response_text", "message"]:
                        if key in response and response[key]:
                            return str(response[key])
                    # If no common keys, return the whole dict as string
                    return str(response)
                elif isinstance(response, str):
                    return response
                elif response is not None:
                    return str(response)
                else:
                    return "Onboarding agent did not return a response. Please check the worker details or try again."

            elif intent == "cash_advance":
                print(f"🔄 Routing to Cash Advance Agent for employer {employer_number}")
                print(f"📤 Calling: cash_advance_agent({employer_number}, '{type_of_message}', '{query}', '{media_id}')")
                
                if cash_advance_agent is None:
                    return "Cash advance service is currently unavailable. Please try again later."
                
                # Call the cash advance agent directly  
                response = cash_advance_agent(employer_number, type_of_message, query, media_id)
                print(f"📥 Cash Advance Agent Response: {response}")
                return str(response) if response else "No response from cash advance agent."
                
            elif intent in ["attendance", "attendance_management", "attendance_info"]:
                print(f"🔄 Routing to Attendance Agent for employer {employer_number}")
                print(f"📤 Calling: attendance_agent({employer_number}, '{type_of_message}', '{query}', '{media_id}')")
                
                if attendance_agent is None:
                    return "Attendance service is currently unavailable. Please try again later."
                
                response = attendance_agent(employer_number, type_of_message, query, media_id)
                print(f"📥 Attendance Agent Response: {response}")
                if isinstance(response, dict):
                    for key in ["output", "result", "ai_message", "response_text", "message"]:
                        if key in response and response[key]:
                            return str(response[key])
                    return str(response)
                elif isinstance(response, str):
                    return response
                elif response is not None:
                    return str(response)
                else:
                    return "Attendance agent did not return a response. Please check the worker details or try again."
                
            else:
                error_msg = f"I couldn't determine which specialist to connect you with for intent '{intent}'. Could you please clarify your request?"
                print(f"❌ Unknown intent: {intent}")
                return error_msg
                
        except Exception as e:
            error_msg = f"I encountered an error while connecting to the {intent} specialist. Please try again."
            print(f"❌ Error routing to {intent} agent: {str(e)}")
            print(f"❌ Error details: {type(e).__name__}: {e}")
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")
            return error_msg

    def process_query(self, employer_number: int, type_of_message: str, query: str, media_id: str, formatted_json: Dict[str, Any]) -> str:
        """Main method to process user queries"""
        print(f"\n🤖 Super Agent Processing Query for Employer {employer_number}")
        print(f"📝 Query: {query}")
        print(f"📋 Type: {type_of_message}")
        print(f"🆔 Media ID: {media_id}")
        
        try:
            
            # Get conversation history
            chat_history = self.get_sorted_chat_history(employer_number)
            print(f"📚 Chat History Length: {len(chat_history)} characters")
                
            # Ensure employer exists in database first
            self.ensure_employer_exists(employer_number)
            
            # If the message is audio, transcribe it first
            if type_of_message == "audio" and media_id:
                print(f"🔊 Transcribing audio with media ID: {media_id}")
                transcribed_text_language = transcribe_audio(media_id)
                query = transcribed_text_language[0]
                user_language = transcribed_text_language[1]
                print(f"🎤 Transcribed text: {query}")
                print(f"User Language:##: ", user_language)
                
            if type_of_message == "image" and media_id:
                resp = extract_document_details(media_id)
                query = resp
                print("Image Resp from the gemini")
            
            
            
            # Classify intent
            intent_analysis = self.classify_intent(query, chat_history)
            print(f"🎯 Intent Detected: {intent_analysis.primary_intent} (confidence: {intent_analysis.confidence:.2f})")
            print(f"🔍 Keywords Found: {intent_analysis.keywords_found}")
            print(f"🤖 Requires Specialized Agent: {intent_analysis.requires_specialized_agent}")
            
            # Store the user query
            self.store_conversation(
                employer_number, 
                f"User: {query}",
                {"intent": intent_analysis.primary_intent, "message_type": type_of_message}
            )
            
            if check_employer_exists(employer_number) is False:
                send_template_message(employer_number, "user_first_message")
                print(f"👤 First time employer detected: {employer_number}")
                self.ensure_employer_exists(employer_number)
                print(f"✅ Employer {employer_number} added to database")
                return
            
            if check_worker_employer_exists(employer_number) is False and intent_analysis.primary_intent == "greeting":
                send_template_message(employer_number, "user_first_message")
                print(f"⚠️ No workers mapped to employer {employer_number}. Prompted user to onboard workers.")
                return
            
            # Handle worker info requests with internal tools
            if intent_analysis.primary_intent == "worker_info" and intent_analysis.confidence >= 0.7:
                print(f"📊 WORKER INFO REQUEST DETECTED")
                print(f"🔧 Using internal tools to fetch worker information")
                
                # Get the worker data
                worker_info_result = self.get_worker_info_response(employer_number, query)
                
                if worker_info_result["success"]:
                    # Generate natural language response based on user query and worker data
                    response = self.generate_worker_info_response(
                        query, 
                        worker_info_result["data"], 
                        chat_history, 
                        employer_number
                    )
                    agent_used = "super_agent_tools"
                else:
                    response = (
                        "Oh no! I encountered an issue while fetching your worker information. 😔\n\n"
                        "This might be a temporary problem. Could you please try again in a moment? "
                        "If the issue persists, I'm here to help troubleshoot!"
                    )
                    agent_used = "super_agent_error"
                
                print(f"✅ Successfully processed worker information request")
                print(f"📄 Response preview: {response[:200]}..." if len(response) > 200 else f"📄 Full response: {response}")
            
            # DYNAMIC ROUTING: Route to specialized agent if intent matches and confidence is high
            elif intent_analysis.primary_intent in ["cash_advance", "onboarding"] and intent_analysis.confidence >= 0.7:
                print(f"✅ HIGH CONFIDENCE ROUTING: {intent_analysis.confidence:.2f} >= 0.7")
                print(f"🚀 Candidate agent: {intent_analysis.primary_intent}_agent")

                # --- Agent Confirmation Step ---
                agent_confirmed = self.confirm_agent(intent_analysis.primary_intent, employer_number, query, chat_history)
                print(f"🔔 Agent confirmation status: {agent_confirmed}")

                if agent_confirmed:
                    print(f"🔑 Agent confirmed. Initializing and invoking {intent_analysis.primary_intent}_agent.")
                    try:
                        response = self.route_to_specialized_agent(
                            intent_analysis.primary_intent,
                            employer_number,
                            type_of_message,
                            query,
                            media_id
                        )
                        agent_used = f"{intent_analysis.primary_intent}_agent"
                        print(f"✅ Successfully got response from {agent_used}")
                        print(f"📄 Response preview: {response[:200]}..." if len(response) > 200 else f"📄 Full response: {response}")
                    except Exception as routing_error:
                        print(f"❌ ROUTING ERROR: {routing_error}")
                        print(f"❌ Falling back to general response")
                        # Fallback to general response
                        super_response = self.generate_general_response(
                            intent_analysis, query, chat_history, employer_number
                        )
                        response = super_response.response_text
                        agent_used = "super_agent_fallback"
                else:
                    print(f"❌ Agent not confirmed. Handling with general conversation.")
                    super_response = self.generate_general_response(
                        intent_analysis, query, chat_history, employer_number
                    )
                    response = super_response.response_text
                    agent_used = "super_agent_not_confirmed"

            else:
                # Handle with general conversation only if confidence is low or general intent
                print(f"ℹ️ LOW CONFIDENCE OR GENERAL INTENT: {intent_analysis.confidence:.2f} < 0.7 OR general intent")
                print(f"🗣️ Handling with general conversation")
                
                super_response = self.generate_general_response(
                    intent_analysis, query, chat_history, employer_number
                )
                response = super_response.response_text
                agent_used = "super_agent"
                
                print(f"✅ Generated general response")
                print(f"📄 Response preview: {response[:200]}..." if len(response) > 200 else f"📄 Full response: {response}")
            
            # Store the assistant response
            self.store_conversation(
                employer_number,
                f"Assistant ({agent_used}): {response}",
                {"agent_used": agent_used, "message_type": type_of_message}
            )
            
            print(f"💾 Stored conversation with agent: {agent_used}")
            display_user_message_on_xbotic(employer_number, response)
            # Send the response based on message type
            if type_of_message=="text":
                
                word_count = len(response.split())
                if word_count > 30:
                    #send_message_user(employer_number, response)
                    send_audio_message(response, "en", employer_number)
                    print("MESSAGE SENT SUCCESSFULLY: ", response)
                    return response
                else:
                    # Send as regular text message for shorter responses
                    print("MESSAGE SENT SUCCESSFULLY: ", response)
                    return response

            if type_of_message=="audio":
                send_audio_message(response, user_language, employer_number)
                print("MESSAGE SENT SUCCESSFULLY: ", response) 
                return response
                
        except Exception as e:
            error_message = f"I apologize, but I encountered an error while processing your request. Please try again."
            print(f"❌ CRITICAL ERROR in Super Agent: {e}")
            print(f"❌ Error Type: {type(e).__name__}")
            print(f"❌ Error Details: {str(e)}")
            
            # Store error
            self.store_conversation(
                employer_number,
                f"Error: {error_message} - {str(e)}",
                {"error": True, "message_type": type_of_message}
            )
            
            return error_message

    # --- Helper for agent confirmation ---
    def confirm_agent(self, agent_name, employer_number, query, chat_history):
        """
        Placeholder for agent confirmation logic. Replace this with actual confirmation (user prompt, rule, etc).
        Returns True if confirmed, False otherwise.
        """
        # TODO: Implement actual confirmation logic here.
        # For now, always confirm for demonstration.
        return True

# Global instance
super_agent_instance = SuperAgent()

def super_agent_query(employer_number: int, type_of_message: str, query: str, media_id: str = "", formatted_json: Dict[str, Any] = {}) -> str:
    """Main entry point for the Super Agent"""
    return super_agent_instance.process_query(employer_number, type_of_message, query, media_id, formatted_json)