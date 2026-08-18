import os
import asyncio
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# Nome del file database
DB_FILE = "bot_data.db"

# ================= FUNZIONI DI SUPPORTO DATABASE =================
def init_db():
    """Inizializza il database se non esiste"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Tabella per le impostazioni generali (es. ruolo di setindex e canale log)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ================= INTERFACCE DEI BOTTONI PERSISTENTI =================

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Necessario per la persistenza

    @discord.ui.button(label="Chiudi Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="chiudi_ticket_btn")
    async def chiudi_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ Questo ticket è stato chiuso. Il canale verrà eliminato tra 5 secondi...")
        
        # Invia una notifica nel canale di log prima di cancellare
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🛑 **Ticket chiuso**: Il canale `{interaction.channel.name}` è stato eliminato da {interaction.user.mention}.")
        
        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Necessario per la persistenza

    @discord.ui.button(label="Apri Ticket", style=discord.ButtonStyle.green, emoji="📩", custom_id="apri_ticket_btn")
    async def apri_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
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
        
        close_view = CloseTicketView()
        await ticket_channel.send(
            f"Benvenuto {interaction.user.mention}! Lo staff si occuperà presto della tua richiesta.\n"
            f"Descrivi pure qui il tuo problema.\n\n"
            f"👉 Usa il pulsante qui sotto se desideri terminare la sessione di supporto.",
            view=close_view
        )
        
        await interaction.response.send_message(f" Ticket creato con successo! Vai qui: {ticket_channel.mention}", ephemeral=True)

        # Invia la notifica nel canale log
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"📩 **Nuovo Ticket**: {interaction.user.mention} ha aperto un ticket privato: {ticket_channel.mention}.")


# ================= CONFIGURAZIONE CLIENT BOT =================

class BotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Inizializza il database SQLite
        init_db()
        # Registra le viste dei bottoni così funzioneranno all'infinito anche dopo i riavvii
        self.add_view(TicketButtonView())
        self.add_view(CloseTicketView())

    async def on_ready(self):
        print(f"Bot connesso come {bot.user}")
        try:
            synced = await self.tree.sync()
            print(f"Sincronizzati {len(synced)} comandi slash!")
        except Exception as e:
            print(f"Errore nella sincronizzazione: {e}")

bot = BotClient()


# ================= COMANDI SLASH DEL BOT =================

# --- /BAN ---
@bot.tree.command(name="ban", description="Banna un utente dal server (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utente="L'utente da bannare", motivo="Il motivo del ban")
async def ban(interaction: discord.Interaction, utente: discord.User, motivo: str = "Nessun motivo specificato"):
    try:
        await interaction.guild.ban(utente, reason=motivo)
        await interaction.response.send_message(f" Tarzanello colpito! **{utente.name}** è stato bannato.\n**Motivo:** {motivo}", ephemeral=True)
        
        # Log del ban
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🔨 **Utente Bannato**: {utente.mention} è stato bannato da {interaction.user.mention}.\n**Motivo**: {motivo}")
    except Exception:
        await interaction.response.send_message(f"Non ho i permessi per bannare questo utente.", ephemeral=True)

# --- /SETLOGS ---
@bot.tree.command(name="setlogs", description="Imposta il canale dove inviare i log dello staff (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(canale="Il canale testuale per i log dello staff")
async def setlogs(interaction: discord.Interaction, canale: discord.TextChannel):
    save_setting("log_channel_id", canale.id)
    await interaction.response.send_message(f" Canale log configurato con successo su {canale.mention}!", ephemeral=True)

# --- /SETINDEX ---
@bot.tree.command(name="setindex", description="Seleziona il ruolo che riceverà i messaggi DM (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(ruolo="Il ruolo a cui inviare i DM con /index")
async def setindex(interaction: discord.Interaction, ruolo: discord.Role):
    save_setting("target_role_id", ruolo.id)
    await interaction.response.send_message(f" Configurato! Il comando `/index` ora invierà i messaggi a tutti i membri con il ruolo: **{ruolo.name}**", ephemeral=True)

# --- /INDEX ---
@bot.tree.command(name="index", description="Invia un messaggio nei DM ai membri del ruolo configurato")
@app_commands.describe(messaggio="Il testo da inviare nei messaggi privati")
async def index(interaction: discord.Interaction, messaggio: str):
    target_role_id = get_setting("target_role_id")
    if not target_role_id:
        await interaction.response.send_message("❌ Errore: Nessun ruolo è stato configurato con `/setindex` da un amministratore.", ephemeral=True)
        return

    # Usa defer() per evitare il timeout di 3 secondi di Discord
    await interaction.response.defer(ephemeral=True)
    
    ruolo = interaction.guild.get_role(target_role_id)
    if not ruolo:
        await interaction.followup.send("❌ Il ruolo configurato non esiste più su questo server.", ephemeral=True)
        return

    successi = 0
    falliti = 0

    for member in ruolo.members:
        if member.bot:
            continue
        try:
            await member.send(f"📬 **Messaggio importante da {interaction.user.name}:**\n\n{messaggio}")
            successi += 1
            # Pausa di sicurezza di 1 secondo per non farsi bloccare da Discord
            await asyncio.sleep(1)
        except Exception:
            falliti += 1

    await interaction.followup.send(f" Spedizione completata!\n Inviati con successo: {successi}\n Non consegnati (DM chiusi): {falliti}", ephemeral=True)

# --- /TICKET ---
@bot.tree.command(name="ticket", description="Invia il pannello per aprire i ticket in questo canale (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
async def ticket(interaction: discord.Interaction):
    view = TicketButtonView()
    await interaction.response.send_message("Pannello Ticket inviato!", ephemeral=True)
    await interaction.channel.send(" Tarzanello Supporto \nClicca sul pulsante qui sotto per aprire un ticket privato con lo staff.", view=view)


# ================= GESTORE ERRORI PERMESSI =================
@ban.error
@setlogs.error
@setindex.error
@ticket.error
async def permessi_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Non hai i permessi di **Amministratore** per usare questo comando!", ephemeral=True)

# Avvio sicuro tramite Render
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
