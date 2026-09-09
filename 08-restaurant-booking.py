# import os

# from dotenv import load_dotenv
# from loguru import logger
# from datetime import datetime


# from pipecat.audio.vad.silero import SileroVADAnalyzer
# from pipecat.evals.transport import EvalTransportParams
# from pipecat.pipeline.pipeline import Pipeline
# from pipecat.pipeline.worker import PipelineParams, PipelineWorker
# from pipecat.processors.aggregators.llm_context import LLMContext
# from pipecat.processors.aggregators.llm_response_universal import (
#     LLMContextAggregatorPair,
#     LLMUserAggregatorParams,
# )
# from pipecat.runner.types import RunnerArguments
# from pipecat.runner.utils import create_transport
# from pipecat.services.cartesia.tts import CartesiaTTSService
# from pipecat.services.deepgram.stt import DeepgramSTTService
# from pipecat.services.groq.llm import GroqLLMService
# from pipecat.services.llm_service import FunctionCallParams
# from pipecat.transports.base_transport import BaseTransport, TransportParams
# from pipecat.transports.daily.transport import DailyParams
# from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
# from pipecat.workers.runner import WorkerRunner
# from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
# from pymongo import AsyncMongoClient #pymongo means when i am writing the query do not mke other tasks to wait
# from datetime import datetime, timezone
# from pymongo.errors import DuplicateKeyError #to avoid duplicates



# load_dotenv(override=True) #without these the api keys in .env never load 

# mongo_client = AsyncMongoClient(os.environ["MONGO_URI"]) #connecting w server 
# db=mongo_client[os.environ["MONGO_DB"]]#selecting the db(in this case saffron)

# tables=db["tables"] #selecting the collection in db (in this case tables)
# reservations=db["reservations"] #selecting the collection in db (in this case reservations)


# #tool calls
# async def _free_tables(date:str, time:str, pax:int, seating:str |None = None):
#     """
    
#     Return capacity-sorted list of table docs that are free for this date/time/pax
#     (optionally filtered to a seating type). Shared by check_availability and book_table
#     so both agree on what "free" means.
    
#     """
#     booked= await reservations.distinct(
#         "table_id",{"date":date,"time":time,"status":"confirmed"}
#     )
#     query= {"_id": {"$nin":booked}, "capacity":{"$gte":pax}}
#     if seating:
#         query["seating"]=seating
#     cursor= tables.find(query,sort=[("capacity",1)])
#     return await cursor.to_list(length=None)


# async def check_availability(params: FunctionCallParams, date:str, time:str, pax:int):
#     """
#     Check whether a table is available.

#     Args:
#         date (str): The reservation date, e.g. "2026-08-20".
#         time (str): The reservation time in 24-hour format, e.g. "20:00".
#         pax (int): Number of people dining.

#     """
#     logger.info(f"Checking availability: {date} {time} for {pax}") #track weired behaviour from bot-this part is mostly for loggings to debug the issue 
#     free= await _free_tables(date,time,pax) #returns
#     seating_options= sorted({t["seating"] for t in free}) #creating a unique set of seating options so if we have 5 indoors then indoor will only come once 

#     await params.result_callback({
#         "available": len(free)>0,
#         "tables_left":len(free),
#         "seating_options":seating_options,
#     })
#     #await params.result_callback({"available": True, "tables_left": 3})  # Simulate availability check


# async def book_table(params : FunctionCallParams, name:str, date:str, time:str, pax:int, seating: str):
#     """
#     Book a Table
#     Args:
#         name (str): Name of the person making the reservation.
#         date(str): The reservation date, e.g. "2026-08-20".
#         time(str): The reservation time in 24-hour format e.g. "20:00".
#         pax(int): Number of people dining.
#         seating(str): Seating preference, e.g. "indoor" or "outdoor".
#     """
#     if not name or name.strip().lower() in ("not given","unknown","none",""):
#         await params.result_callback({
#             "error":"missing_name",
#             "message":"Cannot book without the guests real name . Ask the guest fir their name , then call book_table again"
#         })
#         return

