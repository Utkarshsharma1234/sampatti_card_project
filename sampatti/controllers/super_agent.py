from cgitb import text
import json
import os
import time
import requests, re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
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
from .userControllers import send_audio_message
from .whatsapp_message import send_v2v_message, send_message_user
from .ai_agents import queryExecutor as onboarding_agent
from .cash_advance_agent import queryE as cash_advance_agent
from .tools import transcribe_audio_tool



load_dotenv()
print("✅ Successfully imported onboarding_agent")
print("✅ Successfully imported cash_advance_agent")


# Configuration
openai_api_key = os.environ.get("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key)
embedding = OpenAIEmbeddings(api_key=openai_api_key)

class IntentClassification(BaseModel):
    """Pydantic model for intent classification"""
    primary_intent: str  # "onboarding", "cash_advance", "general_conversation", "greeting", "help"
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
        
        # Intent keywords for classification
        self.intent_keywords = {
            "onboarding": [
                "onboard", "add worker", "new worker", "worker details", "employee details",
                "upi", "bank account", "pan number", "salary", "ifsc", "worker number",
                "add employee", "register worker", "setup worker", "worker information",
                "new employee", "employee setup", "worker registration"
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
            "general_conversation": [
                "hello", "hi", "how are you", "what can you do", "help", "thanks",
                "good morning", "good evening", "bye", "goodbye", "thank you",
                "hey", "capabilities", "what do you do"
            ]
        }
        
        self.setup_intent_classifier()
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
                3. "general_conversation" - Greetings, help requests, general chat
                4. "greeting" - Hello, hi, good morning, etc.
                5. "help" - What can you do, how to use, etc.
                
                Consider conversation history to understand context better.
                
                KEYWORDS FOR CLASSIFICATION:
                Onboarding: {onboarding_keywords}
                Cash Advance: {cash_advance_keywords}
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
            general_keywords=", ".join(self.intent_keywords["general_conversation"])
        )
        
        self.intent_classifier = self.intent_prompt | llm | intent_parser

    def setup_conversation_manager(self):
        """Setup the main conversation management system"""
        response_parser = PydanticOutputParser(pydantic_object=SuperAgentResponse)
        
        self.conversation_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """
                You are a Super AI Assistant for workplace management. You are the main interface between users and specialized systems.
                
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
                
                CAPABILITIES TO MENTION:
                ✅ Onboard new workers (collect UPI, bank details, PAN, salary info)
                ✅ Manage cash advances and repayments  
                ✅ Handle bonuses and salary deductions
                ✅ Generate salary payment links
                ✅ Track and update worker information
                
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
        self.vectordb.persist()

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
                response_text = """Hello! 👋 I'm your workplace management assistant. 

I can help you with:
• **Worker Onboarding** - Add new workers, collect their details (UPI, bank info, PAN, salary)
• **Cash Advances** - Manage advances, repayments, bonuses, and deductions
• **Payment Links** - Generate salary payment links
• **Worker Management** - Update and track worker information

What would you like to do today?"""
            elif any(word in user_message.lower() for word in ["help", "what can you do"]):
                response_text = """I'm here to help with your workplace management needs! Here's what I can assist you with:

🔹 **Worker Onboarding**
   - Add new workers to your system
   - Collect UPI or bank account details
   - Gather PAN numbers and salary information

🔹 **Cash Advance Management**
   - Process cash advance requests
   - Set up repayment schedules
   - Handle bonuses and salary deductions
   - Generate payment links

🔹 **General Support**
   - Answer questions about the system
   - Guide you through processes
   - Provide status updates

Just tell me what you need help with, and I'll take care of it!"""
            else:
                response_text = "I understand you'd like to chat! While I'm here to help with workplace management tasks, feel free to let me know if you need assistance with worker onboarding, cash advances, or payment processing."
        else:
            response_text = "I'm here to help! Please let me know what you'd like assistance with regarding worker management, onboarding, or cash advances."

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
            # If the message is audio, transcribe it first
            if type_of_message == "audio" and media_id:
                print(f"🔊 Transcribing audio with media ID: {media_id}")
                transcribed_text = transcribe_audio_tool(media_id)
                query = transcribed_text
                print(f"🎤 Transcribed text: {query}")
            
            # Get conversation history
            chat_history = self.get_sorted_chat_history(employer_number)
            print(f"📚 Chat History Length: {len(chat_history)} characters")
            
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
            
            # DYNAMIC ROUTING: Route to specialized agent if intent matches and confidence is high
            specialized_agents = ["cash_advance", "onboarding"]  # Add more agent names as needed
            if intent_analysis.primary_intent in specialized_agents and intent_analysis.confidence >= 0.7:
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

            # Return response - let the calling function handle message type routing
            # print(f"🎯 FINAL RESPONSE FROM {agent_used}: {response}")
            # if agent_used == "super_agent":
            #     if type_of_message=="audio":
            #         print("MESSAGE SENT SUCCESSFULLY: ", response) 
            #         return send_audio_message(response, "en-IN", employer_number)
            #     elif type_of_message=="text":
            #         print("MESSAGE SENT SUCCESSFULLY: ", response)
            #         send_message_user(employer_number, response)
            #         return f"MESSAGE SENT SUCCESSFULLY: {response}"
            # else:
            #     # For specialized agents, we assume they handle their own message sending
            #     print(f"✅ {agent_used.upper()} handled message sending internally")
            #     print("MESSAGE SENT SUCCESSFULLY: ",response)
            #     return f"MESSAGE SENT SUCCESSFULLY: {response}"
           
            if type_of_message=="text":
                print("MESSAGE SENT SUCCESSFULLY: ", response) 
                send_message_user(employer_number, response)
            if type_of_message=="audio":
                print("MESSAGE SENT SUCCESSFULLY: ", response) 
                send_audio_message(response, "en-IN", employer_number)
                
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

def super_agent_query(employer_number: int, type_of_message: str, query: str, media_id: str = "", formatted_json: Dict[str, Any] = {}) ->str:
    """Main entry point for the Super Agent"""
    return super_agent_instance.process_query(employer_number, type_of_message, query, media_id, formatted_json)