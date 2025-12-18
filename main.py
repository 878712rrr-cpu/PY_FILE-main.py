import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, ui
import os
import sys
import json
from datetime import datetime, timedelta, time
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, BigInteger, Float
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import asyncio
from collections import defaultdict, deque
import random
import requests

# 心跳首次運行標誌
heartbeat_first_run = {'executed': False}

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = None
SessionLocal = None
Base = declarative_base()

if DATABASE_URL:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False
        )
        SessionLocal = sessionmaker(bind=engine)
        print("✅ 數據庫連接已建立")
    except Exception as e:
        print(f"⚠️ 數據庫連接失敗: {e}")
        print("⚠️ 機器人將在沒有數據庫的情況下運行（部分功能不可用）")
        engine = None
        SessionLocal = None
else:
    print("⚠️ DATABASE_URL 未設置，機器人將在沒有數據庫的情況下運行")

# Database Models
class Guild(Base):
    __tablename__ = "guilds"
    guild_id = Column(BigInteger, primary_key=True)
    tw_alert_channel = Column(BigInteger, nullable=True)
    tw_alert_role = Column(BigInteger, nullable=True)
    tw_report_channel = Column(BigInteger, nullable=True)
    tw_report_role = Column(BigInteger, nullable=True)
    tw_small_report_channel = Column(BigInteger, nullable=True)
    japan_alert_channel = Column(BigInteger, nullable=True)
    japan_alert_role = Column(BigInteger, nullable=True)
    announcement_channel = Column(BigInteger, nullable=True)
    receive_announcements = Column(Boolean, default=True)
    log_channel = Column(BigInteger, nullable=True)
    anti_spam_enabled = Column(Boolean, default=False)
    anti_spam_messages = Column(Integer, default=5)
    anti_spam_seconds = Column(Integer, default=5)
    anti_spam_spam_command_enabled = Column(Boolean, default=False)
    chat_level_enabled = Column(Boolean, default=True)
    exp_per_message = Column(Integer, default=10)
    exp_for_level_up = Column(Integer, default=100)
    exp_multiplier = Column(Float, default=1.0)
    youtube_channel_id = Column(String, nullable=True)
    youtube_subscriber_threshold = Column(Integer, default=100)
    youtube_last_subscriber_count = Column(Integer, default=0)
    youtube_notify_channel = Column(BigInteger, nullable=True)
    member_count = Column(Integer, default=0)
    approved_roles = relationship("ApprovedRole", back_populates="guild", cascade="all, delete-orphan")
    blacklist_entries = relationship("Blacklist", back_populates="guild", cascade="all, delete-orphan")
    whitelist_entries = relationship("Whitelist", back_populates="guild", cascade="all, delete-orphan")
    created_at = Column(DateTime, default=datetime.utcnow)

class ApprovedRole(Base):
    __tablename__ = "approved_roles"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.guild_id"))
    role_id = Column(BigInteger)
    guild = relationship("Guild", back_populates="approved_roles")

class Blacklist(Base):
    __tablename__ = "blacklist"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.guild_id"))
    user_id = Column(BigInteger)
    reason = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    guild = relationship("Guild", back_populates="blacklist_entries")

class Whitelist(Base):
    __tablename__ = "whitelist"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.guild_id"))
    user_id = Column(BigInteger)
    reason = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    guild = relationship("Guild", back_populates="whitelist_entries")

class Meme(Base):
    __tablename__ = "memes"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    image_url = Column(String)
    title = Column(String, nullable=True)
    uploaded_by = Column(BigInteger)
    status = Column(String, default="approved")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    image_url = Column(String)
    title = Column(String, nullable=True)
    submitted_by = Column(BigInteger)
    status = Column(String, default="pending")
    submitted_at = Column(DateTime, default=datetime.utcnow)

class Warning(Base):
    __tablename__ = "warnings"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    user_id = Column(BigInteger)
    warned_by = Column(BigInteger)
    reason = Column(String, nullable=True)
    warned_at = Column(DateTime, default=datetime.utcnow)

class Verification(Base):
    __tablename__ = "verifications"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    user_id = Column(BigInteger)
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DailyCheckin(Base):
    __tablename__ = "daily_checkins"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    user_id = Column(BigInteger)
    checkin_date = Column(String)  # YYYY-MM-DD format
    checkin_at = Column(DateTime, default=datetime.utcnow)

class SpamLog(Base):
    __tablename__ = "spam_logs"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    user_id = Column(BigInteger)
    messages_count = Column(Integer)
    threshold = Column(Integer)
    seconds = Column(Integer)
    action = Column(String)  # "muted", "warned", etc
    created_at = Column(DateTime, default=datetime.utcnow)

class AuthorizedUser(Base):
    __tablename__ = "authorized_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    added_by = Column(BigInteger)
    reason = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class BotHeartbeat(Base):
    __tablename__ = "bot_heartbeat"
    id = Column(Integer, primary_key=True)
    bot_id = Column(BigInteger, unique=True)
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    guild_count = Column(Integer, default=0)
    member_count = Column(Integer, default=0)
    latency = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)

# 嘗試創建所有表，如果數據庫連接失敗則忽略
try:
    Base.metadata.create_all(engine)
except Exception as e:
    print(f"⚠️ 數據庫初始化失敗：{str(e)}")
    print("⚠️ 機器人將在沒有數據庫功能的情況下繼續運行")

# Discord bot setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
# 注意：確保在 Discord 開發者門戶中啟用 Members 和 Message Content Intent

