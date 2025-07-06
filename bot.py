import discord
from discord import app_commands
from discord.ext import commands
import json
import datetime
import os
from keep_alive import start_keep_alive

start_keep_alive()  # Health Check 서버 실행

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
ALLOWED_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
DATA_FILE = 'defense_data.json'

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

synced = False  # ✅ 슬래시 명령어 sync 중복 방지용

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

problem_data = {
    'message_id': None,
    'date': None
}

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

@bot.event
async def on_ready():
    global synced
    if not synced:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        synced = True
    print(f'✅ Logged in as {bot.user}')

@tree.command(name='rdf', description='오늘의 문제를 등록합니다.', guild=discord.Object(id=GUILD_ID))
@app_commands.describe(link='문제 링크')
async def rdf_command(interaction: discord.Interaction, link: str):
    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("❌ 지정된 채널에서만 사용 가능합니다.", ephemeral=True)
        return

    today = datetime.date.today().isoformat()
    msg = await interaction.channel.send(f"@everyone 오늘의 알고리즘 문제입니다!\n{link}\n🅾️ 이모지를 눌러주세요!")
    await msg.add_reaction("🅾️")

    problem_data['message_id'] = msg.id
    problem_data['date'] = today

    await interaction.response.send_message("✅ 문제를 전송했습니다.", ephemeral=True)

@tree.command(name='stat', description='나의 디펜스 통계를 확인합니다.', guild=discord.Object(id=GUILD_ID))
async def stat_command(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    user_data = data.get(uid, {})
    count = user_data.get('count', 0)
    streak = user_data.get('streak', 0)
    await interaction.response.send_message(
        f"🧍 사용자: {interaction.user.display_name}\n"
        f"🛡️ 디펜스 횟수: {count}\n"
        f"🔥 연속 성공 일수: {streak}일",
        ephemeral=True
    )

@tree.command(name='plot', description='전체 순위표를 확인합니다.', guild=discord.Object(id=GUILD_ID))
async def plot_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # ✅ 먼저 응답을 연기합니다.

    data = load_data()
    members = []
    for uid, val in data.items():
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f'사용자 {uid}'
        members.append((name, val.get('count', 0), val.get('streak', 0)))

    members.sort(key=lambda x: (-x[1], -x[2]))

    msg = "🏆 **디펜스 순위표**\n"
    for i, (name, count, streak) in enumerate(members[:10], 1):
        msg += f"{i}. {name} — 🛡️ {count}회, 🔥 {streak}일 연속\n"

    # ✅ 연기된 응답으로 메시지 전송
    await interaction.followup.send(msg, ephemeral=True)

@tree.command(name='edit_stat', description='(관리자 전용) 유저의 스탯을 수정합니다.', guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user='수정할 유저', count='디펜스 횟수', streak='연속 성공 일수')
async def edit_stat_command(interaction: discord.Interaction, user: discord.Member, count: int, streak: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    data = load_data()
    uid = str(user.id)
    data[uid] = {
        'count': count,
        'streak': streak,
        'last_date': datetime.date.today().isoformat()
    }
    save_data(data)

    await interaction.response.send_message(f"✅ {user.display_name} 님의 스탯이 수정되었습니다.", ephemeral=True)

@tree.command(name='download_data', description='(관리자 전용) 데이터 파일(json)을 다운로드합니다.', guild=discord.Object(id=GUILD_ID))
async def download_data_command(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    if not os.path.exists(DATA_FILE):
        await interaction.response.send_message("❌ 데이터 파일이 존재하지 않습니다.", ephemeral=True)
        return

    await interaction.response.send_message("📦 데이터 파일을 첨부합니다.", ephemeral=True, file=discord.File(DATA_FILE))

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != ALLOWED_CHANNEL_ID:
        return
    if payload.message_id != problem_data.get('message_id'):
        return
    if str(payload.emoji) != "🅾️":
        return

    today = datetime.date.today().isoformat()
    if problem_data.get('date') != today:
        return

    data = load_data()
    uid = str(payload.user_id)
    if uid == str(bot.user.id):
        return

    user_data = data.get(uid, {'count': 0, 'streak': 0, 'last_date': None})
    if user_data.get('last_date') == today:
        return

    last = user_data.get('last_date')
    if last:
        last_date = datetime.date.fromisoformat(last)
        delta = (datetime.date.today() - last_date).days
        if delta == 1:
            user_data['streak'] += 1
        else:
            user_data['streak'] = 1
    else:
        user_data['streak'] = 1

    user_data['count'] += 1
    user_data['last_date'] = today
    data[uid] = user_data
    save_data(data)

bot.run(TOKEN)
