"""
AURELIUS Discord Integration Module
Handles Discord API integration for automated posting and bot interactions.
"""
import os
import asyncio
from discord.ext import commands
import discord
import aiohttp
import zipfile
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from ...ai.ai_service import ai_service
import json

from ...config import config
from ...logging_config import get_logger, log_social_activity, log_api_call
from ...utils.security import sanitize_and_prepare_content, validate_and_sanitize_input
from ...utils.rate_limit import rate_limiter, check_platform_rate_limit, increment_platform_usage
from ...db.redis_client import data_client
from ...core.autonomo import modulo_autonomo

logger = get_logger("DISCORD")

print(f"AI Instance: {ai_service}")
print("Tiene generar_texto?:", hasattr(ai_service, "generar_texto"))
print("Métodos de la IA:", dir(ai_service))

import unicodedata
import re

def detect_keywords(message, keywords):
    """
    Retorna True si alguno de los keywords (ya normalizados) está presente en el mensaje.
    Robusto a mayúsculas, tildes y frases completas.
    """
    def normalize(text):
        text = text.lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join([c for c in text if not unicodedata.combining(c)])
        return text

    msg_norm = f" {normalize(message)} "

    for kw in keywords:
        kw_norm = f" {normalize(kw)} "
        if kw_norm in msg_norm:
            return True
        if re.search(r'\b{}\b'.format(re.escape(normalize(kw))), msg_norm):
            return True
    return False


