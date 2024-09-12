import os
import pandas as pd
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
from telethon.tl.functions.messages import GetHistoryRequest
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')

session_file = 'my_telegram.session'
target_group = 1001717037581

async def get_all_messages(client):
    messages = []
    
    # Get the entity (group) object
    entity = await client.get_entity(target_group)
    
    # Fetch messages
    offset_id = 0
    limit = 100
    total_messages = 0
    
    while True:
        history = await client(GetHistoryRequest(
            peer=entity,
            offset_id=offset_id,
            offset_date=None,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=0,
            hash=0
        ))
        if not history.messages:
            break
        messages.extend(history.messages)
        total_messages = len(messages)
        if total_messages % 1000 == 0:
            print(f'Retrieved {total_messages} messages')
        offset_id = messages[-1].id
    
    return messages

async def get_all_dialogs(client):
    dialogs = []
    async for dialog in client.iter_dialogs():
        dialogs.append({
            'id': dialog.id,
            'name': dialog.name,
            'type': 'Channel' if dialog.is_channel else 'Group' if dialog.is_group else 'User'
        })
    return dialogs

async def main():
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.start()
    # await client.start(phone=PHONE_NUMBER)
    
    # print('Fetching all dialogs...')
    # all_dialogs = await get_all_dialogs(client)
    
    # print('Available groups and channels:')
    # for dialog in all_dialogs:
    #     if dialog['type'] in ['Channel', 'Group']:
    #         print(f"ID: {dialog['id']}, Name: {dialog['name']}, Type: {dialog['type']}")
    
    all_messages = await get_all_messages(client)
    print(f'Total messages retrieved: {len(all_messages)}')
    
    df = pd.DataFrame([
        {
            'id': msg.id,
            'date': msg.date,
            'message': msg.message,
            'sender_id': msg.sender_id,
            'reply_to_msg_id': msg.reply_to_msg_id,
            'views': msg.views,
            'forwards': msg.forwards,
            'edit_date': msg.edit_date,

        } for msg in all_messages
    ])

    csv_filename = 'telegram_messages.csv'
    df.to_csv(csv_filename, index=False)
    print(f'Messages saved to {csv_filename}')
    
    await client.disconnect()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())