#     free=  await _free_tables(date,time,pax,seating)
#     if not free:
#         await params.result_callback({
#             "error":"no_tables_available",
#             "message":f"No {seating} tables available for {pax} people"
#         })
#         return #stop here itself aage jaane ki zarurat hi nahi hai
#     for table in free:
#         try:
#             result= await reservations.insert_one({
#                 "table_id":table["_id"],
#                 "name":name,
#                 "date":date,
#                 "time":time,
#                 "pax":pax,
#                 "seating":seating,
#                 "status":"confirmed",
#                 "created_at":datetime.now(timezone.utc),
#             })
#         except DuplicateKeyError:
#             continue
#         else:
#             logger.info(f" booking table for {name} on {date} at {time} for {pax} people, seating preference:{seating}")
#             await params.result_callback({
#                 "status":"confirmed",
#                 "booking_id":str(result.inserted_id),
#             })
#             return
#     await params.result_callback({
#             "error":"tables already booked",
#             "message":f"Sorry all matching tables were just boked. please try a different time or date."
#         })
#     return

        



# SYSTEM_PROMPT = f"""You are Rina, the reservations host at Saffron, a mid-range Indian restaurant.

# Your responses are spoken aloud, so never use emojis, bullet points, asterisks, or any formatting that cannot be spoken. Keep replies to one or two short sentences. Speak warmly and naturally, like a person on the phone.

# Your only job is to take table reservations. You must collect all five of these before booking:
# - the guest's name
# - the date
# - the time
# - the number of people
# - seating preference (indoor or outdoor)
# Today is {datetime.now().strftime("%A, %Y-%m-%d")}. Always convert relative dates like "tomorrow" or "next Friday" into an absolute YYYY-MM-DD date before calling any tool. Never pass words like "tomorrow" as a date.

# Ask for exactly one missing detail per turn. Never ask two questions in the same reply. If the guest already gave a detail, do not ask again. Say each thing once and stop.

# Every value you pass to a tool must be something the guest actually said earlier in this conversation. Never fill in a plausible default. If the date, the time, or the number of people is missing, ask for it instead of calling a tool. Do not call check_availability twice with the same arguments, and never guess whether a table is free.

# <instruction>
# Never tell the guest a booking is confirmed unless book_table has actually returned a "status": "confirmed" result. Never narrate a booking outcome without first calling the corresponding tool.
# If the guest's requested seating type is not in seating_options from check_availability, tell them that seating type is unavailable and ask if they'd like one of the available options instead. Never confirm a seating type that check_availability did not list as available.
# If you have already asked about a detail in this conversation and the guest has not yet answered it, do not repeat it in the same message as other questions. Ask about exactly one topic and stop, even if multiple details are still missing.
# Never let internal tool calling or reasoning be spoken aloud.
# Never read booking IDs or internal reference numbers aloud.
# Never say dates in YYYY-MM-DD form aloud and never explain your reasoning. Say "tomorrow" or "Sunday the seventeenth".
# Never call book_table in the same turn as check_availability. After check_availability returns, you must speak the full reservation back and stop. Only call book_table after the guest has said yes to that specific question.
# If the guest asks about anything other than reservations, politely say you can only help with bookings."""  

# #bot intercatcs w user through browser(webrtc) or twilio (phone call) or daily (web app) or eval (test harness)
# transport_params = {
#     "eval": lambda: EvalTransportParams(
#         audio_in_enabled=True,
#         audio_out_enabled=True,
#     ),
#     "daily": lambda: DailyParams(
#         audio_in_enabled=True,
#         audio_out_enabled=True,
#     ),
#     "twilio": lambda: FastAPIWebsocketParams(
#         audio_in_enabled=True,
#         audio_out_enabled=True,
#     ),
#     "webrtc": lambda: TransportParams(
#         audio_in_enabled=True,
#         audio_out_enabled=True,
#     ),
# }