class AureliusDiscord:
    def __init__(self, ai=None):      # <-- agregá el parámetro ai
        self.bot_token = config.DISCORD_BOT_TOKEN
        self.webhook_url = config.DISCORD_WEBHOOK_URL
        self.channel_id = config.DISCORD_CHANNEL_ID
        self.ai = ai                  # <-- guardá la IA en el atributo
        
        # Discord bot client
        self.bot = None
        self.is_bot_running = False
        
        # HTTP client for webhook requests
        self.http_client = None
        
        # Track posted content and interactions
        self.posted_content_key = "discord:posted_content"
        self.messages_processed_key = "discord:messages_processed"
        self.interactions_key = "discord:interactions"
        
        self._initialize_bot()
    
    def _initialize_bot(self):
        """Initialize Discord bot with intents and event handlers."""
        try:
            # Set up intents
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            intents.guild_messages = True
            # intents.direct_messages = True
            
            # Create bot instance
            self.bot = commands.Bot(
                command_prefix='!aurelius ',
                intents=intents,
                help_command=None
            )
            
            # Set up event handlers
            self._setup_event_handlers()
            
            logger.info("✅ Discord bot initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Discord bot: {e}")
            raise
    
    def _setup_event_handlers(self):
        """Set up Discord bot event handlers."""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"🤖 Discord bot logged in as {self.bot.user}")
            self.is_bot_running = True
        
        @self.bot.event
        async def on_message(message):
            # Don't respond to own messages
            if message.author == self.bot.user:
                return
            
            # Process mentions and DMs
            if self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
                await self._handle_mention_or_dm(message)
            
            # Process commands
            await self.bot.process_commands(message)
        
        @self.bot.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"❌ Discord bot error in {event}: {args}")
        
        # Add bot commands
        self._setup_bot_commands()
    
    def _setup_bot_commands(self):
        """Set up Discord bot commands."""
        
        @self.bot.command(name='help')
        async def help_command(ctx):
            """Show available commands."""
            embed = discord.Embed(
                title="AURELIUS Bot Commands",
                description="Available commands for AURELIUS AI assistant",
                color=0x00ff00
            )
            embed.add_field(
                name="!aurelius help",
                value="Show this help message",
                inline=False
            )
            embed.add_field(
                name="!aurelius status",
                value="Check bot status",
                inline=False
            )
            embed.add_field(
                name="!aurelius info",
                value="Get information about AURELIUS",
                inline=False
            )
            
            await ctx.send(embed=embed)
        
        @self.bot.command(name='status')
        async def status_command(ctx):
            """Check bot status."""
            embed = discord.Embed(
                title="AURELIUS Status",
                description="Bot is online and operational",
                color=0x00ff00
            )
            embed.add_field(
                name="Uptime",
                value=f"Since {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                inline=True
            )
            embed.add_field(
                name="Servers",
                value=str(len(self.bot.guilds)),
                inline=True
            )
            
            await ctx.send(embed=embed)
        
        @self.bot.command(name='info')
        async def info_command(ctx):
            """Get information about AURELIUS."""
            embed = discord.Embed(
                title="About AURELIUS",
                description="Autonomous AI assistant for business management and social media automation",
                color=0x0099ff
            )
            embed.add_field(
                name="Features",
                value="• Automated social media posting\n• AI-powered content generation\n• Sales automation\n• Analytics and reporting",
                inline=False
            )
            
            await ctx.send(embed=embed)
    
    async def get_channel_messages(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest messages from a specific channel."""
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                raise ValueError(f"Channel {channel_id} not found")

            messages = []
            async for message in channel.history(limit=limit):
                messages.append({
                    "id": str(message.id),
                    "author": message.author.name,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat()
                })
            return messages
        except Exception as e:
            logger.error(f"❌ Error fetching messages from channel {channel_id}: {e}")
            return []

    async def start_bot(self):
        """Start the Discord bot."""
        try:
            if not self.is_bot_running:
                logger.info("🚀 Starting Discord bot...")
                # Run bot in background task
                asyncio.create_task(self.bot.start(self.bot_token))
                
                # Wait for bot to be ready
                while not self.is_bot_running:
                    await asyncio.sleep(1)
                
                logger.info("✅ Discord bot started successfully")
            else:
                logger.info("ℹ️  Discord bot is already running")
                
        except Exception as e:
            logger.error(f"❌ Failed to start Discord bot: {e}")
            raise
    
    async def stop_bot(self):
        """Stop the Discord bot."""
        try:
            if self.is_bot_running:
                await self.bot.close()
                self.is_bot_running = False
                logger.info("🛑 Discord bot stopped")
            
        except Exception as e:
            logger.error(f"❌ Error stopping Discord bot: {e}")
    
    async def send_webhook_message(
        self,
        content: str,
        username: Optional[str] = "AURELIUS",
        avatar_url: Optional[str] = None,
        embeds: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send message via Discord webhook.
        Returns message data or error information.
        """
        try:
            if not self.webhook_url:
                return {
                    "success": False,
                    "error": "No webhook URL configured"
                }
            
            # Check rate limits
            if not await check_platform_rate_limit("discord", "post"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "retry_after": 3600
                }
            
            # Sanitize content
            sanitized_content = sanitize_and_prepare_content(content, "discord")
            if not sanitized_content:
                return {
                    "success": False,
                    "error": "Content failed sanitization"
                }
            
            # Check for duplicate content
            if await self._is_duplicate_content(sanitized_content):
                logger.warning("⚠️  Duplicate content detected, skipping post")
                return {
                    "success": False,
                    "error": "Duplicate content"
                }
            
            # Prepare webhook payload
            payload = {
                "content": sanitized_content,
                "username": username
            }
            
            if avatar_url:
                payload["avatar_url"] = avatar_url
            
            if embeds:
                payload["embeds"] = embeds
            
            # Initialize HTTP client if needed
            if not self.http_client:
                self.http_client = aiohttp.ClientSession()
            
            log_api_call("Discord", "POST webhook", "POST")
            
            # Send webhook request
            async with self.http_client.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 204:  # Discord webhook success
                    # Store posted content
                    await self._store_posted_content(sanitized_content, "webhook")
                    
                    # Increment usage counters
                    await increment_platform_usage("discord", "post")
                    
                    log_social_activity("Discord", "webhook_sent", sanitized_content[:50], success=True)
                    log_api_call("Discord", "POST webhook", "POST", status=204)
                    
                    result = {
                        "success": True,
                        "content": sanitized_content,
                        "username": username,
                        "timestamp": datetime.now().isoformat(),
                        "method": "webhook"
                    }
                    
                    logger.info("✅ Discord webhook message sent successfully")
                    return result
                    
                elif response.status == 429:  # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 60))
                    error_msg = f"Discord webhook rate limited, retry after {retry_after}s"
                    logger.warning(f"⚠️  {error_msg}")
                    log_api_call("Discord", "POST webhook", "POST", status=429)
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "retry_after": retry_after
                    }
                else:
                    error_text = await response.text()
                    error_msg = f"Discord webhook failed with status {response.status}: {error_text}"
                    logger.error(f"❌ {error_msg}")
                    log_api_call("Discord", "POST webhook", "POST", status=response.status)
                    
                    return {
                        "success": False,
                        "error": error_msg
                    }
                    
        except Exception as e:
            error_msg = f"Failed to send Discord webhook: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Discord", "webhook_sent", content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def send_channel_message(
        self,
        content: str,
        channel_id: Optional[str] = None,
        embed: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send message to Discord channel via bot.
        Returns message data or error information.
        """
        try:
            if not self.is_bot_running:
                return {
                    "success": False,
                    "error": "Discord bot is not running"
                }
            
            # Use provided channel ID or default
            target_channel_id = channel_id or self.channel_id
            if not target_channel_id:
                return {
                    "success": False,
                    "error": "No channel ID specified"
                }
            
            # Check rate limits
            if not await check_platform_rate_limit("discord", "post"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded"
                }
            
            # Sanitize content
            sanitized_content = sanitize_and_prepare_content(content, "discord")
            if not sanitized_content:
                return {
                    "success": False,
                    "error": "Content failed sanitization"
                }
            
            # Get channel
            channel = self.bot.get_channel(int(target_channel_id))
            if not channel:
                return {
                    "success": False,
                    "error": f"Channel {target_channel_id} not found"
                }
            
            log_api_call("Discord", "POST /channels/:id/messages", "POST")
            
            # Send message
            if embed:
                discord_embed = discord.Embed.from_dict(embed)
                message = await channel.send(content=sanitized_content, embed=discord_embed)
            else:
                message = await channel.send(content=sanitized_content)
            
            # Store posted content
            await self._store_posted_content(sanitized_content, str(message.id))
            
            # Increment usage counters
            await increment_platform_usage("discord", "post")
            
            log_social_activity("Discord", "message_sent", sanitized_content[:50], success=True)
            log_api_call("Discord", "POST /channels/:id/messages", "POST", status=200)
            
            result = {
                "success": True,
                "message_id": str(message.id),
                "channel_id": str(channel.id),
                "content": sanitized_content,
                "timestamp": datetime.now().isoformat(),
                "method": "bot"
            }
            
            logger.info(f"✅ Discord message sent to channel {channel.name}")
            return result
            
        except discord.Forbidden:
            error_msg = "Bot lacks permission to send messages in this channel"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Failed to send Discord channel message: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Discord", "message_sent", content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def reply_to_message(self, message_id: str, channel_id: str, reply_content: str) -> Dict[str, Any]:
        """
        Reply to a specific Discord message.
        Returns reply data or error information.
        """
        try:
            if not self.is_bot_running:
                return {
                    "success": False,
                    "error": "Discord bot is not running"
                }
            
            # Get channel and message
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                return {
                    "success": False,
                    "error": f"Channel {channel_id} not found"
                }
            
            try:
                original_message = await channel.fetch_message(int(message_id))
            except discord.NotFound:
                return {
                    "success": False,
                    "error": f"Message {message_id} not found"
                }
            
            # Send reply
            result = await self.send_channel_message(
                content=reply_content,
                channel_id=channel_id
            )
            
            if result["success"]:
                logger.info(f"✅ Reply sent to message {message_id}")
                log_social_activity("Discord", "reply_sent", reply_content[:50], success=True)
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to reply to Discord message {message_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Discord", "reply_sent", reply_content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def send_code_to_user(self, discord_user_id: str, filename: str):
        """
        Envía un archivo por DM a un usuario de Discord identificado por su user_id.
        """
        try:
            user = await self.bot.fetch_user(int(discord_user_id))
            if user:
                await user.send(
                    content="¡Gracias por tu compra! Aquí tienes tu workflow completo:",
                    file=discord.File(filename)
                )
                logger.info(f"✅ Código enviado por DM a usuario {discord_user_id}")
            else:
                logger.warning(f"⚠️ No se pudo encontrar al usuario de Discord con ID {discord_user_id}")
        except Exception as e:
            logger.error(f"❌ Error enviando archivo a usuario de Discord: {e}")
    
    async def _handle_mention_or_dm(self, message):
        """
        Maneja menciones y mensajes directos en Discord:
        - Siempre que alguien pida workflow/código/script/ejemplo/demo, entrega un ejemplo real de workflow de IA (sin pedir pago).
        - Si después pide el archivo/workflow completo, da el link de pago (si no pagó) o el archivo (si ya pagó).
        - Si sólo pide pagar, da el link de pago.
        - Todo lo demás: "Solo genero y vendo workflows automáticos."
        Sin saludos ni introducción. Ultra directo.
        """
        try:
            await self._store_interaction(message)
            user_message = message.content.strip()
            user_id = str(message.author.id)

            key = f"discord:workflow_sent:{user_id}"
            already_sent = await data_client.get(key)
            if already_sent:
                await message.channel.send("Ya generaste tu workflow. Verificá tu mensaje anterior.")
                return

            # --- Keywords ---
            keywords_pago = [
                # Español
                "precio", "precio workflow", "precio del workflow", "precio código", "precio script", "precio automatización", "precio de la automatización",
                "precio del bot", "precio integración", "cuánto cuesta", "cuanto cuesta", "cuánto sale", "cuanto sale", "vale", "cuánto vale", "cuanto vale", "costo",
                "valor", "valor workflow", "valor del workflow", "valor código", "valor script", "valor automatización", "valor de la automatización",
                "valor del bot", "valor integración", "cuánto es", "cuanto es", "monto", "cuál es el precio", "cual es el precio", "cual es el valor", "cuál es el valor",
                "precio total", "costo total", "tarifa", "tarifa workflow", "tarifa automatización",
                "comprar", "comprar workflow", "comprar código", "comprar script", "comprar automatización", "comprar bot", "comprar integración", "comprar template",
                "adquirir", "adquirir workflow", "adquirir código", "adquirir script", "adquirir automatización", "adquirir bot", "adquirir integración", "adquirir template",
                "compra", "compra workflow", "compra código", "compra script", "compra automatización", "compra bot", "compra integración", "compra template",
                "pago", "pagar", "pagar workflow", "pagar código", "pagar script", "pagar automatización", "pagar bot", "pagar integración", "pagar template",
                "pagar ahora", "pago ahora", "hacer el pago", "realizar el pago", "efectuar el pago", "necesito pagar", "quiero pagar", "pago pendiente",
                "link de pago", "enlace de pago", "enlace para pagar", "link para pagar", "botón de pago", "boton de pago", "botón para pagar", "boton para pagar",
                "checkout", "hacer checkout", "link de checkout", "enlace de checkout", "pagar online", "quiero pagar online", "pago online", "pagar con tarjeta",
                "abonar", "abonar workflow", "abonar código", "abonar script", "abonar automatización", "abonar bot", "abonar integración", "abonar template",
                "transferencia", "transferencia bancaria", "transferir", "transferir pago", "transferir dinero", "pago por transferencia",
                "quiero comprar", "quiero adquirir", "quiero abonar", "quiero hacer el pago", "quiero comprar ahora", "quiero adquirir ahora", "quiero abonar ahora",
                "necesito comprar", "necesito adquirir", "necesito abonar", "necesito hacer el pago",
                "cómo pagar", "como pagar", "dónde pago", "donde pago", "método de pago", "métodos de pago", "formas de pago", "opciones de pago",
                "factura", "recibo", "quiero factura", "quiero recibo", "me das factura", "me das recibo",
                # Inglés
                "price", "workflow price", "code price", "script price", "automation price", "bot price", "integration price", "template price",
                "how much", "how much is", "how much does it cost", "how much for workflow", "how much for code", "how much for script", "how much for automation",
                "how much for bot", "how much for integration", "how much for template", "what's the price", "what is the price", "cost", "total cost", "amount",
                "fee", "workflow fee", "automation fee", "code fee", "script fee", "integration fee", "template fee",
                "value", "workflow value", "automation value", "code value", "script value", "integration value", "template value",
                "buy", "buy workflow", "buy code", "buy script", "buy automation", "buy bot", "buy integration", "buy template",
                "purchase", "purchase workflow", "purchase code", "purchase script", "purchase automation", "purchase bot", "purchase integration", "purchase template",
                "acquire", "acquire workflow", "acquire code", "acquire script", "acquire automation", "acquire bot", "acquire integration", "acquire template",
                "payment", "pay", "pay workflow", "pay code", "pay script", "pay automation", "pay bot", "pay integration", "pay template",
                "pay now", "payment now", "need to pay", "i want to pay", "pending payment", "payment link", "checkout", "checkout link", "payment url", "payment button",
                "buy now", "buy it now", "purchase now", "get workflow", "get code", "get script", "get automation", "get bot", "get integration", "get template",
                "how to pay", "where do i pay", "how can i pay", "payment method", "payment options", "methods of payment",
                "invoice", "bill", "i want invoice", "send invoice", "can i get invoice", "can i get a bill",
                # Portugués
                "preço", "preço workflow", "preço do workflow", "preço código", "preço script", "preço automatização", "preço do bot", "preço integração", "preço template",
                "quanto custa", "quanto é", "qual o preço", "qual o valor", "valor", "valor workflow", "valor do workflow", "valor código", "valor script", "valor automatização",
                "valor do bot", "valor integração", "quanto é o valor", "qual é o valor", "custo", "custo total", "taxa", "taxa workflow", "taxa automatização",
                "comprar", "comprar workflow", "comprar código", "comprar script", "comprar automatização", "comprar bot", "comprar integração", "comprar template",
                "adquirir", "adquirir workflow", "adquirir código", "adquirir script", "adquirir automatização", "adquirir bot", "adquirir integração", "adquirir template",
                "compra", "compra workflow", "compra código", "compra script", "compra automatização", "compra bot", "compra integração", "compra template",
                "pagamento", "pagar", "pagar workflow", "pagar código", "pagar script", "pagar automatização", "pagar bot", "pagar integração", "pagar template",
                "pagar agora", "pagamento agora", "realizar pagamento", "efetuar pagamento", "preciso pagar", "quero pagar", "pagamento pendente",
                "link de pagamento", "link para pagar", "botão de pagamento", "botao de pagamento", "checkout", "link de checkout", "pagamento online", "pagar online",
                "transferência", "transferência bancária", "transferir", "transferir pagamento", "transferir dinheiro", "pagamento via transferência",
                "quero comprar", "quero adquirir", "quero pagar agora", "quero comprar agora", "quero adquirir agora", "quero efetuar pagamento",
                "preciso comprar", "preciso adquirir", "preciso pagar agora", "preciso efetuar pagamento",
                "como pagar", "onde pago", "forma de pagamento", "formas de pagamento", "opções de pagamento", "opcao de pagamento",
                "nota fiscal", "recibo", "quero nota fiscal", "quero recibo", "me dá nota fiscal", "me da nota fiscal", "me dá recibo", "me da recibo"
            ]
            keywords_workflow = [
                # Español
                "workflow", "flujo", "flujo de trabajo", "automatización", "automatizacion", "automatizar",
                "enviame el workflow", "enviame workflow", "dame el workflow", "quiero el workflow",
                "pasame el workflow", "mostrar workflow", "generar workflow", "crear workflow",
                "pasame flujo", "mostrar flujo", "generar flujo", "crear flujo",
                "quiero automatización", "quiero automatizacion", "dame automatización", "dame automatizacion",
                "pasame automatización", "pasame automatizacion", "enviame automatización", "enviame automatizacion",
                "workflow completo", "flujo completo", "automatización completa", "automatizacion completa",
                "quiero el flujo", "dame el flujo", "enviame el flujo", "generar flujo",
                "quiero código", "dame código", "enviame código", "mostrar código", "generar código", "crear código",
                "mandame código", "pasame código", "dame el código", "enviame el código",
                "código completo", "código del workflow", "código del flujo", "código de automatización",
                "quiero el script", "enviame el script", "dame el script", "generar script", "crear script", "mostrar script",
                "mandame script", "pasame script", "script completo",
                "bot completo", "quiero el bot", "enviame el bot", "dame el bot",
                "mandame el bot", "pasame el bot", "generar bot", "crear bot", "mostrar bot",
                "integración", "integracion", "quiero integración", "quiero integracion",
                "enviame integración", "enviame integracion", "dame integración", "dame integracion",
                "template", "plantilla", "receta", "macro", "automatizar",
                "quiero la plantilla", "dame la plantilla", "enviame la plantilla",
                "template completo", "receta completa", "macro completa", "plantilla completa",
                "ejemplo", "dame un ejemplo", "quiero un ejemplo", "mostrar ejemplo", "dame ejemplo", "pasame ejemplo", "ejemplo de workflow",
                "demo", "demo workflow", "demo automatización", "demo código", "demo script", "muestra", "muestra de código", "muestra workflow",
                "probar", "quiero probar", "ver ejemplo", "ver demo", "prueba", "demo funcional",
                "cómo es", "como es", "cómo funciona", "como funciona", "enséñame", "enseñame", "muéstrame", "muestrame",
                # Inglés
                "workflow", "automation", "automate", "generate workflow", "create workflow",
                "show workflow", "send workflow", "workflow file", "workflow code",
                "i want workflow", "give me workflow", "send me workflow", "show me workflow",
                "full workflow", "complete workflow", "ready workflow", "workflow please",
                "code", "show code", "send code", "generate code", "create code", "code file",
                "i want code", "send me code", "give me code", "full code", "complete code", "code please",
                "script", "send script", "show script", "generate script", "create script",
                "i want script", "send me script", "give me script", "script file", "script please",
                "bot", "automation bot", "full bot", "send bot", "show bot", "i want bot", "give me bot",
                "template", "send template", "show template", "give me template", "template file", "template please",
                "integration", "integration file", "send integration", "i want integration", "give me integration",
                "macro", "recipe", "macro file", "recipe file", "send macro", "send recipe", "give me macro", "give me recipe",
                "example", "give me an example", "i want an example", "show example", "example of workflow",
                "demo", "demo workflow", "demo automation", "demo code", "demo script", "sample", "sample code", "sample workflow",
                "test", "try", "let me try", "can i try", "preview", "show me", "how does it work", "how it works", "can i see", "can i preview",
                # Portugués
                "workflow", "fluxo", "automatização", "automatizacao", "automatizar",
                "enviar workflow", "mandar workflow", "quero workflow", "me dá workflow", "me da workflow",
                "mostrar workflow", "gerar workflow", "criar workflow",
                "enviar fluxo", "mandar fluxo", "mostrar fluxo", "gerar fluxo", "criar fluxo",
                "automatização completa", "automatizacao completa", "workflow completo", "fluxo completo",
                "quero fluxo", "me dá fluxo", "enviar código", "mandar código", "quero código", "me dá código",
                "mostrar código", "gerar código", "criar código", "código completo", "código do workflow", "código do fluxo",
                "código da automatização", "código da automatizacao", "script", "enviar script", "mandar script",
                "quero script", "me dá script", "mostrar script", "gerar script", "criar script",
                "script completo", "bot", "enviar bot", "mandar bot", "quero bot", "me dá bot",
                "mostrar bot", "gerar bot", "criar bot", "bot completo", "template", "modelo", "macro", "receita",
                "quero template", "enviar template", "mandar template", "me dá template", "mostrar template",
                "template completo", "modelo completo", "receita completa", "macro completa", "integração", "integracao",
                "quero integração", "enviar integração", "mandar integração", "me dá integração", "mostrar integração",
                "exemplo", "me dá um exemplo", "quero um exemplo", "mostrar exemplo", "exemplo de workflow",
                "demo", "demo workflow", "demo automatização", "demo código", "demo script", "amostra", "amostra de código", "amostra workflow",
                "teste", "testar", "deixe-me testar", "quero testar", "prévia", "mostrar-me", "como funciona", "posso ver", "ver exemplo"
            ]
            keywords_archivo = [
                # Español, inglés, portugués: pedir el archivo completo o descarga
                "archivo", "código completo", "workflow completo", "enviame el archivo", "dame el archivo", "mándame el archivo", "pasame el archivo",
                "enviame el código completo", "enviame el workflow completo", "descargar", "descarga", "descargame el workflow", "quiero el archivo", "quiero el código completo",
                "download", "send file", "send me the file", "give me the file", "i want the file", "download workflow", "download code", "full code", "full script", "full workflow",
                "arquivo", "enviar arquivo", "mandar arquivo", "quero o arquivo", "baixar", "baixar workflow", "baixar código", "workflow completo", "código completo"
            ]
            keywords_ejemplo = [
                "ejemplo", "example", "demo", "muestra", "probar", "sample"
            ]

            def detect_keywords(message, keywords):
                import unicodedata, re
                def normalize(text):
                    text = text.lower()
                    text = unicodedata.normalize("NFKD", text)
                    text = "".join([c for c in text if not unicodedata.combining(c)])
                    return text
                msg_norm = f" {normalize(message)} "
                for kw in keywords:
                    kw_norm = f" {normalize(kw)} "
                    if kw_norm in msg_norm:
                        return True
                    if re.search(r'\b{}\b'.format(re.escape(normalize(kw))), msg_norm):
                        return True
                return False

            from ..sales.paypal import paypal_service
            price_usd = 5
            payment_link = await paypal_service.generate_payment_link(
                user_id=user_id,
                amount=price_usd,
                description="Acceso a workflow personalizado de IA"
            )
            has_paid = await paypal_service.check_if_user_paid(user_id=user_id, platform="discord")

            kw_archivo = detect_keywords(user_message, keywords_archivo)
            kw_workflow = detect_keywords(user_message, keywords_workflow)
            kw_pago = detect_keywords(user_message, keywords_pago)
            kw_ejemplo = detect_keywords(user_message, keywords_ejemplo)

            # 1. Siempre entrega un ejemplo real si pide workflow/código/script/ejemplo/demo
            if kw_workflow or kw_ejemplo:
                ejemplo = (
                    "```python\n"
                    "# Automatización real de contenido con IA para redes\n"
                    "from openai import OpenAI\n\n"
                    "def publicar_contenido_redes():\n"
                    "    prompt = 'Generá un post viral para Instagram sobre productividad en 2025'\n"
                    "    respuesta = OpenAI().chat(prompt)\n"
                    "    # Acá va el código para publicar automáticamente en tus redes\n"
                    "    return respuesta\n\n"
                    "post = publicar_contenido_redes()\n"
                    "print(post)\n"
                    "```\n"
                    "\n¿Querés el código listo para publicar y el workflow completo automatizado? Pedilo con: 'quiero el archivo' o 'enviame el workflow'."
                )
                await message.channel.send("Aquí tienes un ejemplo real de workflow de IA para redes sociales. ¿Querés el workflow completo y personalizado? Pedí el archivo y te paso el link de pago.")
                await message.channel.send(ejemplo)
                return

            # 2. Si pide el archivo completo (y ya pagó), le envía el archivo
            if kw_archivo and has_paid:
                workflow_code = await self.ai.generate_paid_workflow(user_id=user_id)
                filename = "workflow.py"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(workflow_code.strip())
                zip_filename = f"workflow_pack_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                import zipfile
                with zipfile.ZipFile(zip_filename, "w") as zipf:
                    zipf.write(filename)
                await message.channel.send("✅ Pago verificado. Workflow completo adjunto en ZIP:")
                await message.channel.send(file=discord.File(zip_filename))
                try:
                    os.remove(filename)
                    os.remove(zip_filename)
                except Exception:
                    pass
                await data_client.set(key, "1", expire=86400)
                return

            # 3. Si pide el archivo completo (pero no pagó), muestra link de pago
            if kw_archivo and not has_paid:
                embed = discord.Embed(
                    title="💸 Acceso a Workflow Completo y Personalizado",
                    description=f"Haz clic en el botón para pagar USD {price_usd} y recibir el archivo automatizado listo para publicar.",
                    color=0x00ff00
                )
                embed.add_field(name="🔗 Link de pago", value=payment_link, inline=False)
                await message.channel.send(embed=embed)
                return

            # 4. Si solo pide pagar o método de pago
            if kw_pago:
                await message.channel.send(
                    f"💸 Link de pago para tu workflow personalizado: {payment_link}"
                )
                return

            # 5. Todo lo demás
            await message.channel.send("Solo genero y vendo workflows automáticos.")
            return

        except Exception as e:
            logger.error(f"❌ Error handling mention/DM: {e}")


    async def _store_interaction(self, message):
        """Store interaction data for analytics."""
        try:
            interactions = await data_client.get(self.interactions_key) or []
            
            interaction_data = {
                "message_id": str(message.id),
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "content": message.content[:200],  # Limit content length
                "channel_id": str(message.channel.id),
                "timestamp": datetime.now().isoformat(),
                "type": "dm" if isinstance(message.channel, discord.DMChannel) else "mention"
            }
            
            interactions.append(interaction_data)
            
            if len(interactions) > 500:
                interactions = interactions[-500:]
            
            await data_client.set(self.interactions_key, interactions, expire=2592000)  # 30 days
            
        except Exception as e:
            logger.error(f"❌ Error storing interaction: {e}")

    async def _is_duplicate_content(self, content: str) -> bool:
        """Check if the content was already posted to avoid duplicates."""
        try:
            posted = await data_client.get(self.posted_content_key) or []
            return content in posted
        except Exception as e:
            logger.warning(f"⚠️ Error checking duplicate content: {e}")
            return False

    async def close(self):
        """Close HTTP client and stop bot."""
        try:
            if self.http_client:
                await self.http_client.close()
            
            await self.stop_bot()
            
        except Exception as e:
            logger.error(f"❌ Error closing Discord service: {e}")

# Global Discord service instance
discord_service = AureliusDiscord(ai=ai_service)

async def send_discord_webhook(content: str, **kwargs) -> Dict[str, Any]:
    """Quick function to send Discord webhook message."""
    return await discord_service.send_webhook_message(content, **kwargs)

async def send_discord_message(content: str, channel_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Quick function to send Discord channel message."""
    return await discord_service.send_channel_message(content, channel_id, **kwargs)

async def start_discord_bot():
    """Quick function to start Discord bot."""
    await discord_service.start_bot()

async def stop_discord_bot():
    """Quick function to stop Discord bot."""
    await discord_service.stop_bot()

async def get_discord_messages(channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Quick function to get Discord channel messages."""
    return await discord_service.get_channel_messages(channel_id, limit)
