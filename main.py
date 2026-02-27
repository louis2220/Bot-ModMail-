import os
import discord
from discord.ext import commands

# ── Configuração ──────────────────────────────────────────────────────────────
TOKEN = os.environ["DISCORD_TOKEN"]
CATEGORIA_ID = int(os.environ["CATEGORIA_ID"])       # ID da categoria onde os canais serão criados
CARGO_STAFF_ID = int(os.environ["CARGO_STAFF_ID"])   # ID do cargo que pode ver os canais
PREFIX = os.environ.get("PREFIX", ".")

# ── Bot ───────────────────────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Dicionário em memória: user_id → canal
threads = {}  # { user_id: channel_id }


# ── Eventos ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot online como {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    # Ignora bots
    if message.author.bot:
        return

    # ── Mensagem na DM → cria canal no servidor ──
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm(message)
        return

    # ── Mensagem no canal de modmail → repassa para o usuário ──
    if message.guild and message.channel.category_id == CATEGORIA_ID:
        await handle_staff_reply(message)
        return

    await bot.process_commands(message)


async def handle_dm(message: discord.Message):
    user = message.author

    # Pega o servidor (o bot só deve estar em 1 servidor)
    guild = bot.guilds[0]
    categoria = guild.get_channel(CATEGORIA_ID)
    cargo_staff = guild.get_role(CARGO_STAFF_ID)

    if not categoria or not cargo_staff:
        await user.send("❌ Erro de configuração. Contate um administrador.")
        return

    # Se já tem thread aberta, só encaminha a mensagem
    if user.id in threads:
        canal = guild.get_channel(threads[user.id])
        if canal:
            embed = discord.Embed(
                description=message.content or "*[sem texto]*",
                color=0x5865F2
            )
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
            if message.attachments:
                embed.add_field(name="Anexos", value="\n".join(a.url for a in message.attachments))
            await canal.send(embed=embed)
            await message.add_reaction("📨")
            return

    # Cria novo canal privado
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        cargo_staff: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )
    }

    nome_canal = f"modmail-{user.name}".lower().replace(" ", "-")[:100]
    canal = await guild.create_text_channel(
        name=nome_canal,
        category=categoria,
        overwrites=overwrites,
        topic=f"Modmail de {user} (ID: {user.id})"
    )

    threads[user.id] = canal.id

    # Manda a primeira mensagem no canal
    embed_abertura = discord.Embed(
        title="📬 Nova Thread de Modmail",
        color=0x5865F2
    )
    embed_abertura.add_field(name="Usuário", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed_abertura.add_field(name="Conta criada", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
    embed_abertura.set_thumbnail(url=user.display_avatar.url)
    embed_abertura.set_footer(text=f"Digite normal para responder • {PREFIX}fechar para encerrar")
    await canal.send(cargo_staff.mention, embed=embed_abertura)

    # Manda a mensagem do usuário
    embed_msg = discord.Embed(
        description=message.content or "*[sem texto]*",
        color=0x5865F2
    )
    embed_msg.set_author(name=str(user), icon_url=user.display_avatar.url)
    if message.attachments:
        embed_msg.add_field(name="Anexos", value="\n".join(a.url for a in message.attachments))
    await canal.send(embed=embed_msg)

    # Confirma para o usuário
    await user.send(embed=discord.Embed(
        description="📨 Sua mensagem foi enviada para a equipe! Em breve responderemos.",
        color=0x2ECC71
    ))
    await message.add_reaction("📨")


async def handle_staff_reply(message: discord.Message):
    # Ignora comandos
    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return

    # Descobre o user_id pelo tópico do canal
    user_id = None
    if message.channel.topic and "ID: " in message.channel.topic:
        try:
            user_id = int(message.channel.topic.split("ID: ")[1].strip().rstrip(")"))
        except ValueError:
            pass

    if not user_id:
        return

    # Verifica se o autor tem o cargo de staff
    cargo_staff = message.guild.get_role(CARGO_STAFF_ID)
    if cargo_staff not in message.author.roles:
        return

    try:
        user = await bot.fetch_user(user_id)
        embed = discord.Embed(
            description=message.content,
            color=0x2ECC71
        )
        embed.set_author(name=f"Staff — {message.guild.name}", icon_url=message.guild.icon.url if message.guild.icon else discord.Embed.Empty)
        embed.set_footer(text="Resposta da equipe de moderação")
        if message.attachments:
            embed.add_field(name="Anexos", value="\n".join(a.url for a in message.attachments))
        await user.send(embed=embed)

        # Reação de confirmação no canal
        await message.add_reaction("✅")

    except discord.Forbidden:
        await message.channel.send("⚠️ Não consegui enviar DM para esse usuário (DMs fechadas).")
    except discord.NotFound:
        await message.channel.send("⚠️ Usuário não encontrado.")


# ── Comandos ──────────────────────────────────────────────────────────────────

@bot.command(name="fechar")
async def fechar(ctx):
    """Fecha a thread de modmail e deleta o canal."""
    if not ctx.guild or ctx.channel.category_id != CATEGORIA_ID:
        return

    cargo_staff = ctx.guild.get_role(CARGO_STAFF_ID)
    if cargo_staff not in ctx.author.roles:
        await ctx.send("❌ Apenas staff pode fechar threads.")
        return

    # Descobre o user_id
    user_id = None
    if ctx.channel.topic and "ID: " in ctx.channel.topic:
        try:
            user_id = int(ctx.channel.topic.split("ID: ")[1].strip().rstrip(")"))
        except ValueError:
            pass

    # Avisa o usuário
    if user_id:
        threads.pop(user_id, None)
        try:
            user = await bot.fetch_user(user_id)
            await user.send(embed=discord.Embed(
                description="🔒 Sua thread de suporte foi encerrada pela equipe. Se precisar de ajuda novamente, é só mandar uma nova mensagem!",
                color=0x95A5A6
            ))
        except (discord.Forbidden, discord.NotFound):
            pass

    await ctx.send("🔒 Encerrando thread...")
    await ctx.channel.delete(reason=f"Thread fechada por {ctx.author}")


@bot.command(name="threads")
async def listar_threads(ctx):
    """Lista todas as threads abertas."""
    if not ctx.guild:
        return
    cargo_staff = ctx.guild.get_role(CARGO_STAFF_ID)
    if cargo_staff not in ctx.author.roles:
        return

    if not threads:
        await ctx.send(embed=discord.Embed(description="Nenhuma thread aberta no momento.", color=0x95A5A6))
        return

    linhas = []
    for uid, cid in threads.items():
        canal = ctx.guild.get_channel(cid)
        linhas.append(f"• <@{uid}> → {canal.mention if canal else '`canal deletado`'}")

    await ctx.send(embed=discord.Embed(
        title=f"Threads abertas ({len(threads)})",
        description="\n".join(linhas),
        color=0x5865F2
    ))


bot.run(TOKEN)
