import asyncio 
import os 

from dotenv import load_dotenv
from pymongo import AsyncMongoClient

load_dotenv(override=True)

TABLES  = [
    {"_id": "T1", "capacity": 2,  "seating": "indoor"},
    {"_id": "T2", "capacity": 2,  "seating": "outdoor"},
    {"_id": "T3", "capacity": 4,  "seating": "indoor"},
    {"_id": "T4", "capacity": 4,  "seating": "outdoor"},
    {"_id": "T5", "capacity": 6,  "seating": "indoor"},
    {"_id": "T6", "capacity": 10, "seating": "outdoor"},
]

async def main():
    client= AsyncMongoClient(os.environ["MONGO_URI"]) #client connection to mongo server
    db= client[os.environ["MONGO_DB"]] #selecting the db saffron

    for t in TABLES:
        await db["tables"].replace_one({"_id": t["_id"]},t, upsert=True) #upsert means if the table already exists it will update it otherwise it will insert a new one

    print(await db["tables"].count_documents({}),"tables seeded")

    #avoids creation of duplicates this specific combination must never be repeated
    await db["reservations"].create_index(
        [("table_id",1),("date",1),("time",1)],
        unique=True,#rule made to avoid duplicates
        name="no_double_booking",
    )

    await client.close()

asyncio.run(main())