# async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
#     logger.info("Starting restruant booking bot")
#     stt=DeepgramSTTService(
#         api_key=os.environ["DEEPGRAM_API_KEY"],
#         settings=DeepgramSTTService.Settings(
#             # Deepgram's default endpointing finalizes on the slightest pause,
#             # which splits one spoken sentence across several user turns.
#             endpointing=800,
#             utterance_end_ms=1200,
#         ),
#     )

#     tts= CartesiaTTSService(
#         api_key=os.environ["CARTESIA_API_KEY"],
#         settings= CartesiaTTSService.Settings(
#             voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
#         ),
#     )

#     llm=GroqLLMService(
#         api_key=os.environ["GROQ_API_KEY"],
#         settings=GroqLLMService.Settings(
#             model="openai/gpt-oss-120b",

#             system_instruction=SYSTEM_PROMPT,
#             temperature=0.3,
#             # gpt-oss is a reasoning model. Groq streams its chain of thought in
#             # the same `content` field as the reply unless reasoning is hidden,
#             # so without this the bot speaks its own draft phrasings aloud.
#             extra={
#                 "reasoning_effort": "medium",
#                 # reasoning_format is Groq-specific, so it has to bypass the
#                 # OpenAI SDK's known-argument check.
#                 "extra_body": {"include_reasoning": False},
#             },
#         ),
#     )

 

   


#     context = LLMContext(tools=[check_availability, book_table])
#     user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
#         context,
#         user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
#     )

#     pipeline=Pipeline(
#         [
#             transport.input(),
#             stt,
#             user_aggregator,
#             llm,
#             tts,
#             transport.output(),
#             assistant_aggregator,
#         ]
#     )

#     worker = PipelineWorker(
#         pipeline,
#         params=PipelineParams(
#             enable_metrics=True,           
#             enable_usage_metrics=True,
#         ),
#         idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
#     )

#     # @transport.event_handler("on_client_connected")
#     # async def on_client_connected(transport,client):
#     #     logger.info("CLient connected")
#     #     context.add_message(
#     #         {
#     #             "role":"developer",
#     #             "content": " Say this exactly - Good evening, thank you for calling Saffron. I can help you book a table. How may I help you?"
#     #         }
#     #     )
#     #     await worker.queue_frames([LLMRunFrame()])

#     @transport.event_handler("on_client_connected")
#     async def on_client_connected(transport, client):
#         logger.info("Client connected")
#         # The assistant aggregator records the greeting in the context once it
#         # is spoken, so it must not be added here as well.
#         greeting = "Good evening, thank you for calling Saffron. I can help you book a table. How may I help you?"
#         await tts.queue_frame(TTSSpeakFrame(greeting))

#     @transport.event_handler("on_client_disconnected")
#     async def on_client_disconnected(transport, client):
#         logger.info("Client disconnected")
#         await worker.cancel()

#     runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

#     await runner.add_workers(worker)
#     await runner.run()


# async def bot(runner_args: RunnerArguments):
#     """Main bot entry point compatible with Pipecat Cloud."""
#     transport = await create_transport(runner_args, transport_params)
#     await run_bot(transport, runner_args)


# if __name__ == "__main__":
#     from pipecat.runner.run import main

#     main()

import os
import random

from dotenv import load_dotenv
from loguru import logger
from datetime import datetime


from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.evals.transport import EvalTransportParams
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pymongo import AsyncMongoClient
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.runner.utils import parse_telephony_websocket

load_dotenv(override=True)

mongo_client = AsyncMongoClient(os.environ["MONGO_URI"])
db = mongo_client[os.environ["MONGO_DB"]]

tables = db["tables"]
reservations = db["reservations"]

RESTAURANT_OPEN_TIME = "09:00"
RESTAURANT_CLOSE_TIME = "23:00"

def _is_within_operating_hours(time: str) -> bool:
    """Check if a HH:MM time string falls within restaurant operating hours (09:00-23:00)."""
    return RESTAURANT_OPEN_TIME <= time <= RESTAURANT_CLOSE_TIME


