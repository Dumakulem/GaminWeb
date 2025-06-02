import os
import discord
from dotenv import load_dotenv
from ai_logic import chat_chain


load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"{client.user} is now online!")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.lower().startswith("-kusa "):
        query = message.content[6:].strip()
        username = message.author.name

        # Send thinking first
        thinking_msg = await message.channel.send("🧠 Thinking...")

        try:
            response = chat_chain.invoke({"input": f"{username}: {query}"})
            await thinking_msg.edit(content=response)
        except Exception as e:
            await thinking_msg.edit(content=f"❌ Error: {e}")

client.run(os.getenv("DISCORD_TOKEN"))
