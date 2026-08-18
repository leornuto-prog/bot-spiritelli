import os
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks

DB_FILE = "bot_data.db"

# ================= FUNZIONI DI SUPPORTO DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    # Nuova tabella per monitorare l'inattività dei ticket
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS open_tickets (
            channel_id INTEGER PRIMARY KEY,
            creator_id INTEGER,
            last_activity TEXT
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

def register_ticket(channel_id, creator_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute('INSERT OR REPLACE INTO open_tickets (channel_id, creator_id, last_activity) VALUES (?, ?, ?)', (channel_id, creator_id, now_str))
    conn.commit()
    conn.close()

def update_ticket_activity(channel_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute('UPDATE open_tickets SET last_activity = ? WHERE channel_id = ?', (now_str, channel_id))
    conn.commit()
    conn.close()

def remove_ticket(channel_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM open_tickets WHERE channel_id = ?', (channel_id,))
    conn.commit()
    conn.close()


# ================= INTERFACCE DEI BOTTONI =================

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chiudi Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="chiudi_ticket_btn")
    async def chiudi_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se l'utente che clicca ha i permessi di amministratore
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Solo gli **Amministratori** possono chiudere manualmente questo ticket!", ephemeral=True)
            return

        await interaction.response.send_message("⚠️ Il ticket è stato chiuso dall'amministratore. Eliminazione in corso...")
        
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🛑 **Ticket chiuso**: `{interaction.channel.name}` è stato eliminato manualmente da {interaction.user.mention}.")
        
        remove_ticket(interaction.channel.id)
        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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
        
        # Registra il ticket nel database per il controllo inattività
        register_ticket(ticket_channel.id, interaction.user.id)
        
        close_view = CloseTicketView()
        
        # Testo formattato con emoji per le regole richieste
        regole_testo = (
            f"👋 Benvenuto {interaction.user.mention}! Lo staff si occuperà presto di te.\n\n"
            f"📌 **Per procedere, compila subito questi dati:**\n"
            f"🆔 **1. ID FORTNITE:** _Scrivi qui il tuo ID_\n"
            f"👻 **2. SPIRITELLO CHE VI SERVE:** _Specifica quale spiritello desideri_\n\n"
            f"⚠️ **ATTENZIONE:** È obbligatorio restituire lo spiritello. Inoltre, è necessario invitare un amico per ricevere uno spiritello (o più inviti se desideri più spiritelli).\n\n"
            f"🔒 _Nota: I membri non possono chiudere questo ticket. Solo gli amministratori hanno il permesso di farlo._"
        )
        
        await ticket_channel.send(regole_testo, view=close_view)
        await interaction.response.send_message(f" Ticket creato con successo! Vai qui: {ticket_channel.mention}", ephemeral=True)

        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"📩 **Nuovo Ticket**: {interaction.user.mention} ha aperto: {ticket_channel.mention}.")


# ================= CONFIGURAZIONE CLIENT BOT =================

class BotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_db()
        self.add_view(TicketButtonView())
        self.add_view(CloseTicketView())
        # Avvia il ciclo di controllo inattività automatico
        self.check_ticket_inactivity.start()

    async def on_ready(self):
        print(f"Bot connesso come {bot.user}")
        try:
            synced = await self.tree.sync()
            print(f"Sincronizzati {len(synced)} comandi slash!")
        except Exception as e:
            print(f"Errore nella sincronizzazione: {e}")

    async def on_message(self, message):
        if message.author.bot:
            return
        # Se un utente scrive in un ticket aperto, aggiorna l'orario di attività
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM open_tickets WHERE channel_id = ?', (message.channel.id,))
        if cursor.fetchone():
            update_ticket_activity(message.channel.id)
        conn.close()
        await self.process_commands(message)

    # LOOP AUTOMATICO CONTROLLO 3 ORE INATTIVITÀ
    @tasks.loop(minutes=5)
    async def check_ticket_inactivity(self):
        await self.wait_until_ready()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT channel_id, last_activity FROM open_tickets')
        rows = cursor.fetchall()
        conn.close()

        now = datetime.now(timezone.utc)
        for channel_id, last_activity_str in rows:
            try:
                last_activity = datetime.fromisoformat(last_activity_str)
                # Verifica se sono passate più di 3 ore (180 minuti)
                if now - last_activity > timedelta(hours=3):
                    channel = self.get_channel(channel_id)
                    if channel:
                        await channel.send("⏰ **Chiusura Automatica**: Questo ticket è stato chiuso automaticamente per inattività (nessuna risposta da 3 ore).")
                        await asyncio.sleep(5)
                        await channel.delete()
                    remove_ticket(channel_id)
            except Exception as e:
                print(f"Errore nel controllo inattività ticket {channel_id}: {e}")

bot = BotClient()


# ================= COMANDI SLASH DI MODERAZIONE =================

# --- /CLEAR ---
@bot.tree.command(name="clear", description="Cancella un numero specifico di messaggi (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(quantita="Il numero di messaggi da eliminare")
async def clear(interaction: discord.Interaction, quantita: int):
    if quantita < 1:
        await interaction.response.send_message("❌ Inserisci un numero maggiore di 0.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=quantita)
    await interaction.followup.send(f"🧹 Pulizia effettuata! Rimossi **{len(deleted)}** messaggi.", ephemeral=True)
    
    log_channel_id = get_setting("log_channel_id")
    if log_channel_id:
        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"🧹 **Messaggi Cancellati**: {interaction.user.mention} ha rimosso `{len(deleted)}` messaggi nel canale {interaction.channel.mention}.")

# --- /KICK ---
@bot.tree.command(name="kick", description="Espelle un utente dal server (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utente="L'utente da cacciare", motivo="Il motivo dell'espulsione")
async def kick(interaction: discord.Interaction, utente: discord.Member, motivo: str = "Nessun motivo specificato"):
    try:
        await utente.kick(reason=motivo)
        await interaction.response.send_message(f"👞 **{utente.name}** è stato espulso dal server.\n**Motivo:** {motivo}", ephemeral=True)
        
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"👞 Utente Espulso: {utente.mention} è stato cacciato da {interaction.user.mention}.\nMotivo: {motivo}")
    except Exception:
        await interaction.response.send_message("❌ Impossibile espellere questo utente (ruolo superiore o permessi insufficienti).", ephemeral=True)

# --- /TIMEOUT ---
@bot.tree.command(name="timeout", description="Mette in muto un utente per un tempo prestabilito (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utente="L'utente da isolare", minuti="Durata del muto in minuti", motivo="Il motivo del timeout")
async def timeout(interaction: discord.Interaction, utente: discord.Member, minuti: int, motivo: str = "Nessun motivo specificato"):
    try:
        durata = timedelta(minutes=minuti)
        await utente.timeout(durata, reason=motivo)
        await interaction.response.send_message(f"🔇 {utente.name} è stato messo in muto per {minuti} minutes.\nMotivo: {motivo}", ephemeral=True)
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🔇 Timeout Utente: {utente.mention} è stato mutato per {minuti}m da {interaction.user.mention}.\nMotivo: {motivo}")
    except Exception:
        await interaction.response.send_message("❌ Impossibile mettere in timeout questo utente.", ephemeral=True)

# ================= ALTRI COMANDI GESTIONALI BASE =================

@bot.tree.command(name="ban", description="Banna un utente dal server (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utente="L'utente da bannare", motivo="Il motivo del ban")
async def ban(interaction: discord.Interaction, utente: discord.User, motivo: str = "Nessun motivo specificato"):
    try:
        await interaction.guild.ban(utente, reason=motivo)
        await interaction.response.send_message(f"🔨 Tarzanello colpito! {utente.name} è stato bannato.\nMotivo: {motivo}", ephemeral=True)
        log_channel_id = get_setting("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(f"🔨 Utente Bannato: {utente.mention} è stato bannato da {interaction.user.mention}.\nMotivo: {motivo}")
    except Exception:
        await interaction.response.send_message("Non ho i permessi per bannare questo utente.", ephemeral=True)

@bot.tree.command(name="setlogs", description="Imposta il canale dove inviare i log dello staff (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
async def setlogs(interaction: discord.Interaction, canale: discord.TextChannel):
    save_setting("log_channel_id", canale.id)
    await interaction.response.send_message(f" Canale log configurato con successo su {canale.mention}!", ephemeral=True)

@bot.tree.command(name="setindex", description="Seleziona il ruolo che riceverà i messaggi DM (Solo Amministratori)")
@app_commands.checks.has_permissions(administrator=True)
async def setindex(interaction: discord.Interaction, ruolo: discord.Role):
    save_setting("target_role_id", ruolo.id)
    await interaction.response.send_message(f" Configurato! Il comando /index ora invierà i messaggi a tutti i membri con il ruolo: {ruolo.name}", ephemeral=True)

@bot.tree.command(name="index", description="Invia un messaggio nei DM ai membri del ruolo configurato")
async def index(interaction: discord.Interaction, messaggio: str):
    target_role_id = get_setting("target_role_id")
    if not target_role_id:
        await interaction.response.send_message("❌ Errore: Nessun ruolo è stato configurato con /setindex.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    ruolo = interaction.guild.get_role(target_role_id)
    if not ruolo:
        await interaction.followup.send("❌ Il ruolo configurato non esiste più.", ephemeral=True)
        return
    successi, falliti = 0, 0
    for member in ruolo.members:
        if member.bot: continue
        try:
            await member.send(f"📬 Messaggio importante da {interaction.user.name}:\n\n{messaggio}")
            successi += 1
            await asyncio.sleep(1)
        except Exception:
            falliti += 1
    await interaction.followup.send(f" Spedizione completata!\n Inviati: {successi}\n Falliti (DM chiusi): {falliti}", ephemeral=True)

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
@clear.error
@kick.error
@timeout.error
async def permessi_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Non hai i permessi di Amministratore per usare questo comando!", ephemeral=True)

token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