class OneQuestionGuardrail(FrameProcessor):
    """Hard backstop for the "ask exactly one question per turn" rule.

    Streaming-safe: processes each LLMTextFrame as it arrives, doesn't buffer
    the whole response, so it adds no measurable latency. Once the first "?"
    is seen in a turn, everything after it is dropped before reaching TTS.
    """

    def __init__(self):
        super().__init__()
        self._done_for_turn = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._done_for_turn = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMTextFrame):
            if self._done_for_turn:
                return  # swallow anything stacked after the first question

            text = frame.text
            if "?" in text:
                cutoff = text.index("?") + 1
                await self.push_frame(LLMTextFrame(text[:cutoff]))
                self._done_for_turn = True
            else:
                await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)


# tool calls
async def _free_tables(date: str, time: str, pax: int, seating: str | None = None):
    """
    Return capacity-sorted list of table docs that are free for this date/time/pax
    (optionally filtered to a seating type). Shared by check_availability and book_table
    so both agree on what "free" means.
    """
    booked = await reservations.distinct(
        "table_id", {"date": date, "time": time, "status": "confirmed"}
    )
    query = {"_id": {"$nin": booked}, "capacity": {"$gte": pax}}
    if seating:
        query["seating"] = seating
    cursor = tables.find(query, sort=[("capacity", 1)])
    return await cursor.to_list(length=None)


async def check_availability(params: FunctionCallParams, date: str, time: str, pax: int):
    """
    Check whether a table is available.

    Args:
        date (str): The reservation date, e.g. "2026-08-20".
        time (str): The reservation time in 24-hour format, e.g. "20:00".
        pax (int): Number of people dining.
    """
    if pax < 1:
        await params.result_callback({
            "error": "invalid_party_size",
            "message": "Ask the guest how many people will be dining before checking availability.",
        })
        return

    if not _is_within_operating_hours(time):
        await params.result_callback({
            "error": "outside_operating_hours",
            "message": f"Saffron is open from {RESTAURANT_OPEN_TIME} to {RESTAURANT_CLOSE_TIME}. Tell the guest we're closed at that time and ask if they'd like a different time within our hours.",

        })
        return

    logger.info(f"Checking availability: {date} {time} for {pax}")
    free = await _free_tables(date, time, pax)
    seating_options = sorted({t["seating"] for t in free})

    await params.result_callback({
        "available": len(free) > 0,
        "tables_left": len(free),
        "seating_options": seating_options,
    })


async def book_table(
    params: FunctionCallParams,
    name: str,
    date: str,
    time: str,
    pax: int,
    seating: str,
    confirmed: bool,
):
    """
    Book a Table
    Args:
        name (str): Name of the person making the reservation.
        date(str): The reservation date, e.g. "2026-08-20".
        time(str): The reservation time in 24-hour format e.g. "20:00".
        pax(int): Number of people dining.
        seating(str): Seating preference, e.g. "indoor" or "outdoor".
        confirmed (bool): Set to true only if the guest has explicitly said yes
            after hearing the full reservation details (date, time, pax, seating)
            read back to them. Never set this to true otherwise.
    """
    if not confirmed:
        await params.result_callback({
            "error": "not_confirmed",
            "message": "Read the full reservation details back to the guest and get explicit confirmation before calling book_table.",
        })
        return

    if not name or name.strip().lower() in ("not given", "unknown", "none", ""):
        await params.result_callback({
            "error": "missing_name",
            "message": "Cannot book without the guests real name. Ask the guest for their name, then call book_table again.",
        })
        return

    if pax < 1:
        await params.result_callback({
            "error": "invalid_party_size",
            "message": "Ask the guest how many people will be dining before booking.",
        })
        return

    if not _is_within_operating_hours(time):
        await params.result_callback({
            "error": "outside_operating_hours",
            "message": f"Saffron is open from {RESTAURANT_OPEN_TIME} to {RESTAURANT_CLOSE_TIME}. Tell the guest we're closed at that time and ask if they'd like a different time within our hours.",
        })
        return

    free = await _free_tables(date, time, pax, seating)
    if not free:
        await params.result_callback({
            "error": "no_tables_available",
            "message": f"No {seating} tables available for {pax} people",
        })
        return

    for table in free:
        try:
            result = await reservations.insert_one({
                "table_id": table["_id"],
                "name": name,
                "date": date,
                "time": time,
                "pax": pax,
                "seating": seating,
                "status": "confirmed",
                "created_at": datetime.now(timezone.utc),
            })
        except DuplicateKeyError:
            continue
        else:
            logger.info(f"booking table for {name} on {date} at {time} for {pax} people, seating preference:{seating}")
            await params.result_callback({
                "status": "confirmed",
                "booking_id": str(result.inserted_id),
            })
            return
    await params.result_callback({
        "error": "tables already booked",
        "message": "Sorry all matching tables were just booked. Please try a different time or date.",
    })
    return


