import logging
from dataclasses import dataclass, field
from typing import Optional, Dict
import os
import pandas as pd
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import cartesia, deepgram, openai, groq, silero

from utils import load_prompt, get_free_slots, store_appointment, cancel_appointment


logger = logging.getLogger("appointment-booking")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


load_dotenv()

@dataclass
class UserData:
    appointment_csv: str = "appointments.csv"
    selected_date: Optional[str] = None
    selected_time: Optional[str] = None
    purpose: Optional[str] = None
    name: Optional[str] = None
    personas: Dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None
    ctx: Optional[JobContext] = None
    # Added for simple confirmation tracking
    awaiting_confirmation: bool = False

    def summarize(self) -> str:
        return "User data: Appointment booking system"

RunContext_T = RunContext[UserData]

class BaseAgent(Agent):
    async def on_enter(self) -> None:
        agent_name = self.__class__.__name__
        logger.info(f"Entering {agent_name}")

        userdata: UserData = self.session.userdata
        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"agent": agent_name})

        chat_ctx = self.chat_ctx.copy()

        if userdata.prev_agent:
            items_copy = self._truncate_chat_ctx(
                userdata.prev_agent.chat_ctx.items, keep_function_call=True
            )
            existing_ids = {item.id for item in chat_ctx.items}
            items_copy = [item for item in items_copy if item.id not in existing_ids]
            chat_ctx.items.extend(items_copy)

        chat_ctx.add_message(
            role="system",
            content=f"You are the {agent_name}. {userdata.summarize()}"
        )
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply()

    def _truncate_chat_ctx(self, items: list, keep_last_n_messages: int = 6,
                           keep_system_message: bool = False,
                           keep_function_call: bool = False) -> list:
        def _valid_item(item) -> bool:
            if not keep_system_message and item.type == "message" and item.role == "system":
                return False
            if not keep_function_call and item.type in ["function_call", "function_call_output"]:
                return False
            return True

        new_items = []
        for item in reversed(items):
            if _valid_item(item):
                new_items.append(item)
            if len(new_items) >= keep_last_n_messages:
                break
        new_items = new_items[::-1]

        while new_items and new_items[0].type in ["function_call", "function_call_output"]:
            new_items.pop(0)

        return new_items

class AppointmentAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt('appointment_prompt.yaml'),
            stt=deepgram.STT(),
            # Adjusted model name to a typical Groq llama3 model — adjust as per your deployment
            llm=groq.LLM(model="llama3-70b-8192"),
            tts=cartesia.TTS(),
            vad=silero.VAD.load()
        )

    @function_tool
    async def get_available_slots(self, context: RunContext_T, date: str) -> list[str]:
        userdata = context.userdata
        userdata.selected_date = date

        # Check if appointment file exists
        if not os.path.exists(userdata.appointment_csv):
            await self.session.say("Sorry, the appointment system is currently unavailable.")
            logger.error(f"Appointment CSV file not found: {userdata.appointment_csv}")
            return []

        try:
            slots = get_free_slots(userdata.appointment_csv, date)
        except Exception as e:
            await self.session.say("Sorry, I encountered an error retrieving slots.")
            logger.error(f"Error retrieving free slots: {e}")
            return []

        if slots:
            await self.session.say(f"The available slots on {date} are: {', '.join(slots)}")
        else:
            await self.session.say(f"Sorry, there are no available slots on {date}.")
        return slots

    @function_tool
    async def select_slot(self, context: RunContext_T, time: str) -> str:
        userdata = context.userdata

        # Validate slot is in available slots
        if userdata.selected_date is None:
            await self.session.say("Please select a date first.")
            return "Date not selected"

        try:
            slots = get_free_slots(userdata.appointment_csv, userdata.selected_date)
        except Exception as e:
            await self.session.say("Sorry, I couldn't verify available slots.")
            logger.error(f"Error verifying slots in select_slot: {e}")
            return "Error verifying slots"

        if time not in slots:
            await self.session.say(f"Sorry, {time} is not an available slot on {userdata.selected_date}. Please choose a valid time.")
            return "Invalid slot selected"

        userdata.selected_time = time
        await self.session.say(f"Okay, you've selected {time}. What is the purpose of your visit? (eye, dentist, general etc.)")
        return time

    @function_tool
    async def set_purpose(self, context: RunContext_T, purpose: str) -> str:
        context.userdata.purpose = purpose
        await self.session.say("Got it. What's your name?")
        return purpose

    @function_tool
    async def set_name_and_confirm(self, context: RunContext_T, name: str) -> str:
        userdata = context.userdata
        userdata.name = name

        confirm_msg = (
            f"Confirming your appointment on {userdata.selected_date} at {userdata.selected_time} "
            f"for {userdata.purpose} with name {userdata.name}. Shall I book it? (yes/no)"
        )
        userdata.awaiting_confirmation = True
        await self.session.say(confirm_msg)
        return confirm_msg

    @function_tool
    async def appointment_saved(self, context: RunContext_T, date: str, time: str, purpose: str, name: str) -> str:
        userdata = context.userdata
        saved = store_appointment(userdata.appointment_csv, date, time, purpose, name)

        status_msg = (
            "The appointment has been saved."
            if saved else
            "There was an error saving the appointment."
            )

        await self.session.say(status_msg)
        return status_msg
        

    @function_tool
    async def cancel_appointment(self, context: RunContext_T, name: str, date: str) -> str:
        appointment_csv = "appointments.csv"  # You can customize this path as needed
        success = cancel_appointment(appointment_csv, date, name)
        msg = "Your appointment has been canceled." if success else "Could not find an appointment to cancel."
        await self.session.say(msg)
        return msg

     

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    userdata = UserData(ctx=ctx)
    appointment_agent = AppointmentAgent()
    userdata.personas.update({"appointment": appointment_agent})

    session = AgentSession[UserData](userdata=userdata)
    await session.start(agent=appointment_agent, room=ctx.room)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
