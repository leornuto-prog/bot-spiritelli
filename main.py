import os
import discord
from discord import app_commands
from discord.ext import commands

# Configurazione iniziale del bot
class BotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        
        # Variabili temporanee per salvare la configurazione dei comandi
        self.target_role_id = None

    async def on_ready(self):
        print(f"Bot connesso come {bot.user}")
        try:
            # Sincronizza i comandi / globalmente con Discord
            synced = await self.tree.sync()
            print(f"Sincronizzati {len(synced)} comandi slash!")
        except Exception as e:
            print(f"Errore nella sincronizzazione: {e}")

bot = BotClient()

# ================= COMANDO /BAN =================
@bot.tree.command(name="ban", description="Banna un utente dal server (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utente="L'utente da bannare", motivo="Il motivo del ban")
async def ban(interaction: discord.Interaction, utente: discord.User, motivo: str = "Nessun motivo specificato"):
    try:
        await interaction.guild.ban(utente, reason=motivo)
        await interaction.response.send_message(f" Tarzanello colpito! **{utente.name}** è stato bannato.\n**Motivo:** {motivo}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Non ho i permessi per bannare questo utente.", ephemeral=True)

# ================= COMANDO /SETINDEX =================
@bot.tree.command(name="setindex", description="Seleziona il ruolo che riceverà i messaggi DM (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(ruolo="Il ruolo a cui inviare i DM con /index")
async def setindex(interaction: discord.Interaction, ruolo: discord.Role):
    bot.target_role_id = ruolo.id
    await interaction.response.send_message(f" Configurato! Il comando `/index` ora invierà i messaggi a tutti i membri con il ruolo: **{ruolo.name}**", ephemeral=True)

# ================= COMANDO /INDEX =================
@bot.tree.command(name="index", description="Invia un messaggio nei DM ai membri del ruolo configurato")
@app_commands.describe(messaggio="Il testo da inviare nei messaggi privati")
async def index(interaction: discord.Interaction, messaggio: str):
    if not bot.target_role_id:
        await interaction.response.send_message("❌ Errore: Nessun ruolo è stato configurato con `/setindex` da un amministratore.", ephemeral=True)
        return

    # Rispondi subito all'utente per evitare che il comando vada in timeout
    await interaction.response.send_message(" Invio dei messaggi privati in corso...", ephemeral=True)
    
    ruolo = interaction.guild.get_role(bot.target_role_id)
    if not ruolo:
        await interaction.followup.send("❌ Il ruolo configurato non esiste più su questo server.", ephemeral=True)
        return

    successi = 0
    falliti = 0

    # Invia il DM a ogni membro che possiede quel ruolo
    for member in ruolo.members:
        if member.bot:
            continue
        try:
            await member.send(f"📬 **Messaggio importante da {interaction.user.name}:**\n\n{messaggio}")
            successi += 1
        except Exception:
            falliti += 1

    await interaction.followup.send(f" Spedizione completata!\n Inviati con successo: {successi}\n Non consegnati (DM chiusi): {falliti}", ephemeral=True)

# ================= COMANDO /TICKET (INTERFACCIA E TASTO) =================
# Questa è la classe visiva del bottone per aprire il ticket
class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Il bottone non scade mai

    @discord.ui.button(label="Apri Ticket", style=discord.ButtonStyle.green, emoji="📩", custom_id="apri_ticket_btn")
    async def apri_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        # Crea un canale testuale privato per il ticket
        # Visibile solo a chi lo apre e agli amministratori del server
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            topic=f"Ticket aperto da {interaction.user.name}"
        )
        
        await ticket_channel.send(f"Benvenuto {interaction.user.mention}! Gli amministratori e lo staff si occuperanno presto della tua richiesta. Descrivi pure qui il tuo problema.")
        await interaction.response.send_message(f" Ticket creato con successo! Vai qui: {ticket_channel.mention}", ephemeral=True)

@bot.tree.command(name="ticket", description="Invia il pannello per aprire i ticket in questo canale (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
async def ticket(interaction: discord.Interaction):
    view = TicketButtonView()
    await interaction.response.send_message("Pannello Ticket inviato!", ephemeral=True)
    await interaction.channel.send(" Tarzanello Supporto \nClicca sul pulsante qui sotto per aprire un ticket privato con lo staff.", view=view)

# Gestione degli errori per i permessi mancanti
@ban.error
@setindex.error
@ticket.error
async def permessi_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Non hai i permessi di **Amministratore** per usare questo comando!", ephemeral=True)

# Avvio del bot
token = os.environ.get("DISCORD_TOKEN")
bot.run(MTUzOTI1NzA3NDY5MTYwODY2Ng.GE2lyr.67X8tAFGRgtPYkH5vIUuHwiddC5DKA8zo9sQlk)