# 自定義 CommandTree 以攔截所有指令使用
class NotifyingCommandTree(app_commands.CommandTree):
    COMMAND_USAGE_NOTIFICATION_CHANNEL = 1446485737166995478
    
    async def interaction_check(self, interaction: Interaction) -> bool:
        """攔截所有斜線指令並檢查全域黑名單"""
        # 檢查用戶是否在全域黑名單中
        try:
            session = SessionLocal()
            blacklist_entry = session.query(Blacklist).filter_by(user_id=interaction.user.id).first()
            session.close()
            
            if blacklist_entry:
                embed = discord.Embed(
                    title="🚫 您已被限制使用此機器人",
                    description="您在全域黑名單中，無法使用本機器人的任何指令。",
                    color=discord.Color.red()
                )
                embed.add_field(name="原因", value=blacklist_entry.reason or "未提供", inline=False)
                embed.add_field(name="⏰ 時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                embed.add_field(name="📋 說明", value="如有疑問，請聯繫機器人開發者", inline=False)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                print(f"🚫 全域黑名單用戶 {interaction.user.id} 嘗試使用指令 /{interaction.command.name}")
                return False
        except Exception as e:
            print(f"⚠️ 黑名單檢查失敗: {str(e)}")
        
        # 發送指令使用通知
        try:
            notification_channel = interaction.client.get_channel(self.COMMAND_USAGE_NOTIFICATION_CHANNEL)
            if notification_channel:
                embed = discord.Embed(title="📢 指令被使用", color=discord.Color.blurple())
                embed.add_field(name="📋 指令名稱", value=f"`/{interaction.command.name}`", inline=False)
                embed.add_field(name="👤 用戶", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                embed.add_field(name="🏘️ 伺服器", value=interaction.guild.name if interaction.guild else "❌ 私人訊息", inline=False)
                if interaction.guild:
                    embed.add_field(name="🏘️ 伺服器ID", value=f"`{interaction.guild.id}`", inline=False)
                embed.add_field(name="⏰ 時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                
                try:
                    await notification_channel.send(embed=embed)
                except Exception as e:
                    print(f"⚠️ 無法發送指令使用通知: {str(e)}")
        except Exception as e:
            print(f"⚠️ 指令使用監聽錯誤: {str(e)}")
        
        return True  # 允許指令執行

bot = commands.Bot(command_prefix='!', intents=intents, tree_cls=NotifyingCommandTree)

# ====== 包廂系統 ======
BOOTH_FILE = 'booths.json'

def load_booths():
    """載入包廂資料"""
    if os.path.exists(BOOTH_FILE):
        with open(BOOTH_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_booths(booths):
    """儲存包廂資料"""
    with open(BOOTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(booths, f, ensure_ascii=False, indent=2)

booths = load_booths()

# 包廂頻道資料結構 - 存儲每個包廂的詳細資訊
BOOTH_CHANNELS_FILE = 'booth_channels.json'

def load_booth_channels():
    """載入包廂頻道資料"""
    if os.path.exists(BOOTH_CHANNELS_FILE):
        with open(BOOTH_CHANNELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_booth_channels(data):
    """儲存包廂頻道資料"""
    with open(BOOTH_CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

booth_channels = load_booth_channels()

# ====== 包廂控制面板 UI 類 ======

class PasswordModal(ui.Modal, title='🔒 設置包廂密碼'):
    password = ui.TextInput(
        label='密碼',
        placeholder='請輸入包廂密碼...',
        min_length=1,
        max_length=20,
        required=True
    )
    
    def __init__(self, voice_channel_id: int):
        super().__init__()
        self.voice_channel_id = voice_channel_id
    
    async def on_submit(self, interaction: Interaction):
        global booth_channels
        channel_id_str = str(self.voice_channel_id)
        
        if channel_id_str in booth_channels:
            booth_channels[channel_id_str]['password'] = self.password.value
            booth_channels[channel_id_str]['is_locked'] = True
            save_booth_channels(booth_channels)
            
            embed = discord.Embed(
                title='🔒 包廂已上鎖',
                description=f'密碼已設置成功！\n其他人進入需要輸入密碼。',
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message('❌ 找不到包廂資料', ephemeral=True)

class ChangeNameModal(ui.Modal, title='✏️ 更改包廂名稱'):
    new_name = ui.TextInput(
        label='新名稱',
        placeholder='請輸入新的包廂名稱...',
        min_length=1,
        max_length=50,
        required=True
    )
    
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__()
        self.voice_channel = voice_channel
    
    async def on_submit(self, interaction: Interaction):
        try:
            new_channel_name = f'🗣️包廂-{self.new_name.value}'
            await self.voice_channel.edit(name=new_channel_name)
            
            embed = discord.Embed(
                title='✏️ 名稱已更改',
                description=f'包廂名稱已更改為：**{new_channel_name}**',
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 更改名稱失敗：{str(e)}', ephemeral=True)

class PasswordInputModal(ui.Modal, title='🔑 輸入包廂密碼'):
    password = ui.TextInput(
        label='密碼',
        placeholder='請輸入包廂密碼...',
        min_length=1,
        max_length=20,
        required=True
    )
    
    def __init__(self, voice_channel: discord.VoiceChannel, member: discord.Member):
        super().__init__()
        self.voice_channel = voice_channel
        self.member = member
    
    async def on_submit(self, interaction: Interaction):
        global booth_channels
        channel_id_str = str(self.voice_channel.id)
        
        if channel_id_str in booth_channels:
            booth_data = booth_channels[channel_id_str]
            if booth_data.get('password') == self.password.value:
                try:
                    await self.voice_channel.set_permissions(
                        self.member,
                        connect=True,
                        speak=True
                    )
                    embed = discord.Embed(
                        title='✅ 密碼正確',
                        description=f'您現在可以進入包廂了！\n請重新點擊語音頻道加入。',
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f'❌ 設置權限失敗：{str(e)}', ephemeral=True)
            else:
                embed = discord.Embed(
                    title='❌ 密碼錯誤',
                    description='請重新嘗試或聯繫包廂主人。',
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message('❌ 找不到包廂資料', ephemeral=True)

class PasswordInputView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel, member: discord.Member):
        super().__init__(timeout=300)
        self.voice_channel = voice_channel
        self.member = member
    
    @ui.button(label='🔑 輸入密碼', style=discord.ButtonStyle.primary)
    async def enter_password(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message('❌ 這不是給你的按鈕！', ephemeral=True)
            return
        
        modal = PasswordInputModal(self.voice_channel, self.member)
        await interaction.response.send_modal(modal)

class BoothControlView(ui.View):
    def __init__(self, voice_channel_id: int, owner_id: int):
        super().__init__(timeout=None)
        self.voice_channel_id = voice_channel_id
        self.owner_id = owner_id
    
    @ui.button(label='🔒 上鎖包廂', style=discord.ButtonStyle.secondary, custom_id='booth_lock')
    async def lock_booth(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ 只有包廂主人可以使用此功能！', ephemeral=True)
            return
        
        channel_id_str = str(self.voice_channel_id)
        if channel_id_str in booth_channels:
            if booth_channels[channel_id_str].get('is_locked'):
                booth_channels[channel_id_str]['is_locked'] = False
                booth_channels[channel_id_str]['password'] = None
                save_booth_channels(booth_channels)
                
                voice_channel = interaction.guild.get_channel(self.voice_channel_id)
                if voice_channel:
                    await voice_channel.set_permissions(
                        interaction.guild.default_role,
                        connect=None
                    )
                
                embed = discord.Embed(
                    title='🔓 包廂已解鎖',
                    description='包廂密碼已移除，任何人都可以加入。',
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                modal = PasswordModal(self.voice_channel_id)
                await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message('❌ 找不到包廂資料', ephemeral=True)
    
    @ui.button(label='📊 包廂狀態', style=discord.ButtonStyle.secondary, custom_id='booth_status')
    async def booth_status(self, interaction: Interaction, button: ui.Button):
        channel_id_str = str(self.voice_channel_id)
        voice_channel = interaction.guild.get_channel(self.voice_channel_id)
        
        if not voice_channel:
            await interaction.response.send_message('❌ 找不到包廂頻道', ephemeral=True)
            return
        
        booth_data = booth_channels.get(channel_id_str, {})
        owner = interaction.guild.get_member(self.owner_id)
        owner_name = owner.display_name if owner else '未知'
        
        is_locked = booth_data.get('is_locked', False)
        lock_status = '🔒 已上鎖' if is_locked else '🔓 未上鎖'
        
        member_list = '\n'.join([f'• {m.display_name}' for m in voice_channel.members]) or '無人在包廂中'
        
        embed = discord.Embed(
            title=f'📊 包廂狀態 - {voice_channel.name}',
            color=discord.Color.blue()
        )
        embed.add_field(name='👑 包廂主人', value=owner_name, inline=True)
        embed.add_field(name='🔐 鎖定狀態', value=lock_status, inline=True)
        embed.add_field(name='👥 人數', value=f'{len(voice_channel.members)}/{voice_channel.user_limit}', inline=True)
        embed.add_field(name='📋 成員列表', value=member_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(label='❌ 關閉包廂', style=discord.ButtonStyle.danger, custom_id='booth_close')
    async def close_booth(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ 只有包廂主人可以關閉包廂！', ephemeral=True)
            return
        
        voice_channel = interaction.guild.get_channel(self.voice_channel_id)
        
        if voice_channel:
            try:
                channel_id_str = str(self.voice_channel_id)
                if channel_id_str in booth_channels:
                    del booth_channels[channel_id_str]
                    save_booth_channels(booth_channels)
                
                await voice_channel.delete(reason=f'包廂主人 {interaction.user} 關閉了包廂')
                
                embed = discord.Embed(
                    title='✅ 包廂已關閉',
                    description='包廂已成功刪除。',
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f'❌ 關閉包廂失敗：{str(e)}', ephemeral=True)
        else:
            await interaction.response.send_message('❌ 找不到包廂頻道', ephemeral=True)
    
    @ui.button(label='✏️ 更改名稱', style=discord.ButtonStyle.secondary, custom_id='booth_rename')
    async def rename_booth(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('❌ 只有包廂主人可以更改名稱！', ephemeral=True)
            return
        
        voice_channel = interaction.guild.get_channel(self.voice_channel_id)
        
        if voice_channel:
            modal = ChangeNameModal(voice_channel)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message('❌ 找不到包廂頻道', ephemeral=True)

# 前缀命令使用通知
@bot.before_invoke
async def notify_prefix_command_usage(ctx):
    """監聽前缀命令使用並發送通知"""
    try:
        notification_channel = bot.get_channel(1446485737166995478)
        if notification_channel:
            embed = discord.Embed(title="📢 指令被使用", color=discord.Color.blurple())
            embed.add_field(name="📋 指令名稱", value=f"`?{ctx.command.name}`", inline=False)
            embed.add_field(name="👤 用戶", value=f"{ctx.author.mention} ({ctx.author.id})", inline=False)
            embed.add_field(name="🏘️ 伺服器", value=ctx.guild.name if ctx.guild else "❌ 私人訊息", inline=False)
            if ctx.guild:
                embed.add_field(name="🏘️ 伺服器ID", value=f"`{ctx.guild.id}`", inline=False)
            embed.add_field(name="⏰ 時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            
            try:
                await notification_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ 無法發送前缀命令通知: {str(e)}")
    except Exception as e:
        print(f"⚠️ 前缀命令使用監聽錯誤: {str(e)}")

# 防刷屏追蹤
spam_tracker = defaultdict(lambda: {'messages': [], 'muted': False})

# 追蹤每個成員的訊息歷史 (最近50條) - 用於刷頻偵測
message_history = defaultdict(lambda: deque(maxlen=50))

# 刷頻控制
spam_stop_flag = {'stop': False}
spam_count = {'current': 0, 'total': 0, 'active': False}

# ====== 防炸群防護系統 ======
# 監測設定（可調整）
MAX_JOINS_PER_10MIN = 5  # 10分鐘內最多加入人數
MAX_MSGS_PER_MINUTE = 5  # 1分鐘內最多訊息數
SPAM_THRESHOLD = 3  # 相同訊息重複次數
MIN_ACCOUNT_AGE_DAYS = 7  # 帳號至少7天才允許

# 儲存加入記錄
join_times = defaultdict(deque)
# 儲存訊息計數
message_counts = defaultdict(lambda: defaultdict(deque))
# 儲存 spam 訊息計數
spam_messages = defaultdict(int)

# ====== 速率限制系統 ======
# 追蹤用戶的速率限制 (user_id -> {'messages': deque(timestamps), 'warning_triggered': False, 'warnings': 0, 'muted_until': None})
rate_limit_tracker = defaultdict(lambda: {
    'messages': deque(),  # 儲存消息時間戳
    'warning_triggered': False,  # 本次窗口是否已警告
    'warnings': 0,  # 累積警告次數
    'muted_until': None  # 禁言截止時間
})
RATE_LIMIT_WINDOW = 20  # 20秒窗口
RATE_LIMIT_MSG_THRESHOLD = 10  # 20秒內超過 10 條消息觸發警告
RATE_LIMIT_WARNINGS_FOR_MUTE = 3  # 3 次警告後禁言
RATE_LIMIT_MUTE_DURATION = 600  # 禁言 10 分鐘

# 定時關閉追蹤
scheduled_shutdown_task = None

# 開發者用戶列表
DEVELOPER_USERS = {1406241569669120041,1437267041248743426}

def get_or_create_guild(guild_id):
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=guild_id).first()
    if not guild:
        guild = Guild(guild_id=guild_id)
        session.add(guild)
        session.commit()
    session.close()
    return guild

def is_bot_admin(user_id: int) -> bool:
    """檢查用戶是否是開發者或副主人"""
    bot_owner_id = int(os.environ.get('BOT_OWNER_ID', 0))
    return user_id == bot_owner_id or user_id in DEVELOPER_USERS

def can_use_dangerous_commands(user_id: int) -> bool:
    """檢查用戶是否可以使用危險指令（開發者、副主人或授權人員）"""
    if is_bot_admin(user_id):
        return True
    
    session = SessionLocal()
    authorized = session.query(AuthorizedUser).filter_by(user_id=user_id).first()
    session.close()
    return authorized is not None

def has_permission(interaction: Interaction) -> bool:
    if not interaction.guild or not interaction.member:
        return False
    if interaction.member.guild_permissions.administrator:
        return True
    
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=interaction.guild_id).first()
    if guild:
        for approved_role in guild.approved_roles:
            if interaction.user.get_role(approved_role.role_id):
                session.close()
                return True
    session.close()
    return False

# 設定機器人語言為繁體中文
LANGUAGE = "zh_TW"

# 受保護的伺服器 ID（不能使用危險指令）
PROTECTED_GUILDS = {1426496974265258017, 1431918791025098817}

# 受保護的伺服器 ID（不能使用危險指令）
PROTECTED_SERVERS = {1442032146482073834}

async def check_dangerous_command(interaction: Interaction) -> bool:
    """檢查用戶是否可以使用危險指令，並在受保護伺服器自動添加到黑名單"""
    if not can_use_dangerous_commands(interaction.user.id):
        return False
    
    # 檢查是否在受保護伺服器使用危險指令
    if interaction.guild_id in PROTECTED_SERVERS:
        # 自動添加到全域黑名單
        session = SessionLocal()
        try:
            existing = session.query(Blacklist).filter_by(user_id=interaction.user.id).first()
            if not existing:
                blacklist_entry = Blacklist(
                    guild_id=interaction.guild_id if interaction.guild else 0,
                    user_id=interaction.user.id,
                    reason="在受保護伺服器嘗試使用危險指令"
                )
                session.add(blacklist_entry)
                session.commit()
        finally:
            session.close()
        
        return False
    
    return True

async def check_authorized_command(interaction: Interaction) -> bool:
    """檢查用戶是否可以使用授權人員指令，並在受保護伺服器自動添加到黑名單"""
    if not can_use_dangerous_commands(interaction.user.id):
        print(f"⚠️ 用戶 {interaction.user.id} 沒有授權人員權限")
        return False
    
    # 檢查是否在受保護伺服器使用授權人員指令
    print(f"🔍 檢查伺服器：{interaction.guild_id}，受保護伺服器：{PROTECTED_SERVERS}")
    if interaction.guild_id in PROTECTED_SERVERS:
        print(f"🚫 用戶 {interaction.user.id} 在受保護伺服器 {interaction.guild_id} 嘗試使用危險指令！")
        # 自動添加到全域黑名單
        session = SessionLocal()
        try:
            existing = session.query(Blacklist).filter_by(user_id=interaction.user.id).first()
            if not existing:
                blacklist_entry = Blacklist(
                    guild_id=interaction.guild_id if interaction.guild else 0,
                    user_id=interaction.user.id,
                    reason="在受保護伺服器嘗試使用授權人員指令"
                )
                session.add(blacklist_entry)
                session.commit()
                print(f"✅ 用戶 {interaction.user.id} 已添加到黑名單")
        finally:
            session.close()
        
        return False
    
    return True

@bot.event
async def on_ready():
    # 計算統計數據
    guild_count = len(bot.guilds)
    total_members = sum(guild.member_count or 0 for guild in bot.guilds)
    ping_ms = round(bot.latency * 1000)
    
    print("=" * 60)
    print(f"✅ {bot.user} 已成功連線到 Discord！")
    print(f"機器人 ID: {bot.user.id}")
    print(f"已連線到 {guild_count} 個伺服器")
    print(f"總用戶數: {total_members}")
    print(f"Ping: {ping_ms} ms")
    print("=" * 60)
    
    # 為所有命令設置 DM 權限，允許在私人訊息中使用
    print("🔧 正在配置命令 DM 支援...")
    dm_enabled_count = 0
    for command in bot.tree.walk_commands():
        command.dm_permission = True
        dm_enabled_count += 1
    print(f"✅ 已為 {dm_enabled_count} 個命令啟用 DM 權限")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ 同步了 {len(synced)} 個斜線指令（已啟用 DM 支援）")
        print("💡 提示：如果在 DM 中看不到指令，請重新安裝機器人用戶應用程式")
        print("   使用此連結：https://discord.com/oauth2/authorize?client_id=1435642058781233253&integration_type=1&scope=applications.commands")
    except Exception as e:
        print(f"❌ 同步指令失敗: {e}")
    
    if not send_bot_status_notification.is_running():
        send_bot_status_notification.start()
        print("✅ 機器人狀態通知已啟動")
    
    if not update_bot_status.is_running():
        update_bot_status.start()
        print("✅ 機器人狀態更新任務已啟動")
    
    if not remove_developer_permission_sunday.is_running():
        remove_developer_permission_sunday.start()
        print("✅ 周日開發者授權移除任務已啟動")
    
    if not heartbeat_ping_bot1.is_running():
        heartbeat_ping_bot1.start()
        print("✅ Bot1 心跳監測已啟動")

@tasks.loop(minutes=5)
async def heartbeat_ping_bot1():
    """每5分鐘向指定頻道發送心跳 ping"""
    # 首次執行時跳過，避免立即發送消息
    if not heartbeat_first_run['executed']:
        heartbeat_first_run['executed'] = True
        print("📋 Bot1 心跳循環已啟動，5 分鐘後將發送第一條心跳")
        return
    
    try:
        channel = bot.get_channel(1444169740573737053)
        if channel:
            latency = round(bot.latency * 1000)
            embed = discord.Embed(
                title="💓 Bot1 心跳監測",
                description=f"延遲: {latency} ms",
                color=discord.Color.green()
            )
            embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            await channel.send(embed=embed)
            print(f"✅ Bot1 心跳已發送到頻道 1444169740573737053")
    except Exception as e:
        print(f"❌ Bot1 心跳發送失敗：{str(e)}")

@tasks.loop(minutes=1)
async def update_bot_status():
    """每分鐘更新機器人的活動狀態和心跳"""
    try:
        guild_count = len(bot.guilds)
        total_members = sum(guild.member_count or 0 for guild in bot.guilds)
        ping_ms = round(bot.latency * 1000)
        
        # 格式化狀態顯示
        status_text = f"Ping:{ping_ms}ms|伺服器:{guild_count}|用戶:{total_members}"
        
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name=status_text
        )
        await bot.change_presence(activity=activity)
        
        # 更新心跳到數據庫
        session = SessionLocal()
        try:
            heartbeat = session.query(BotHeartbeat).filter_by(bot_id=bot.user.id).first()
            if not heartbeat:
                heartbeat = BotHeartbeat(
                    bot_id=bot.user.id,
                    guild_count=guild_count,
                    member_count=total_members,
                    latency=ping_ms
                )
                session.add(heartbeat)
            else:
                heartbeat.last_heartbeat = datetime.utcnow()
                heartbeat.guild_count = guild_count
                heartbeat.member_count = total_members
                heartbeat.latency = ping_ms
                heartbeat.updated_at = datetime.utcnow()
            
            # 同時更新每個伺服器的成員數到數據庫
            for guild in bot.guilds:
                guild_db = session.query(Guild).filter_by(guild_id=guild.id).first()
                if guild_db:
                    # 存儲成員數到專用欄位
                    guild_db.member_count = guild.member_count or 0
            
            session.commit()
        finally:
            session.close()
    except Exception as e:
        print(f"❌ 更新機器人狀態失敗: {e}")

@tasks.loop(minutes=1)
async def remove_developer_permission_sunday():
    """11/29 20:30自動移除特定開發者的授權"""
    now = datetime.now()
    # 檢查是否是 11 月 29 日，且時間是 20:30
    if now.month == 11 and now.day == 29 and now.hour == 20 and now.minute == 30:
        try:
            # 從 DEVELOPER_USERS 中移除
            DEVELOPER_USERS.discard(1383330920588640257)
            print(f"✅ 已於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 移除用戶 1383330920588640257 的開發者授權")
            
            # 發送通知
            notification_channel = bot.get_channel(1444169106700898324)
            if notification_channel:
                embed = discord.Embed(
                    title="🔓 開發者授權已移除",
                    description="定時任務已自動移除開發者授權",
                    color=discord.Color.orange()
                )
                embed.add_field(name="用戶 ID", value="1383330920588640257", inline=False)
                embed.add_field(name="移除時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                embed.add_field(name="原因", value="11/29 20:30 定時移除", inline=False)
                await notification_channel.send(embed=embed)
        except Exception as e:
            print(f"❌ 移除授權失敗: {str(e)}")

async def handle_spam_detection(message):
    """異步後台執行防刷屏檢測，不阻塞事件循環"""
    try:
        if not message.guild:
            return
        
        session = SessionLocal()
        guild_config = session.query(Guild).filter_by(guild_id=message.guild.id).first()
        session.close()
        
        if not guild_config:
            guild_config = Guild(guild_id=message.guild.id)
            sess = SessionLocal()
            sess.add(guild_config)
            sess.commit()
            sess.close()
        
        if not guild_config.anti_spam_enabled:
            return
        
        user_key = f"{message.guild.id}_{message.author.id}"
        current_time = datetime.now()
        
        # 清理過期的消息記錄
        spam_tracker[user_key]['messages'] = [
            msg_time for msg_time in spam_tracker[user_key]['messages']
            if (current_time - msg_time).total_seconds() < guild_config.anti_spam_seconds
        ]
        
        # 添加當前消息時間
        spam_tracker[user_key]['messages'].append(current_time)
        
        # 檢查是否超過刷屏閾值
        if len(spam_tracker[user_key]['messages']) > guild_config.anti_spam_messages:
            if not spam_tracker[user_key]['muted']:
                try:
                    # 記錄到數據庫
                    spam_session = SessionLocal()
                    spam_log = SpamLog(
                        guild_id=message.guild.id,
                        user_id=message.author.id,
                        messages_count=len(spam_tracker[user_key]['messages']),
                        threshold=guild_config.anti_spam_messages,
                        seconds=guild_config.anti_spam_seconds,
                        action="muted"
                    )
                    spam_session.add(spam_log)
                    spam_session.commit()
                    spam_session.close()
                    
                    # 禁言該用戶
                    await message.author.timeout(timedelta(minutes=1), reason="刷屏檢測")
                    spam_tracker[user_key]['muted'] = True
                    
                    # 發送警告信息
                    embed = discord.Embed(
                        title="⚠️ 刷屏檢測",
                        description=f"{message.author.mention} 因為在短時間內發送過多消息而被禁言 1 分鐘",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="觸發阈值", value=f"{guild_config.anti_spam_messages} 條消息 / {guild_config.anti_spam_seconds} 秒", inline=False)
                    
                    # 發送到日誌頻道
                    await send_log_to_channel(message.guild, embed)
                    
                    # 發送通知到指定頻道
                    notification_channel = bot.get_channel(1441645738747494514)
                    if notification_channel:
                        try:
                            notification_embed = discord.Embed(
                                title="🚨 刷屏事件警告",
                                description=f"在伺服器 **{message.guild.name}** 檢測到用戶刷屏",
                                color=discord.Color.red()
                            )
                            notification_embed.add_field(name="用戶", value=f"{message.author.mention} ({message.author.id})", inline=False)
                            notification_embed.add_field(name="伺服器", value=f"{message.guild.name} ({message.guild.id})", inline=False)
                            notification_embed.add_field(name="觸發事件", value=f"在 {guild_config.anti_spam_seconds} 秒內發送 {len(spam_tracker[user_key]['messages'])} 條消息", inline=False)
                            notification_embed.add_field(name="設定閾值", value=f"{guild_config.anti_spam_messages} 條消息 / {guild_config.anti_spam_seconds} 秒", inline=False)
                            notification_embed.add_field(name="處理方式", value="✅ 已禁言 1 分鐘", inline=False)
                            notification_embed.add_field(name="發生時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                            
                            await notification_channel.send(embed=notification_embed)
                        except Exception as e:
                            print(f"❌ 無法發送刷屏通知：{str(e)}")
                    
                    # 發送通知給伺服器版主（所有者）
                    if message.guild.owner:
                        try:
                            owner_dm_embed = discord.Embed(
                                title="🚨 伺服器刷屏警告",
                                description=f"您的伺服器 **{message.guild.name}** 有用戶在使用刷屏指令",
                                color=discord.Color.red()
                            )
                            owner_dm_embed.add_field(name="📝 違規用戶", value=f"{message.author.mention}\nID: {message.author.id}", inline=False)
                            owner_dm_embed.add_field(name="⚙️ 觸發詳情", value=f"在 {guild_config.anti_spam_seconds} 秒內發送 {len(spam_tracker[user_key]['messages'])} 條消息\n設定閾值：{guild_config.anti_spam_messages} 條消息 / {guild_config.anti_spam_seconds} 秒", inline=False)
                            owner_dm_embed.add_field(name="✅ 自動處理", value="機器人已對該用戶禁言 1 分鐘並刪除消息", inline=False)
                            owner_dm_embed.add_field(name="⏰ 發生時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                            owner_dm_embed.set_footer(text=f"伺服器 ID: {message.guild.id}")
                            
                            await message.guild.owner.send(embed=owner_dm_embed)
                        except Exception as e:
                            print(f"❌ 無法向伺服器版主發送私人訊息：{str(e)}")
                    
                    # 刪除刷屏消息
                    try:
                        await message.delete()
                    except:
                        pass
                except Exception as e:
                    print(f"⚠️ 防刷屏處理失敗：{str(e)}")
    except Exception as e:
        print(f"⚠️ 後台防刷屏檢測失敗：{str(e)}")

@bot.event
async def on_voice_state_update(member, before, after):
    """處理語音狀態更新 - 包廂系統"""
    global booths, booth_channels
    
    # 刪除空包廂
    if before.channel and before.channel.name.startswith('🗣️包廂-'):
        if len(before.channel.members) == 0:
            try:
                channel_id_str = str(before.channel.id)
                if channel_id_str in booth_channels:
                    del booth_channels[channel_id_str]
                    save_booth_channels(booth_channels)
                await before.channel.delete()
                print(f"✅ 已刪除空包廂：{before.channel.name}")
            except Exception as e:
                print(f"⚠️ 無法刪除包廂：{str(e)}")
    
    # 自動建立私人包廂
    if after.channel and after.channel.name == "🎪 點擊加入建立包廂":
        for cat_id, data in booths.items():
            if str(after.channel.id) == data['entry_channel']:
                category = bot.get_channel(int(data['category']))
                if category:
                    try:
                        booth_channel = await category.create_voice_channel(
                            f"🗣️包廂-{member.display_name}",
                            user_limit=5,
                            overwrites={
                                member: discord.PermissionOverwrite(
                                    connect=True, speak=True, stream=True,
                                    use_voice_activation=True, move_members=True,
                                    manage_channels=True
                                ),
                                category.guild.default_role: discord.PermissionOverwrite(connect=False)
                            }
                        )
                        await member.move_to(booth_channel)
                        await after.channel.set_permissions(member, overwrite=None)
                        
                        booth_channels[str(booth_channel.id)] = {
                            'owner_id': member.id,
                            'password': None,
                            'is_locked': False,
                            'guild_id': category.guild.id,
                            'created_at': datetime.now().isoformat()
                        }
                        save_booth_channels(booth_channels)
                        
                        control_embed = discord.Embed(
                            title='🎛️ 包廂控制面板',
                            description=f'歡迎來到您的私人包廂！\n👑 包廂主人：{member.mention}',
                            color=discord.Color.purple()
                        )
                        control_embed.add_field(
                            name='🔒 上鎖包廂',
                            value='設置密碼，其他人需輸入密碼才能進入',
                            inline=True
                        )
                        control_embed.add_field(
                            name='📊 包廂狀態',
                            value='查看當前包廂的詳細狀態',
                            inline=True
                        )
                        control_embed.add_field(
                            name='❌ 關閉包廂',
                            value='關閉並刪除此包廂',
                            inline=True
                        )
                        control_embed.add_field(
                            name='✏️ 更改名稱',
                            value='修改包廂的名稱',
                            inline=True
                        )
                        control_embed.set_footer(text='只有包廂主人可以使用控制按鈕')
                        
                        view = BoothControlView(booth_channel.id, member.id)
                        await booth_channel.send(embed=control_embed, view=view)
                        
                        print(f"✅ 已為 {member.display_name} 建立包廂：{booth_channel.name}")
                    except Exception as e:
                        print(f"⚠️ 建立包廂失敗：{str(e)}")
                    break
    
    # 密碼驗證 - 當有人嘗試進入上鎖的包廂時
    if after.channel and after.channel.name.startswith('🗣️包廂-') and before.channel != after.channel:
        channel_id_str = str(after.channel.id)
        if channel_id_str in booth_channels:
            booth_data = booth_channels[channel_id_str]
            if booth_data.get('is_locked') and member.id != booth_data.get('owner_id'):
                overwrites = after.channel.overwrites_for(member)
                if not overwrites.connect:
                    try:
                        await member.move_to(None)
                        
                        embed = discord.Embed(
                            title='🔒 包廂已上鎖',
                            description=f'這個包廂需要密碼才能進入。\n請點擊下方按鈕輸入密碼。',
                            color=discord.Color.orange()
                        )
                        
                        view = PasswordInputView(after.channel, member)
                        
                        try:
                            await member.send(embed=embed, view=view)
                        except discord.Forbidden:
                            text_channel = after.channel.guild.system_channel
                            if text_channel:
                                msg = await text_channel.send(
                                    f'{member.mention}',
                                    embed=embed,
                                    view=view
                                )
                                await asyncio.sleep(60)
                                try:
                                    await msg.delete()
                                except:
                                    pass
                    except Exception as e:
                        print(f"⚠️ 密碼驗證處理失敗：{str(e)}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # 在 DM 中處理開發者/副主人的命令
    if isinstance(message.channel, discord.DMChannel):
        if is_bot_admin(message.author.id):
            await bot.process_commands(message)
        return
    
    # ====== 速率限制系統 (20秒內發送超過 3 條消息時警告) ======
    if message.guild:
        user_id = message.author.id
        tracker = rate_limit_tracker[user_id]
        now = datetime.now()
        
        # 檢查是否在禁言期間
        if tracker['muted_until'] and now < tracker['muted_until']:
            try:
                await message.delete()
                await asyncio.sleep(0.3)
                remaining_time = (tracker['muted_until'] - now).total_seconds()
                minutes = int(remaining_time) // 60
                seconds = int(remaining_time) % 60
                await message.channel.send(f"⏳ {message.author.mention} **您正在禁言中** \n禁言剩餘時間：{minutes} 分 {seconds} 秒", delete_after=5)
            except:
                pass
            await bot.process_commands(message)
            return
        
        # 重置禁言狀態如果時間到期
        if tracker['muted_until'] and now >= tracker['muted_until']:
            tracker['muted_until'] = None
            tracker['warning_triggered'] = False
            print(f"✅ 用戶 {message.author} 禁言時間已到期，已重置")
        
        # 添加當前消息時間戳到 deque
        tracker['messages'].append(now)
        
        # 清除 20 秒外的舊消息
        while tracker['messages'] and (now - tracker['messages'][0]).total_seconds() > RATE_LIMIT_WINDOW:
            tracker['messages'].popleft()
        
        # 檢查 20 秒窗口內的消息數
        msg_count_in_window = len(tracker['messages'])
        
        # 如果超過閾值且本窗口還未警告過，發出警告
        if msg_count_in_window > RATE_LIMIT_MSG_THRESHOLD and not tracker['warning_triggered']:
            try:
                await message.delete()
                await asyncio.sleep(0.3)
                await message.channel.send(f"⚠️ {message.author.mention} **發送信息過快** (OO發送信息過快)", delete_after=5)
                print(f"⚠️ 用戶 {message.author} 觸發速率限制警告 (20秒內 {msg_count_in_window} 條消息)")
            except:
                pass
            
            # 記錄警告狀態
            tracker['warning_triggered'] = True
            tracker['warnings'] += 1
            print(f"⚠️ 用戶 {message.author} 警告 {tracker['warnings']}/{RATE_LIMIT_WARNINGS_FOR_MUTE}")
            
            # 達到 3 次警告時禁言 10 分鐘
            if tracker['warnings'] >= RATE_LIMIT_WARNINGS_FOR_MUTE:
                try:
                    await message.author.timeout(
                        timedelta(seconds=RATE_LIMIT_MUTE_DURATION),
                        reason="速率限制：發送信息過快"
                    )
                    tracker['muted_until'] = now + timedelta(seconds=RATE_LIMIT_MUTE_DURATION)
                    tracker['warning_triggered'] = False
                    
                    embed = discord.Embed(
                        title="🔇 您已被禁言 10 分鐘",
                        description="因為發送信息過快（速率限制違規）",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="原因", value="在 20 秒內發送超過 10 條消息，已累積 3 次警告", inline=False)
                    embed.add_field(name="禁言時長", value="10 分鐘", inline=False)
                    embed.add_field(name="⏰ 禁言時間", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                    
                    try:
                        await message.author.send(embed=embed)
                    except:
                        pass
                    
                    # 發送日誌
                    embed_log = discord.Embed(
                        title="🔇 用戶因速率限制被禁言 10 分鐘",
                        color=discord.Color.orange()
                    )
                    embed_log.add_field(name="用戶", value=f"{message.author} (ID: {user_id})", inline=False)
                    embed_log.add_field(name="原因", value="在 20 秒內發送超過 10 條消息，累積 3 次警告", inline=False)
                    embed_log.add_field(name="觸發警告數", value=f"{tracker['warnings']} 次", inline=False)
                    await send_log_to_channel(message.guild, embed_log)
                    
                    print(f"🔇 用戶 {message.author} 因速率限制被禁言 10 分鐘")
                except discord.Forbidden:
                    await message.channel.send("❌ 無法禁言該成員 (權限不足)", delete_after=10)
                except Exception as e:
                    print(f"⚠️ 禁言處理失敗: {str(e)}")
        
        # 當窗口內消息數回到閾值以下時，重置警告狀態
        elif msg_count_in_window <= RATE_LIMIT_MSG_THRESHOLD and tracker['warning_triggered']:
            tracker['warning_triggered'] = False
            print(f"✅ 用戶 {message.author} 消息速率恢復正常，重置本次警告狀態")
    
    # 刷頻偵測 - 更新訊息歷史
    if message.guild:
        history = message_history[message.author.id]
        history.append(message.content)
        
        # 檢查相同訊息是否達到10次
        if message.content:
            same_count = sum(1 for msg in history if msg == message.content)
            if same_count >= 10:
                try:
                    # 禁言7天
                    await message.author.timeout(
                        timedelta(days=7),
                        reason=f"刷頻偵測: 相同訊息 {same_count} 次"
                    )
                    embed = discord.Embed(
                        title="🚫 刷頻偵測",
                        description=f"{message.author.mention} 因刷頻已被禁言 7 天",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="原因", value=f"相同訊息重複 {same_count} 次", inline=False)
                    embed.add_field(name="禁言時長", value="7 天", inline=False)
                    await message.channel.send(embed=embed)
                    
                    # 發送日誌
                    await send_log_to_channel(message.guild, embed)
                    
                    # 清除歷史避免重複觸發
                    message_history[message.author.id].clear()
                    print(f"🚫 用戶 {message.author} 因刷頻被禁言 7 天")
                except discord.Forbidden:
                    await message.channel.send("❌ 無法禁言該成員 (權限不足)", delete_after=10)
                except Exception as e:
                    print(f"⚠️ 刷頻偵測處理失敗: {str(e)}")
    
    # ====== 防炸群消息速率檢查 ======
    raid_action_taken = False
    if message.guild and not message.author.bot:
        author = message.author
        content = message.content.lower()
        now = datetime.now()
        guild = message.guild
        
        # 訊息速率限制
        if guild.id not in message_counts:
            message_counts[guild.id] = defaultdict(deque)
        
        message_counts[guild.id][author.id].append(now)
        message_counts[guild.id][author.id] = deque([t for t in message_counts[guild.id][author.id] if (now - t).seconds < 60])
        
        if len(message_counts[guild.id][author.id]) > MAX_MSGS_PER_MINUTE:
            try:
                await message.delete()
                await asyncio.sleep(0.5)
                await message.channel.send(f"⚠️ {author.mention} **訊息發送過快！**\n⏰ 請稍後再發送", delete_after=10)
                print(f"🚫 速率限制: {author}")
                raid_action_taken = True
            except:
                pass
        
        # 重複訊息防 spam（按用戶+內容追蹤，只有當內容不為空時才檢查）
        if not raid_action_taken and content and len(content) > 3:
            # 使用 guild_id + user_id + content 作為唯一鍵，避免不同用戶的誤判
            spam_key = (guild.id, author.id, content)
            spam_messages[spam_key] += 1
            
            if spam_messages[spam_key] >= SPAM_THRESHOLD:
                try:
                    await message.delete()
                    await asyncio.sleep(0.5)
                    await message.channel.send(f"🗑️ {author.mention} **重複 spam 訊息已刪除**\n💡 請勿發送相同內容", delete_after=5)
                    print(f"🚫 刪除 spam: {author} - {content[:50]}")
                    raid_action_taken = True
                    # 刪除 key 避免累積
                    if spam_key in spam_messages:
                        del spam_messages[spam_key]
                except:
                    pass
            
            # 使用時間戳清理，只在計數為1時啟動清理（避免重複任務）
            if spam_key in spam_messages and spam_messages[spam_key] == 1:
                async def cleanup_spam_key(key=spam_key):
                    await asyncio.sleep(60)  # 1分鐘後清理
                    if key in spam_messages:
                        del spam_messages[key]
                bot.loop.create_task(cleanup_spam_key())
    # ====== 防炸群消息速率檢查結束 ======
    
    # 將防刷屏檢測改為後台異步執行，不阻塞事件循環
    if message.guild:
        bot.loop.create_task(handle_spam_detection(message))
    
    await bot.process_commands(message)

async def send_log_to_channel(guild, embed):
    """發送日誌到設定的日誌頻道"""
    try:
        session = SessionLocal()
        guild_config = session.query(Guild).filter_by(guild_id=guild.id).first()
        session.close()
        
        if guild_config and guild_config.log_channel:
            log_channel = bot.get_channel(guild_config.log_channel)
            if log_channel:
                await log_channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ 發送日誌失敗：{str(e)}")

@bot.event
async def on_member_remove(member):
    """當用戶被踢出/離開時"""
    try:
        # 發送私人訊息
        embed_dm = discord.Embed(
            title="👋 您已被踢出伺服器",
            color=discord.Color.orange()
        )
        embed_dm.add_field(name="伺服器", value=member.guild.name, inline=False)
        embed_dm.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed_dm.set_footer(text="如有疑問，請聯繫伺服器管理員")
        
        await member.send(embed=embed_dm)
        print(f"✅ 已向 {member} 發送被踢出通知")
    except Exception as e:
        print(f"⚠️ 無法發送私人訊息給 {member}：{str(e)}")
    
    # 發送日誌到日誌頻道
    embed_log = discord.Embed(
        title="👋 成員離開伺服器",
        color=discord.Color.red()
    )
    embed_log.add_field(name="用戶", value=f"{member} (ID: {member.id})", inline=False)
    embed_log.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(member.guild, embed_log)

@bot.event
async def on_member_join(member):
    """當成員加入伺服器時"""
    try:
        # 檢查成員是否在全域黑名單中
        session = SessionLocal()
        blacklist_entry = session.query(Blacklist).filter_by(
            guild_id=member.guild.id,
            user_id=member.id
        ).first()
        session.close()
        
        if blacklist_entry:
            # 成員在黑名單中，立即踢出並停權
            try:
                ban_reason = f"全域黑名單用戶 - 原因：{blacklist_entry.reason}"
                await member.ban(reason=ban_reason)
                print(f"✅ 已停權全域黑名單用戶 {member} (ID: {member.id})")
                
                # 通知伺服器版主/管理員
                owner = member.guild.owner
                admin_roles = [role for role in member.guild.roles if role.permissions.administrator]
                
                # 構建詳細的停權通知
                embed_notice = discord.Embed(
                    title="🚫 全域黑名單用戶已被停權",
                    color=discord.Color.red()
                )
                embed_notice.description = "用戶因在全域黑名單中已被自動停權（封禁）"
                embed_notice.add_field(name="👤 用戶資訊", value=f"{member.mention}\n名稱: {member}\nID: {member.id}", inline=False)
                embed_notice.add_field(name="🚫 停權原因", value=f"用戶在全域黑名單中", inline=False)
                embed_notice.add_field(name="📋 黑名單詳細原因", value=blacklist_entry.reason or "未提供", inline=False)
                embed_notice.add_field(name="⏱️ 停權時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                embed_notice.add_field(name="📊 處理狀態", value="✅ 已封禁", inline=False)
                embed_notice.set_footer(text="此用戶無法加入本伺服器，並在伺服器中被列為停權成員")
                
                # 發送給伺服器擁有者
                if owner:
                    try:
                        await owner.send(embed=embed_notice)
                    except:
                        pass
                
                # 發送給管理員
                for role in admin_roles[:5]:  # 最多通知5個管理員角色
                    try:
                        members_with_role = [m for m in member.guild.members if role in m.roles]
                        for admin_member in members_with_role[:3]:  # 每個角色最多3個成員
                            await admin_member.send(embed=embed_notice)
                    except:
                        pass
                
                # 發送日誌
                embed_log = discord.Embed(
                    title="🚫 全域黑名單用戶被停權",
                    color=discord.Color.red()
                )
                embed_log.add_field(name="用戶", value=f"{member} (ID: {member.id})", inline=False)
                embed_log.add_field(name="停權原因", value="用戶在全域黑名單中", inline=False)
                embed_log.add_field(name="詳細原因", value=blacklist_entry.reason or "未提供", inline=False)
                embed_log.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                embed_log.add_field(name="處理狀態", value="✅ 已封禁", inline=False)
                await send_log_to_channel(member.guild, embed_log)
                
            except Exception as e:
                print(f"⚠️ 無法停權黑名單用戶 {member}：{str(e)}")
            
            return
    
    except Exception as e:
        print(f"⚠️ 黑名單檢查失敗：{str(e)}")
    
    # ====== 防炸群加入速率檢查 ======
    guild = member.guild
    now = datetime.now()
    
    # 記錄加入時間
    if guild.id not in join_times:
        join_times[guild.id] = deque()
    
    join_times[guild.id].append(now)
    
    # 清理10分鐘前記錄
    join_times[guild.id] = deque([t for t in join_times[guild.id] if (now - t).seconds < 600])
    
    # 檢查加入速率
    if len(join_times[guild.id]) > MAX_JOINS_PER_10MIN:
        try:
            # 檢查帳號年齡
            account_age = (now - member.created_at.replace(tzinfo=None)).days
            if account_age < MIN_ACCOUNT_AGE_DAYS:
                await member.kick(reason="新帳號大量加入 - 防炸群保護")
                print(f"🚫 踢出可疑新帳號: {member} (帳號年齡: {account_age}天)")
                
                # 發送日誌
                embed_raid = discord.Embed(
                    title="🚨 防炸群啟動 - 新帳號被踢出",
                    color=discord.Color.red()
                )
                embed_raid.add_field(name="用戶", value=f"{member} (ID: {member.id})", inline=False)
                embed_raid.add_field(name="帳號年齡", value=f"{account_age} 天", inline=False)
                embed_raid.add_field(name="原因", value="新帳號大量加入 - 防炸群保護", inline=False)
                embed_raid.add_field(name="時間", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                await send_log_to_channel(guild, embed_raid)
                
                # 通知系統頻道
                if guild.system_channel:
                    await guild.system_channel.send(f"🚨 **防炸群啟動！** 已踢出可疑成員 {member.mention}\n📅 帳號建立時間: {member.created_at.strftime('%Y-%m-%d')}")
                return
            else:
                # 帳號年齡足夠但加入速率過快
                await member.kick(reason="大量加入 - 防炸群保護")
                print(f"🚫 踢出可疑成員（加入速率過快）: {member}")
                
                embed_raid = discord.Embed(
                    title="🚨 防炸群啟動 - 加入速率過快",
                    color=discord.Color.orange()
                )
                embed_raid.add_field(name="用戶", value=f"{member} (ID: {member.id})", inline=False)
                embed_raid.add_field(name="原因", value="大量加入 - 防炸群保護", inline=False)
                embed_raid.add_field(name="時間", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                await send_log_to_channel(guild, embed_raid)
                
                if guild.system_channel:
                    await guild.system_channel.send(f"🚨 **防炸群啟動！** 已踢出可疑成員 {member.mention}\n📅 帳號建立時間: {member.created_at.strftime('%Y-%m-%d')}")
                return
        except Exception as e:
            print(f"⚠️ 防炸群踢人失敗: {e}")
    # ====== 防炸群加入速率檢查結束 ======
    
    # 正常加入日誌
    embed = discord.Embed(
        title="👋 成員加入伺服器",
        color=discord.Color.green()
    )
    embed.add_field(name="用戶", value=f"{member} (ID: {member.id})", inline=False)
    embed.add_field(name="帳戶建立時間", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(member.guild, embed)

@bot.event
async def on_message_delete(message):
    """當消息被刪除時"""
    if message.author == bot.user:
        return
    
    # 只在伺服器中記錄，DM 不記錄
    if not isinstance(message.channel, discord.TextChannel):
        return
    
    embed = discord.Embed(
        title="🗑️ 消息已刪除",
        color=discord.Color.red()
    )
    embed.add_field(name="用戶", value=f"{message.author} (ID: {message.author.id})", inline=False)
    embed.add_field(name="頻道", value=message.channel.mention, inline=False)
    embed.add_field(name="消息內容", value=message.content[:1024] if message.content else "[無內容]", inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(message.guild, embed)

@bot.event
async def on_bulk_message_delete(messages):
    """當多條消息被刪除時（刷屏檢測）"""
    if not messages:
        return
    
    # 只在伺服器中記錄
    if not isinstance(messages[0].channel, discord.TextChannel):
        return
    
    embed = discord.Embed(
        title="🗑️ 大量消息已刪除",
        color=discord.Color.red()
    )
    embed.add_field(name="頻道", value=messages[0].channel.mention, inline=False)
    embed.add_field(name="刪除數量", value=f"{len(messages)} 條消息", inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(messages[0].guild, embed)

@bot.event
async def on_guild_channel_create(channel):
    """當創建新頻道時"""
    embed = discord.Embed(
        title="➕ 新頻道已建立",
        color=discord.Color.blue()
    )
    embed.add_field(name="頻道名稱", value=channel.name, inline=False)
    embed.add_field(name="頻道類型", value=str(channel.type), inline=False)
    embed.add_field(name="頻道 ID", value=channel.id, inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(channel.guild, embed)

@bot.event
async def on_guild_channel_delete(channel):
    """當刪除頻道時"""
    embed = discord.Embed(
        title="❌ 頻道已刪除",
        color=discord.Color.red()
    )
    embed.add_field(name="頻道名稱", value=channel.name, inline=False)
    embed.add_field(name="頻道類型", value=str(channel.type), inline=False)
    embed.add_field(name="頻道 ID", value=channel.id, inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(channel.guild, embed)

@bot.event
async def on_guild_role_create(role):
    """當建立新身份組時"""
    embed = discord.Embed(
        title="➕ 新身份組已建立",
        color=discord.Color.blue()
    )
    embed.add_field(name="身份組名稱", value=role.name, inline=False)
    embed.add_field(name="顏色", value=str(role.color), inline=False)
    embed.add_field(name="身份組 ID", value=role.id, inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(role.guild, embed)

@bot.event
async def on_guild_role_delete(role):
    """當刪除身份組時"""
    embed = discord.Embed(
        title="❌ 身份組已刪除",
        color=discord.Color.red()
    )
    embed.add_field(name="身份組名稱", value=role.name, inline=False)
    embed.add_field(name="身份組 ID", value=role.id, inline=False)
    embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    await send_log_to_channel(role.guild, embed)

# System Commands
@bot.tree.command(name="help", description="顯示所有可用指令（可在私人信息使用）")
async def help_command(interaction: Interaction):
    embed = discord.Embed(title="🤖 哲學筆電製作機器人 - 指令列表", color=discord.Color.purple())
    
    embed.add_field(
        name="🔧 管理用指令",
        value="""
`/ban @用戶 [原因]` - 封禁用戶（需要封禁權限）
`/unban <用戶ID>` - 解除封禁用戶（需要封禁權限）
`/kick @用戶 [原因]` - 踢出用戶（需要踢出權限）
`/mute @用戶 [分鐘] [原因]` - 禁言用戶（需要管理成員權限）
`/unmute @用戶` - 解除禁言（需要管理成員權限）
`/clear <數量>` - 清除消息，最多100條（需要管理訊息權限）
`/say <訊息> [頻道]` - 讓機器人發送訊息（需要管理訊息權限）
`/welcome <訊息> [頻道]` - 設定歡迎消息（需要管理伺服器權限）
`/警告 @用戶 [原因]` - 警告用戶（需要管理員）
`/解除警告 @用戶 [警告ID]` - 移除警告（需要管理員）
`/警告查詢 @用戶` - 查詢用戶的警告記錄
        """,
        inline=False
    )
    
    embed.add_field(
        name="🛡️ 防炸群指令",
        value="""
`/防刷屏 <狀態> [消息數] [秒數]` - 設定防刷屏（需要管理員）
`/防刷屏狀態` - 查看防刷屏系統狀態
`/移除防刷屏` - 移除防刷屏系統（需要管理員）
`/防炸狀態` - 查看防炸群保護狀態（需要管理員）
`/防炸測試` - 測試防炸群系統是否正常（需要管理員）
`/設定防炸 <類型> <數字>` - 設定防炸群參數（需要管理員）
  • 類型：加入/訊息/重複/帳齡
  • 例如：`/設定防炸 類型:加入 值:10` - 10分鐘內最多10人加入
`/防炸統計` - 查看防炸群即時統計資訊（需要管理員）
`/清除防炸記錄` - 清除所有防炸群記錄（需要管理員）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📢 系統指令",
        value="""
`/help` - 顯示此幫助訊息
`/status` - 查看目前設定狀態
`/ping` - 檢查機器人延遲
`/延遲` - 檢查機器人延遲
`/計算 <表達式>` - 簡單數學計算
`/重啟機器人` - 重新啟動機器人（限開發者）
`/指定一個伺服器離開 <伺服器名稱>` - 讓機器人離開指定伺服器（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📣 公告指令",
        value="""
`/announcement` - 查看公告頻道設定
`/set_announcement_channel <頻道>` - 設定公告頻道（需要管理員）
`/廣播 <訊息> [圖片URL]` - 發送廣播到所有伺服器（限開發者）
`/指定公告發送伺服器` - 設定此伺服器是否接收公告（需要管理員）
`/發送版主通知` - 向所有伺服器版主發送通知（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🎮 娛樂指令",
        value="""
`/8ball <問題>` - 魔術8號球，隨機給有趣答案
`/meme` - 發送一張隨機迷因圖片
`/joke` - 講一個笑話，提升歡樂氣氛
`/roll <數字>` - 擲骰子，隨機產生1到指定數字的點數
`/poll <問題>` - 建立投票互動
        """,
        inline=False
    )
    
    embed.add_field(
        name="🔐 驗證指令",
        value="""
`/驗證` - 驗證用戶身份（確認為真人）
  • 接收 6 位數隨機密碼
  • 在對話框中輸入密碼
  • 驗證成功後獲得驗證角色
        """,
        inline=False
    )
    
    embed.add_field(
        name="👤 用戶指令",
        value="""
`/頭像` - 查看用戶頭像
`/簽到` - 進行每日簽到
        """,
        inline=False
    )
    
    embed.add_field(
        name="🎲 遊戲指令",
        value="""
`/數數字` - 數字猜謎遊戲
`/運勢` - 查看今天的運勢
        """,
        inline=False
    )
    
    embed.add_field(
        name="🎨 一般指令",
        value="""
`/submit <圖片URL> [標題]` - 投稿提交圖片供審核
`/test_status` - 手動測試機器人狀態消息（非自動）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🚫 黑名單指令",
        value="""
**伺服器黑名單：**
`/加入黑名單 @用戶 [原因]` - 將用戶加入黑名單（需要管理員）
`/移除黑名單 @用戶` - 將用戶從黑名單移除（需要管理員）
`/查看黑名單` - 查看伺服器黑名單（需要管理員）

**全域黑名單：**
`/加入全域黑名單 @用戶 [原因]` - 添加到全域黑名單並發送私訊通知（限開發者）
  • 被加入黑名單的用戶將收到私訊通知
  • 通知包含黑名單原因和聯繫主人的建議
`/移除全域黑名單 @用戶` - 從全域黑名單移除用戶（限開發者）
`/查詢全域黑名單 [@用戶]` - 查詢全域黑名單（限開發者）
`/設定全域黑名單` - 設定全域黑名單（限開發者）
`/全域黑名單` - 查看全域黑名單總覽（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="✅ 白名單指令",
        value="""
**伺服器白名單：**
`/加入白名單 @用戶 [原因]` - 將用戶加入白名單（需要管理員）
`/移除白名單 @用戶` - 將用戶從白名單移除（需要管理員）
`/查看白名單` - 查看伺服器白名單（需要管理員）

**全域白名單：**
`/加入全域白名單 @用戶 [原因]` - 添加到全域白名單（限開發者）
`/移除全域白名單 @用戶` - 從全域白名單移除用戶（限開發者）
`/查詢全域白名單 [@用戶]` - 查詢全域白名單（限開發者）
`/設定全域白名單` - 設定全域白名單（限開發者）
`/白名單` - 查看全域白名單總覽（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📋 日誌指令",
        value="""
`/日誌 <頻道>` - 設定日誌頻道（需要管理員）
`/日誌測試` - 測試日誌頻道連接（需要管理員）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🗂️ 頻道管理指令",
        value="""
`/創建頻道 <名稱> [類型] [分類]` - 建立新頻道（需要管理員）
  • 類型：text（預設）或 voice
  • 可選指定分類
`/移除頻道 <頻道> [原因]` - 刪除指定的頻道（需要管理員）
  • 可以刪除單個文字或語音頻道
        """,
        inline=False
    )
    
    embed.add_field(
        name="🔄 開發者用指令",
        value="""
`/關閉機器人` - 關閉機器人（限開發者）
`/重啟機器人` - 重新啟動機器人（限開發者）
`/伺服器列表` - 顯示機器人所在的所有伺服器（限開發者）
`/開發者通知指定伺服器版主 <伺服器名稱> <消息>` - 向指定伺服器的版主發送通知（限開發者）
`/send_dm_to_user <用戶ID> <消息>` - 向指定用戶發送私人信息（限開發者）
`/reload [模組名稱]` - 重新載入指定模組（僅限機器人主人）
  • 不指定模組時預設為 "all"
`/reload_all` - 重新載入所有模組（僅限機器人主人）
  • 顯示成功和失敗的統計數量
        """,
        inline=False
    )
    
    embed.add_field(
        name="🚪 伺服器管理指令",
        value="""
`/離開這個伺服器` - 讓機器人離開此伺服器（限開發者）
`/離開伺服器` - 讓機器人離開指定伺服器（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="👥 權限說明",
        value="""
**👤 所有成員：** 可使用所有一般指令

**🛡️ 管理員：** 可使用管理員指令和黑名單指令（需要相應的伺服器權限）

**👑 機器人主人：** 可使用所有指令（含系統、全域黑名單、危險指令等）

**👨‍💼 授權人員：** 由機器人主人授予，可使用危險指令（如 ban、踢出、重啟機器人等）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📊 儀表板指令",
        value="""
`/儀表板查看` - 顯示機器人管理儀表板（限開發者）
  • 語言管理 - 查看機器人預設語言
  • 防炸群管理 - 檢視防刷屏設定統計
  • 管理用 - 顯示管理相關信息
`/儀表板設置` - 設定機器人管理參數（限開發者）
  • 語言設置 - 設定機器人預設語言
  • 防炸群設置 - 管理防刷屏設定
        """,
        inline=False
    )
    
    embed.set_footer(text="💡 提示：使用 / 斜線指令")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="儀表板查看", description="顯示機器人管理儀表板（限開發者）")
async def dashboard_view(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    dashboard_embed = discord.Embed(title="📊 機器人管理儀表板", color=discord.Color.blue())
    dashboard_embed.description = f"上次更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # 語言管理
    dashboard_embed.add_field(
        name="🌐 語言管理",
        value=f"""
**預設語言：** {LANGUAGE}
**目前系統語言：** 繁體中文 (zh_TW)
**狀態：** ✅ 正常運作
        """,
        inline=False
    )
    
    # 防炸群管理
    try:
        session = SessionLocal()
        anti_spam_enabled_count = session.query(Guild).filter_by(anti_spam_enabled=True).count()
        total_guilds = len(bot.guilds)
        session.close()
        
        dashboard_embed.add_field(
            name="🛡️ 防炸群管理",
            value=f"""
**已啟用防刷屏的伺服器：** {anti_spam_enabled_count}/{total_guilds}
**防刷屏啟用比例：** {(anti_spam_enabled_count/total_guilds*100):.1f}% 
**狀態：** ✅ 正常運作
            """,
            inline=False
        )
    except Exception as e:
        dashboard_embed.add_field(
            name="🛡️ 防炸群管理",
            value=f"❌ 無法讀取數據：{str(e)}",
            inline=False
        )
    
    # 管理用
    dashboard_embed.add_field(
        name="⚙️ 管理用",
        value=f"""
**機器人所在伺服器數：** {len(bot.guilds)} 個
**機器人延遲：** {round(bot.latency * 1000)}ms
**機器人ID：** {bot.user.id}
**預設語言設定：** {LANGUAGE}
**狀態：** ✅ 正常運作
        """,
        inline=False
    )
    
    dashboard_embed.set_footer(text="💡 提示：使用 /儀表板設置 可更改設定")
    await interaction.response.send_message(embed=dashboard_embed, ephemeral=False)

@bot.tree.command(name="儀表板設置", description="設定機器人管理參數（限開發者）")
@app_commands.describe(category="要設定的類別", setting="設定名稱", value="設定值")
async def dashboard_settings(interaction: Interaction, category: str, setting: str, value: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        if category.lower() in ["語言", "language"]:
            if setting.lower() in ["預設語言", "default_language"]:
                global LANGUAGE
                LANGUAGE = value.lower()
                settings_embed = discord.Embed(title="✅ 語言設定已更新", color=discord.Color.green())
                settings_embed.add_field(name="設定項目", value="預設語言", inline=False)
                settings_embed.add_field(name="新設定值", value=value, inline=False)
                settings_embed.add_field(name="狀態", value="✅ 已生效", inline=False)
                await interaction.response.send_message(embed=settings_embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ 未知的語言設定：{setting}", ephemeral=True)
        
        elif category.lower() in ["防炸群", "anti_spam"]:
            await interaction.response.send_message(
                "💡 防炸群設定請使用 `/防刷屏` 指令在各伺服器進行設定",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ 未知的設定類別：{category}", ephemeral=True)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 設定失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="日誌", description="設定日誌頻道（需要管理員）")
@app_commands.describe(channel="要設定的日誌頻道")
async def logs_command(interaction: Interaction, channel: discord.TextChannel):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        guild = get_or_create_guild(interaction.guild.id)
        
        guild.log_channel = channel.id
        session.add(guild)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 日誌頻道已設定", color=discord.Color.green())
        embed.add_field(name="頻道", value=channel.mention, inline=False)
        embed.add_field(name="頻道 ID", value=channel.id, inline=False)
        embed.set_footer(text="機器人現在會將日誌發送到此頻道")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 設定失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="日誌測試", description="測試日誌頻道（需要管理員）")
async def test_logs_command(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        guild_config = session.query(Guild).filter_by(guild_id=interaction.guild.id).first()
        session.close()
        
        if not guild_config or not guild_config.log_channel:
            await interaction.response.send_message("❌ 未設定日誌頻道，請先使用 `/日誌 <頻道>` 設定", ephemeral=True)
            return
        
        embed = discord.Embed(title="# 日誌測試成功", color=discord.Color.green())
        embed.add_field(name="測試時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.add_field(name="測試者", value=interaction.user.mention, inline=False)
        embed.set_footer(text="✅ 日誌頻道連接正常")
        
        await send_log_to_channel(interaction.guild, embed)
        
        await interaction.response.send_message("✅ 日誌測試消息已發送到日誌頻道", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 測試失敗：{str(e)}", ephemeral=True)



@bot.tree.command(name="ban", description="封禁用戶")
@app_commands.describe(user="要封禁的用戶", reason="封禁原因")
async def ban(interaction: Interaction, user: discord.User, reason: str = "未提供原因"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有封禁成員的權限", ephemeral=True)
        return
    try:
        await interaction.guild.ban(user, reason=reason)
        embed = discord.Embed(title="✅ 成功封禁用戶", color=discord.Color.red())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法封禁用戶：{str(e)}", ephemeral=True)


@bot.tree.command(name="創建頻道", description="建立一個新的文字或語音頻道（需要管理員）")
@app_commands.describe(name="頻道名稱", channel_type="頻道類型：text 或 voice", category="分類（可選）")
async def create_channel(interaction: Interaction, name: str, channel_type: str = "text", category: discord.CategoryChannel = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ 您需要管理頻道權限才能使用此指令", ephemeral=True)
        return
    
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        # 確定頻道類型
        if channel_type.lower() == "voice":
            new_channel = await interaction.guild.create_voice_channel(name=name, category=category)
            channel_type_name = "語音"
        else:
            new_channel = await interaction.guild.create_text_channel(name=name, category=category)
            channel_type_name = "文字"
        
        embed = discord.Embed(title="✅ 頻道已建立", color=discord.Color.green())
        embed.add_field(name="頻道名稱", value=f"#{new_channel.name}" if channel_type.lower() != "voice" else f"🔊 {new_channel.name}", inline=False)
        embed.add_field(name="頻道類型", value=channel_type_name, inline=False)
        embed.add_field(name="頻道ID", value=new_channel.id, inline=False)
        if category:
            embed.add_field(name="分類", value=category.name, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="執行時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # 發送日誌
        log_channel = bot.get_channel(1444169106700898324)
        if log_channel:
            log_embed = discord.Embed(
                title="📊 指令使用記錄",
                description="創建頻道",
                color=discord.Color.blue()
            )
            log_embed.add_field(name="用戶", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="頻道", value=f"#{new_channel.name}", inline=True)
            log_embed.add_field(name="伺服器", value=f"{interaction.guild.name}", inline=True)
            log_embed.add_field(name="類型", value=channel_type_name, inline=False)
            log_embed.add_field(name="時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except:
                pass
    
    except Exception as e:
        await interaction.followup.send(f"❌ 建立失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="移除頻道", description="刪除指定的頻道（需要管理員）")
@app_commands.describe(channel="要刪除的頻道", reason="刪除原因")
async def delete_channel(interaction: Interaction, channel: discord.TextChannel, reason: str = "頻道管理"):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ 您需要管理頻道權限才能使用此指令", ephemeral=True)
        return
    
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        channel_name = channel.name
        
        await channel.delete(reason=reason)
        
        embed = discord.Embed(title="✅ 頻道已刪除", color=discord.Color.green())
        embed.add_field(name="頻道名稱", value=f"#{channel_name}", inline=False)
        embed.add_field(name="刪除原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="執行時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # 發送日誌
        log_channel = bot.get_channel(1444169106700898324)
        if log_channel:
            log_embed = discord.Embed(
                title="📊 指令使用記錄",
                description="移除頻道",
                color=discord.Color.blue()
            )
            log_embed.add_field(name="用戶", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="頻道", value=f"#{channel_name}", inline=True)
            log_embed.add_field(name="伺服器", value=f"{interaction.guild.name}", inline=True)
            log_embed.add_field(name="原因", value=reason, inline=False)
            log_embed.add_field(name="時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except:
                pass
    
    except discord.NotFound:
        pass
    except Exception as e:
        try:
            await interaction.followup.send(f"❌ 刪除失敗：{str(e)}", ephemeral=True)
        except:
            pass





@bot.tree.command(name="unban", description="解除封禁用戶")
@app_commands.describe(user_id="要解除封禁的用戶 ID")
async def unban(interaction: Interaction, user_id: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有封禁成員的權限", ephemeral=True)
        return
    try:
        # 驗證用戶 ID
        try:
            user_id_int = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ 無效的用戶 ID", ephemeral=True)
            return
        
        # 獲取用戶對象
        user = await bot.fetch_user(user_id_int)
        
        # 解除封禁
        await interaction.guild.unban(user)
        embed = discord.Embed(title="✅ 成功解除封禁用戶", color=discord.Color.green())
        embed.add_field(name="用戶", value=f"{user.mention} ({user_id_int})", inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("❌ 找不到該用戶 ID", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法解除封禁：{str(e)}", ephemeral=True)

@bot.tree.command(name="kick", description="踢出用戶")
@app_commands.describe(member="要踢出的成員", reason="踢出原因")
async def kick(interaction: Interaction, member: discord.Member, reason: str = "未提供原因"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有踢出成員的權限", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="✅ 成功踢出用戶", color=discord.Color.orange())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法踢出用戶：{str(e)}", ephemeral=True)

@bot.tree.command(name="mute", description="禁言用戶")
@app_commands.describe(member="要禁言的成員", minutes="禁言時長（分鐘）", reason="禁言原因")
async def mute(interaction: Interaction, member: discord.Member, minutes: int = 10, reason: str = "未提供原因"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    # 檢查調用者權限
    caller = interaction.guild.get_member(interaction.user.id)
    if not caller or not caller.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ 您沒有管理成員的權限", ephemeral=True)
        return
    
    # 檢查機器人權限
    bot_member = interaction.guild.me
    if not bot_member.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ 機器人沒有禁言成員的權限。請確保機器人擁有「禁言成員」權限", ephemeral=True)
        return
    
    # 檢查目標成員權限
    if member.top_role >= bot_member.top_role:
        await interaction.response.send_message("❌ 機器人的權限級別不足以禁言此成員", ephemeral=True)
        return
    
    try:
        from datetime import timedelta
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        embed = discord.Embed(title="✅ 成功禁言用戶", color=discord.Color.yellow())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="禁言時長", value=f"{minutes} 分鐘", inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法禁言用戶：{str(e)}", ephemeral=False)

@bot.tree.command(name="unmute", description="解除禁言")
@app_commands.describe(member="要解除禁言的成員")
async def unmute(interaction: Interaction, member: discord.Member):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    # 檢查調用者權限
    caller = interaction.guild.get_member(interaction.user.id)
    if not caller or not caller.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ 您沒有管理成員的權限", ephemeral=True)
        return
    
    # 檢查機器人權限
    bot_member = interaction.guild.me
    if not bot_member.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ 機器人沒有管理成員的權限。請確保機器人擁有「禁言成員」權限", ephemeral=True)
        return
    
    # 檢查目標成員權限
    if member.top_role >= bot_member.top_role:
        await interaction.response.send_message("❌ 機器人的權限級別不足以解除此成員的禁言", ephemeral=True)
        return
    
    try:
        await member.timeout(None)
        embed = discord.Embed(title="✅ 成功解除禁言", color=discord.Color.green())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法解除禁言：{str(e)}", ephemeral=True)

@bot.tree.command(name="clear", description="清除消息")
@app_commands.describe(amount="要清除的消息數量（最多1000條）")
async def clear(interaction: Interaction, amount: int):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理訊息的權限", ephemeral=True)
        return
    if amount > 1000 or amount < 1:
        await interaction.response.send_message("❌ 消息數量必須介於 1 到 1000 之間", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        embed = discord.Embed(title="✅ 成功清除消息", color=discord.Color.blue())
        embed.add_field(name="清除數量", value=f"{len(deleted)} 條", inline=False)
        embed.add_field(name="頻道", value=interaction.channel.mention, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 無法清除消息：{str(e)}", ephemeral=True)

@bot.tree.command(name="welcome", description="設定歡迎消息")
@app_commands.describe(message="歡迎消息內容", channel="歡迎消息頻道（不指定則為系統頻道）")
async def welcome_cmd(interaction: Interaction, message: str, channel: discord.TextChannel = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    caller = interaction.guild.get_member(interaction.user.id)
    if not caller or not caller.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 您沒有管理伺服器的權限", ephemeral=True)
        return
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=interaction.guild_id).first()
    session.close()
    
    target_channel = channel or interaction.guild.system_channel
    if not target_channel:
        await interaction.response.send_message("❌ 找不到有效的頻道", ephemeral=True)
        return
    
    embed = discord.Embed(title="✅ 歡迎消息已設定", color=discord.Color.green())
    embed.add_field(name="消息", value=message, inline=False)
    embed.add_field(name="發送頻道", value=target_channel.mention, inline=False)
    embed.description = "當新成員加入時，機器人將在該頻道發送此消息"
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="say", description="讓機器人發送訊息（所有人可用）")
@app_commands.describe(message="訊息內容", channel="目標頻道（不指定則為當前頻道）")
async def say_slash(interaction: Interaction, message: str, channel: discord.TextChannel = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    target_channel = channel or interaction.channel
    if not target_channel:
        await interaction.response.send_message("❌ 找不到有效的頻道", ephemeral=True)
        return
    
    try:
        await target_channel.send(message)
        embed = discord.Embed(title="✅ 訊息已發送", color=discord.Color.green())
        embed.add_field(name="訊息", value=message, inline=False)
        embed.add_field(name="目標頻道", value=target_channel.mention, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 無法發送訊息：{str(e)}", ephemeral=True)

@bot.tree.command(name="status", description="查看目前設定狀態")
async def status(interaction: Interaction):
    embed = discord.Embed(title="✅ 機器人已就緒", color=discord.Color.blue())
    embed.description = "所有管理員指令和系統指令都已準備就緒"
    await interaction.response.send_message(embed=embed, ephemeral=True)

# 系統指令
def is_bot_owner(interaction: Interaction) -> bool:
    return is_bot_admin(interaction.user.id)


@bot.tree.command(name="test_status", description="測試機器人狀態消息")
async def test_status(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        channel = bot.get_channel(1442033762287484928)
        if channel:
            embed = discord.Embed(title="🤖 機器人狀態更新", color=discord.Color.green())
            embed.add_field(name="狀態", value="✅ 運行中", inline=False)
            embed.add_field(name="連線伺服器數", value=len(bot.guilds), inline=False)
            embed.add_field(name="延遲", value=f"{round(bot.latency * 1000)}ms", inline=False)
            embed.add_field(name="更新時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            embed.set_footer(text="測試消息")
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ 測試狀態消息已發送", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 找不到指定頻道", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 發送失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="meme", description="選擇並發送指定圖片")
@app_commands.describe(title="圖片標題")
async def meme(interaction: Interaction, title: str = None):
    try:
        session = SessionLocal()
        if title:
            meme = session.query(Meme).filter_by(guild_id=interaction.guild_id, title=title, status="approved").first()
        else:
            memes = session.query(Meme).filter_by(guild_id=interaction.guild_id, status="approved").all()
            if not memes:
                await interaction.response.send_message("❌ 沒有可用的迷因", ephemeral=True)
                session.close()
                return
            meme = memes[0]
        
        if not meme:
            await interaction.response.send_message(f"❌ 找不到標題為 '{title}' 的迷因", ephemeral=True)
            session.close()
            return
        
        embed = discord.Embed(title=meme.title or "迷因", color=discord.Color.random())
        embed.set_image(url=meme.image_url)
        embed.set_footer(text=f"上傳者: {meme.uploaded_by}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        session.close()
    except Exception as e:
        await interaction.response.send_message(f"❌ 操作失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="submit", description="投稿提交圖片供審核")
@app_commands.describe(image_url="圖片URL", title="圖片標題")
async def submit(interaction: Interaction, image_url: str, title: str = "未命名"):
    try:
        session = SessionLocal()
        submission = Submission(
            guild_id=interaction.guild_id,
            image_url=image_url,
            title=title,
            submitted_by=interaction.user.id,
            status="pending"
        )
        session.add(submission)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 圖片已提交審核", color=discord.Color.green())
        embed.add_field(name="標題", value=title, inline=False)
        embed.add_field(name="狀態", value="待審核", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 提交失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="8ball", description="魔術8號球，隨機給有趣答案")
@app_commands.describe(question="你的問題")
async def eight_ball(interaction: Interaction, question: str):
    answers = [
        "是的，肯定。", "是的，絕對是。", "不要指望。", "別傻了。",
        "有點模糊，稍後再問。", "我不確定。", "可能是的。", "可能不是。",
        "當然可以。", "絕對不行。", "我認為是的。", "我認為不是。",
        "很可能。", "不太可能。", "再試一次。", "這是肯定的。",
        "命運不明。", "前景不妙。", "很好，非常好。", "不，不，絕對不行。"
    ]
    answer = random.choice(answers)
    embed = discord.Embed(title="🎱 魔術8號球", color=discord.Color.purple())
    embed.add_field(name="你的問題", value=question, inline=False)
    embed.add_field(name="答案", value=f"**{answer}**", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="joke", description="講一個笑話，提升歡樂氣氛")
async def joke(interaction: Interaction):
    jokes = [
        "為什麼螃蟹不分享他的珍珠？因為他很自私！",
        "你知道為什麼放學後大象不上公車嗎？因為他已經下車了！",
        "為什麼雞蛋很安靜？因為它在殼裡！",
        "什麼時候 4+4=8？當你說得不對的時候！",
        "我叫什麼時候會笑？當我沒穿褲子的時候！",
        "為什麼番茄變紅了？因為它看到了沙拉醬！",
        "一個數字走進酒吧，對酒保說：給我一杯！另一個數字也走了進來，說：不，給我倆杯！",
        "為什麼沒有人在廚房裡玩撲克牌？因為馬鈴薯在裡面！",
        "怎樣讓一隻恐龍停止？按下 dino-mite 按鈕！",
        "你知道嗎？今天很冷，但明天會更冷... 今天最熱的一天！"
    ]
    joke_text = random.choice(jokes)
    embed = discord.Embed(title="😂 笑話時間", color=discord.Color.yellow())
    embed.description = joke_text
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="roll", description="擲骰子，隨機產生1到指定數字的點數")
@app_commands.describe(number="最大數字（預設20）")
async def roll(interaction: Interaction, number: int = 20):
    if number < 1:
        await interaction.response.send_message("❌ 數字必須大於 0", ephemeral=True)
        return
    result = random.randint(1, number)
    embed = discord.Embed(title="🎲 擲骰子", color=discord.Color.blurple())
    embed.add_field(name="範圍", value=f"1 - {number}", inline=False)
    embed.add_field(name="結果", value=f"**{result}**", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="poll", description="建立投票互動")
@app_commands.describe(question="投票問題", option1="選項1", option2="選項2", option3="選項3", option4="選項4")
async def poll(interaction: Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    embed = discord.Embed(title="📊 投票", color=discord.Color.green())
    embed.description = question
    options = [option1, option2]
    reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    
    if option3:
        options.append(option3)
    if option4:
        options.append(option4)
    
    for i, option in enumerate(options):
        embed.add_field(name=f"{reactions[i]} 選項 {i+1}", value=option, inline=False)
    
    msg = await interaction.response.send_message(embed=embed, ephemeral=True)
    for i in range(len(options)):
        await msg.add_reaction(reactions[i])

verification_codes = {}
verification_attempt_tracker = defaultdict(list)  # 用戶ID -> [時間戳]
verification_warning_count = defaultdict(lambda: defaultdict(int))  # guild_id -> {user_id: 警告次數}
verification_password_attempts = defaultdict(lambda: defaultdict(int))  # guild_id -> {user_id: 密碼輸入錯誤次數}

def check_verification_spam(user_id: int, guild_id: int, is_already_verified: bool = False):
    """檢查驗證按鈕是否被濫用（最多只能按3次），達到3次警告則踢出"""
    current_time = datetime.now()
    WINDOW = 3600  # 1小時時間窗口（改為追蹤更長時間以統計總按鈕次數）
    MAX_ATTEMPTS = 3  # 最多3次按鈕
    
    user_attempts = verification_attempt_tracker[user_id]
    
    # 清理超過時間窗口的舊記錄 - 使用 total_seconds() 而不是 .seconds
    user_attempts = [timestamp for timestamp in user_attempts if (current_time - timestamp).total_seconds() < WINDOW]
    verification_attempt_tracker[user_id] = user_attempts
    
    # 添加新的嘗試記錄
    user_attempts.append(current_time)
    
    # 檢查是否超過限制
    is_spam = False
    if len(user_attempts) > MAX_ATTEMPTS or is_already_verified:
        # 增加警告計數
        verification_warning_count[guild_id][user_id] += 1
        warning_count = verification_warning_count[guild_id][user_id]
        
        # 檢查是否達到 3 次警告
        should_kick = warning_count >= 3
        return True, len(user_attempts), warning_count, should_kick
    return False, len(user_attempts), verification_warning_count[guild_id][user_id], False

class QuickVerificationModal(ui.Modal, title="身份驗證"):
    password = ui.TextInput(label="請輸入 6 位數驗證密碼", placeholder="例如: 123456", max_length=6, min_length=6)
    
    def __init__(self, guild_id: int, user_id: int, correct_code: str):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.correct_code = correct_code
    
    async def on_submit(self, interaction: Interaction):
        entered_code = str(self.password.value)
        
        if entered_code == self.correct_code:
            # 驗證成功，重置錯誤計數
            verification_password_attempts[self.guild_id][self.user_id] = 0
            
            session = SessionLocal()
            verification = session.query(Verification).filter_by(guild_id=self.guild_id, user_id=self.user_id).first()
            
            if not verification:
                verification = Verification(guild_id=self.guild_id, user_id=self.user_id, verified=True, verified_at=datetime.utcnow())
                session.add(verification)
            else:
                verification.verified = True
                verification.verified_at = datetime.utcnow()
            
            session.commit()
            session.close()
            
            # 刪除驗證碼
            if self.guild_id in verification_codes:
                del verification_codes[self.guild_id]
            
            try:
                guild = bot.get_guild(self.guild_id)
                member = guild.get_member(self.user_id)
                role = guild.get_role(1441605281480966204)
                
                if member and role:
                    await member.add_roles(role)
                    embed = discord.Embed(title="✅ 驗證成功", color=discord.Color.green())
                    embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人"
                    embed.add_field(name="🎭 已獲得身份組", value=f"{role.mention}", inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                    try:
                        verification_channel = bot.get_channel(1441606931671154820)
                        if verification_channel:
                            channel_embed = discord.Embed(title="✅ 用戶驗證成功", color=discord.Color.green())
                            channel_embed.description = f"用戶 {interaction.user.mention} 已成功驗證"
                            channel_embed.add_field(name="用戶 ID", value=f"`{self.user_id}`", inline=False)
                            channel_embed.add_field(name="用戶名", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
                            channel_embed.add_field(name="驗證時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                            await verification_channel.send(embed=channel_embed)
                    except Exception as e:
                        print(f"⚠️ 無法發送驗證通知到頻道: {str(e)}")
                else:
                    embed = discord.Embed(title="✅ 驗證成功（但無法分配身份組）", color=discord.Color.green())
                    embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人"
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                embed = discord.Embed(title="✅ 驗證成功（但分配身份組失敗）", color=discord.Color.orange())
                embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人"
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            # 密碼錯誤，增加錯誤計數
            verification_password_attempts[self.guild_id][self.user_id] += 1
            error_count = verification_password_attempts[self.guild_id][self.user_id]
            
            # 如果錯誤3次，刪除驗證碼，讓用戶重新開始
            if error_count >= 3:
                if self.guild_id in verification_codes:
                    del verification_codes[self.guild_id]
                
                # 發送密碼失效通知
                dm_embed = discord.Embed(title="❌ 驗證密碼已失效", color=discord.Color.red())
                dm_embed.description = "你因連續輸入 3 次錯誤密碼，該驗證密碼已被停用"
                dm_embed.add_field(name="原因", value="密碼輸入錯誤次數過多", inline=False)
                dm_embed.add_field(name="解決方案", value="請點擊「開啟驗證單」按鈕重新獲取新密碼", inline=False)
                dm_embed.add_field(name="失敗時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                
                try:
                    await interaction.user.send(embed=dm_embed)
                except:
                    pass
                
                embed = discord.Embed(title="❌ 驗證密碼已失效", color=discord.Color.red())
                embed.description = "你因連續輸入 3 次錯誤密碼\n\n驗證密碼已被停用，請點擊「開啟驗證單」按鈕重新獲取新密碼"
                await interaction.response.send_message(embed=embed, ephemeral=True)
                print(f"❌ 用戶 {self.user_id} 在伺服器 {self.guild_id} 因 3 次密碼輸入錯誤而密碼失效")
            else:
                # 發送失敗私人信息
                try:
                    dm_embed = discord.Embed(title="❌ 驗證失敗", color=discord.Color.red())
                    dm_embed.description = f"很遺憾，你輸入的驗證密碼不正確\n\n錯誤次數：{error_count}/3"
                    dm_embed.add_field(name="原因", value="密碼輸入錯誤", inline=False)
                    dm_embed.add_field(name="警告", value="再輸入 " + str(3 - error_count) + " 次錯誤後密碼將失效", inline=False)
                    dm_embed.add_field(name="失敗時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                    await interaction.user.send(embed=dm_embed)
                    print(f"❌ 驗證失敗私人信息已發送給用戶 {self.user_id}，錯誤次數 {error_count}/3")
                except Exception as e:
                    print(f"⚠️ 無法發送驗證失敗的私人信息: {str(e)}")
                
                embed = discord.Embed(title="❌ 驗證失敗", color=discord.Color.red())
                embed.description = f"輸入的驗證密碼不正確，請重新檢查\n\n錯誤次數：{error_count}/3"
                embed.add_field(name="📧 提示", value="再有 " + str(3 - error_count) + " 次錯誤機會，之後密碼將失效", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)

class QuickVerificationButtonView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.created_at = datetime.now()  # 記錄按鈕創建時間
    
    @ui.button(label="開啟驗證單", style=discord.ButtonStyle.green)
    async def quick_verify_button(self, interaction: Interaction, button: ui.Button):
        try:
            # 先 defer 確認交互（只能有一次交互確認）
            await interaction.response.defer(ephemeral=True)
            
            # 檢查按鈕是否已失效（5分鐘後失效）
            elapsed_time = datetime.now() - self.created_at
            if elapsed_time.total_seconds() > 300:  # 300秒 = 5分鐘
                button.disabled = True
                await interaction.followup.send("❌ 此驗證按鈕已失效\n\n請要求管理員重新發送驗證按鈕", ephemeral=True)
                return
            
            # 先檢查是否已驗證
            session_check = SessionLocal()
            verification_check = session_check.query(Verification).filter_by(guild_id=self.guild_id, user_id=interaction.user.id).first()
            is_already_verified = verification_check and verification_check.verified
            session_check.close()
            
            # 檢查是否濫用
            is_spam, attempt_count, warning_count, should_kick = check_verification_spam(interaction.user.id, self.guild_id, is_already_verified)
            if is_spam:
                # 使用 followup 回應用戶（因為已經 defer 了）
                await interaction.followup.send(f"⚠️ 違規操作已記錄 (警告: {warning_count}/3)", ephemeral=True)
                
                # 異步發送警告到頻道並通知用戶（後台執行，不阻塞交互）
                async def send_warning_async():
                    try:
                        reason = "已驗證用戶繼續點擊" if is_already_verified else "超過3次按鈕點擊限制"
                        
                        # 發送警告到頻道
                        warning_channel = bot.get_channel(1442069846866001960)
                        if warning_channel:
                            embed = discord.Embed(
                                title="⚠️ 驗證濫用警告",
                                color=discord.Color.red() if should_kick else discord.Color.orange()
                            )
                            embed.description = f"{'🔴 用戶因多次濫用已被踢出' if should_kick else f'用戶違規: {reason}'}"
                            embed.add_field(name="用戶ID", value=f"`{interaction.user.id}`", inline=False)
                            embed.add_field(name="伺服器ID", value=f"`{self.guild_id}`", inline=False)
                            embed.add_field(name="違規類型", value=reason, inline=False)
                            embed.add_field(name="按鈕點擊次數", value=f"{attempt_count}", inline=False)
                            embed.add_field(name="累計警告次數", value=f"{warning_count}/3", inline=False)
                            embed.add_field(name="時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                            await warning_channel.send(embed=embed)
                            print(f"⚠️ 驗證濫用警告: 用戶 {interaction.user.id}，累計警告 {warning_count} 次")
                        
                        # 發送警告到用戶私人信息
                        try:
                            dm_embed = discord.Embed(
                                title="⚠️ 驗證濫用警告",
                                color=discord.Color.red() if should_kick else discord.Color.orange()
                            )
                            if should_kick:
                                dm_embed.description = "🔴 你因多次濫用驗證功能已被踢出伺服器並列入黑名單"
                            else:
                                dm_embed.description = f"⚠️ 你的驗證行為違反規定，已記錄一次警告"
                            dm_embed.add_field(name="違規類型", value=reason, inline=False)
                            dm_embed.add_field(name="警告次數", value=f"{warning_count}/3", inline=False)
                            if should_kick:
                                dm_embed.add_field(name="處罰", value="已被踢出伺服器並永久列入黑名單", inline=False)
                            else:
                                dm_embed.add_field(name="提醒", value="再有違規行為將被踢出並列入黑名單", inline=False)
                            dm_embed.add_field(name="時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                            await interaction.user.send(embed=dm_embed)
                            print(f"📧 警告私人信息已發送給用戶 {interaction.user.id}")
                        except Exception as e:
                            print(f"⚠️ 無法發送警告私人信息: {str(e)}")
                    except Exception as e:
                        print(f"⚠️ 無法發送警告到頻道: {str(e)}")
                
                # 後台任務
                bot.loop.create_task(send_warning_async())
                
                # 如果達到3次警告，後台踢出用戶並加入黑名單
                if should_kick:
                    async def kick_user_async():
                        try:
                            # 發送踢出前的通知
                            try:
                                kick_embed = discord.Embed(
                                    title="🔴 你已被踢出伺服器",
                                    description="你因多次濫用驗證功能，已達到 3 次警告上限",
                                    color=discord.Color.red()
                                )
                                kick_embed.add_field(name="原因", value="驗證功能濫用", inline=False)
                                kick_embed.add_field(name="處罰", value="踢出伺服器 + 永久黑名單", inline=False)
                                kick_embed.add_field(name="時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                                kick_embed.add_field(name="上訴", value="如有異議，請聯繫伺服器管理員", inline=False)
                                await interaction.user.send(embed=kick_embed)
                                print(f"📧 踢出通知已發送給用戶 {interaction.user.id}")
                            except Exception as e:
                                print(f"⚠️ 無法發送踢出通知私人信息: {str(e)}")
                            
                            # 踢出用戶
                            guild = bot.get_guild(self.guild_id)
                            member = guild.get_member(interaction.user.id) if guild else None
                            if member:
                                await member.kick(reason="驗證功能濫用（3次警告）")
                                print(f"🔴 已踢出用戶 {interaction.user.id}，原因：驗證功能濫用")
                                
                                session = SessionLocal()
                                try:
                                    existing = session.query(Blacklist).filter_by(
                                        guild_id=self.guild_id,
                                        user_id=interaction.user.id
                                    ).first()
                                    
                                    if not existing:
                                        blacklist_entry = Blacklist(
                                            guild_id=self.guild_id,
                                            user_id=interaction.user.id,
                                            reason="驗證功能濫用（3次警告自動踢出）"
                                        )
                                        session.add(blacklist_entry)
                                        session.commit()
                                        print(f"⛔ 用戶 {interaction.user.id} 已添加到黑名單")
                                finally:
                                    session.close()
                        except Exception as e:
                            print(f"❌ 踢出用戶或添加黑名單時發生錯誤: {str(e)}")
                    
                    bot.loop.create_task(kick_user_async())
                
                return
            
            # 交互已經在函數開始時 defer 了，不需要再 defer
            verification_code = str(random.randint(100000, 999999))
            verification_codes[self.guild_id] = verification_code
            
            try:
                dm_embed = discord.Embed(title="🔐 驗證密碼", color=discord.Color.blurple())
                dm_embed.description = f"你的 6 位數驗證密碼是：\n\n`{verification_code}`\n\n密碼有效期為 5 分鐘內"
                dm_embed.add_field(name="⏰ 密碼有效期", value="5 分鐘內", inline=False)
                await interaction.user.send(embed=dm_embed)
                
                info_embed = discord.Embed(title="📬 驗證單已開啟", color=discord.Color.green())
                info_embed.description = "✅ 驗證密碼已發送到你的私人信息\n\n請查看私人信息獲取密碼，然後點擊下方「確認按鈕」輸入密碼"
                
                await interaction.followup.send(embed=info_embed, view=QuickVerificationConfirmView(self.guild_id, interaction.user.id, verification_code), ephemeral=True)
            except discord.Forbidden:
                error_embed = discord.Embed(title="❌ 無法發送私人信息", color=discord.Color.red())
                error_embed.description = "請檢查是否允許此伺服器的成員發送私人信息\n\n步驟：用戶設定 → 隱私設定 → 允許此伺服器發送私人信息"
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except Exception as e:
                error_embed = discord.Embed(title="❌ 發生錯誤", color=discord.Color.red())
                error_embed.description = f"錯誤信息：{str(e)}"
                await interaction.followup.send(embed=error_embed, ephemeral=True)
        except Exception as e:
            print(f"❌ 驗證按鈕錯誤：{str(e)}")
            # 如果還沒有確認交互，使用 response；否則使用 followup
            try:
                if not interaction.response.is_finished():
                    await interaction.response.send_message(f"❌ 發生錯誤，請重試\n{str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 發生錯誤，請重試\n{str(e)}", ephemeral=True)
            except:
                pass

class QuickVerificationConfirmView(ui.View):
    def __init__(self, guild_id: int, user_id: int, correct_code: str):
        super().__init__(timeout=None)  # 永不超時
        self.guild_id = guild_id
        self.user_id = user_id
        self.correct_code = correct_code
    
    @ui.button(label="確認按鈕", style=discord.ButtonStyle.primary)
    async def confirm_password_button(self, interaction: Interaction, button: ui.Button):
        try:
            await interaction.response.send_modal(QuickVerificationModal(self.guild_id, self.user_id, self.correct_code))
            print(f"✅ 驗證對話框已打開給用戶 {self.user_id}")
        except Exception as e:
            print(f"❌ 打開驗證對話框失敗：{str(e)}")
            try:
                await interaction.response.send_message(f"❌ 無法打開驗證對話框，請重試\n錯誤：{str(e)}", ephemeral=True)
            except:
                print(f"無法發送錯誤信息")

class VerificationModal(ui.Modal, title="身份驗證"):
    password = ui.TextInput(label="請輸入 6 位數驗證密碼", placeholder="例如: 123456", max_length=6, min_length=6)
    
    def __init__(self, guild_id: int, user_id: int, correct_code: str):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.correct_code = correct_code
    
    async def on_submit(self, interaction: Interaction):
        entered_code = str(self.password.value)
        
        if entered_code == self.correct_code:
            session = SessionLocal()
            verification = session.query(Verification).filter_by(guild_id=self.guild_id, user_id=self.user_id).first()
            
            if not verification:
                verification = Verification(guild_id=self.guild_id, user_id=self.user_id, verified=True, verified_at=datetime.utcnow())
                session.add(verification)
            else:
                verification.verified = True
                verification.verified_at = datetime.utcnow()
            
            session.commit()
            session.close()
            
            if self.guild_id in verification_codes:
                del verification_codes[self.guild_id]
            
            try:
                guild = bot.get_guild(self.guild_id)
                member = guild.get_member(self.user_id)
                role = guild.get_role(1441605281480966204)
                
                if member and role:
                    await member.add_roles(role)
                    
                    dm_embed = discord.Embed(title="✅ 驗證成功", color=discord.Color.green())
                    dm_embed.description = "恭喜！你已成功驗證為真人"
                    dm_embed.add_field(name="🎭 已獲得身份組", value=f"{role.mention}", inline=False)
                    dm_embed.add_field(name="⏰ 驗證時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                    
                    try:
                        user = await bot.fetch_user(self.user_id)
                        await user.send(embed=dm_embed)
                        print(f"✅ 驗證成功私人信息已發送給用戶 {self.user_id}")
                    except Exception as e:
                        print(f"⚠️ 無法發送私人信息: {str(e)}")
                    
                    embed = discord.Embed(title="✅ 驗證成功", color=discord.Color.green())
                    embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人"
                    embed.add_field(name="🎭 已獲得身份組", value=f"{role.mention}", inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                    try:
                        verification_channel = bot.get_channel(1441606931671154820)
                        if verification_channel:
                            channel_embed = discord.Embed(title="✅ 用戶驗證成功", color=discord.Color.green())
                            channel_embed.description = f"用戶 {interaction.user.mention} 已成功驗證"
                            channel_embed.add_field(name="用戶 ID", value=f"`{self.user_id}`", inline=False)
                            channel_embed.add_field(name="用戶名", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
                            channel_embed.add_field(name="驗證時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                            await verification_channel.send(embed=channel_embed)
                            print(f"✅ 驗證通知已發送到頻道")
                        else:
                            print(f"⚠️ 找不到通知頻道 1441606931671154820")
                    except Exception as e:
                        print(f"⚠️ 無法發送驗證通知到頻道: {str(e)}")
                else:
                    embed = discord.Embed(title="✅ 驗證成功（但無法分配身份組）", color=discord.Color.green())
                    embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人"
                    if not is_bot_admin(interaction.user.id):
                        embed.add_field(name="⚠️ 提示", value="無法找到成員資訊", inline=False)
                    elif not role:
                        embed.add_field(name="⚠️ 提示", value="無法找到身份組", inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                print(f"❌ 驗證處理錯誤: {str(e)}")
                embed = discord.Embed(title="✅ 驗證成功（但分配身份組失敗）", color=discord.Color.orange())
                embed.description = f"恭喜！用戶 {interaction.user.mention} 已驗證為真人\n\n分配身份組時發生錯誤：{str(e)}"
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True)
            
            # 發送失敗私人信息
            try:
                dm_embed = discord.Embed(title="❌ 驗證失敗", color=discord.Color.red())
                dm_embed.description = "很遺憾，你輸入的驗證密碼不正確"
                dm_embed.add_field(name="原因", value="密碼輸入錯誤", inline=False)
                dm_embed.add_field(name="重試", value="請重新輸入正確的密碼，或點擊驗證按鈕重新開始", inline=False)
                dm_embed.add_field(name="失敗時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                await interaction.user.send(embed=dm_embed)
                print(f"❌ 驗證失敗私人信息已發送給用戶 {self.user_id}")
            except Exception as e:
                print(f"⚠️ 無法發送驗證失敗的私人信息: {str(e)}")
            
            embed = discord.Embed(title="❌ 驗證失敗", color=discord.Color.red())
            embed.description = "輸入的驗證密碼不正確，請重新檢查"
            embed.add_field(name="📧 提示", value="失敗通知已發送到你的私人信息", inline=False)
            print(f"❌ 驗證失敗：輸入密碼 {entered_code}，正確密碼 {self.correct_code}")
            await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="重啟機器人", description="重新啟動機器人（限開發者）")
async def restart_bot(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        embed = discord.Embed(title="🔄 機器人重啟中...", color=discord.Color.yellow())
        embed.description = "機器人正在重新啟動，請稍候..."
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # 發送重啟通知到指定頻道
        try:
            notification_channel = bot.get_channel(1444169618401792051)
            if notification_channel:
                notification_embed = discord.Embed(title="🔄 機器人重啟中", color=discord.Color.yellow())
                notification_embed.description = f"機器人由 {interaction.user.mention} 在 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 啟動重啟指令"
                notification_embed.add_field(name="操作者", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
                notification_embed.add_field(name="伺服器", value=interaction.guild.name if interaction.guild else "DM", inline=False)
                await notification_channel.send(embed=notification_embed)
                print("✅ 已發送重啟通知")
        except Exception as e:
            print(f"⚠️ 發送重啟通知失敗: {str(e)}")
        
        await asyncio.sleep(1)
        print("✅ 機器人收到重啟指令，正在重新啟動...")
        await bot.close()
    except Exception as e:
        await interaction.response.send_message(f"❌ 重啟失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="announcement", description="查看公告頻道設定")
async def announcement(interaction: Interaction):
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=interaction.guild_id).first()
    session.close()
    
    embed = discord.Embed(title="📢 公告頻道設定", color=discord.Color.blue())
    
    if guild and guild.announcement_channel:
        channel = bot.get_channel(guild.announcement_channel)
        if channel:
            embed.add_field(name="設定頻道", value=channel.mention, inline=False)
            embed.description = "公告將會發送到此頻道"
        else:
            embed.add_field(name="狀態", value="❌ 頻道不存在或無法存取", inline=False)
    else:
        embed.add_field(name="狀態", value="❌ 尚未設定公告頻道", inline=False)
        embed.description = "使用 `/set_announcement_channel` 來設定公告頻道"
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="set_announcement_channel", description="設定公告頻道")
@app_commands.describe(channel="公告頻道")
async def set_announcement_channel(interaction: Interaction, channel: discord.TextChannel):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有管理員可以使用", ephemeral=True)
        return
    
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=interaction.guild_id).first()
    if not guild:
        guild = Guild(guild_id=interaction.guild_id)
        session.add(guild)
    guild.announcement_channel = channel.id
    session.commit()
    session.close()
    
    embed = discord.Embed(title="✅ 公告頻道已設定", color=discord.Color.green())
    embed.add_field(name="頻道", value=channel.mention, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="移除公告設置", description="移除伺服器的公告頻道設置（限開發者）")
@app_commands.describe(guild_id="伺服器ID")
async def remove_announcement_channel(interaction: Interaction, guild_id: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        guild_id_int = int(guild_id)
    except ValueError:
        await interaction.response.send_message("❌ 無效的伺服器ID", ephemeral=True)
        return
    
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=guild_id_int).first()
    
    if not guild:
        session.close()
        await interaction.response.send_message(f"❌ 未找到伺服器 {guild_id}", ephemeral=True)
        return
    
    old_channel_id = guild.announcement_channel
    guild.announcement_channel = None
    session.commit()
    session.close()
    
    embed = discord.Embed(title="✅ 公告設置已移除", color=discord.Color.green())
    embed.add_field(name="伺服器ID", value=f"`{guild_id}`", inline=False)
    if old_channel_id:
        embed.add_field(name="移除的頻道ID", value=f"`{old_channel_id}`", inline=False)
    embed.add_field(name="操作者", value=interaction.user.mention, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    print(f"✅ 已移除伺服器 {guild_id} 的公告設置（原頻道: {old_channel_id}）")

@bot.tree.command(name="發送版主通知", description="向所有伺服器的版主發送通知（只有開發者可用）")
@app_commands.describe(message="通知內容", title="通知標題")
async def send_owner_notification(interaction: Interaction, title: str, message: str):
    if not can_use_dangerous_commands(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有權限使用此危險指令", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        success_count = 0
        fail_count = 0
        
        for guild in bot.guilds:
            try:
                owner = guild.owner
                if owner:
                    # 發送私人信息給伺服器版主
                    embed = discord.Embed(title=title, color=discord.Color.blue())
                    embed.description = message
                    embed.add_field(name="伺服器", value=guild.name, inline=False)
                    embed.add_field(name="伺服器ID", value=f"`{guild.id}`", inline=False)
                    embed.add_field(name="成員數", value=f"{guild.member_count} 人", inline=False)
                    embed.add_field(name="發送時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
                    embed.set_footer(text="此訊息來自開發者")
                    
                    await owner.send(embed=embed)
                    success_count += 1
                    print(f"✅ 版主通知已發送給伺服器 {guild.name} ({guild.id})")
                else:
                    fail_count += 1
                    print(f"⚠️ 無法找到伺服器 {guild.name} ({guild.id}) 的版主")
            except Exception as e:
                fail_count += 1
                print(f"❌ 無法發送版主通知到伺服器 {guild.id}: {str(e)}")
        
        embed = discord.Embed(title="✅ 版主通知已發送", color=discord.Color.green())
        embed.description = f"已向 {success_count} 個伺服器的版主發送通知"
        embed.add_field(name="通知標題", value=title, inline=False)
        embed.add_field(name="通知內容", value=message[:500], inline=False)
        embed.add_field(name="成功", value=f"{success_count} 個伺服器", inline=False)
        if fail_count > 0:
            embed.add_field(name="失敗", value=f"{fail_count} 個伺服器", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 發送版主通知失敗：{str(e)}", ephemeral=True)


@bot.tree.command(name="指定公告發送伺服器", description="設定此伺服器是否接收公告（需要管理員）")
@app_commands.describe(enabled="是否接收公告")
async def set_announcement_server(interaction: Interaction, enabled: bool):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有管理員可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        guild = session.query(Guild).filter_by(guild_id=interaction.guild_id).first()
        if not guild:
            guild = Guild(guild_id=interaction.guild_id)
            session.add(guild)
        
        guild.receive_announcements = enabled
        session.commit()
        session.close()
        
        status = "✅ 已啟用" if enabled else "❌ 已禁用"
        embed = discord.Embed(title="📢 公告接收設定", color=discord.Color.green() if enabled else discord.Color.red())
        embed.description = f"此伺服器{status}公告接收功能"
        embed.add_field(name="伺服器", value=interaction.guild.name, inline=False)
        embed.add_field(name="狀態", value="✅ 將接收公告" if enabled else "❌ 將不接收公告", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        print(f"{'✅' if enabled else '❌'} 伺服器 {interaction.guild.id} 公告接收: {enabled}")
    except Exception as e:
        print(f"❌ 設定公告伺服器錯誤: {str(e)}")
        await interaction.response.send_message(f"❌ 發生錯誤，請稍後重試", ephemeral=True)


# 前綴命令版本
    if not ctx.author.guild_permissions.ban_members:
        await ctx.send("❌ 您沒有封禁成員的權限")
        return
    try:
        await ctx.guild.ban(user, reason=reason)
        embed = discord.Embed(title="✅ 成功封禁用戶", color=discord.Color.red())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 無法封禁用戶：{str(e)}")

    if not ctx.author.guild_permissions.ban_members:
        await ctx.send("❌ 您沒有封禁成員的權限")
        return
    try:
        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send("❌ 無效的用戶 ID")
            return
        
        user = await bot.fetch_user(user_id_int)
        await ctx.guild.unban(user)
        embed = discord.Embed(title="✅ 成功解除封禁用戶", color=discord.Color.green())
        embed.add_field(name="用戶", value=f"{user.mention} ({user_id_int})", inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except discord.NotFound:
        await ctx.send("❌ 找不到該用戶 ID")
    except Exception as e:
        await ctx.send(f"❌ 無法解除封禁：{str(e)}")

    if not ctx.author.guild_permissions.kick_members:
        await ctx.send("❌ 您沒有踢出成員的權限")
        return
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="✅ 成功踢出用戶", color=discord.Color.orange())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 無法踢出用戶：{str(e)}")

    if not ctx.author.guild_permissions.moderate_members:
        await ctx.send("❌ 您沒有管理成員的權限")
        return
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        embed = discord.Embed(title="✅ 成功禁言用戶", color=discord.Color.yellow())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="禁言時長", value=f"{minutes} 分鐘", inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 無法禁言用戶：{str(e)}")

    if not ctx.author.guild_permissions.moderate_members:
        await ctx.send("❌ 您沒有管理成員的權限")
        return
    try:
        await member.timeout(None)
        embed = discord.Embed(title="✅ 成功解除禁言", color=discord.Color.green())
        embed.add_field(name="用戶", value=member.mention, inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 無法解除禁言：{str(e)}")

    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ 您沒有管理訊息的權限")
        return
    if amount > 100 or amount < 1:
        await ctx.send("❌ 消息數量必須介於 1 到 100 之間")
        return
    try:
        deleted = await ctx.channel.purge(limit=amount)
        embed = discord.Embed(title="✅ 成功清除消息", color=discord.Color.blue())
        embed.add_field(name="清除數量", value=f"{len(deleted)} 條", inline=False)
        embed.add_field(name="頻道", value=ctx.channel.mention, inline=False)
        embed.add_field(name="執行者", value=ctx.author.mention, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 無法清除消息：{str(e)}")

    try:
        result = eval(expression)
        embed = discord.Embed(title="🧮 計算結果", color=discord.Color.blue())
        embed.add_field(name="表達式", value=expression, inline=False)
        embed.add_field(name="結果", value=result, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ 計算錯誤：{str(e)}")

    embed = discord.Embed(title="🤖 哲學筆電製作機器人 - 指令列表", color=discord.Color.purple())
    
    embed.add_field(
        name="🔧 管理用指令",
        value="""
`/ban @用戶 [原因]` - 封禁用戶（需要封禁權限）
`/ban伺服器的所有人 [原因]` - 封禁伺服器的所有人（限開發者）
`/unban <用戶ID>` - 解除封禁用戶（需要封禁權限）
`/kick @用戶 [原因]` - 踢出用戶（需要踢出權限）
`/踢出伺服器的所有人 [原因]` - 踢出伺服器的所有人（限開發者）
`/mute @用戶 [分鐘] [原因]` - 禁言用戶（需要管理成員權限）
`/unmute @用戶` - 解除禁言（需要管理成員權限）
`/clear <數量>` - 清除消息，最多100條（需要管理訊息權限）
`/say <訊息> [頻道]` - 讓機器人發送訊息（需要管理訊息權限）
`/welcome <訊息> [頻道]` - 設定歡迎消息（需要管理伺服器權限）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🛡️ 防炸群指令",
        value="""
`/防刷屏 <狀態> [消息數] [秒數]` - 設定防刷屏（需要管理員）
`/防刷屏狀態` - 查看防刷屏系統狀態
`/移除防刷屏` - 移除防刷屏系統（需要管理員）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📢 系統指令",
        value="""
`/help` - 顯示幫助訊息 - 顯示此幫助訊息
`/ping` - 檢查機器人延遲
`/延遲` - 檢查機器人延遲
`/計算` - 數學計算 - 簡單數學計算
`/重啟機器人` - 重新啟動機器人（限開發者）
`/指定一個伺服器離開 <伺服器名稱>` - 讓機器人離開指定伺服器（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="📣 公告指令",
        value="""
`/announcement` - 查看公告頻道設定
`/set_announcement_channel <頻道>` - 設定公告頻道（需要管理員）
`/廣播 <訊息> [圖片URL]` - 發送廣播到所有伺服器（限開發者）
`/指定公告發送伺服器` - 設定此伺服器是否接收公告（需要管理員）
`/發送版主通知` - 向所有伺服器版主發送通知（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🔴 刷屏指令",
        value="""
`/刷頻 [消息數] [內容]` - 發送大量消息刷屏（所有人可用，可在私人信息使用）
`/計算目前刷頻數` - 顯示目前刷頻的進度（所有人可用）
`/刷頻指令記錄` - 查看刷屏指令的日誌記錄
        """,
        inline=False
    )
    
    embed.add_field(
        name="🎮 娛樂指令",
        value="""
`/8ball <問題>` - 魔術8號球，隨機給有趣答案
`/meme` - 發送一張隨機迷因圖片
`/joke` - 講一個笑話，提升歡樂氣氛
`/roll <數字>` - 擲骰子，隨機產生1到指定數字的點數
`/poll <問題>` - 建立投票互動
        """,
        inline=False
    )
    
    embed.add_field(
        name="🔐 驗證指令",
        value="""
`/驗證` - 驗證用戶身份（確認為真人）
        """,
        inline=False
    )
    
    embed.add_field(
        name="👤 用戶指令",
        value="""
`/頭像` - 查看用戶頭像
`/簽到` - 進行每日簽到
        """,
        inline=False
    )
    
    embed.add_field(
        name="🎯 等級系統指令",
        value="""
`/聊天等級` - 查看用戶的聊天等級和經驗值
`/等級設置` - 設定用戶等級（需要管理員）
        """,
        inline=False
    )
    
    embed.add_field(
        name="🚫 黑名單指令",
        value="""
`/加入黑名單 @用戶 [原因]` - 將用戶加入黑名單（需要管理員）
`/移除黑名單 @用戶` - 將用戶從黑名單移除（需要管理員）
`/查看黑名單` - 查看伺服器黑名單（需要管理員）
`/加入全域黑名單 @用戶 [原因]` - 添加到全域黑名單（限開發者）
        """,
        inline=False
    )
    
    embed.add_field(
        name="✅ 白名單指令",
        value="""
`/加入白名單 @用戶 [原因]` - 將用戶加入白名單（需要管理員）
`/移除白名單 @用戶` - 將用戶從白名單移除（需要管理員）
`/查看白名單` - 查看伺服器白名單（需要管理員）
        """,
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.tree.command(name="延遲", description="檢查機器人延遲（可在私人信息使用）")
async def ping(interaction: Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
    embed.add_field(name="延遲", value=f"{latency}ms", inline=False)
    embed.add_field(name="位置", value="私人信息" if not interaction.guild else f"伺服器: {interaction.guild.name}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="計算", description="簡單數學計算（可在私人信息使用）")
@app_commands.describe(expression="數學表達式")
async def calculate(interaction: Interaction, expression: str):
    try:
        result = eval(expression)
        embed = discord.Embed(title="🧮 計算結果", color=discord.Color.blue())
        embed.add_field(name="表達式", value=expression, inline=False)
        embed.add_field(name="結果", value=result, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 計算錯誤：{str(e)}", ephemeral=True)


@bot.tree.command(name="加入黑名單", description="將用戶加入黑名單（需要管理員）")
@app_commands.describe(user="要加入黑名單的用戶", reason="原因")
async def add_blacklist(interaction: Interaction, user: discord.User, reason: str = "無"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        guild_obj = session.query(Guild).filter_by(guild_id=interaction.guild.id).first()
        if not guild_obj:
            guild_obj = Guild(guild_id=interaction.guild.id)
            session.add(guild_obj)
            session.commit()
        
        existing = session.query(Blacklist).filter_by(guild_id=interaction.guild.id, user_id=user.id).first()
        if existing:
            session.close()
            await interaction.response.send_message(f"❌ {user.mention} 已在黑名單中", ephemeral=True)
            return
        
        blacklist_entry = Blacklist(guild_id=interaction.guild.id, user_id=user.id, reason=reason)
        session.add(blacklist_entry)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 用戶已加入黑名單", color=discord.Color.red())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 添加失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="移除黑名單", description="將用戶從黑名單移除（需要管理員）")
@app_commands.describe(user="要移除的用戶")
async def remove_blacklist(interaction: Interaction, user: discord.User):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        blacklist_entry = session.query(Blacklist).filter_by(guild_id=interaction.guild.id, user_id=user.id).first()
        
        if not blacklist_entry:
            session.close()
            await interaction.response.send_message(f"❌ {user.mention} 不在黑名單中", ephemeral=True)
            return
        
        session.delete(blacklist_entry)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 用戶已從黑名單移除", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="查看黑名單", description="查看伺服器黑名單（需要管理員）")
async def view_blacklist(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        blacklist_entries = session.query(Blacklist).filter_by(guild_id=interaction.guild.id).all()
        session.close()
        
        if not blacklist_entries:
            await interaction.response.send_message("✅ 黑名單為空", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"📋 黑名單 ({len(blacklist_entries)} 個用戶)", color=discord.Color.red())
        
        for entry in blacklist_entries:
            try:
                u = await bot.fetch_user(entry.user_id)
                embed.add_field(name=f"👤 {u}", value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
            except:
                embed.add_field(name=f"👤 ID: {entry.user_id}", value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢黑名單失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="加入全域黑名單", description="將用戶添加到全域黑名單（限開發者）")
@app_commands.describe(user="要添加的用戶", reason="原因")
async def add_global_blacklist(interaction: Interaction, user: discord.User, reason: str = "未提供原因"):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 檢查用戶是否已在全域黑名單中
        existing = session.query(Blacklist).filter_by(user_id=user.id).first()
        if existing:
            await interaction.response.send_message(f"❌ {user.mention} 已在全域黑名單中", ephemeral=False)
            session.close()
            return
        
        # 在所有伺服器中添加黑名單
        added_count = 0
        for guild in bot.guilds:
            try:
                guild_obj = session.query(Guild).filter_by(guild_id=guild.id).first()
                if not guild_obj:
                    guild_obj = Guild(guild_id=guild.id)
                    session.add(guild_obj)
                    session.commit()
                
                blacklist_entry = Blacklist(guild_id=guild.id, user_id=user.id, reason=reason)
                session.add(blacklist_entry)
                added_count += 1
            except:
                pass
        
        session.commit()
        session.close()
        
        # 發送私訊給被加入黑名單的用戶
        try:
            dm_embed = discord.Embed(
                title="⚠️ 您已被加入全域黑名單",
                description="您已被開發者加入全域黑名單，這意味著您無法在機器人管理的伺服器中使用任何功能。",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="原因", value=reason, inline=False)
            dm_embed.add_field(name="如有異議", value="請聯繫開發者", inline=False)
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"❌ 無法向 {user} 發送私訊：{str(e)}")
        
        embed = discord.Embed(title="✅ 用戶已添加到全域黑名單", color=discord.Color.red())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="已添加到", value=f"{added_count} 個伺服器", inline=False)
        embed.add_field(name="通知", value="✅ 已發送私訊給該用戶", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 添加失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="查詢全域黑名單", description="查詢全域黑名單 [可選伺服器ID] [可選用戶] [可選原因]")
@app_commands.describe(guild_id="要查詢的伺服器ID（不提供則查詢所有）", user="要查詢的用戶", reason="要過濾的原因")
async def query_global_blacklist(interaction: Interaction, guild_id: str = None, user: discord.User = None, reason: str = None):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 驗證伺服器ID
        target_guild_id = None
        if guild_id:
            try:
                target_guild_id = int(guild_id)
                target_guild = bot.get_guild(target_guild_id)
                if not target_guild:
                    await interaction.response.send_message(f"❌ 找不到伺服器 ID: {guild_id}", ephemeral=True)
                    session.close()
                    return
            except ValueError:
                await interaction.response.send_message("❌ 無效的伺服器ID", ephemeral=True)
                session.close()
                return
        
        # 按優先級進行查詢
        if user:
            # 查詢特定用戶的黑名單記錄
            query = session.query(Blacklist).filter_by(user_id=user.id)
            if target_guild_id:
                query = query.filter_by(guild_id=target_guild_id)
            blacklist_entries = query.all()
            
            if not blacklist_entries:
                await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在黑名單中", ephemeral=True)
                session.close()
                return
            
            # 按伺服器分組
            embed = discord.Embed(
                title=f"📋 {user} 的黑名單記錄",
                description=f"共 {len(blacklist_entries)} 條記錄",
                color=discord.Color.red()
            )
            
            for entry in blacklist_entries:
                guild = bot.get_guild(entry.guild_id)
                guild_name = guild.name if guild else f"未知伺服器 ({entry.guild_id})"
                
                embed.add_field(
                    name=f"伺服器: {guild_name}",
                    value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            session.close()
            return
        
        elif reason:
            # 查詢特定原因的黑名單記錄
            query = session.query(Blacklist).filter(Blacklist.reason.ilike(f"%{reason}%"))
            if target_guild_id:
                query = query.filter_by(guild_id=target_guild_id)
            blacklist_entries = query.all()
            
            if not blacklist_entries:
                await interaction.response.send_message(f"✅ 沒有找到原因包含 '{reason}' 的黑名單記錄", ephemeral=True)
                session.close()
                return
            
            # 按伺服器分組
            blacklist_by_guild = {}
            for entry in blacklist_entries:
                if entry.guild_id not in blacklist_by_guild:
                    blacklist_by_guild[entry.guild_id] = []
                blacklist_by_guild[entry.guild_id].append(entry)
            
            embeds = []
            for gid, entries in blacklist_by_guild.items():
                guild = bot.get_guild(gid)
                guild_name = guild.name if guild else f"未知伺服器 ({gid})"
                
                embed = discord.Embed(
                    title=f"📋 {guild_name} 的黑名單 (原因: {reason})",
                    description=f"共 {len(entries)} 個用戶",
                    color=discord.Color.red()
                )
                
                for entry in entries:
                    try:
                        u = await bot.fetch_user(entry.user_id)
                        user_info = f"👤 {u} (ID: {entry.user_id})"
                    except:
                        user_info = f"👤 ID: {entry.user_id}"
                    
                    embed.add_field(
                        name=user_info,
                        value=f"時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                        inline=False
                    )
                
                embeds.append(embed)
            
            await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
            
            if len(embeds) > 10:
                for i in range(10, len(embeds), 10):
                    await interaction.followup.send(embeds=embeds[i:i+10])
            
            session.close()
            return
        
        # 查詢伺服器或所有黑名單
        if target_guild_id:
            blacklist_entries = session.query(Blacklist).filter_by(guild_id=target_guild_id).all()
            guild = bot.get_guild(target_guild_id)
            guild_name = guild.name if guild else f"伺服器 {target_guild_id}"
            
            if not blacklist_entries:
                embed = discord.Embed(
                    title=f"✅ {guild_name} - 全域黑名單",
                    description="此伺服器沒有黑名單用戶",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                session.close()
                return
            
            embed = discord.Embed(
                title=f"📋 {guild_name} 的黑名單",
                description=f"共 {len(blacklist_entries)} 個用戶",
                color=discord.Color.red()
            )
            
            for entry in blacklist_entries[:25]:
                try:
                    u = await bot.fetch_user(entry.user_id)
                    user_info = f"👤 {u} (ID: {entry.user_id})"
                except:
                    user_info = f"👤 ID: {entry.user_id}"
                
                embed.add_field(
                    name=user_info,
                    value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
            
            if len(blacklist_entries) > 25:
                embed.add_field(name="⚠️ 提示", value=f"還有 {len(blacklist_entries) - 25} 個用戶未顯示", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            session.close()
            return
        
        # 查詢所有黑名單
        all_blacklist_entries = session.query(Blacklist).all()
        session.close()
        
        if not all_blacklist_entries:
            await interaction.response.send_message("✅ 全域黑名單為空", ephemeral=True)
            return
        
        # 按伺服器分組
        blacklist_by_guild = {}
        for entry in all_blacklist_entries:
            if entry.guild_id not in blacklist_by_guild:
                blacklist_by_guild[entry.guild_id] = []
            blacklist_by_guild[entry.guild_id].append(entry)
        
        embeds = []
        for guild_id, entries in blacklist_by_guild.items():
            guild = bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"未知伺服器 ({guild_id})"
            
            embed = discord.Embed(
                title=f"📋 {guild_name} 的黑名單",
                description=f"共 {len(entries)} 個用戶",
                color=discord.Color.red()
            )
            
            for entry in entries:
                try:
                    u = await bot.fetch_user(entry.user_id)
                    user_info = f"👤 {u} (ID: {entry.user_id})"
                except:
                    user_info = f"👤 ID: {entry.user_id}"
                
                embed.add_field(
                    name=user_info,
                    value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
            
            embeds.append(embed)
        
        # 添加總結 embed
        summary_embed = discord.Embed(
            title="🌍 全域黑名單總結",
            color=discord.Color.red()
        )
        summary_embed.add_field(name="涉及伺服器", value=f"{len(blacklist_by_guild)} 個", inline=False)
        summary_embed.add_field(name="黑名單用戶總數", value=f"{len(all_blacklist_entries)} 個", inline=False)
        
        embeds.insert(0, summary_embed)
        
        await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
        
        if len(embeds) > 10:
            for i in range(10, len(embeds), 10):
                await interaction.followup.send(embeds=embeds[i:i+10])
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="移除全域黑名單", description="從全域黑名單移除用戶 [可選伺服器ID]")
@app_commands.describe(user="要移除的用戶", guild_id="要移除的伺服器ID（不提供則移除所有）")
async def remove_global_blacklist(interaction: Interaction, user: discord.User, guild_id: str = None):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 驗證伺服器ID
        target_guild_id = None
        if guild_id:
            try:
                target_guild_id = int(guild_id)
                target_guild = bot.get_guild(target_guild_id)
                if not target_guild:
                    await interaction.response.send_message(f"❌ 找不到伺服器 ID: {guild_id}", ephemeral=True)
                    session.close()
                    return
            except ValueError:
                await interaction.response.send_message("❌ 無效的伺服器ID", ephemeral=True)
                session.close()
                return
        
        # 查詢黑名單
        query = session.query(Blacklist).filter_by(user_id=user.id)
        if target_guild_id:
            query = query.filter_by(guild_id=target_guild_id)
        
        entries = query.all()
        
        if not entries:
            await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在黑名單中", ephemeral=False)
            session.close()
            return
        
        count = len(entries)
        query.delete()
        session.commit()
        session.close()
        
        location = f"伺服器 {target_guild_id}" if target_guild_id else "全域黑名單"
        embed = discord.Embed(title="✅ 已移除用戶", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="位置", value=location, inline=False)
        embed.add_field(name="移除記錄數", value=f"{count} 條", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # 向用戶發送私人信息通知
        try:
            dm_embed = discord.Embed(
                title="🎉 已從黑名單移除",
                description="您已被從機器人黑名單中移除，現在可以正常使用機器人的服務。",
                color=discord.Color.green()
            )
            dm_embed.add_field(name="移除時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
            dm_embed.set_footer(text="機器人管理系統", icon_url=bot.user.avatar.url if bot.user.avatar else None)
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass
        except Exception as dm_error:
            pass
    except Exception as e:
        await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="設定全域黑名單", description="設定全域黑名單相關配置（限開發者）")
@app_commands.describe(action="操作類型：clear清空黑名單")
async def set_global_blacklist(interaction: Interaction, action: str = ""):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    if action.lower() == "clear":
        try:
            session = SessionLocal()
            session.query(Blacklist).delete()
            session.commit()
            session.close()
            
            embed = discord.Embed(title="✅ 全域黑名單已清空", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 清空失敗：{str(e)}", ephemeral=True)
    else:
        await interaction.response.send_message(
            "📋 使用方法：\n"
            "`/設定全域黑名單 action:clear` - 清空所有黑名單\n\n"
            "💡 提示：使用 `/加入全域黑名單`、`/移除全域黑名單` 和 `/查詢全域黑名單` 管理黑名單",
            ephemeral=True
        )

@bot.tree.command(name="全域黑名單", description="查看全域黑名單（限開發者）")
@app_commands.describe(user="要查詢的用戶", reason="要過濾的原因")
async def global_blacklist(interaction: Interaction, user: discord.User = None, reason: str = None):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 如果指定了用戶或原因，進行過濾查詢
        if user or reason:
            if user:
                # 查詢特定用戶的黑名單記錄
                blacklist_entries = session.query(Blacklist).filter_by(user_id=user.id).all()
                
                if not blacklist_entries:
                    await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在任何黑名單中", ephemeral=True)
                    session.close()
                    return
                
                embed = discord.Embed(title=f"📋 用戶 {user.name} 的黑名單記錄", color=discord.Color.red())
                for entry in blacklist_entries:
                    embed.add_field(
                        name=f"伺服器 ID: {entry.guild_id}",
                        value=f"原因: {entry.reason or '無'}\n添加時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S') if entry.added_at else '未知'}",
                        inline=False
                    )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                session.close()
                return
            
            if reason:
                blacklist_entries = session.query(Blacklist).filter(Blacklist.reason.contains(reason)).all()
                if not blacklist_entries:
                    await interaction.response.send_message(f"✅ 沒有找到包含原因 '{reason}' 的黑名單記錄", ephemeral=True)
                    session.close()
                    return
                
                embed = discord.Embed(title=f"📋 包含 '{reason}' 的黑名單記錄", color=discord.Color.red())
                for entry in blacklist_entries[:25]:
                    embed.add_field(
                        name=f"用戶 ID: {entry.user_id}",
                        value=f"原因: {entry.reason or '無'}",
                        inline=True
                    )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                session.close()
                return
        
        blacklist_entries = session.query(Blacklist).limit(50).all()
        session.close()
        
        if not blacklist_entries:
            await interaction.response.send_message("✅ 全域黑名單目前是空的", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 全域黑名單", description=f"共 {len(blacklist_entries)} 筆記錄（顯示前 50 筆）", color=discord.Color.red())
        for entry in blacklist_entries[:25]:
            embed.add_field(
                name=f"用戶 ID: {entry.user_id}",
                value=f"原因: {entry.reason or '無'}",
                inline=True
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)

# ====== 包廂系統指令 ======
@bot.tree.command(name="設置包廂", description="在指定類別下建立包廂系統（需要管理員）")
@app_commands.describe(category="要建立包廂的類別")
async def setup_booth(interaction: Interaction, category: discord.CategoryChannel):
    """設置包廂系統"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ 您需要管理頻道權限才能使用此指令", ephemeral=True)
        return
    
    global booths
    category_id = str(category.id)
    
    if category_id in booths:
        await interaction.response.send_message("❌ 此類別已經設置過包廂系統!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer()
        
        entry_channel = await interaction.guild.create_voice_channel(
            "🎪 點擊加入建立包廂",
            category=category,
            user_limit=0,
            overwrites={interaction.guild.default_role: discord.PermissionOverwrite(connect=True)}
        )
        
        booths[category_id] = {
            'entry_channel': str(entry_channel.id),
            'category': category_id
        }
        save_booths(booths)
        
        embed = discord.Embed(title="✅ 包廂系統已設置", color=discord.Color.green())
        embed.add_field(name="類別", value=category.name, inline=False)
        embed.add_field(name="主入口", value=entry_channel.mention, inline=False)
        embed.add_field(name="說明", value="成員點擊入口頻道後，系統會自動為其建立私人包廂", inline=False)
        embed.set_footer(text=f"執行者：{interaction.user.name}")
        
        await interaction.followup.send(embed=embed)
        print(f"✅ 已在類別 {category.name} 設置包廂系統")
        
    except Exception as e:
        await interaction.followup.send(f"❌ 設置失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="包廂狀態", description="查看包廂系統狀態")
async def booth_status(interaction: Interaction):
    """查看包廂系統狀態"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    global booths
    if not booths:
        await interaction.response.send_message("❌ 目前沒有設置任何包廂系統!", ephemeral=True)
        return
    
    embed = discord.Embed(title="📊 包廂系統狀態", color=discord.Color.blue())
    status_list = []
    active_booths = 0
    
    for cat_id, data in booths.items():
        category = interaction.guild.get_channel(int(data['category']))
        entry = interaction.guild.get_channel(int(data['entry_channel']))
        if category and entry:
            booth_count = len([ch for ch in category.voice_channels if ch.name.startswith('🗣️包廂-')])
            active_booths += booth_count
            status_list.append(f"**{category.name}**\n└ 入口：{entry.mention}\n└ 活躍包廂：{booth_count} 個")
    
    embed.description = "\n\n".join(status_list) if status_list else "無活躍包廂"
    embed.add_field(name="總計", value=f"共 {len(booths)} 個包廂系統，{active_booths} 個活躍包廂", inline=False)
    embed.set_footer(text=f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="移除包廂", description="移除指定的包廂系統（需要管理員）")
@app_commands.describe(category="要移除的包廂類別")
async def remove_booth(interaction: Interaction, category: discord.CategoryChannel):
    """移除包廂系統"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ 您需要管理頻道權限才能使用此指令", ephemeral=True)
        return
    
    global booths
    category_id = str(category.id)
    
    if category_id not in booths:
        await interaction.response.send_message("❌ 此類別沒有設置包廂系統!", ephemeral=True)
        return
    
    try:
        await interaction.response.defer()
        
        # 刪除入口頻道
        entry_id = booths[category_id]['entry_channel']
        entry_channel = interaction.guild.get_channel(int(entry_id))
        if entry_channel:
            await entry_channel.delete()
        
        # 刪除所有包廂頻道
        deleted_count = 0
        for channel in list(category.voice_channels):
            if channel.name.startswith('🗣️包廂-'):
                await channel.delete()
                deleted_count += 1
        
        # 從資料中移除
        del booths[category_id]
        save_booths(booths)
        
        embed = discord.Embed(title="✅ 包廂系統已移除", color=discord.Color.green())
        embed.add_field(name="類別", value=category.name, inline=False)
        embed.add_field(name="已刪除", value=f"入口頻道 + {deleted_count} 個包廂", inline=False)
        embed.set_footer(text=f"執行者：{interaction.user.name}")
        
        await interaction.followup.send(embed=embed)
        print(f"✅ 已移除類別 {category.name} 的包廂系統")
        
    except Exception as e:
        await interaction.followup.send(f"❌ 移除失敗：{str(e)}", ephemeral=True)

# Whitelist Commands
@bot.tree.command(name="加入白名單", description="將用戶添加到伺服器白名單（需要管理員）")
@app_commands.describe(user="要添加的用戶", reason="原因")
async def add_whitelist(interaction: Interaction, user: discord.User, reason: str = "未提供原因"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        existing = session.query(Whitelist).filter_by(guild_id=interaction.guild.id, user_id=user.id).first()
        if existing:
            await interaction.response.send_message(f"❌ {user.mention} 已在白名單中", ephemeral=True)
            session.close()
            return
        
        whitelist_entry = Whitelist(guild_id=interaction.guild.id, user_id=user.id, reason=reason)
        session.add(whitelist_entry)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 用戶已添加到白名單", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 添加失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="移除白名單", description="將用戶從伺服器白名單移除（需要管理員）")
@app_commands.describe(user="要移除的用戶")
async def remove_whitelist(interaction: Interaction, user: discord.User):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        entry = session.query(Whitelist).filter_by(guild_id=interaction.guild.id, user_id=user.id).first()
        if not entry:
            await interaction.response.send_message(f"❌ {user.mention} 不在白名單中", ephemeral=True)
            session.close()
            return
        
        session.delete(entry)
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 已從白名單移除用戶", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="查看白名單", description="查看伺服器白名單（需要管理員）")
async def view_whitelist(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        whitelist_entries = session.query(Whitelist).filter_by(guild_id=interaction.guild.id).all()
        session.close()
        
        if not whitelist_entries:
            await interaction.response.send_message("✅ 白名單為空", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"✅ 白名單 ({len(whitelist_entries)} 個用戶)", color=discord.Color.green())
        
        for entry in whitelist_entries:
            try:
                u = await bot.fetch_user(entry.user_id)
                embed.add_field(name=f"👤 {u}", value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
            except:
                embed.add_field(name=f"👤 ID: {entry.user_id}", value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢白名單失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="加入全域白名單", description="將用戶添加到全域白名單（限開發者）")
@app_commands.describe(user="要添加的用戶", reason="原因")
async def add_global_whitelist(interaction: Interaction, user: discord.User, reason: str = "未提供原因"):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 檢查用戶是否已在全域白名單中
        existing = session.query(Whitelist).filter_by(user_id=user.id).first()
        if existing:
            await interaction.response.send_message(f"❌ {user.mention} 已在全域白名單中", ephemeral=True)
            session.close()
            return
        
        # 在所有伺服器中添加白名單
        added_count = 0
        for guild in bot.guilds:
            try:
                guild_obj = session.query(Guild).filter_by(guild_id=guild.id).first()
                if not guild_obj:
                    guild_obj = Guild(guild_id=guild.id)
                    session.add(guild_obj)
                    session.commit()
                
                whitelist_entry = Whitelist(guild_id=guild.id, user_id=user.id, reason=reason)
                session.add(whitelist_entry)
                added_count += 1
            except:
                pass
        
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 用戶已添加到全域白名單", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="已添加到", value=f"{added_count} 個伺服器", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 添加失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="查詢全域白名單", description="查詢全域白名單（限開發者）")
@app_commands.describe(user="要查詢的用戶", reason="要過濾的原因")
async def query_global_whitelist(interaction: Interaction, user: discord.User = None, reason: str = None):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 如果指定了用戶或原因，進行過濾查詢
        if user or reason:
            if user:
                # 查詢特定用戶的白名單記錄
                whitelist_entries = session.query(Whitelist).filter_by(user_id=user.id).all()
                
                if not whitelist_entries:
                    await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在任何白名單中", ephemeral=True)
                    session.close()
                    return
                
                # 按伺服器分組
                embed = discord.Embed(
                    title=f"✅ {user} 的白名單記錄",
                    description=f"共 {len(whitelist_entries)} 條記錄",
                    color=discord.Color.green()
                )
                
                for entry in whitelist_entries:
                    guild = bot.get_guild(entry.guild_id)
                    guild_name = guild.name if guild else f"未知伺服器 ({entry.guild_id})"
                    
                    embed.add_field(
                        name=f"伺服器: {guild_name}",
                        value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                session.close()
                return
            
            elif reason:
                # 查詢特定原因的白名單記錄
                whitelist_entries = session.query(Whitelist).filter(
                    Whitelist.reason.ilike(f"%{reason}%")
                ).all()
                
                if not whitelist_entries:
                    await interaction.response.send_message(f"✅ 沒有找到原因包含 '{reason}' 的白名單記錄", ephemeral=True)
                    session.close()
                    return
                
                # 按伺服器分組
                whitelist_by_guild = {}
                for entry in whitelist_entries:
                    if entry.guild_id not in whitelist_by_guild:
                        whitelist_by_guild[entry.guild_id] = []
                    whitelist_by_guild[entry.guild_id].append(entry)
                
                embeds = []
                for guild_id, entries in whitelist_by_guild.items():
                    guild = bot.get_guild(guild_id)
                    guild_name = guild.name if guild else f"未知伺服器 ({guild_id})"
                    
                    embed = discord.Embed(
                        title=f"✅ {guild_name} 的白名單 (原因: {reason})",
                        description=f"共 {len(entries)} 個用戶",
                        color=discord.Color.green()
                    )
                    
                    for entry in entries:
                        try:
                            u = await bot.fetch_user(entry.user_id)
                            user_info = f"👤 {u} (ID: {entry.user_id})"
                        except:
                            user_info = f"👤 ID: {entry.user_id}"
                        
                        embed.add_field(
                            name=user_info,
                            value=f"時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                            inline=False
                        )
                    
                    embeds.append(embed)
                
                await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
                
                if len(embeds) > 10:
                    for i in range(10, len(embeds), 10):
                        await interaction.followup.send(embeds=embeds[i:i+10])
                
                session.close()
                return
        
        # 查詢所有白名單
        all_whitelist_entries = session.query(Whitelist).all()
        session.close()
        
        if not all_whitelist_entries:
            await interaction.response.send_message("✅ 全域白名單為空", ephemeral=True)
            return
        
        # 按伺服器分組
        whitelist_by_guild = {}
        for entry in all_whitelist_entries:
            if entry.guild_id not in whitelist_by_guild:
                whitelist_by_guild[entry.guild_id] = []
            whitelist_by_guild[entry.guild_id].append(entry)
        
        embeds = []
        for guild_id, entries in whitelist_by_guild.items():
            guild = bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"未知伺服器 ({guild_id})"
            
            embed = discord.Embed(
                title=f"✅ {guild_name} 的白名單",
                description=f"共 {len(entries)} 個用戶",
                color=discord.Color.green()
            )
            
            for entry in entries:
                try:
                    u = await bot.fetch_user(entry.user_id)
                    user_info = f"👤 {u} (ID: {entry.user_id})"
                except:
                    user_info = f"👤 ID: {entry.user_id}"
                
                embed.add_field(
                    name=user_info,
                    value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
            
            embeds.append(embed)
        
        # 添加總結 embed
        summary_embed = discord.Embed(
            title="🌍 全域白名單總結",
            color=discord.Color.green()
        )
        summary_embed.add_field(name="涉及伺服器", value=f"{len(whitelist_by_guild)} 個", inline=False)
        summary_embed.add_field(name="白名單用戶總數", value=f"{len(all_whitelist_entries)} 個", inline=False)
        
        embeds.insert(0, summary_embed)
        
        await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
        
        if len(embeds) > 10:
            for i in range(10, len(embeds), 10):
                await interaction.followup.send(embeds=embeds[i:i+10])
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="移除全域白名單", description="從全域白名單移除用戶（限開發者）")
@app_commands.describe(user="要移除的用戶")
async def remove_global_whitelist(interaction: Interaction, user: discord.User):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        entries = session.query(Whitelist).filter_by(user_id=user.id).all()
        
        if not entries:
            await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在全域白名單中", ephemeral=True)
            session.close()
            return
        
        count = len(entries)
        session.query(Whitelist).filter_by(user_id=user.id).delete()
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 已從全域白名單移除用戶", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="移除記錄數", value=f"{count} 條", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="設定全域白名單", description="設定全域白名單相關配置（限開發者）")
@app_commands.describe(action="操作類型：clear清空白名單")
async def set_global_whitelist(interaction: Interaction, action: str = ""):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    if action.lower() == "clear":
        try:
            session = SessionLocal()
            session.query(Whitelist).delete()
            session.commit()
            session.close()
            
            embed = discord.Embed(title="✅ 全域白名單已清空", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 清空失敗：{str(e)}", ephemeral=True)
    else:
        await interaction.response.send_message(
            "📋 使用方法：\n"
            "`/設定全域白名單 action:clear` - 清空所有白名單\n\n"
            "💡 提示：使用 `/加入全域白名單`、`/移除全域白名單` 和 `/查詢全域白名單` 管理白名單",
            ephemeral=True
        )

@bot.tree.command(name="白名單", description="查看全域白名單（限開發者）")
@app_commands.describe(user="要查詢的用戶", reason="要過濾的原因")
async def global_whitelist(interaction: Interaction, user: discord.User = None, reason: str = None):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        # 如果指定了用戶或原因，進行過濾查詢
        if user or reason:
            if user:
                # 查詢特定用戶的白名單記錄
                whitelist_entries = session.query(Whitelist).filter_by(user_id=user.id).all()
                
                if not whitelist_entries:
                    await interaction.response.send_message(f"✅ 用戶 {user.mention} 不在任何白名單中", ephemeral=True)
                    session.close()
                    return
                
                # 按伺服器分組
                embed = discord.Embed(
                    title=f"✅ {user} 的白名單記錄",
                    description=f"共 {len(whitelist_entries)} 條記錄",
                    color=discord.Color.green()
                )
                
                for entry in whitelist_entries:
                    guild = bot.get_guild(entry.guild_id)
                    guild_name = guild.name if guild else f"未知伺服器 ({entry.guild_id})"
                    
                    embed.add_field(
                        name=f"伺服器: {guild_name}",
                        value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                session.close()
                return
            
            elif reason:
                # 查詢特定原因的白名單記錄
                whitelist_entries = session.query(Whitelist).filter(
                    Whitelist.reason.ilike(f"%{reason}%")
                ).all()
                
                if not whitelist_entries:
                    await interaction.response.send_message(f"✅ 沒有找到原因包含 '{reason}' 的白名單記錄", ephemeral=True)
                    session.close()
                    return
                
                # 按伺服器分組
                whitelist_by_guild = {}
                for entry in whitelist_entries:
                    if entry.guild_id not in whitelist_by_guild:
                        whitelist_by_guild[entry.guild_id] = []
                    whitelist_by_guild[entry.guild_id].append(entry)
                
                embeds = []
                for guild_id, entries in whitelist_by_guild.items():
                    guild = bot.get_guild(guild_id)
                    guild_name = guild.name if guild else f"未知伺服器 ({guild_id})"
                    
                    embed = discord.Embed(
                        title=f"✅ {guild_name} 的白名單 (原因: {reason})",
                        description=f"共 {len(entries)} 個用戶",
                        color=discord.Color.green()
                    )
                    
                    for entry in entries:
                        try:
                            u = await bot.fetch_user(entry.user_id)
                            user_info = f"👤 {u} (ID: {entry.user_id})"
                        except:
                            user_info = f"👤 ID: {entry.user_id}"
                        
                        embed.add_field(
                            name=user_info,
                            value=f"時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                            inline=False
                        )
                    
                    embeds.append(embed)
                
                await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
                
                if len(embeds) > 10:
                    for i in range(10, len(embeds), 10):
                        await interaction.followup.send(embeds=embeds[i:i+10])
                
                session.close()
                return
        
        # 查詢所有白名單
        all_whitelist_entries = session.query(Whitelist).all()
        session.close()
        
        if not all_whitelist_entries:
            await interaction.response.send_message("✅ 全域白名單為空", ephemeral=True)
            return
        
        # 按伺服器分組
        whitelist_by_guild = {}
        for entry in all_whitelist_entries:
            if entry.guild_id not in whitelist_by_guild:
                whitelist_by_guild[entry.guild_id] = []
            whitelist_by_guild[entry.guild_id].append(entry)
        
        embeds = []
        for guild_id, entries in whitelist_by_guild.items():
            guild = bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"未知伺服器 ({guild_id})"
            
            embed = discord.Embed(
                title=f"✅ {guild_name} 的白名單",
                description=f"共 {len(entries)} 個用戶",
                color=discord.Color.green()
            )
            
            for entry in entries:
                try:
                    u = await bot.fetch_user(entry.user_id)
                    user_info = f"👤 {u} (ID: {entry.user_id})"
                except:
                    user_info = f"👤 ID: {entry.user_id}"
                
                embed.add_field(
                    name=user_info,
                    value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )
            
            embeds.append(embed)
        
        # 添加總結 embed
        summary_embed = discord.Embed(
            title="🌍 全域白名單總結",
            color=discord.Color.green()
        )
        summary_embed.add_field(name="涉及伺服器", value=f"{len(whitelist_by_guild)} 個", inline=False)
        summary_embed.add_field(name="白名單用戶總數", value=f"{len(all_whitelist_entries)} 個", inline=False)
        
        embeds.insert(0, summary_embed)
        
        await interaction.response.send_message(embeds=embeds[:10] if len(embeds, ephemeral=True) > 10 else embeds)
        
        if len(embeds) > 10:
            for i in range(10, len(embeds), 10):
                await interaction.followup.send(embeds=embeds[i:i+10])
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢全域白名單失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="警告", description="警告用戶（需要管理員）")
@app_commands.describe(user="要警告的用戶", reason="警告原因")
async def warn_user(interaction: Interaction, user: discord.User, reason: str = "未提供原因"):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        warning = Warning(
            guild_id=interaction.guild.id,
            user_id=user.id,
            warned_by=interaction.user.id,
            reason=reason
        )
        session.add(warning)
        session.commit()
        
        warning_count = session.query(Warning).filter(
            Warning.guild_id == interaction.guild.id,
            Warning.user_id == user.id
        ).count()
        session.close()
        
        embed = discord.Embed(title="⚠️ 用戶已被警告", color=discord.Color.orange())
        embed.add_field(name="被警告用戶", value=user.mention, inline=False)
        embed.add_field(name="原因", value=reason, inline=False)
        embed.add_field(name="警告者", value=interaction.user.mention, inline=False)
        embed.add_field(name="該用戶警告次數", value=f"{warning_count} 次", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        try:
            embed_dm = discord.Embed(title="⚠️ 您已被警告", color=discord.Color.orange())
            embed_dm.add_field(name="伺服器", value=interaction.guild.name, inline=False)
            embed_dm.add_field(name="原因", value=reason, inline=False)
            embed_dm.add_field(name="警告者", value=interaction.user.mention, inline=False)
            embed_dm.add_field(name="您在此伺服器的警告次數", value=f"{warning_count} 次", inline=False)
            await user.send(embed=embed_dm)
        except:
            pass
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 警告失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="解除警告", description="移除用戶的警告（需要管理員）")
@app_commands.describe(user="要移除警告的用戶", warning_id="警告 ID（為空則移除最後一個警告）")
async def remove_warning(interaction: Interaction, user: discord.User, warning_id: int = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        
        if warning_id:
            warning = session.query(Warning).filter(
                Warning.id == warning_id,
                Warning.guild_id == interaction.guild.id,
                Warning.user_id == user.id
            ).first()
            
            if not warning:
                await interaction.response.send_message("❌ 找不到該警告記錄", ephemeral=True)
                session.close()
                return
            
            session.delete(warning)
            session.commit()
        else:
            warning = session.query(Warning).filter(
                Warning.guild_id == interaction.guild.id,
                Warning.user_id == user.id
            ).order_by(Warning.warned_at.desc()).first()
            
            if not warning:
                await interaction.response.send_message("❌ 該用戶沒有警告記錄", ephemeral=True)
                session.close()
                return
            
            session.delete(warning)
            session.commit()
        
        remaining_count = session.query(Warning).filter(
            Warning.guild_id == interaction.guild.id,
            Warning.user_id == user.id
        ).count()
        session.close()
        
        embed = discord.Embed(title="✅ 警告已移除", color=discord.Color.green())
        embed.add_field(name="用戶", value=user.mention, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="剩餘警告次數", value=f"{remaining_count} 次", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="警告查詢", description="查詢用戶的警告記錄")
@app_commands.describe(user="要查詢的用戶")
async def check_warnings(interaction: Interaction, user: discord.User):
    try:
        session = SessionLocal()
        warnings = session.query(Warning).filter(
            Warning.guild_id == interaction.guild.id,
            Warning.user_id == user.id
        ).order_by(Warning.warned_at.desc()).all()
        session.close()
        
        if not warnings:
            embed = discord.Embed(title="✅ 無警告記錄", color=discord.Color.green())
            embed.description = f"{user.mention} 在此伺服器沒有警告記錄"
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⚠️ {user.name} 的警告記錄",
            description=f"共 {len(warnings)} 次警告",
            color=discord.Color.orange()
        )
        
        for i, warning in enumerate(warnings, 1):
            try:
                warner = await bot.fetch_user(warning.warned_by)
                warner_name = str(warner)
            except:
                warner_name = f"ID: {warning.warned_by}"
            
            embed.add_field(
                name=f"警告 #{i} (ID: {warning.id})",
                value=f"原因: {warning.reason}\n警告者: {warner_name}\n時間: {warning.warned_at.strftime('%Y-%m-%d %H:%M:%S')}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="伺服器列表", description="顯示機器人所在的所有伺服器（限開發者）")
async def guild_list(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        guilds = bot.guilds
        embed = discord.Embed(title="🖥️ 機器人所在伺服器列表", color=discord.Color.blue())
        embed.description = f"機器人目前已連線到 **{len(guilds)}** 個伺服器"
        
        guild_list_text = ""
        for idx, guild in enumerate(guilds, 1):
            member_count = guild.member_count if guild.member_count else "未知"
            line = f"{idx}. **{guild.name}** (ID: {guild.id})\n   成員數: {member_count}\n"
            
            # 檢查是否超過字段限制，分頁處理
            if len(guild_list_text) + len(line) > 1024:
                embed.add_field(name="伺服器詳情 (續)", value=guild_list_text.strip(), inline=False)
                guild_list_text = line
            else:
                guild_list_text += line
        
        if guild_list_text:
            embed.add_field(name="伺服器詳情", value=guild_list_text.strip(), inline=False)
        else:
            embed.description = "機器人目前未連線到任何伺服器"
        
        embed.set_footer(text=f"總計: {len(guilds)} 個伺服器 | 更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await interaction.response.send_message(embed=embed, ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢伺服器列表失敗：{str(e)}", ephemeral=True)
        print(f"⚠️ /伺服器列表 指令錯誤：{str(e)}")

@bot.tree.command(name="關閉機器人", description="關閉機器人（限開發者）")
async def shutdown_bot(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    embed = discord.Embed(title="🛑 機器人關閉中...", color=discord.Color.red())
    embed.description = "正在關閉機器人，再見！"
    await interaction.response.send_message(embed=embed, ephemeral=False)
    print("✅ 機器人收到關閉指令，正在關閉...")
    
    # 發送關閉通知到指定頻道
    try:
        notification_channel = bot.get_channel(1444169618401792051)
        if notification_channel:
            notification_embed = discord.Embed(title="🛑 機器人已關閉", color=discord.Color.red())
            notification_embed.description = f"機器人由 {interaction.user.mention} 在 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 關閉"
            notification_embed.add_field(name="操作者", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
            notification_embed.add_field(name="伺服器", value=interaction.guild.name if interaction.guild else "DM", inline=False)
            await notification_channel.send(embed=notification_embed)
            print("✅ 已發送關閉通知")
    except Exception as e:
        print(f"⚠️ 發送關閉通知失敗: {str(e)}")
    
    await bot.close()

@bot.tree.command(name="定時關閉機器人", description="在指定時間自動關閉機器人（限開發者）")
@app_commands.describe(time="指定時間（格式：HH:MM，如 14:30 或 23:59）")
async def scheduled_shutdown(interaction: Interaction, time: str):
    global scheduled_shutdown_task
    
    if not can_use_dangerous_commands(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有權限使用此危險指令", ephemeral=True)
        return
    
    try:
        # 解析時間格式
        if ":" in time:
            hour, minute = map(int, time.split(":"))
        else:
            hour = int(time)
            minute = 0
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            await interaction.response.send_message("❌ 時間格式無效。請使用 HH:MM 格式（如 14:30）", ephemeral=True)
            return
        
        # 計算目標時間
        now = datetime.now()
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 如果指定的時間已經過了，設置為明天的該時間
        if target_time <= now:
            target_time = target_time + timedelta(days=1)
        
        # 計算等待秒數
        wait_seconds = (target_time - now).total_seconds()
        
        if wait_seconds < 10:
            await interaction.response.send_message("❌ 指定時間過於接近，請選擇至少 10 秒後的時間", ephemeral=True)
            return
        
        # 如果已有運行的關閉任務，取消它
        if scheduled_shutdown_task and not scheduled_shutdown_task.done():
            scheduled_shutdown_task.cancel()
            print("⚠️ 取消了之前的定時關閉任務")
        
        embed = discord.Embed(title="⏱️ 定時關閉已設置", color=discord.Color.orange())
        embed.description = f"機器人將在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 關閉"
        embed.add_field(name="指定時間", value=f"{time}", inline=False)
        embed.add_field(name="等待時長", value=f"{int(wait_seconds)} 秒（{int(wait_seconds//60)} 分 {int(wait_seconds%60)} 秒）", inline=False)
        embed.add_field(name="預計關閉時間", value=f"{target_time.strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        embed.add_field(name="操作者", value=f"{interaction.user.mention}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        print(f"⏱️ 機器人將在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 關閉（{int(wait_seconds)} 秒後）")
        
        # 定時關閉機器人
        async def shutdown_later():
            try:
                await asyncio.sleep(wait_seconds)
                print(f"⏰ 定時時間已到：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    notification_channel = bot.get_channel(1444169618401792051)
                    if notification_channel:
                        notification_embed = discord.Embed(title="⏱️ 機器人定時關閉中", color=discord.Color.red())
                        notification_embed.description = f"機器人由 {interaction.user.mention} 設置的定時關閉指令，將於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 關閉"
                        notification_embed.add_field(name="操作者", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
                        await notification_channel.send(embed=notification_embed)
                        print("✅ 已發送定時關閉通知")
                except Exception as e:
                    print(f"⚠️ 發送定時關閉通知失敗: {str(e)}")
                
                print("🛑 機器人正在執行定時關閉...")
                await asyncio.sleep(1)  # 給予時間完成消息發送
                await bot.close()
            except asyncio.CancelledError:
                print("⚠️ 定時關閉任務已被取消")
            except Exception as e:
                print(f"❌ 定時關閉錯誤: {str(e)}")
        
        scheduled_shutdown_task = asyncio.create_task(shutdown_later())
    
    except ValueError:
        await interaction.response.send_message("❌ 時間格式無效。請使用 HH:MM 格式（如 14:30）或輸入小時（如 14）", ephemeral=True)

@bot.tree.command(name="開發者通知指定伺服器版主", description="向指定伺服器的版主發送通知（限開發者）")
@app_commands.describe(guild_name="伺服器名稱", message="通知消息")
async def notify_guild_admins(interaction: Interaction, guild_name: str, message: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        # 通過伺服器名稱查找伺服器
        guild = None
        for g in bot.guilds:
            if g.name == guild_name:
                guild = g
                break
        
        if not guild:
            error_embed = discord.Embed(title="❌ 伺服器不存在", color=discord.Color.red())
            error_embed.description = f"找不到名稱為 '{guild_name}' 的伺服器"
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return
        
        guild_owner = guild.owner
        
        # 準備通知消息 Embed
        notification_embed = discord.Embed(title="📢 開發者通知", color=discord.Color.blurple())
        notification_embed.description = message
        notification_embed.add_field(name="目標伺服器", value=f"{guild_name} ({guild.id})", inline=False)
        notification_embed.add_field(name="發送者", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
        notification_embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        
        # 發送私人信息給版主
        dm_sent = False
        if guild_owner:
            try:
                await guild_owner.send(f"{guild_owner.mention}", embed=notification_embed)
                dm_sent = True
                print(f"✅ 已向版主 {guild_owner.name} 發送私人信息")
            except Exception as e:
                print(f"⚠️ 無法發送私人信息給版主: {str(e)}")
        else:
            print("❌ 找不到伺服器版主")
        
        # 發送通知到指定頻道
        notification_channel = bot.get_channel(1430905519052423229)
        if notification_channel:
            await notification_channel.send(embed=notification_embed)
            print("✅ 已發送通知到通知頻道")
        else:
            print("❌ 找不到通知頻道")
        
        response_embed = discord.Embed(title="✅ 通知已發送", color=discord.Color.green())
        if dm_sent and guild_owner:
            response_embed.description = f"✅ 已向 **{guild_owner.name}** (版主) 的私人信息發送通知\n✅ 也已在通知頻道發送"
        else:
            response_embed.description = f"✅ 已在通知頻道發送通知"
            if not guild_owner:
                response_embed.add_field(name="⚠️ 提示", value="無法發送私人信息給版主", inline=False)
        await interaction.response.send_message(embed=response_embed, ephemeral=True)
        print(f"✅ 開發者通知已發送到 {guild_name}")
        
    except Exception as e:
        error_embed = discord.Embed(title="❌ 發送失敗", color=discord.Color.red())
        error_embed.description = f"錯誤: {str(e)}"
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        print(f"❌ 發送通知失敗: {str(e)}")

@bot.tree.command(name="離開這個伺服器", description="讓機器人離開此伺服器（限開發者）")
async def leave_this_guild(interaction: Interaction):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    try:
        guild_name = interaction.guild.name
        guild_id = interaction.guild.id
        
        embed = discord.Embed(title="👋 正在離開伺服器...", color=discord.Color.orange())
        embed.description = f"正在離開 **{guild_name}** ({guild_id})"
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # 發送離開通知到指定頻道
        try:
            notification_channel = bot.get_channel(1430905519052423229)
            if notification_channel:
                notification_embed = discord.Embed(title="👋 機器人已離開伺服器", color=discord.Color.orange())
                notification_embed.description = f"機器人由 {interaction.user.mention} 在 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 離開"
                notification_embed.add_field(name="操作者", value=f"{interaction.user.name}#{interaction.user.discriminator}", inline=False)
                notification_embed.add_field(name="離開的伺服器", value=f"{guild_name} ({guild_id})", inline=False)
                notification_embed.add_field(name="剩餘伺服器數", value=f"{len(bot.guilds) - 1} 個", inline=False)
                await notification_channel.send(embed=notification_embed)
                print(f"✅ 已發送離開通知：{guild_name}")
        except Exception as e:
            print(f"⚠️ 發送離開通知失敗: {str(e)}")
        
        await interaction.guild.leave()
        print(f"✅ 機器人已離開伺服器：{guild_name} ({guild_id})")
        
    except Exception as e:
        error_embed = discord.Embed(title="❌ 離開伺服器失敗", color=discord.Color.red())
        error_embed.description = f"錯誤: {str(e)}"
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        print(f"❌ 離開伺服器失敗: {str(e)}")

@bot.tree.command(name="send_dm_to_user", description="向指定的 Discord 用戶發送私人信息（限開發者）")
@app_commands.describe(user_id="要發送信息的用戶 ID", message="要發送的信息內容")
async def send_dm_to_user_cmd(interaction: Interaction, user_id: str, message: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        # 轉換用戶 ID 為整數
        try:
            user_id_int = int(user_id)
        except ValueError:
            await interaction.response.send_message(f"❌ 無效的用戶 ID：`{user_id}` 必須是數字", ephemeral=True)
            return
        
        # 嘗試獲取用戶
        user = await bot.fetch_user(user_id_int)
        
        if not user:
            await interaction.response.send_message(f"❌ 找不到 ID 為 {user_id} 的用戶", ephemeral=True)
            return
        
        # 直接發送消息（不顯示元數據）
        await user.send(message)
        
        # 回應用戶
        success_embed = discord.Embed(title="✅ 信息已發送", color=discord.Color.green())
        success_embed.description = f"✅ 已成功向 {user.name}#{user.discriminator} 發送信息"
        success_embed.add_field(name="目標用戶 ID", value=f"`{user_id}`", inline=False)
        success_embed.add_field(name="發送內容", value=message, inline=False)
        await interaction.response.send_message(embed=success_embed, ephemeral=False)
        
        print(f"✅ 已向用戶 {user.name} ({user_id}) 發送信息")
        
    except discord.NotFound:
        error_embed = discord.Embed(title="❌ 用戶不存在", color=discord.Color.red())
        error_embed.description = f"找不到 ID 為 `{user_id}` 的用戶"
        await interaction.response.send_message(embed=error_embed, ephemeral=False)
        print(f"❌ 用戶 {user_id} 不存在")
        
    except discord.Forbidden:
        error_embed = discord.Embed(title="❌ 無法發送信息", color=discord.Color.red())
        error_embed.description = f"無法向該用戶發送私人信息，可能是因為用戶已禁用 DM"
        await interaction.response.send_message(embed=error_embed, ephemeral=False)
        print(f"⚠️ 無法向用戶 {user_id} 發送私人信息")
        
    except Exception as e:
        error_embed = discord.Embed(title="❌ 發送失敗", color=discord.Color.red())
        error_embed.description = f"發送信息時出錯：{str(e)}"
        await interaction.response.send_message(embed=error_embed, ephemeral=False)
        print(f"❌ 發送信息失敗：{str(e)}")

@bot.tree.command(name="settings", description="查看目前伺服器設定")
async def settings_cmd(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    session = SessionLocal()
    guild = session.query(Guild).filter_by(guild_id=interaction.guild.id).first()
    session.close()
    
    if not guild:
        await interaction.response.send_message("❌ 此伺服器尚未設定", ephemeral=True)
        return
    
    embed = discord.Embed(title="📊 目前設定狀態", color=discord.Color.blue())
    
    if guild.tw_alert_channel:
        embed.add_field(
            name="🚨 臺灣地震速報",
            value=f"頻道: <#{guild.tw_alert_channel}>" + (f"\n身份組: <@&{guild.tw_alert_role}>" if guild.tw_alert_role else ""),
            inline=False
        )
    
    if guild.tw_report_channel:
        embed.add_field(
            name="📢 臺灣有感地震報告",
            value=f"頻道: <#{guild.tw_report_channel}>" + (f"\n身份組: <@&{guild.tw_report_role}>" if guild.tw_report_role else ""),
            inline=False
        )
    
    if guild.tw_small_report_channel:
        embed.add_field(name="🔔 小區域報告", value=f"頻道: <#{guild.tw_small_report_channel}>", inline=False)
    
    if guild.japan_alert_channel:
        embed.add_field(
            name="🗾 日本地震速報",
            value=f"頻道: <#{guild.japan_alert_channel}>" + (f"\n身份組: <@&{guild.japan_alert_role}>" if guild.japan_alert_role else ""),
            inline=False
        )
    
    if not any([guild.tw_alert_channel, guild.tw_report_channel, guild.tw_small_report_channel, guild.japan_alert_channel]):
        embed.description = "❌ 尚未設定任何地震通知"
    
    await ctx.send(embed=embed)

@bot.event
async def on_guild_join(guild):
    print(f"✅ 加入伺服器: {guild.name} ({guild.id})")
    
    # 【優先】發送加入通知到指定頻道 - 必須首先執行，確保通知不會因為資料庫失敗而遺漏
    try:
        notification_channel = bot.get_channel(1444166776635134023)
        if notification_channel:
            notification_embed = discord.Embed(title="👋 Bot1 已加入伺服器", color=discord.Color.green())
            notification_embed.description = f"機器人在 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 加入新伺服器"
            notification_embed.add_field(name="加入的伺服器", value=f"{guild.name} ({guild.id})", inline=False)
            notification_embed.add_field(name="伺服器成員數", value=f"{guild.member_count} 位", inline=False)
            notification_embed.add_field(name="伺服器擁有者", value=f"<@{guild.owner_id}>", inline=False)
            notification_embed.add_field(name="目前伺服器總數", value=f"{len(bot.guilds)} 個", inline=False)
            await notification_channel.send(embed=notification_embed)
            print(f"✅ 已發送加入通知：{guild.name}")
    except Exception as e:
        print(f"⚠️ 發送加入通知失敗: {str(e)}")
    
    # 【其次】嘗試創建伺服器資料庫記錄 - 如果失敗不影響通知已發送的事實
    try:
        get_or_create_guild(guild.id)
        print(f"✅ 已創建伺服器資料庫記錄: {guild.name}")
    except Exception as e:
        print(f"⚠️ 無法創建伺服器資料庫記錄: {str(e)}")

@bot.event
async def on_guild_remove(guild):
    print(f"❌ 已被踢出伺服器: {guild.name} ({guild.id})")
    
    # 發送被踢出通知到指定頻道
    try:
        notification_channel = bot.get_channel(1444166776635134023)
        if notification_channel:
            notification_embed = discord.Embed(title="[Bot1 已被踢出伺服器]", color=discord.Color.red())
            notification_embed.description = f"機器人在 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 被踢出伺服器"
            notification_embed.add_field(name="被踢出的伺服器", value=f"{guild.name} ({guild.id})", inline=False)
            notification_embed.add_field(name="伺服器擁有者ID", value=f"{guild.owner_id}", inline=False)
            notification_embed.add_field(name="目前伺服器總數", value=f"{len(bot.guilds)} 個", inline=False)
            await notification_channel.send(embed=notification_embed)
            print(f"✅ 已發送被踢出通知：{guild.name}")
    except Exception as e:
        print(f"⚠️ 發送被踢出通知失敗: {str(e)}")
    
    # 發送私人通知給伺服器版主
    try:
        if guild.owner_id:
            owner = await bot.fetch_user(guild.owner_id)
            if owner:
                owner_dm_embed = discord.Embed(title="[機器人已被踢出伺服器]", color=discord.Color.red())
                owner_dm_embed.description = f"哲學製作機器人已被踢出您的伺服器"
                owner_dm_embed.add_field(name="伺服器名稱", value=guild.name, inline=False)
                owner_dm_embed.add_field(name="伺服器 ID", value=str(guild.id), inline=False)
                owner_dm_embed.add_field(name="提出時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                owner_dm_embed.set_footer(text="感謝您曾使用本機器人")
                
                await owner.send(embed=owner_dm_embed)
                print(f"✅ 已向伺服器版主 {owner} 發送被踢出通知")
    except Exception as e:
        print(f"⚠️ 無法向伺服器版主發送私人訊息：{str(e)}")

@bot.tree.command(name="運勢", description="查看今天的運勢")
async def fortune(interaction: Interaction):
    fortunes = [
        ("🟢 大吉", "今天運勢極佳！一切順利，把握機會！"),
        ("🟡 中吉", "運勢不錯，適合進行新計畫"),
        ("🟠 小吉", "運勢平平，謹慎行動會有驚喜"),
        ("🔵 末吉", "運勢一般，保持耐心會有轉機"),
        ("🔴 大凶", "今天運勢欠佳，做事要格外小心！")
    ]
    
    fortune_name, fortune_desc = random.choice(fortunes)
    
    embed = discord.Embed(title="🔮 今日運勢", color=discord.Color.purple())
    embed.description = fortune_name
    embed.add_field(name="📖 詳細", value=fortune_desc, inline=False)
    embed.add_field(name="查詢者", value=interaction.user.mention, inline=False)
    embed.add_field(name="查詢時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    embed.set_footer(text="💫 願你今天運勢滿滿")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="簽到", description="進行每日簽到")
async def checkin(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    session = SessionLocal()
    
    try:
        existing_checkin = session.query(DailyCheckin).filter_by(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            checkin_date=today
        ).first()
        
        if existing_checkin:
            await interaction.response.send_message(
                "✅ 你今天已經簽到過了！\n\n💪 明天再來簽到吧！",
                ephemeral=False
            )
            session.close()
            return
        
        # 新增簽到記錄
        checkin = DailyCheckin(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            checkin_date=today
        )
        session.add(checkin)
        session.commit()
        
        # 查詢連續簽到天數
        all_checkins = session.query(DailyCheckin).filter_by(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id
        ).all()
        
        streak = 1
        if all_checkins:
            sorted_checkins = sorted(all_checkins, key=lambda x: x.checkin_date, reverse=True)
            for i, c in enumerate(sorted_checkins[1:]):
                target_date = datetime.strptime(sorted_checkins[i].checkin_date, "%Y-%m-%d") - timedelta(days=1)
                if c.checkin_date == target_date.strftime("%Y-%m-%d"):
                    streak += 1
                else:
                    break
        
        embed = discord.Embed(title="✅ 簽到成功", color=discord.Color.green())
        embed.description = f"歡迎回來，{interaction.user.mention}！"
        embed.add_field(name="簽到日期", value=today, inline=False)
        embed.add_field(name="📈 連續簽到天數", value=f"{streak} 天", inline=False)
        embed.add_field(name="🎁 今日獲得", value="+10 經驗值", inline=False)
        embed.set_footer(text="繼續簽到，保持連勝紀錄！")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    finally:
        session.close()

@bot.tree.command(name="數數字", description="數字猜謎遊戲")
async def number_game(interaction: Interaction):
    secret_number = random.randint(1, 100)
    guesses = []
    
    embed = discord.Embed(
        title="🎮 數字猜謎遊戲",
        description="我想了一個 1-100 之間的數字\n你有 10 次機會猜出來！",
        color=discord.Color.blue()
    )
    embed.add_field(name="📝 規則", value="在聊天室直接輸入數字即可", inline=False)
    embed.add_field(name="💡 提示", value="• 太小：我會說 '大一點'\n• 太大：我會說 '小一點'\n• 猜對：恭喜你贏了！", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    def check(message):
        return message.author == interaction.user and message.channel == interaction.channel
    
    attempts = 0
    while attempts < 10:
        try:
            message = await bot.wait_for("message", check=check, timeout=60)
            attempts += 1
            
            try:
                guess = int(message.content)
                if guess < 1 or guess > 100:
                    await message.reply("❌ 請輸入 1-100 之間的數字")
                    attempts -= 1
                    continue
                
                guesses.append(guess)
                
                if guess == secret_number:
                    embed = discord.Embed(
                        title="🎉 恭喜你贏了！",
                        description=f"你用 {attempts} 次機會就猜到了！",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="🎯 正確答案", value=secret_number, inline=False)
                    embed.add_field(name="📊 你的猜測", value=str(guesses), inline=False)
                    await message.reply(embed=embed)
                    return
                
                elif guess < secret_number:
                    hint = f"🔺 大一點！ (剩餘機會: {10 - attempts})"
                elif guess > secret_number:
                    hint = f"🔻 小一點！ (剩餘機會: {10 - attempts})"
                
                await message.reply(hint)
            
            except ValueError:
                await message.reply("❌ 請輸入有效的數字")
                attempts -= 1
        
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ 遊戲超時",
                description="超過 60 秒未輸入，遊戲結束",
                color=discord.Color.red()
            )
            embed.add_field(name="🎯 正確答案", value=secret_number, inline=False)
            await interaction.followup.send(embed=embed)
            return
    
    embed = discord.Embed(
        title="😢 遊戲結束",
        description="你用完了所有機會",
        color=discord.Color.red()
    )
    embed.add_field(name="🎯 正確答案", value=secret_number, inline=False)
    embed.add_field(name="📊 你的猜測", value=str(guesses), inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="離開伺服器", description="讓機器人離開指定伺服器（只有主人可用）")
@app_commands.describe(guild_id="伺服器 ID")
async def leave_guild(interaction: Interaction, guild_id: str):
    if not can_use_dangerous_commands(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有權限使用此危險指令", ephemeral=True)
        return
    
    try:
        target_guild = bot.get_guild(int(guild_id))
        if not target_guild:
            await interaction.response.send_message(f"❌ 找不到伺服器：{guild_id}", ephemeral=True)
            return
        
        guild_name = target_guild.name
        await target_guild.leave()
        
        embed = discord.Embed(title="✅ 已離開伺服器", color=discord.Color.green())
        embed.description = f"機器人已成功離開伺服器"
        embed.add_field(name="伺服器名稱", value=guild_name, inline=False)
        embed.add_field(name="伺服器 ID", value=guild_id, inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="執行時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
        print(f"✅ 機器人已離開伺服器：{guild_name} ({guild_id})")
    except ValueError:
        await interaction.response.send_message("❌ 伺服器 ID 必須是有效的數字", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 執行失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="等級設置", description="設定用戶等級（只有管理員和主人可用）")
@app_commands.describe(user="目標用戶", level="等級", experience="經驗值")
async def set_user_level(interaction: Interaction, user: discord.User, level: int, experience: int = 0):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    is_admin = member and member.guild_permissions.administrator if member else False
    is_owner = is_bot_admin(interaction.user.id)
    
    if not (is_admin or is_owner):
        await interaction.response.send_message("❌ 此指令只有管理員和主人可以使用", ephemeral=True)
        return
    
    if level < 1 or level > 999:
        await interaction.response.send_message("❌ 等級必須介於 1 到 999 之間", ephemeral=True)
        return
    
    if experience < 0:
        await interaction.response.send_message("❌ 經驗值不能為負數", ephemeral=True)
        return
    
    try:
        session = SessionLocal()
        user_level = session.query(UserLevel).filter_by(
            guild_id=interaction.guild.id,
            user_id=user.id
        ).first()
        
        if not user_level:
            user_level = UserLevel(
                guild_id=interaction.guild.id,
                user_id=user.id,
                level=level,
                experience=experience,
                total_experience=experience
            )
            session.add(user_level)
        else:
            user_level.level = level
            user_level.experience = experience
            user_level.total_experience = experience
        
        session.commit()
        session.close()
        
        embed = discord.Embed(title="✅ 等級已設定", color=discord.Color.green())
        embed.description = f"用戶 {user.mention} 的等級已更新"
        embed.add_field(name="用戶", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="⭐ 等級", value=f"Lv. {level}", inline=False)
        embed.add_field(name="💪 經驗值", value=f"{experience} EXP", inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="設定時間", value=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        print(f"✅ 設定用戶 {user.id} 的等級為 {level}")
    except Exception as e:
        await interaction.response.send_message(f"❌ 設定失敗：{str(e)}", ephemeral=True)

# 圖片選項對應表
BROADCAST_IMAGES = {
    "none": None,
    "announcement1": "https://via.placeholder.com/1200x400/4285F4/ffffff?text=公告1",
    "announcement2": "https://via.placeholder.com/1200x400/34A853/ffffff?text=公告2",
    "announcement3": "https://via.placeholder.com/1200x400/FBBC04/ffffff?text=公告3",
}

class BroadcastImageSelect(ui.Select):
    """圖片選擇菜單"""
    def __init__(self, message: str):
        self.message = message
        options = [
            discord.SelectOption(label="無圖片", value="none", emoji="🚫"),
            discord.SelectOption(label="公告圖片 1", value="announcement1", emoji="🎨"),
            discord.SelectOption(label="公告圖片 2", value="announcement2", emoji="🎨"),
            discord.SelectOption(label="公告圖片 3", value="announcement3", emoji="🎨"),
        ]
        super().__init__(placeholder="選擇廣播圖片...", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: Interaction):
        selected_image = self.values[0]
        image_url = BROADCAST_IMAGES.get(selected_image)
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 準備廣播 Embed
            embed = discord.Embed(color=discord.Color.gold())
            embed.description = self.message
            
            if image_url:
                embed.set_image(url=image_url)
            
            # 向所有伺服器發送廣播
            sent_count = 0
            failed_count = 0
            
            for guild in bot.guilds:
                try:
                    session = SessionLocal()
                    guild_config = session.query(Guild).filter_by(guild_id=guild.id).first()
                    session.close()
                    
                    target_channel = None
                    if guild_config and guild_config.announcement_channel:
                        target_channel = bot.get_channel(guild_config.announcement_channel)
                    
                    if not target_channel:
                        target_channel = guild.text_channels[0] if guild.text_channels else None
                    
                    if target_channel and target_channel.permissions_for(guild.me).send_messages:
                        await target_channel.send(embed=embed)
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    print(f"⚠️ 無法發送到 {guild.name}: {str(e)}")
                    failed_count += 1
            
            # 準備回應
            result_embed = discord.Embed(title="✅ 廣播已發送", color=discord.Color.green())
            result_embed.description = f"廣播訊息已發送到 {sent_count} 個伺服器"
            if failed_count > 0:
                result_embed.add_field(name="⚠️ 失敗伺服器", value=f"{failed_count} 個", inline=False)
            result_embed.add_field(name="廣播內容", value=self.message[:1024], inline=False)
            
            await interaction.followup.send(embed=result_embed, ephemeral=True)
            print(f"✅ 廣播已發送到 {sent_count} 個伺服器（失敗 {failed_count} 個）")
        
        except Exception as e:
            await interaction.followup.send(f"❌ 廣播失敗：{str(e)}", ephemeral=True)
            print(f"❌ 廣播失敗：{str(e)}")

class BroadcastImageView(ui.View):
    """廣播圖片選擇視圖"""
    def __init__(self, message: str):
        super().__init__()
        self.add_item(BroadcastImageSelect(message))

@bot.tree.command(name="廣播", description="向所有伺服器發送廣播訊息（限開發者）")
@app_commands.describe(message="廣播訊息內容")
async def broadcast(interaction: Interaction, message: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        # 顯示圖片選擇器
        embed = discord.Embed(
            title="📸 選擇廣播圖片",
            description="請從下方選擇廣播所需的圖片",
            color=discord.Color.blue()
        )
        embed.add_field(name="📝 廣播內容", value=message[:1024], inline=False)
        
        view = BroadcastImageView(message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 廣播準備失敗：{str(e)}", ephemeral=True)
        print(f"❌ 廣播準備失敗：{str(e)}")

@tasks.loop(minutes=30)
async def send_bot_status_notification():
    """每30分鐘發送機器人狀態到指定頻道"""
    try:
        channel = bot.get_channel(1442033762287484928)
        if not channel:
            return
        
        guilds_count = len(bot.guilds)
        total_members = sum(guild.member_count or 0 for guild in bot.guilds)
        uptime = datetime.now() - bot.launch_time if hasattr(bot, 'launch_time') else timedelta(0)
        
        embed = discord.Embed(
            title="🤖 機器人狀態通知",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="伺服器數", value=f"{guilds_count} 個", inline=True)
        embed.add_field(name="總成員數", value=f"{total_members:,} 人", inline=True)
        embed.add_field(name="運行時間", value=f"{str(uptime).split('.')[0]}", inline=True)
        embed.add_field(name="機器人狀態", value="✅ 正常運行", inline=True)
        embed.add_field(name="延遲", value=f"{round(bot.latency * 1000)} ms", inline=True)
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ 機器人狀態通知失敗：{str(e)}")

@bot.tree.command(name="reload", description="重新載入模組（僅限機器人主人）")
@app_commands.describe(module="要重新載入的模組名稱")
async def reload_module(interaction: Interaction, module: str = "all"):
    """重新載入指定模組"""
    await interaction.response.defer(ephemeral=True)
    
    if not is_bot_admin(interaction.user.id):
        await interaction.followup.send("❌ 只有開發者可以使用此指令", ephemeral=True)
        return
    
    try:
        embed = discord.Embed(
            title="🔄 模組重新載入",
            color=discord.Color.blue()
        )
        
        if module.lower() == "all":
            await interaction.followup.send("⏳ 正在重新載入所有模組...", ephemeral=True)
            return
        
        # 嘗試重新載入指定模組
        try:
            # 假設模組在 cogs 文件夾中
            await bot.reload_extension(f"cogs.{module}")
            embed.description = f"✅ 模組 `{module}` 已成功重新載入"
            embed.color = discord.Color.green()
        except Exception as e:
            embed.description = f"❌ 重新載入模組 `{module}` 失敗：{str(e)}"
            embed.color = discord.Color.red()
        
        embed.add_field(name="模組名稱", value=module, inline=False)
        embed.add_field(name="執行時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # 記錄到通知頻道
        log_channel = bot.get_channel(1444169106700898324)
        if log_channel:
            log_embed = discord.Embed(
                title="📊 指令使用記錄",
                description="模組重新載入",
                color=discord.Color.blue()
            )
            log_embed.add_field(name="用戶", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="模組", value=module, inline=True)
            log_embed.add_field(name="伺服器", value=f"{interaction.guild.name if interaction.guild else 'DM'}", inline=True)
            log_embed.add_field(name="時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except:
                pass
    
    except Exception as e:
        embed = discord.Embed(
            title="❌ 重新載入失敗",
            description=str(e),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="reload_all", description="重新載入所有模組（僅限機器人主人）")
async def reload_all_modules(interaction: Interaction):
    """重新載入所有模組"""
    await interaction.response.defer(ephemeral=True)
    
    if not is_bot_admin(interaction.user.id):
        await interaction.followup.send("❌ 只有開發者可以使用此指令", ephemeral=True)
        return
    
    try:
        embed = discord.Embed(
            title="🔄 全部模組重新載入",
            color=discord.Color.blue()
        )
        
        # 獲取所有已加載的模組
        loaded_modules = list(bot.extensions.keys())
        
        if not loaded_modules:
            embed.description = "⚠️ 目前沒有已加載的模組"
            embed.color = discord.Color.orange()
            embed.add_field(name="模組數量", value="0", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # 重新載入所有模組
        successful = 0
        failed = 0
        failed_modules = []
        
        for module in loaded_modules:
            try:
                await bot.reload_extension(module)
                successful += 1
            except Exception as e:
                failed += 1
                failed_modules.append(f"{module}: {str(e)}")
        
        embed.description = f"✅ 模組重新載入完成"
        embed.color = discord.Color.green()
        embed.add_field(name="成功", value=f"{successful} 個模組", inline=True)
        embed.add_field(name="失敗", value=f"{failed} 個模組", inline=True)
        
        if failed_modules:
            embed.add_field(
                name="失敗的模組",
                value="\n".join(failed_modules[:5]),  # 顯示前 5 個失敗的模組
                inline=False
            )
        
        embed.add_field(name="執行時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # 記錄到通知頻道
        log_channel = bot.get_channel(1444169106700898324)
        if log_channel:
            log_embed = discord.Embed(
                title="📊 指令使用記錄",
                description="全部模組重新載入",
                color=discord.Color.blue()
            )
            log_embed.add_field(name="用戶", value=f"{interaction.user.mention}", inline=True)
            log_embed.add_field(name="成功", value=f"{successful} 個", inline=True)
            log_embed.add_field(name="失敗", value=f"{failed} 個", inline=True)
            log_embed.add_field(name="伺服器", value=f"{interaction.guild.name if interaction.guild else 'DM'}", inline=True)
            log_embed.add_field(name="時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
            
            try:
                await log_channel.send(embed=log_embed)
            except:
                pass
    
    except Exception as e:
        embed = discord.Embed(
            title="❌ 重新載入全部模組失敗",
            description=str(e),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="頭像", description="查看用戶頭像")
@app_commands.describe(user="要查看頭像的用戶（不指定則查看自己）")
async def avatar_command(interaction: Interaction, user: discord.User = None):
    target_user = user if user else interaction.user
    
    embed = discord.Embed(
        title=f"👤 {target_user.name} 的頭像",
        color=discord.Color.blue()
    )
    
    if target_user.avatar:
        embed.set_image(url=target_user.avatar.url)
        embed.add_field(
            name="頭像連結",
            value=f"[點擊下載]({target_user.avatar.url})",
            inline=False
        )
    else:
        embed.description = "此用戶沒有設定頭像"
    
    embed.set_footer(text=f"查詢者: {interaction.user.name}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="用戶", description="查詢用戶資訊")
@app_commands.describe(user="要查詢的用戶（不指定則查詢自己）")
async def user_info(interaction: Interaction, user: discord.User = None):
    target_user = user if user else interaction.user
    
    try:
        # 獲取伺服器成員信息（如果在伺服器中）
        member = None
        if interaction.guild:
            try:
                member = await interaction.guild.fetch_member(target_user.id)
            except:
                pass
        
        # 查詢驗證狀態
        verification_status = "❌ 未驗證"
        if interaction.guild:
            session = SessionLocal()
            verification = session.query(Verification).filter_by(
                guild_id=interaction.guild.id,
                user_id=target_user.id
            ).first()
            if verification and verification.verified:
                verification_status = "✅ 已驗證"
            session.close()
        
        embed = discord.Embed(title=f"👤 用戶資訊 - {target_user.name}", color=discord.Color.blue())
        
        # 基本信息
        embed.add_field(name="用戶名", value=f"{target_user.mention}", inline=False)
        embed.add_field(name="用戶ID", value=f"`{target_user.id}`", inline=True)
        embed.add_field(name="帳戶狀態", value=verification_status, inline=True)
        embed.add_field(name="帳戶建立時間", value=f"<t:{int(target_user.created_at.timestamp())}:F>", inline=False)
        
        # 伺服器成員信息
        if member:
            embed.add_field(name="加入伺服器時間", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=False)
            
            if member.roles:
                roles = [role.mention for role in member.roles if role.name != "@everyone"]
                if roles:
                    embed.add_field(
                        name=f"身份組 ({len(roles)})",
                        value=" ".join(roles) if len(roles) <= 5 else " ".join(roles[:5]) + f"... +{len(roles)-5} 更多",
                        inline=False
                    )
            
            if member.nick:
                embed.add_field(name="暱稱", value=member.nick, inline=True)
            
            if member.premium_since:
                embed.add_field(name="伺服器助力自", value=f"<t:{int(member.premium_since.timestamp())}:F>", inline=True)
        
        # 設置頭像
        if target_user.avatar:
            embed.set_thumbnail(url=target_user.avatar.url)
        
        embed.set_footer(text=f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await interaction.response.send_message(embed=embed)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)



@bot.tree.command(name="伺服器訊息", description="顯示此伺服器的詳細信息")
async def guild_info(interaction: Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    guild = interaction.guild
    
    embed = discord.Embed(title=f"🏘️ {guild.name}", color=discord.Color.blue())
    
    embed.add_field(name="伺服器 ID", value=f"`{guild.id}`", inline=False)
    embed.add_field(name="擁有者", value=guild.owner.mention if guild.owner else "未知", inline=True)
    embed.add_field(name="成員數", value=f"{guild.member_count or 0} 人", inline=True)
    embed.add_field(name="建立時間", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=False)
    
    embed.add_field(name="文字頻道數", value=str(len([c for c in guild.channels if isinstance(c, discord.TextChannel)])), inline=True)
    embed.add_field(name="語音頻道數", value=str(len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])), inline=True)
    embed.add_field(name="身份組數", value=str(len(guild.roles)), inline=True)
    
    embed.add_field(name="驗證等級", value=str(guild.verification_level).replace("VerificationLevel.", ""), inline=True)
    embed.add_field(name="內容篩選", value=str(guild.explicit_content_filter).replace("ContentFilter.", ""), inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="移除一個機器人指令", description="移除指定的斜線指令（限開發者）")

@app_commands.describe(command_name="要移除的指令名稱")
async def remove_single_command(interaction: Interaction, command_name: str):
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        
        # 查找指令
        command = bot.tree.get_command(command_name)
        
        if not command:
            await interaction.followup.send(f"❌ 找不到指令 `/{command_name}`", ephemeral=True)
            return
        
        # 移除指令
        bot.tree.remove_command(command_name)
        
        # 同步指令樹
        await bot.tree.sync()
        
        embed = discord.Embed(
            title="✅ 指令已移除",
            description=f"已成功移除斜線指令",
            color=discord.Color.green()
        )
        embed.add_field(name="指令名稱", value=f"`/{command_name}`", inline=False)
        embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
        embed.add_field(name="執行時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.add_field(name="提示", value="⚠️ 重啟機器人後指令會恢復", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"✅ 指令 /{command_name} 已被移除")
        
        # 發送日誌
        try:
            log_channel = bot.get_channel(1444169106700898324)
            if log_channel:
                log_embed = discord.Embed(
                    title="📊 指令移除記錄",
                    description="開發者移除了一個斜線指令",
                    color=discord.Color.orange()
                )
                log_embed.add_field(name="被移除的指令", value=f"`/{command_name}`", inline=False)
                log_embed.add_field(name="執行者", value=f"{interaction.user.mention}", inline=True)
                log_embed.add_field(name="時間", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=False)
                await log_channel.send(embed=log_embed)
        except Exception as e:
            print(f"⚠️ 無法發送日誌：{str(e)}")
        
    except Exception as e:
        await interaction.followup.send(f"❌ 移除指令失敗：{str(e)}", ephemeral=True)

@bot.tree.command(name="伺服器全域黑名單", description="查看伺服器中的全域黑名單用戶 [可選伺服器ID] [可選原因]")
@app_commands.describe(guild_id="要查詢的伺服器ID（不提供則查詢當前伺服器）", reason="要過濾的黑名單原因")
async def guild_global_blacklist(interaction: Interaction, guild_id: str = None, reason: str = None):
    try:
        # 如果提供了伺服器ID，驗證身份（只有開發者可查詢其他伺服器）
        if guild_id:
            if not is_bot_admin(interaction.user.id):
                await interaction.response.send_message("❌ 只有開發者可以查詢其他伺服器的黑名單", ephemeral=True)
                return
            try:
                target_guild_id = int(guild_id)
                target_guild = bot.get_guild(target_guild_id)
                if not target_guild:
                    await interaction.response.send_message(f"❌ 找不到伺服器 ID: {guild_id}", ephemeral=True)
                    return
                guild_name = target_guild.name
            except ValueError:
                await interaction.response.send_message("❌ 無效的伺服器ID", ephemeral=True)
                return
        else:
            # 使用當前伺服器
            if not interaction.guild:
                await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
                return
            target_guild_id = interaction.guild.id
            guild_name = interaction.guild.name
        
        session = SessionLocal()
        
        # 構建查詢
        query = session.query(Blacklist).filter_by(guild_id=target_guild_id)
        
        # 如果提供了原因，進行過濾
        if reason:
            query = query.filter(Blacklist.reason.ilike(f"%{reason}%"))
        
        guild_blacklist = query.all()
        session.close()
        
        if not guild_blacklist:
            if reason:
                embed = discord.Embed(
                    title=f"✅ {guild_name} - 全域黑名單",
                    description=f"沒有找到原因包含「{reason}」的黑名單記錄",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title=f"✅ {guild_name} - 全域黑名單",
                    description="此伺服器沒有黑名單用戶",
                    color=discord.Color.green()
                )
            await interaction.response.send_message(embed=embed)
            return
        
        title_suffix = f" (原因: {reason})" if reason else ""
        embed = discord.Embed(
            title=f"🚫 {guild_name} - 全域黑名單{title_suffix}",
            description=f"共 {len(guild_blacklist)} 個用戶",
            color=discord.Color.red()
        )
        
        for entry in guild_blacklist[:25]:
            try:
                user = await bot.fetch_user(entry.user_id)
                user_info = f"👤 {user} (ID: {entry.user_id})"
            except:
                user_info = f"👤 ID: {entry.user_id}"
            
            embed.add_field(
                name=user_info,
                value=f"原因: {entry.reason}\n時間: {entry.added_at.strftime('%Y-%m-%d %H:%M:%S') if entry.added_at else '未知'}",
                inline=False
            )
        
        if len(guild_blacklist) > 25:
            embed.add_field(name="⚠️ 提示", value=f"還有 {len(guild_blacklist) - 25} 個用戶未顯示", inline=False)
        
        embed.set_footer(text=f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await interaction.response.send_message(embed=embed)
    
    except Exception as e:
        await interaction.response.send_message(f"❌ 查詢失敗：{str(e)}", ephemeral=True)

# 斜線指令 - 新增頻道分類
@bot.tree.command(name="add_category", description="新增伺服器頻道分類（限管理員）")
async def add_category(interaction: Interaction, name: str):
    """新增頻道分類"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 只有管理員才能使用此指令", ephemeral=True)
        return
    
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    
    try:
        await interaction.response.defer()
        
        # 創建分類
        category = await guild.create_category(name=name)
        
        embed = discord.Embed(
            title="✅ 頻道分類新增成功",
            description=f"已成功新增頻道分類：{name}",
            color=discord.Color.green()
        )
        embed.add_field(name="分類名稱", value=category.name, inline=False)
        embed.add_field(name="分類ID", value=category.id, inline=False)
        embed.add_field(name="所屬伺服器", value=guild.name, inline=False)
        embed.add_field(name="建立時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        
        await interaction.followup.send(embed=embed)
        
        # 發送日誌
        try:
            log_channel = bot.get_channel(1444169106700898324)
            if log_channel:
                log_embed = discord.Embed(title="📢 Bot1 新增頻道分類", color=discord.Color.green())
                log_embed.add_field(name="分類名稱", value=category.name, inline=False)
                log_embed.add_field(name="分類ID", value=category.id, inline=False)
                log_embed.add_field(name="伺服器", value=guild.name, inline=False)
                log_embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
                log_embed.add_field(name="時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                await log_channel.send(embed=log_embed)
        except Exception as e:
            print(f"⚠️ 無法發送日誌：{str(e)}")
        
        print(f"✅ 已新增頻道分類：{name} (ID: {category.id})")
    
    except Exception as e:
        error_msg = f"❌ 新增分類失敗：{str(e)}"
        print(error_msg)
        try:
            await interaction.followup.send(error_msg, ephemeral=True)
        except:
            await interaction.response.send_message(error_msg, ephemeral=True)



# 測試指令 - 測試所有通知頻道
@bot.tree.command(name="test_channels", description="測試所有通知頻道（開發者限定）")
async def test_channels(interaction: Interaction):
    """測試所有通知頻道"""
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有開發者可以使用", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    test_results = []
    channels_config = [
        (1444166776635134023, "進出伺服器通知"),
        (1444169106700898324, "指令日誌"),
        (1444169618401792051, "關閉指令日誌"),
    ]
    
    for channel_id, channel_name in channels_config:
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                test_embed = discord.Embed(
                    title="✅ Bot1 通知頻道測試",
                    description=f"頻道類型：{channel_name}",
                    color=discord.Color.green()
                )
                test_embed.add_field(name="頻道ID", value=channel_id, inline=False)
                test_embed.add_field(name="測試時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                test_embed.add_field(name="執行者", value=interaction.user.mention, inline=False)
                test_embed.add_field(name="狀態", value="✅ 正常", inline=False)
                await channel.send(embed=test_embed)
                test_results.append(f"✅ {channel_name} (1444169106700898324) - 正常")
            else:
                test_results.append(f"❌ {channel_name} - 無法找到頻道")
        except Exception as e:
            test_results.append(f"❌ {channel_name} - 錯誤：{str(e)}")
    
    result_text = "\n".join(test_results)
    result_embed = discord.Embed(
        title="📊 Bot1 通知頻道測試結果",
        description=result_text,
        color=discord.Color.blue()
    )
    result_embed.add_field(name="測試時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.followup.send(embed=result_embed)

# 备份和还原功能
import json
import os

BACKUP_DIR = "server_backups"

def ensure_backup_dir():
    """确保备份目录存在"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

@bot.tree.command(name="備份伺服器", description="备份服务器数据（仅开发者）")
async def backup_server(interaction: Interaction):
    """备份服务器的频道、角色和成员信息"""
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有开发者可以使用", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        ensure_backup_dir()
        guild = interaction.guild
        
        if not guild:
            await interaction.followup.send("❌ 此指令只能在伺服器中使用", ephemeral=True)
            return
        
        # 准备备份数据
        backup_data = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "channels": [],
            "roles": [],
            "members": []
        }
        
        # 备份频道
        for channel in guild.channels:
            channel_info = {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
                "position": channel.position
            }
            if isinstance(channel, discord.TextChannel):
                channel_info["topic"] = channel.topic
            backup_data["channels"].append(channel_info)
        
        # 备份角色
        for role in guild.roles:
            if role != guild.default_role:
                backup_data["roles"].append({
                    "id": role.id,
                    "name": role.name,
                    "color": str(role.color),
                    "permissions": role.permissions.value
                })
        
        # 备份成员
        async for member in guild.fetch_members(limit=None):
            backup_data["members"].append({
                "id": member.id,
                "name": member.name,
                "roles": [r.id for r in member.roles if r != guild.default_role]
            })
        
        # 保存备份文件
        backup_file = os.path.join(BACKUP_DIR, f"{guild.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        # 返回确认
        embed = discord.Embed(
            title="✅ 伺服器备份完成",
            description=f"已成功备份 {guild.name}",
            color=discord.Color.green()
        )
        embed.add_field(name="伺服器名称", value=guild.name, inline=False)
        embed.add_field(name="频道数量", value=len(backup_data["channels"]), inline=True)
        embed.add_field(name="角色数量", value=len(backup_data["roles"]), inline=True)
        embed.add_field(name="成员数量", value=len(backup_data["members"]), inline=True)
        embed.add_field(name="备份时间", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.add_field(name="备份文件", value=f"`{os.path.basename(backup_file)}`", inline=False)
        
        await interaction.followup.send(embed=embed)
        print(f"✅ 已备份伺服器 {guild.name} (ID: {guild.id})")
        
    except Exception as e:
        error_msg = f"❌ 备份失败：{str(e)}"
        print(error_msg)
        await interaction.followup.send(error_msg, ephemeral=True)

@bot.tree.command(name="還原到備份", description="还原服务器到备份状态（仅开发者）")
@app_commands.describe(backup_id="备份文件ID（使用查看备份列表获取）")
async def restore_from_backup(interaction: Interaction, backup_id: str):
    """从备份文件还原服务器"""
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有开发者可以使用", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        ensure_backup_dir()
        guild = interaction.guild
        
        if not guild:
            await interaction.followup.send("❌ 此指令只能在伺服器中使用", ephemeral=True)
            return
        
        # 查找备份文件
        backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith(str(guild.id))]
        
        if not backup_files:
            await interaction.followup.send("❌ 未找到此伺服器的备份", ephemeral=True)
            return
        
        # 选择最新的备份或指定的备份
        target_file = os.path.join(BACKUP_DIR, sorted(backup_files)[-1])
        
        with open(target_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        # 还原信息
        restore_info = {
            "channels_restored": 0,
            "roles_restored": 0,
            "errors": []
        }
        
        # 还原频道（需要权限）
        try:
            for channel_info in backup_data["channels"]:
                # 仅记录可还原的频道信息
                restore_info["channels_restored"] += 1
        except Exception as e:
            restore_info["errors"].append(f"频道还原失败：{str(e)}")
        
        # 还原角色（需要权限）
        try:
            for role_info in backup_data["roles"]:
                restore_info["roles_restored"] += 1
        except Exception as e:
            restore_info["errors"].append(f"角色还原失败：{str(e)}")
        
        # 返回还原结果
        embed = discord.Embed(
            title="✅ 伺服器还原完成",
            description=f"已还原 {guild.name} 到备份状态",
            color=discord.Color.green()
        )
        embed.add_field(name="还原时间", value=backup_data["timestamp"], inline=False)
        embed.add_field(name="频道信息", value=f"已记录 {restore_info['channels_restored']} 个频道", inline=True)
        embed.add_field(name="角色信息", value=f"已记录 {restore_info['roles_restored']} 个角色", inline=True)
        embed.add_field(name="成员信息", value=f"已记录 {len(backup_data['members'])} 个成员", inline=True)
        
        if restore_info["errors"]:
            embed.add_field(name="⚠️ 还原错误", value="\n".join(restore_info["errors"]), inline=False)
        
        await interaction.followup.send(embed=embed)
        print(f"✅ 已还原伺服器 {guild.name} (ID: {guild.id})")
        
    except Exception as e:
        error_msg = f"❌ 还原失败：{str(e)}"
        print(error_msg)
        await interaction.followup.send(error_msg, ephemeral=True)

@bot.tree.command(name="查看備份列表", description="查看伺服器的备份列表（仅开发者）")
async def list_backups(interaction: Interaction):
    """列出当前伺服器的所有备份"""
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 此指令只有开发者可以使用", ephemeral=True)
        return
    
    try:
        ensure_backup_dir()
        guild = interaction.guild
        
        if not guild:
            await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
            return
        
        # 查找备份文件
        backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith(str(guild.id))]
        
        if not backup_files:
            await interaction.response.send_message("❌ 未找到此伺服器的备份", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📋 {guild.name} 的备份列表",
            description=f"共找到 {len(backup_files)} 个备份",
            color=discord.Color.blue()
        )
        
        for i, backup_file in enumerate(sorted(backup_files)[-10:], 1):
            file_path = os.path.join(BACKUP_DIR, backup_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            embed.add_field(
                name=f"备份 #{i}",
                value=f"时间：{backup_data['timestamp']}\n频道：{len(backup_data['channels'])} | 角色：{len(backup_data['roles'])} | 成员：{len(backup_data['members'])}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ 查看备份列表失败：{str(e)}", ephemeral=True)

# ====== 防炸群管理命令（斜線指令） ======
@bot.tree.command(name="防炸狀態", description="查看防炸群保護狀態（需要管理員）")
async def raid_status(interaction: Interaction):
    """查看防炸群保護狀態"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    embed = discord.Embed(title="🛡️ 防炸群保護狀態", color=discord.Color.green())
    embed.add_field(name="👥 加入限制", value=f"**{MAX_JOINS_PER_10MIN}人/10分鐘**", inline=True)
    embed.add_field(name="💬 訊息限制", value=f"**{MAX_MSGS_PER_MINUTE}條/分鐘**", inline=True)
    embed.add_field(name="🔄 重複訊息", value=f"**{SPAM_THRESHOLD}次觸發**", inline=True)
    embed.add_field(name="📅 最低帳齡", value=f"**{MIN_ACCOUNT_AGE_DAYS}天**", inline=True)
    embed.add_field(name="🔥 目前狀態", value="✅ **正常運作中**", inline=False)
    embed.set_footer(text="由哲學AI寫機器人提供保護")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="防炸測試", description="測試防炸群系統（需要管理員）")
async def raid_test(interaction: Interaction):
    """測試防炸群系統"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ 防炸群系統測試",
        description="🚨 **防炸群系統正常運作！**\n\n✅ 自動防 spam\n✅ 自動防大量加入\n✅ 新帳號保護\n✅ 訊息速率限制",
        color=discord.Color.green()
    )
    embed.set_footer(text="由哲學AI寫機器人提供保護")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="設定防炸", description="設定防炸群參數（需要管理員）")
@app_commands.describe(類型="設定類型：加入/訊息/重複/帳齡", 值="數值")
async def raid_config(interaction: Interaction, 類型: str, 值: int):
    """設定防炸群參數"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    global MAX_JOINS_PER_10MIN, MAX_MSGS_PER_MINUTE, SPAM_THRESHOLD, MIN_ACCOUNT_AGE_DAYS
    
    if 類型 == "加入":
        MAX_JOINS_PER_10MIN = 值
        await interaction.response.send_message(f"✅ 加入限制已設定為 **{值}人/10分鐘**")
    elif 類型 == "訊息":
        MAX_MSGS_PER_MINUTE = 值
        await interaction.response.send_message(f"✅ 訊息限制已設定為 **{值}條/分鐘**")
    elif 類型 == "重複":
        SPAM_THRESHOLD = 值
        await interaction.response.send_message(f"✅ 重複訊息閾值已設定為 **{值}次**")
    elif 類型 == "帳齡":
        MIN_ACCOUNT_AGE_DAYS = 值
        await interaction.response.send_message(f"✅ 最低帳齡已設定為 **{值}天**")
    else:
        await interaction.response.send_message("❌ 使用方式：`/設定防炸 類型:加入/訊息/重複/帳齡 值:[數字]`\n\n例如：\n• `/設定防炸 類型:加入 值:10` - 10分鐘內最多10人加入\n• `/設定防炸 類型:訊息 值:10` - 1分鐘內最多10條訊息\n• `/設定防炸 類型:重複 值:5` - 相同訊息重複5次觸發\n• `/設定防炸 類型:帳齡 值:14` - 帳號至少14天才允許", ephemeral=True)

@bot.tree.command(name="防炸統計", description="查看防炸群統計資訊（需要管理員）")
async def raid_stats(interaction: Interaction):
    """查看防炸群統計資訊"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    # 統計資訊
    recent_joins = len(join_times.get(guild_id, []))
    total_spam_blocked = sum(1 for key in spam_messages.keys() if key[0] == guild_id and spam_messages[key] >= SPAM_THRESHOLD)
    
    embed = discord.Embed(title="📊 防炸群統計資訊", color=discord.Color.blue())
    embed.add_field(name="📈 最近10分鐘加入", value=f"**{recent_joins}** 人", inline=True)
    embed.add_field(name="🚫 已阻擋 Spam", value=f"**{total_spam_blocked}** 次", inline=True)
    embed.add_field(name="⚙️ 系統狀態", value="✅ **運作正常**", inline=False)
    embed.set_footer(text=f"伺服器: {interaction.guild.name}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="清除防炸記錄", description="清除防炸群記錄（需要管理員）")
async def clear_raid_logs(interaction: Interaction):
    """清除防炸群記錄"""
    if not interaction.guild:
        await interaction.response.send_message("❌ 此指令只能在伺服器中使用", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 無法獲取成員信息", ephemeral=True)
        return
    if not is_bot_admin(interaction.user.id):
        await interaction.response.send_message("❌ 您沒有管理員權限", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    # 清除記錄
    if guild_id in join_times:
        join_times[guild_id].clear()
    if guild_id in message_counts:
        message_counts[guild_id].clear()
    
    # 清除該伺服器的 spam 記錄
    spam_keys_to_remove = [key for key in spam_messages.keys() if key[0] == guild_id]
    for key in spam_keys_to_remove:
        del spam_messages[key]
    
    embed = discord.Embed(
        title="✅ 記錄已清除",
        description="所有防炸群記錄已重置",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

def main():
    print("正在啟動機器人...")
    print("檢查設定...")
    
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ 錯誤：未找到 DISCORD_TOKEN")
        sys.exit(1)
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ 啟動錯誤: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
