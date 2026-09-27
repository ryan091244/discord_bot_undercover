import discord
from discord.ext import commands
from google.colab import userdata
import csv
import random
import asyncio
import nest_asyncio
from discord import app_commands
nest_asyncio.apply()

# ===== 可修改參數 =====
TOKEN = userdata.get('bot_token')  # 👈 將此處替換為你的 Discord Bot Token
ANNOUNCE_CHANNEL_ID =   # 👈 請填寫你的頻道 ID
# ======================

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)


class Player:
    def __init__(self, user):
        self.user = user
        self.id = user.id
        self.role = None
        self.word = None
        self.is_alive = True
        self.revealed = False
        self.has_killed_this_night = False
        self.has_voted = False
        self.has_guessed = False
    def reset(self):
        self.role = None
        self.word = None
        self.is_alive = True
        self.revealed = False
        self.has_killed_this_night = False
        self.has_voted = False
        self.has_guessed = False

class GameRoom:
    def __init__(self):
        self.players = []
        self.host = None
        self.in_game = False
        self.round = 0
        self.votes = {}
        self.kill_requests = []
        self.revealed_info = {}
        self.words = {"good": "", "undercover": ""}
        self.white_hint = ""
        self.is_night = False  # 初始為白天
    def reset(self):
        self.__init__()

    def get_player(self, user_id):
        return next((p for p in self.players if p.id == user_id), None)

