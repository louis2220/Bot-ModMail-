import os
import discord
from discord.ext import commands

# ── Configuração ──────────────────────────────────────────────────────────────
TOKEN = os.environ["DISCORD_TOKEN"]
CATEGORIA_ID = int(os.environ["CATEGORIA_ID"])
CARGO_STAFF_IDS = [int(i.strip()) for i in os.environ["CARGO_STAFF_IDS"].split(",")]
PREFIX = os.environ.get("PREFIX", ".")

# ── Bot ───────────────────────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

threads = {}  # { user_id: channel_id }


def is_staff(member: discord.Member) -> bool:
    return any(role.id in CARGO_STAFF_IDS for role in member.roles)


# ── Eventos ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot online como {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="DMs"
        )
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        await handle_dm(message)
        return

    if message.guild and message.channel.category_id == CATEGORIA_ID:
        await handle_staff_reply(message)
        return

    await bot.process_commands(message)


async def handle_dm(message: discord.Message):
    user = message.author
    guild = bot.guilds[0]
    categoria = guild.get_channel(CATEGORIA_ID)

    if not categoria:
        return

    # Se já tem thread aberta, só encaminha
    if user.id in threads:
        canal = guild.get_channel(threads[user.id])
        if canal:
            conteudo = message.content or ""
            anexos = "\n".join(a.url for a in message.attachments)
            texto = f"**{user}:** {conteudo}"
            if anexos:
                texto += f"\n{anexos}"
            await canal.send(texto)
            await message.add_reaction("📨")
            return

    # Permissões do novo canal
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    for cargo_id in CARGO_STAFF_IDS:
        cargo = guild.get_role(cargo_id)
        if cargo:
            overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    nome_canal = f"modmail-{user.name}".lower().replace(" ", "-")[:100]
    canal = await guild.create_text_channel(
        name=nome_canal,
        category=categoria,
        overwrites=overwrites,
        topic=f"Modmail de {user} (ID: {user.id})"
    )
    threads[user.id] = canal.id

    # Menciona todos os cargos de staff
    mencoes = " ".join(f"<@&{cid}>" for cid in CARGO_STAFF_IDS)

    embed_abertura = discord.Embed(color=0x000000)
    embed_abertura.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed_abertura.add_field(name="Usuário", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed_abertura.add_field(name="Conta criada", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
    embed_abertura.set_footer(text=f"Digite normal para responder • {PREFIX}fechar para encerrar")
    await canal.send(mencoes, embed=embed_abertura)

    conteudo = message.content or ""
    anexos = "\n".join(a.url for a in message.attachments)
    texto = f"**{user}:** {conteudo}"
    if anexos:
        texto += f"\n{anexos}"
    await canal.send(texto)

    await message.add_reaction("📨")


async def handle_staff_reply(message: discord.Message):
    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return

    user_id = None
    if message.channel.topic and "ID: " in message.channel.topic:
        try:
            user_id = int(message.channel.topic.split("ID: ")[1].strip().rstrip(")"))
        except ValueError:
            pass

    if not user_id:
        return

    if not is_staff(message.author):
        return

    try:
        user = await bot.fetch_user(user_id)
        conteudo = message.content or ""
        anexos = "\n".join(a.url for a in message.attachments)
        texto = conteudo
        if anexos:
            texto += f"\n{anexos}"
        await user.send(texto)
        await message.add_reaction("✅")

    except discord.Forbidden:
        await message.channel.send("⚠️ Não consegui enviar DM para esse usuário (DMs fechadas).")
    except discord.NotFound:
        await message.channel.send("⚠️ Usuário não encontrado.")


# ── Comandos ──────────────────────────────────────────────────────────────────

@bot.command(name="fechar")
async def fechar(ctx):
    if not ctx.guild or ctx.channel.category_id != CATEGORIA_ID:
        return

    if not is_staff(ctx.author):
        await ctx.send("❌ Apenas staff pode fechar threads.")
        return

    user_id = None
    if ctx.channel.topic and "ID: " in ctx.channel.topic:
        try:
            user_id = int(ctx.channel.topic.split("ID: ")[1].strip().rstrip(")"))
        except ValueError:
            pass

    if user_id:
        threads.pop(user_id, None)

    await ctx.channel.delete(reason=f"Thread fechada por {ctx.author}")


@bot.command(name="threads")
async def listar_threads(ctx):
    if not ctx.guild or not is_staff(ctx.author):
        return

    if not threads:
        await ctx.send("Nenhuma thread aberta no momento.")
        return

    linhas = []
    for uid, cid in threads.items():
        canal = ctx.guild.get_channel(cid)
        linhas.append(f"• <@{uid}> → {canal.mention if canal else '`canal deletado`'}")

    await ctx.send("\n".join(linhas))


bot.run(TOKEN)