SYSTEM_PROMPT = f"""You are Rina, the reservations host at Saffron, a mid-range Indian restaurant.

Your responses are spoken aloud, so never use emojis, bullet points, asterisks, or any formatting that cannot be spoken. Keep replies to one or two short sentences. Speak warmly and naturally, like a person on the phone.

Your only job is to take table reservations. You must collect all five of these before booking:
- the guest's name
- the date
- the time
- the number of people
- seating preference (indoor or outdoor)
Today is {datetime.now().strftime("%A, %Y-%m-%d")}. Always convert relative dates like "tomorrow" or "next Friday" into an absolute YYYY-MM-DD date before calling any tool. Never pass words like "tomorrow" as a date.

Ask for exactly one missing detail per turn. Never ask two questions in the same reply. If the guest already gave a detail, do not ask again. Say each thing once and stop.

Every value you pass to a tool must be something the guest actually said earlier in this conversation. Never fill in a plausible default. If the date, the time, or the number of people is missing, ask for it instead of calling a tool. Do not call check_availability twice with the same arguments, and never guess whether a table is free.

<instruction>
Never tell the guest a booking is confirmed unless book_table has actually returned a "status": "confirmed" result. Never narrate a booking outcome without first calling the corresponding tool.
If the guest's requested seating type is not in seating_options from check_availability, tell them that seating type is unavailable and ask if they'd like one of the available options instead. Never confirm a seating type that check_availability did not list as available.
If you have already asked about a detail in this conversation and the guest has not yet answered it, do not repeat it in the same message as other questions. Ask about exactly one topic and stop, even if multiple details are still missing.
Never let internal tool calling or reasoning be spoken aloud.
Never read booking IDs or internal reference numbers aloud.
Never say dates in YYYY-MM-DD form aloud and never explain your reasoning. Say "tomorrow" or "Sunday the seventeenth".
Never call book_table in the same turn as check_availability. After check_availability returns, you must speak the full reservation back and stop. Only call book_table after the guest has said yes to that specific question. Only set confirmed to true when the guest has clearly agreed.
Saffron is open from 9 AM to 11 PM daily. If the guest asks for a time outside these hours, politely tell them we're closed at that time and ask for a time within our operating hours — don't call check_availability or book_table for an out-of-hours time.
If the guest asks about anything other than reservations, politely say you can only help with bookings."""

transport_params = {
    "eval": lambda: EvalTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "telnyx": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True, 
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting restruant booking bot")
    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(
            endpointing=800,
            utterance_end_ms=1200,
        ),
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",
        ),
    )

    llm = GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model="openai/gpt-oss-120b",
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            
            extra={
                "reasoning_effort": "medium",
                "extra_body": {"include_reasoning": False},
            },
        ),
    )

    one_question_guardrail = OneQuestionGuardrail()

    context = LLMContext(tools=[check_availability, book_table])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            one_question_guardrail,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        greeting = "Good evening, thank you for calling Saffron. I can help you book a table. How may I help you?"
        await tts.queue_frame(TTSSpeakFrame(greeting))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()