room = GameRoom()
@bot.event
async def on_ready():
    print(f"✅ Bot 登入成功: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 個斜線指令：{[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"❌ Slash 指令同步失敗: {e}")


# Utility Functions
def read_word_csv():
    with open('/content/drive/MyDrive/undercover/animewordlist.csv', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        return [row for row in reader if len(row) >= 3]

async def reveal_all_roles(channel):
    reveal_message = "🎭 遊戲結束，以下是所有玩家的角色揭曉：\n"
    for i, player in enumerate(room.players, start=1):
        status = "死亡" if not player.is_alive else "存活"
        reveal_message += f"[{i}] {player.user.name} - {status} - {player.role}\n"
    await channel.send(f"```{reveal_message}```")

async def check_victory_condition(channel):
    alive_players = [p for p in room.players if p.is_alive]
    alive_roles = [p.role for p in alive_players]

    count = {
        'good': alive_roles.count('good'),
        'undercover': alive_roles.count('undercover'),
        'white': alive_roles.count('white'),
        'angel': alive_roles.count('angel'),
    }

    total_alive = len(alive_players)
    # 三方平手
    if count['good'] + count['angel'] <= count['undercover'] and total_alive == count['good'] + count['undercover'] + count['white'] + count['angel'] and count['white']>0:
        await channel.send("🎨🕵️ 白板活到最後且臥底人數大於等於好人陣營！等待白板使用 !guess 指令猜詞！")
        return True
    # 好人勝
    if total_alive == count['good']+count['angel']:
        await channel.send("💙 好人獲勝！")
        await reveal_all_roles(channel)
        room.in_game = False
        return True

    # 臥底勝
    if count['good'] +count['angel'] <= count['undercover'] and total_alive == count['good'] + count['undercover'] + count['angel']:
        await channel.send("🕵️ 臥底人數大於等於好人陣營，臥底勝利！")
        await reveal_all_roles(channel)
        room.in_game = False
        return True

    # 白板進入猜詞
    if count['good'] + count['angel'] == count['white'] and total_alive == count['good'] + count['white'] + count['angel']:
        await channel.send("🎨 白板活至最後！白板勝利！")
        return True



    return False  # 遊戲尚未結束
def get_status_detail():
    detail = f"目前為第 {room.round} 回合\n"
    for i, player in enumerate(room.players, start=1):
        status = "死亡" if not player.is_alive else "存活"
        role = player.role if player.revealed else "???"
        detail += f"[{i}] {player.user.name} - {status} - {role}\n"
    return detail
async def assign_roles():
    player_count = len(room.players)
    config = {
        5: (2, 1, 1, 1),
        6: (3, 1, 1, 1),
        7: (4, 1, 1, 1),
        8: (4, 2, 1, 1),
        9: (5, 2, 1, 1),
        10: (6, 2, 1, 1),
        11: (6, 3, 1, 1),
        12: (7, 3, 1, 1),
        13: (7, 4, 1, 1),
        14: (8, 4, 1, 1),
        15: (9, 4, 1, 1),
    }
    if player_count not in config:
        return False

    goods, undercovers, whites, angels = config[player_count]

    # 讀取所有題目並隨機選擇一題
    all_words = read_word_csv()
    selected = random.choice(all_words)
    room.words['good'], room.words['undercover'], room.white_hint = selected

    # 移除已抽中的題目並寫回 CSV
    all_words.remove(selected)
    with open('/content/drive/MyDrive/undercover/animewordlist.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(all_words)

    roles = (['good'] * goods + ['undercover'] * undercovers + ['white'] * whites + ['angel'] * angels)
    random.shuffle(roles)

    for player, role in zip(room.players, roles):
        player.role = role
        if role == "good":
            player.word = room.words['good']
            display_role = "unknown role"
        elif role == "undercover":
            player.word = room.words['undercover']
            display_role = "unknown role"
        elif role == "angel":
            shuffled = random.sample([room.words['good'], room.words['undercover']], k=2)
            player.word = f"{shuffled[0]} / {shuffled[1]}"
            display_role = role
        elif role == "white":
            player.word = f"提示: {room.white_hint}"
            display_role = role
        else:
            player.word = ""
            display_role = "unknown"

        try:
            await player.user.send(f"你的角色是：{display_role}\n你的線索：{player.word}")
        except:
            continue
    return True

# Commands
@bot.hybrid_command(name="join", help="加入遊戲")
async def join(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if room.in_game:
        await ctx.reply("遊戲已經開始，無法加入。", ephemeral=True)
        return
    if room.get_player(ctx.author.id):
        await ctx.reply("你已經加入過了。", ephemeral=True)
        return
    player = Player(ctx.author)
    room.players.append(player)
    if len(room.players) == 1:
        room.host = ctx.author
        await ctx.reply("✅", ephemeral=True)
        await channel.send(f"{ctx.author.name} 加入並成為房主。")
    else:
        await ctx.reply("✅", ephemeral=True)
        await channel.send(f"{ctx.author.name} 加入了遊戲。")

@bot.hybrid_command(name="start", help="開始遊戲（房主）")
async def start(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)

    # ✅ 避免 interaction 過期
    if ctx.interaction:
        await ctx.interaction.response.defer(ephemeral=True)

    if ctx.author != room.host:
        await ctx.send("只有房主能啟動遊戲。", ephemeral=True)
        return

    if room.in_game:
        await ctx.send("遊戲已經開始。", ephemeral=True)
        return

    success = await assign_roles()
    if not success:
        await ctx.send("玩家人數不符合設定，請確認在5到15人之間。", ephemeral=True)
        return

    print("成功啟動遊戲")
    room.in_game = True
    print("room.in_game = True")
    room.round = 1
    print("room.round = 1")

    starter = random.choice(room.players)
    print("starter = random.choice(room.players)")

    # ✅ 延後的回應
    await ctx.send("✅", ephemeral=True)
    await channel.send("🎲 遊戲開始！角色與字卡已私訊發送。")
    await channel.send(f"🎤 **第一位開始發言的是：{starter.user.name}**")




@bot.hybrid_command(name="detail",help="查看狀態")
async def detail(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    details = f"目前為第 {room.round} 回合\n"
    for i, player in enumerate(room.players, start=1):
        status = "死亡" if not player.is_alive else "存活"
        role = player.role if player.revealed else "???"
        details += f"[{i}] {player.user.name} - {status} - {role}\n"
    await ctx.reply(f"```{details}```", ephemeral=True)

@bot.hybrid_command(name="vote",help="投票")
@app_commands.describe(target_index="你要投的玩家編號是?（0 為棄權）")
async def vote(ctx, target_index: int):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not room.in_game:
        await ctx.reply("遊戲尚未開始。", ephemeral=True)
        return

    voter = room.get_player(ctx.author.id)
    if not voter or not voter.is_alive:
        await ctx.reply("你不能投票（可能已死亡或未加入）。", ephemeral=True)
        return

    if voter.has_voted:
        await ctx.reply("你已經投過票，不能再次投票。", ephemeral=True)
        return

    if target_index == 0:
        voter.has_voted = True
        await ctx.reply("你選擇了棄權。", ephemeral=True)
        await channel.send(f"{ctx.author.name} 投票了。")
        return

    if target_index < 1 or target_index > len(room.players):
        await ctx.reply("無效的玩家編號。", ephemeral=True)
        return

    room.votes[ctx.author.id] = target_index
    voter.has_voted = True
    await ctx.reply(f"{ctx.author.name} 投給了編號 {target_index} 的玩家。", ephemeral=True)
    await channel.send(f"{ctx.author.name} 投票了。")


@bot.hybrid_command(name="night", help="結算投票並進入夜晚（限房主）")
async def night(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ctx.author != room.host:
        await ctx.reply("只有房主可以操作。", ephemeral=True)
        return

    # ✅ 結算投票
    for player in room.players:
        player.has_voted = False

    tally = {}
    for voter_id, target_index in room.votes.items():
        tally[target_index] = tally.get(target_index, 0) + 1

    if not tally:
        await ctx.reply("✅", ephemeral=True)
        await channel.send("沒有任何人投票。")
    else:
        max_votes = max(tally.values())
        targets = [idx for idx, v in tally.items() if v == max_votes]

        if len(targets) > 1:
            await ctx.reply("✅", ephemeral=True)
            await channel.send("平票，無人出局。")
        else:
            target = room.players[targets[0] - 1]
            target.is_alive = False
            target.revealed = True
            await ctx.reply("✅", ephemeral=True)
            await channel.send(f"{target.user.name} 被票出局，角色是 {target.role}")

            if target.role == "white":
                alive_roles = [p.role for p in room.players if p.is_alive]
                if all(r in {"good", "white", "angel"} for r in alive_roles):
                    await channel.send("🎨 白板可以使用 !guess 好人詞 臥底詞 來猜詞獲勝！")
                else:
                    await channel.send("白板被淘汰，但場上尚有臥底，不能猜詞。")

        room.votes.clear()

    # ✅ 判斷勝利條件
    await check_victory_condition(channel)

    # 🌙 進入夜晚
    for player in room.players:
        player.has_killed_this_night = False
    room.is_night = True
    await channel.send("夜晚來臨，臥底與好人請私訊 !kill 玩家編號 進行動作。")

@bot.hybrid_command(name="kill", help="殺人（限臥底與好人）")
@app_commands.describe(target_index="你要殺的玩家編號是?")
async def kill(ctx, target_index: int):
    if not room.is_night:
      await ctx.reply("你只能在夜晚使用 kill 指令。", ephemeral=True)
      return

    if not room.in_game:
        return

    killer = room.get_player(ctx.author.id)
    if not killer or not killer.is_alive:
        await ctx.reply("你無法使用 kill 指令（可能已死亡或未參與遊戲）。", ephemeral=True)
        return

    if killer.role not in ("undercover", "good"):
        await ctx.reply("你的角色無法使用 kill 指令。", ephemeral=True)
        return

    if killer.has_killed_this_night:
        await ctx.reply("你今晚已經使用過 kill 指令了，不能再次行動。", ephemeral=True)
        return

    if target_index < 1 or target_index > len(room.players):
        await ctx.reply("你的目標編號不存在於遊戲房間。", ephemeral=True)
        return

    target = room.players[target_index - 1]
    if not target.is_alive:
        await ctx.reply("你的目標已經死亡，請選擇其他目標。", ephemeral=True)
        return

    if killer.role == "undercover":
        room.kill_requests.append(target)
        await ctx.reply(f"你成功對 {target.user.name} 發動了 kill 指令。", ephemeral=True)
    elif killer.role == "good":
        room.kill_requests.append(killer)
        await ctx.reply(f"你成功對 {target.user.name} 發動了 kill 指令。", ephemeral=True)

    killer.has_killed_this_night = True  # 標記已行動



@bot.hybrid_command(name="day",help="進入天亮(房主)")
async def day(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ctx.author != room.host:
        await ctx.reply("只有房主可以宣布天亮", ephemeral=True)
        return
    if room.kill_requests:
      killed_names = []
      for victim in set(room.kill_requests):
        if victim.is_alive:
          victim.is_alive = False
          killed_names.append(victim.user.name)
      await ctx.reply("✅", ephemeral=True)
      await channel.send("昨晚死亡的玩家：\n" + "\n".join(f"- {name}" for name in killed_names))
      await channel.send(f"```{get_status_detail()}```")
      await check_victory_condition(channel)
    else:
      await ctx.reply("✅", ephemeral=True)
      await channel.send(f"```{get_status_detail()}```")
      await channel.send("昨晚沒有人死亡。")
    room.is_night = False
    room.kill_requests.clear()
    room.round += 1

@bot.hybrid_command(name="guess",help="猜詞指令(白板)")
@app_commands.describe(good_word="好人詞",bad_word="臥底詞")
async def guess(ctx, good_word, bad_word):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    player = room.get_player(ctx.author.id)

    if not player or player.role != "white":
        await ctx.reply("你不是白板or未參與遊戲", ephemeral=True)
        return

    if player.has_guessed:
        await ctx.reply("你已經使用過猜詞機會，不能再次使用。", ephemeral=True)
        return

    # ✅ 允許條件一：白板被淘汰（傳統）
    # ✅ 允許條件二：三方平手（白板還活著）
    alive_roles = [p.role for p in room.players if p.is_alive]
    total_alive = len(alive_roles)
    count = {
        'good': alive_roles.count('good'),
        'undercover': alive_roles.count('undercover'),
        'white': alive_roles.count('white'),
        'angel': alive_roles.count('angel'),
    }

    is_three_way = (
        count['white'] == 1 and
        count['undercover'] >= (count['good'] + count['angel'])
    )

    if not is_three_way and player.is_alive:
        await ctx.reply("你必須在被淘汰後，或活到最後時才能猜詞。", ephemeral=True)
        return

    if not all(r in {"good", "white", "angel"} for r in alive_roles) and not is_three_way:
        await ctx.reply("場上尚有臥底，無法猜詞。", ephemeral=True)
        return

    player.has_guessed = True
    if good_word == room.words['good'] and bad_word == room.words['undercover'] and is_three_way:
        await ctx.reply("✅", ephemeral=True)
        await channel.send("🎯 白板猜中！白板與臥底共同勝利！")
    elif good_word == room.words['good'] and bad_word == room.words['undercover'] :
        await ctx.reply("✅", ephemeral=True)
        await channel.send("🎯 白板猜中！白板與臥底勝利！")
    elif is_three_way:
        await ctx.reply("✅", ephemeral=True)
        await channel.send("💥 白板猜錯！只有臥底獲勝！")
    else:
        await ctx.reply("✅", ephemeral=True)
        await channel.send("💥 白板猜錯！好人獲勝！")

    await reveal_all_roles(channel)
    room.in_game = False

@bot.hybrid_command(name="transfer",help="轉讓房主權限(房主)")
@app_commands.describe(target_index="轉移房主給幾號?")
async def transfer(ctx, target_index: int):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ctx.author != room.host:
        await ctx.reply("只有房主可以轉讓房主權限。", ephemeral=True)
        return

    if target_index < 1 or target_index > len(room.players):
        await ctx.reply("無效的玩家編號。", ephemeral=True)
        return

    new_host = room.players[target_index - 1].user
    room.host = new_host
    await ctx.reply("✅", ephemeral=True)
    await channel.send(f"房主已轉讓給 {new_host.name}。")

@bot.hybrid_command(name="reset",help="強迫重置(房主)")
async def reset(ctx):
    if ctx.author != room.host:
        await ctx.reply("只有房主可以reset。", ephemeral=True)
        return
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    room.reset()
    await ctx.reply("✅", ephemeral=True)
    await channel.send("房間與所有遊戲狀態已清空。")
@bot.hybrid_command(name="end",help="結束遊戲(房主)")
async def end(ctx):
    if ctx.author != room.host:
        await ctx.reply("只有房主可以結束遊戲。", ephemeral=True)
        return
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    for p in room.players:
      p.reset()
    room.in_game = False
    room.round = 0
    room.votes = {}
    room.kill_requests = []
    room.revealed_info = {}
    room.words = {"good": "", "undercover": ""}
    room.white_hint = ""
    room.is_night = False  # 初始為白天
    await ctx.reply("✅", ephemeral=True)
    await channel.send("已結束遊戲")

@bot.hybrid_command(name="leave",help="離開房間")
async def leave(ctx):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if room.in_game:
        await ctx.reply("遊戲進行中，無法退出。", ephemeral=True)
        return

    player = room.get_player(ctx.author.id)
    if not player:
        await ctx.reply("你尚未加入遊戲。", ephemeral=True)
        return

    room.players.remove(player)
    if ctx.author == room.host:
        room.host = room.players[0].user if room.players else None
        if room.host:
            await ctx.reply("✅", ephemeral=True)
            await channel.send(f"{ctx.author.name} 已退出，房主轉移給 {room.host.name}。")
        else:
            await ctx.reply("✅", ephemeral=True)
            await channel.send(f"{ctx.author.name} 已退出，房間已清空。")
    else:
        await ctx.reply("✅", ephemeral=True)
        await channel.send(f"{ctx.author.name} 已退出遊戲。")

await bot.start(TOKEN)