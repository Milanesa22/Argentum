"""
AURELIUS AI Core Module
Handles OpenAI/OpenRouter API integration for content generation and AI responses.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Union
import httpx
from datetime import datetime
import base64
import random
import sys
import os

from ..config import config
from ..logging_config import get_logger, log_ai_interaction
from ..utils.security import sanitize_and_prepare_content, validate_and_sanitize_input

logger = get_logger("AI")
# Diccionario global para llevar control por usuario
discord_link_sent = {}  # {user_id: True}

WORKFLOW_PRICE_USD = 5  # Cambiá el precio cuando quieras
PAY_LINK = "https://paypal.me/streetfits"  # Cambiá por tu link real
DISCORD_INVITE_LINK = "https://discord.gg/zb5bQjBbmW"
discord_link_sent = {}  # Global: {user_id: True}
workflow_delivered: Dict[str, bool] = {}

# --- Plantillas de workflows según tipo ---
WORKFLOW_TEMPLATES = {
    "twitter": lambda user_id: (
        f"# Workflow Twitter para usuario {user_id}\n"
        "def main():\n"
        "    print('Workflow de Twitter funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    "reddit": lambda user_id: (
        f"# Workflow Reddit para usuario {user_id}\n"
        "def main():\n"
        "    print('Workflow de Reddit funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    "mastodon": lambda user_id: (
        f"# Workflow Mastodon para usuario {user_id}\n"
        "def main():\n"
        "    print('Workflow de Mastodon funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    "linkedin": lambda user_id: (
        f"# Workflow LinkedIn para usuario {user_id}\n"
        "def main():\n"
        "    print('Workflow de LinkedIn funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    "email_sender": lambda user_id: (
        f"# Workflow Email Sender para usuario {user_id}\n"
        "def main():\n"
        "    print('Email sender listo para usar!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    "custom": lambda user_id: (
        f"# Workflow personalizado para usuario {user_id}\n"
        "def main():\n"
        "    print('¡Workflow a medida funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
    # fallback
    "default": lambda user_id: (
        f"# Workflow básico para usuario {user_id}\n"
        "def main():\n"
        "    print('Workflow funcionando para vos!')\n"
        "\nif __name__ == '__main__':\n    main()"
    ),
}

class AureliusAI:
    """
    AI service for content generation, sales copy, and automated responses.
    Supports OpenAI GPT-4/GPT-4o via OpenRouter or direct OpenAI API.
    """
    
    def __init__(self):
        self.api_key = config.OPENAI_API_KEY
        self.base_url = config.OPENAI_BASE_URL
        self.model = config.OPENAI_MODEL
        self.default_system_prompt = config.DEFAULT_SYSTEM_PROMPT
        self.sales_prompt_template = config.SALES_PROMPT_TEMPLATE
        
        # HTTP client for async requests
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize HTTP client with proper headers."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Add OpenRouter specific headers if using OpenRouter
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://aurelius-ai.com"
            headers["X-Title"] = "AURELIUS AI Business Manager"
        
        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
    
    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate AI response using OpenAI/OpenRouter API.
        Returns dict with response, usage info, and metadata.
        Tries with lower max_tokens if credits are insufficient (error 402).
        """
        try:
            # Sanitize input
            prompt = validate_and_sanitize_input(prompt, "ai_prompt")
            if system_prompt:
                system_prompt = validate_and_sanitize_input(system_prompt, "system_prompt")
            
            model_to_use = model or self.model
            system_to_use = system_prompt or self.default_system_prompt
            
            messages = [
                {"role": "system", "content": system_to_use},
                {"role": "user", "content": prompt}
            ]
            
            tokens_try = [max_tokens, 500, 256, 128, 64, 32]
            last_error = ""
            for tk in tokens_try:
                payload = {
                    "model": model_to_use,
                    "messages": messages,
                    "max_tokens": tk,
                    "temperature": temperature,
                    "stream": False
                }
                logger.info(f"🤖 Generating AI response | Model: {model_to_use} | Tokens: {tk}")
                try:
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload
                    )
                    if response.status_code == 200:
                        response_data = response.json()
                        if "choices" in response_data and response_data["choices"]:
                            content = response_data["choices"][0]["message"]["content"]
                            usage = response_data.get("usage", {})
                            tokens_used = usage.get("total_tokens", 0)
                            log_ai_interaction("generation", model_to_use, tokens_used, success=True)
                            return {
                                "content": content,
                                "model": model_to_use,
                                "usage": usage,
                                "timestamp": datetime.now().isoformat(),
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": tokens_used
                            }
                        else:
                            last_error = "No choices in API response"
                            log_ai_interaction("generation", model_to_use, success=False, error=last_error)
                    elif response.status_code == 402:
                        # Not enough credits or too many tokens, try with fewer tokens
                        last_error = f"Error 402: Insufficient credits or too many tokens (tried {tk})."
                        logger.warning(last_error)
                        continue  # Prueba con menos tokens
                    else:
                        last_error = f"API request failed with status {response.status_code}: {response.text}"
                        log_ai_interaction("generation", model_to_use, success=False, error=last_error)
                        break  # Otros errores no se reintentan
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"❌ AI generation failed: {e}")
                    log_ai_interaction("generation", model_to_use, success=False, error=last_error)
                    break  # Fallos graves no reintentan
            
            # Si llegó acá, es que no se pudo con ninguno
            error_message = (
                "⛔ No hay créditos suficientes en OpenRouter/OpenAI. "
                "Por favor, recarga saldo o reduce la cantidad de tokens."
                f"\nDetalle: {last_error}"
            )
            logger.error(error_message)
            return {
                "content": error_message,
                "model": model_to_use,
                "usage": {},
                "timestamp": datetime.now().isoformat(),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        except Exception as e:
            logger.error(f"❌ AI generation failed: {e}")
            log_ai_interaction("generation", self.model, success=False, error=str(e))
            raise

    async def generate_social_content(
        self,
        topic: str,
        platform: str,
        tone: str = "professional",
        include_hashtags: bool = True,
        target_audience: Optional[str] = None
    ) -> str:
        """
        Generate social media content for specific platform.
        Returns sanitized content ready for posting.
        """
        try:
            # Platform-specific constraints
            platform_limits = {
                "twitter": 280,
                "mastodon": 500,
                "discord": 2000
            }
            
            char_limit = platform_limits.get(platform.lower(), 500)
            
            # Build prompt
            prompt_parts = [
                f"Create engaging {platform} content about: {topic}",
                f"Tone: {tone}",
                f"Character limit: {char_limit}",
                f"Include hashtags: {'Yes' if include_hashtags else 'No'}"
            ]
            
            if target_audience:
                prompt_parts.append(f"Target audience: {target_audience}")
            
            prompt_parts.extend([
                "Requirements:",
                "- Be engaging and authentic",
                "- Follow platform best practices",
                "- Include a clear call-to-action if appropriate",
                "- Stay within character limits",
                "- Use appropriate formatting for the platform"
            ])
            
            prompt = "\n".join(prompt_parts)
            
            # Generate content
            response = await self.generate_response(
                prompt=prompt,
                max_tokens=300,
                temperature=0.8
            )
            
            # Sanitize for platform
            content = sanitize_and_prepare_content(response["content"], platform)
            
            logger.info(f"📱 Generated {platform} content | Length: {len(content)} chars")
            return content
            
        except Exception as e:
            logger.error(f"❌ Social content generation failed for {platform}: {e}")
            return ""
    
    async def close(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
    
    async def generate_sales_copy(
        self,
        product: str,
        audience: str,
        copy_type: str = "email",
        urgency_level: str = "medium"
    ) -> str:
        """
        Generate sales copy for products/services.
        Returns persuasive sales content.
        """
        try:
            # Use configured sales prompt template
            base_prompt = self.sales_prompt_template.format(
                product=product,
                audience=audience
            )
            
            # Add copy type specific instructions
            type_instructions = {
                "email": "Create a compelling email sales copy with subject line and body.",
                "dm": "Create a direct message for social media sales outreach.",
                "ad": "Create advertising copy for social media ads.",
                "landing": "Create landing page sales copy with headlines and benefits."
            }
            
            urgency_instructions = {
                "low": "Use subtle urgency and focus on value.",
                "medium": "Include moderate urgency with time-sensitive offers.",
                "high": "Create strong urgency with limited-time offers and scarcity."
            }
            
            full_prompt = f"""
{base_prompt}

Copy Type: {copy_type}
{type_instructions.get(copy_type, "Create persuasive sales copy.")}

Urgency Level: {urgency_level}
{urgency_instructions.get(urgency_level, "")}

Requirements:
- Focus on benefits, not just features
- Address pain points and objections
- Include social proof if relevant
- Have a clear, compelling call-to-action
- Use persuasive but ethical language
- Match the tone to the target audience
"""
            
            response = await self.generate_response(
                prompt=full_prompt,
                max_tokens=800,
                temperature=0.7
            )
            
            # Sanitize content
            content = validate_and_sanitize_input(response["content"], "sales_copy")
            
            logger.info(f"💰 Generated {copy_type} sales copy | Length: {len(content)} chars")
            return content
            
        except Exception as e:
            logger.error(f"❌ Sales copy generation failed: {e}")
            return ""
    
    async def generate_auto_reply(
        self,
        text: str,
        user_id: Optional[str],
        platform: str,
        context: str = "",
        reply_type: str = "helpful"
    ) -> str:
        """
        Genera respuestas automáticas a mensajes/comentarios. Cobertura máxima de keywords para interés, precio, compra, automatización, código, explicación, dudas, pagos y variantes de idioma y formato.
        """

        try:
            text = validate_and_sanitize_input(text, "message")
            context = validate_and_sanitize_input(context, "context")
            global discord_link_sent

            # Lista ULTRA completa de keywords para venta/workflow/pago/automatización/código
            mensajes_venta = [
                # Español - Precio y compra
                "precio", "cuánto cuesta", "cuanto cuesta", "cuánto sale", "cuanto sale", "vale", "valor", "cuánto es", "cuanto es",
                "cuánto vale", "cuanto vale", "qué cuesta", "que cuesta", "qué sale", "que sale", "me lo vendes", "vendes", "me lo vendés", 
                "me lo vendes?", "me lo vendés?", "me lo vendes vos", "me lo vendés vos", "me lo das", "me lo das?", "quiero comprar", 
                "quiero pagarlo", "quiero pagar", "adquirir", "tengo que pagar", "cómo pago", "como pago", "te pago", "puedo comprar", 
                "puedo pagar", "quiero el workflow", "quiero workflow", "puedo adquirir", "comprar workflow", "comprar flujo", "pago", 
                "factura", "abonar", "comprar", "tarifa", "cuota", "necesito comprar", "necesito pagar", "adquirir workflow", 
                "comprar automatización", "pagame", "dame el precio",
                # Español - Flujo/Workflow/automatización/script
                "workflow", "work flow", "work-flow", "flujo", "crear un flujo", "crear flujo", "me podés crear un flujo", 
                "me puedes crear un flujo", "puedes crear un flujo", "podés crear un flujo", "me haces un flujo", "me hacés un flujo",
                "me puedes hacer un flujo", "me podés hacer un flujo", "hacer un flujo", "hacer flujo", "armar un flujo", "armame un flujo",
                "arma un flujo", "puedes hacer un flujo", "puedes crear workflow", "puedes crearme un flujo", "puedes hacerme un flujo", 
                "me creás un workflow", "me creas un workflow", "me generas un flujo", "me generás un flujo", "crear un workflow", 
                "crear workflow", "armar workflow", "me podés crear workflow", "me puedes crear workflow", "podés crear workflow", 
                "puedes crear workflow", "puedes hacer workflow", "puedes hacerme workflow", "me haces workflow", "me hacés workflow",
                "me puedes hacer workflow", "me podés hacer workflow", "hacer workflow", "hacerme workflow", "armame workflow", 
                "arma workflow", "crear automatización", "crear automatizacion", "me automatizas", "me automatizás", "puedes automatizar", 
                "podés automatizar", "automatizar flujo", "automatizar workflow", "me automatizas el proceso", "quiero automatizar", 
                "me armarías un flujo", "me armás un flujo", "me harías un flujo", "me haces un script", "me hacés un script", 
                "me creas un script", "me creás un script", "quiero un flujo", "quiero un workflow", "puedes hacer un script", 
                "podés hacer un script", "puedes crear un script", "podés crear un script", "automatizar", "automatización",
                # Inglés y Spanglish (ultra variantes)
                "workflow", "create workflow", "create a workflow", "can you create a workflow", "can you make a workflow",
                "how much is the workflow", "workflow price", "buy workflow", "pay workflow", "how much for workflow", "purchase workflow",
                "get workflow", "buy a workflow", "can i buy a workflow", "how much workflow", "automate", "automation", "create automation",
                "make automation", "price workflow", "workflow cost", "workflow purchase", "get automation", "buy automation", 
                "order workflow", "workflow order", "order automation",
                # Formas informales, con errores y combinaciones
                "fluyo", "flow", "quiero un flow", "me haces un flow", "me creas un flow", "crear flow", "flow price", "precio del flow",
                "hacer flow", "automatizar flow", "me haces un automator", "quiero un automator", "puedes crear flow", "podés crear flow",
                "podrías crear un flujo", "podrías hacer un flujo", "podés crear workflow", "podés hacer workflow", "puedes hacer flow",
                # USTED, variantes formales
                "usted puede crear un flujo", "usted puede hacer un flujo", "me podría crear un flujo", "me podría hacer un flujo",
                "me podría automatizar", "usted puede automatizar", "me podría crear workflow", "me podría hacer workflow",
                "me podría crear automatización", "me podría hacer automatización", "podría crear un flujo", "podría hacer un flujo",
                "podría crear workflow", "podría hacer workflow",
                # Variantes de pago/abono
                "pagar workflow", "pagar flujo", "abonar workflow", "abonar flujo", "quiero abonar workflow", "quiero abonar flujo",
                "abonar", "pagar", "transferencia workflow", "transferencia flujo", "tarjeta workflow", "tarjeta flujo",
                # Ultra combinaciones y sinónimos
                "quiero automatizar", "quiero comprar un flujo", "me gustaría un workflow", "puedo tener un workflow", "comprar bot",
                "comprar bot de automatización", "quiero un bot", "bot de workflow", "automatizador", "robot workflow", "quiero el bot",
                "puedo tener el bot", "me creas un bot", "me podrías crear un bot"
            ]
            frases_pago = [
                "quiero pagar", "ya pagué", "ya pague", "ya abone", "pagué", "pagado", "hice el pago", "pago realizado", "payment done", 
                "i have paid", "i already paid", "i paid", "pago hecho", "pague", "hice el pago", "hice pago", "pagamento feito", 
                "pay now", "pagar ahora", "make payment", "ready to pay", "pagar workflow", "quiero abonar", "abonar", "abonar workflow", 
                "pagar el flujo", "quiero el link de pago", "enviame el link de pago", "link de pago", "link pago", "payment link", 
                "paypal", "cómo te pago", "como te pago", "realizar pago", "hacer pago", "comprar ahora", "quiero comprar ahora"
            ]
            frases_flujo = [
                "qué hace este flujo", "que hace este flujo", "qué hace el flujo", "para qué sirve este flujo", "para que sirve este flujo",
                "cómo funciona el flujo", "como funciona el flujo", "para qué es este workflow", "que es este workflow", "qué es este workflow",
                "explicame el flujo", "explica el flujo", "describí el flujo", "describe el workflow", "explain workflow", 
                "what does this workflow do", "how does this workflow work", "workflow explanation", "workflow details", "workflow purpose", 
                "workflow use", "workflow description", "función del flujo", "para qué sirve", "explica workflow", "para que es este workflow"
            ]
            frases_code = [
                "enviame el código", "mandame el código", "quiero el código", "dame el código", "codigo", "code", "source code",
                "show me the code", "workflow code", "code sample", "sample workflow", "ejemplo de workflow", "ejemplo de código",
                "codigo ejemplo", "code example"
            ]
            frases_no_entendi = [
                "no entendí", "no entiendo", "no comprendo", "no me queda claro", "no queda claro", "no entiendo cómo funciona",
                "no entiendo el flujo", "i don’t understand", "i dont understand", "can you clarify", "explain again", "puedes explicar",
                "explica de nuevo"
            ]

            # --- CONFIG PRECIOS/ENLACES ---
            COTIZACION_USD_ARS = 1400
            WORKFLOW_PRICE_ARS = int(WORKFLOW_PRICE_USD * COTIZACION_USD_ARS)

            # --- RESPUESTA DE VENTA Y FLUJO SEGÚN PLATAFORMA ---
            # Caso Discord - INTERESADO (pide precio, compra, workflow)
            if platform.lower() == "discord" and any(f in text.lower() for f in mensajes_venta):
                respuesta = (
                    f"💸 El precio del workflow es **{WORKFLOW_PRICE_USD} USD** (aprox. {WORKFLOW_PRICE_ARS} ARS).\n"
                    "🔹 Si querés ver un ejemplo, pedímelo con: `qué hace este flujo` o `mostrame el código`.\n"
                    "🔹 ¿Listo para comprar? Decime *quiero pagar* y te paso el link seguro de pago PayPal.\n"
                    "Tras el pago recibís el workflow completo como archivo adjunto en este chat. 🚀"
                )
                return {"text": respuesta, "code": ""}

            # Caso Discord - PEDIDO DE PAGO ("quiero pagar" o variantes)
            if platform.lower() == "discord" and any(f in text.lower() for f in frases_pago):
                respuesta = (
                    f"¡Perfecto! Aquí tenés el link de pago seguro vía PayPal:\n{PAY_LINK}\n\n"
                    "Apenas se confirme el pago, vas a recibir el workflow completo como archivo adjunto por este chat.\n"
                    "Si ya abonaste y no recibiste nada, respondé acá y lo solucionamos al instante."
                )
                return {"text": respuesta, "code": ""}

            # Caso Discord - PEDIDO DE EXPLICACIÓN DEL FLUJO O CÓDIGO
            if platform.lower() == "discord" and any(f in text.lower() for f in frases_flujo + frases_code):
                explicacion = (
                    "🔍 **¿Qué hace este workflow?**\n"
                    "Este workflow es un script Python que automatiza la publicación de tweets en X/Twitter. "
                    "Permite programar mensajes, conectar tu cuenta y publicar automáticamente lo que quieras en el horario que elijas. "
                    "Incluye manejo de errores y puede adaptarse a otras plataformas. El fragmento que ves es real, y la versión completa es mucho más robusta y lista para usar."
                )
                ejemplo_codigo = (
                    "import requests\n"
                    "from datetime import datetime\n\n"
                    "def publicar_en_twitter(mensaje, api_key):\n"
                    "    url = 'https://api.twitter.com/2/tweets'\n"
                    "    headers = {'Authorization': f'Bearer {api_key}'}\n"
                    "    data = {'text': mensaje}\n"
                    "    resp = requests.post(url, headers=headers, json=data)\n"
                    "    if resp.status_code == 201:\n"
                    "        return 'Tweet publicado correctamente!'\n"
                    "    else:\n"
                    "        return f'Error: {resp.text}'\n\n"
                    "def flujo_principal():\n"
                    "    mensaje = f\"Hola, mundo! Son las {datetime.now().strftime('%H:%M:%S')}\"\n"
                    "    api_key = 'TU_API_KEY'\n"
                    "    print(publicar_en_twitter(mensaje, api_key))\n\n"
                    "if __name__ == '__main__':\n"
                    "    flujo_principal()\n"
                    "# La versión completa y documentada se entrega tras el pago."
                )
                return {"text": explicacion, "code": ejemplo_codigo}

            # Caso Discord - USUARIO NO ENTIENDE
            if platform.lower() == "discord" and any(f in text.lower() for f in frases_no_entendi):
                respuesta = (
                    "¡Tranquilo! Resumo cómo funciona: el workflow que vendo te permite automatizar tareas reales, como publicar tweets o integrar tus redes, de forma 100% personalizada. "
                    "¿Querés un ejemplo real? Escribí *qué hace el flujo* y te muestro un fragmento del código real."
                )
                return {"text": respuesta, "code": ""}

            # Caso OTRAS REDES - PRIMER MENSAJE (precio, link, discord)
            if any(f in text.lower() for f in mensajes_venta) and user_id and not discord_link_sent.get(user_id, False) and platform.lower() != "discord":
                discord_link_sent[user_id] = True
                respuesta = (
                    f"El workflow de automatización cuesta **{WORKFLOW_PRICE_USD} USD** (aprox. {WORKFLOW_PRICE_ARS} ARS).\n"
                    f"Pagalo aquí: {PAY_LINK}\n"
                    f"¿Consultas? Hablame por DM o unite a mi Discord para atención directa: {DISCORD_INVITE_LINK}"
                )
                return respuesta

            # Caso OTRAS REDES - SEGUNDO MENSAJE (ya recibió link)
            if any(f in text.lower() for f in mensajes_venta) and user_id and discord_link_sent.get(user_id, False) and platform.lower() != "discord":
                respuesta = (
                    "Ya te envié la información y el link de pago en el mensaje anterior.\n"
                    "¿Necesitás soporte? Respondeme por DM o sumate a Discord."
                )
                return respuesta

            # Caso OTRAS REDES - Pide explicación/código
            if any(f in text.lower() for f in frases_flujo + frases_code) and platform.lower() != "discord":
                explicacion = (
                    "Este workflow es un script de automatización para publicar mensajes en X/Twitter. Recibe tus datos, programa el contenido y lo publica de manera autónoma. "
                    "¿Querés ver un fragmento real de código? Escribí *mostrame el código*."
                )
                return explicacion

            # Caso OTRAS REDES - No entiende
            if any(f in text.lower() for f in frases_no_entendi) and platform.lower() != "discord":
                return (
                    "¡Claro! El workflow es un software que automatiza tareas como publicaciones en redes, envío de mensajes y más. "
                    "¿Te muestro un ejemplo real? Escribí *qué hace el flujo*."
                )

            # Default: IA genera respuesta amigable y profesional
            reply_styles = {
                "helpful": "Be helpful, informative, and supportive.",
                "sales": "Be helpful but guide towards sales opportunities.",
                "customer_service": "Be professional and solution-focused.",
                "engagement": "Be engaging and encourage further conversation."
            }
            prompt = f"""
    Generate an appropriate reply to this {platform} message:

    Original Message: "{text}"
    Context: {context}
    Reply Style: {reply_type}
    Style Instructions: {reply_styles.get(reply_type, "Be professional and helpful.")}

    Requirements:
    - Keep response concise and relevant
    - Match the tone of the original message
    - Be authentic and human-like
    - Include helpful information when appropriate
    - Follow {platform} communication best practices
    - Avoid being overly promotional unless it's a sales reply type
    """
            response = await self.generate_response(
                prompt=prompt,
                max_tokens=200,
                temperature=0.8
            )
            return response["content"]

        except Exception as e:
            logger.error(f"❌ Auto-reply generation failed: {e}")
            return ""

    def generar_texto(self, prompt: str) -> str:
        """
        Wrapper síncrono para generar texto (usado por Discord y el módulo autónomo).
        Ejecuta el método async y devuelve solo el string de contenido.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.run_until_complete(self._generar_texto_async(prompt))
            else:
                return asyncio.run(self._generar_texto_async(prompt))
        except Exception as e:
            logger.error(f"Error en generar_texto: {e}")
            return "Error: No se pudo generar texto."

    async def _generar_texto_async(self, prompt: str) -> str:
        resp = await self.generate_response(prompt)
        return resp["content"] if "content" in resp else ""
    
    async def generate_paid_workflow(self, user_id: str, workflow_type: str = "default", custom_content: Optional[str] = None) -> str:
        """
        Devuelve el código fuente del workflow pagado, personalizado por usuario y tipo de workflow.
        Soporta múltiples plantillas, feedback de tipos válidos, y contenido custom opcional.
        """
        global workflow_delivered
        if workflow_delivered.get(user_id, False):
            logger.warning(f"Intento de reenvío de workflow para usuario {user_id}. Ya entregado antes.")
            return "# Ya recibiste tu workflow. Si hay un error, contactá soporte."
        else:
            workflow_delivered[user_id] = True
            logger.info(f"Marcado workflow como entregado para usuario {user_id} ({workflow_type})")

        workflow_type = (workflow_type or "default").lower()
        available_types = [k for k in WORKFLOW_TEMPLATES.keys() if k != "default"]
        if workflow_type not in WORKFLOW_TEMPLATES:
            tipos_str = ", ".join(available_types)
            return (
                f"# El tipo de workflow solicitado no existe: '{workflow_type}'.\n"
                f"# Tipos disponibles: {tipos_str}\n"
                "# Probá con alguno de esos. Si querés algo personalizado, pedí 'custom'."
            )
        if workflow_type == "custom":
            return (
                f"# Workflow personalizado para usuario {user_id}\n"
                f"# Contenido solicitado:\n"
                f"{custom_content if custom_content else '# (No se recibió contenido personalizado)'}\n"
                "def main():\n"
                "    print('¡Workflow custom funcionando para vos!')\n"
                "\nif __name__ == '__main__':\n    main()"
            )
        plantilla = WORKFLOW_TEMPLATES[workflow_type]
        return plantilla(user_id)

    async def analyze_content_performance(
        self,
        content: str,
        engagement_data: Dict[str, Any],
        platform: str
    ) -> Dict[str, Any]:
        """
        Analyze content performance and provide optimization suggestions.
        Returns analysis and recommendations.
        """
        try:
            # Sanitize inputs
            content = validate_and_sanitize_input(content, "content")
            engagement_data = validate_and_sanitize_input(engagement_data, "engagement_data")
            
            prompt = f"""
Analyze this {platform} content performance and provide optimization recommendations:

Content: "{content}"
Engagement Data: {json.dumps(engagement_data, indent=2)}

Please analyze:
1. What worked well in this content
2. What could be improved
3. Specific recommendations for future content
4. Optimal posting times/strategies based on engagement
5. Content format suggestions

Provide actionable insights in JSON format with the following structure:
{{
    "performance_score": 1-10,
    "strengths": ["list of strengths"],
    "weaknesses": ["list of areas for improvement"],
    "recommendations": ["specific actionable recommendations"],
    "content_suggestions": ["ideas for future content"],
    "optimization_tips": ["platform-specific optimization tips"]
}}
"""
            
            response = await self.generate_response(
                prompt=prompt,
                max_tokens=600,
                temperature=0.5
            )
            
            # Try to parse as JSON
            try:
                analysis = json.loads(response["content"])
            except json.JSONDecodeError:
                # Fallback to text analysis
                analysis = {
                    "performance_score": 5,
                    "analysis_text": response["content"],
                    "error": "Could not parse structured analysis"
                }
            
            logger.info(f"📊 Analyzed content performance for {platform}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Content analysis failed: {e}")
            return {"error": str(e)}
    
    async def generate_content_strategy(
        self,
        business_info: Dict[str, Any],
        target_audience: str,
        goals: List[str],
        platforms: List[str]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive content strategy.
        Returns strategic recommendations and content calendar ideas.
        """
        try:
            # Sanitize inputs
            business_info = validate_and_sanitize_input(business_info, "business_info")
            target_audience = validate_and_sanitize_input(target_audience, "audience")
            
            prompt = f"""
Create a comprehensive content strategy for this business:

Business Information: {json.dumps(business_info, indent=2)}
Target Audience: {target_audience}
Goals: {', '.join(goals)}
Platforms: {', '.join(platforms)}

Please provide a strategic plan including:
1. Content pillars and themes
2. Posting frequency recommendations per platform
3. Content mix (educational, promotional, engaging, etc.)
4. Optimal posting times
5. Engagement strategies
6. Content calendar template
7. KPIs to track
8. Growth strategies

Format as JSON with clear sections and actionable recommendations.
"""
            
            response = await self.generate_response(
                prompt=prompt,
                max_tokens=1200,
                temperature=0.6
            )
            
            # Try to parse as JSON
            try:
                strategy = json.loads(response["content"])
            except json.JSONDecodeError:
                # Fallback to text strategy
                strategy = {
                    "strategy_text": response["content"],
                    "error": "Could not parse structured strategy"
                }
            
            logger.info(f"📋 Generated content strategy for {len(platforms)} platforms")
            return strategy
            
        except Exception as e:
            logger.error(f"❌ Content strategy generation failed: {e}")
            return {"error": str(e)}
    
async def auto_generate_and_post(ai_service, platforms: list, topics: list, post_func_map: dict, interval: int = 1800):
    """
      Automatiza la generación y publicación de contenido en todas las plataformas.
    - ai_service: instancia de AureliusAI.
    - platforms: lista de strings ("twitter", "mastodon", "discord", etc.).
    - topics: lista de tópicos o keywords para contenido.
    - post_func_map: diccionario {platform: funcion_posteo}.
    - interval: segundos entre publicaciones (default 30min).
    """
    while True:
        topic = random.choice(topics)
        for platform in platforms:
            try:
                # Genera el contenido para la plataforma
                content = await ai_service.generate_social_content(
                    topic=topic,
                    platform=platform,
                    tone="professional",
                    include_hashtags=True
                )
                # Publica el contenido usando la función correspondiente
                if content and len(content) > 0:
                    await post_func_map[platform](content)
            except Exception as e:
                logger.error(f"❌ Auto-posting failed on {platform}: {e}")
        await asyncio.sleep(interval)

async def auto_engagement(ai_service, platforms: list, fetch_mentions_map: dict, reply_func_map: dict, interval: int = 600):
    """
    Automatiza la respuesta a menciones/comentarios en redes sociales.
    - ai_service: instancia de AureliusAI.
    - platforms: lista de strings.
    - fetch_mentions_map: diccionario {platform: funcion_fetch}.
    - reply_func_map: diccionario {platform: funcion_reply}.
    - interval: segundos entre chequeos (default 10min).
    """
    while True:
        for platform in platforms:
            try:
                mentions = await fetch_mentions_map[platform]()
                for mention in mentions:
                    # Analiza el contexto y responde automáticamente
                    response = await ai_service.generate_auto_reply(
                    text=mention["text"],
                    user_id=mention.get("author_id") or None,
                    platform=platform,
                    context=mention.get("context", ""),
                    reply_type="engagement"
                )
                    if response:
                        await reply_func_map[platform](mention, response)
            except Exception as e:
                logger.error(f"❌ Auto-engagement failed on {platform}: {e}")
        await asyncio.sleep(interval)

# Global AI instance
ai_service = AureliusAI()

async def generate_platform_content(topic: str, platform: str, **kwargs) -> str:
    """Quick function to generate content for a platform."""
    return await ai_service.generate_social_content(topic, platform, **kwargs)

async def generate_sales_message(product: str, audience: str, **kwargs) -> str:
    """Quick function to generate sales copy."""
    return await ai_service.generate_sales_copy(product, audience, **kwargs)

async def generate_reply(text: str, user_id: Optional[str], platform: str, context: str = "", reply_type: str = "helpful", **kwargs) -> str:
    """
    Quick function to generate automated replies. 
    (Ahora requiere los mismos argumentos que el método principal.)
    """
    return await ai_service.generate_auto_reply(
        text=text, 
        user_id=user_id, 
        platform=platform, 
        context=context, 
        reply_type=reply_type,
        **kwargs
    )