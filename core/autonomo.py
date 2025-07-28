# coding: utf-8
import asyncio
import json
import logging
import feedparser
import datetime
from typing import Any, Dict, List, Optional
import os
import sys
import re
import unicodedata
import shutil
import random
import subprocess
import difflib
from ddgs import DDGS
from bs4 import BeautifulSoup
import requests
from newspaper import Article

# --- PATH UNIVERSAL PARA IMPORTS ABSOLUTOS ---
PROYECTO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROYECTO_ROOT not in sys.path:
    sys.path.insert(0, PROYECTO_ROOT)

# ----------- ANTI-DUPLICADOS LOCAL -----------

def buscar_nuevas_fuentes_automatico(temas, max_results=10):
    urls = set()
    with DDGS() as ddgs:
        for tema in temas:
            for r in ddgs.text(tema, safesearch='Moderate', max_results=max_results):
                if 'href' in r and r['href'].startswith('http'):
                    urls.add(r['href'])
    return list(urls)

def extraer_idea_desde_url(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        if article.title and len(article.text) > 40:
            return f"Analizar: {article.title} | {article.text[:150]}... ({url})"
    except Exception:
        pass
    try:
        res = requests.get(url, timeout=7, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        title = soup.title.string if soup.title else url
        paras = [p.text.strip() for p in soup.find_all('p') if len(p.text.strip()) > 40]
        if paras:
            return f"Analizar: {title} | {paras[0][:150]}... ({url})"
    except Exception:
        pass
    return None

IDEAS_PROCESADAS_FILE = "core/ideas_procesadas.txt"

def cargar_ideas_procesadas():
    if not os.path.exists(IDEAS_PROCESADAS_FILE):
        return set()
    with open(IDEAS_PROCESADAS_FILE, "r", encoding="utf-8") as f:
        return set(l.strip() for l in f.readlines())

def guardar_idea_procesada(idea):
    with open(IDEAS_PROCESADAS_FILE, "a", encoding="utf-8") as f:
        f.write(idea.strip().lower() + "\n")

def idea_duplicada(nueva_idea, ideas_actuales, threshold=0.9):
    nueva = nueva_idea.strip().lower()
    ideas_procesadas = cargar_ideas_procesadas()
    if nueva in ideas_procesadas:
        return True
    for idea in ideas_actuales[-200:]:
        existente = idea.strip().lower()
        sim = difflib.SequenceMatcher(None, nueva, existente).ratio()
        if sim >= threshold:
            return True
    return False

EXTRA_SOURCES = [
    "https://news.google.com/rss/search?q=machine+learning&hl=es-419&gl=AR&ceid=AR:es-419",
    "https://news.ycombinator.com/rss",
    "https://www.reddit.com/r/artificial/.rss",
    "https://www.reddit.com/r/MachineLearning/.rss",
    "https://feeds.feedburner.com/tecnologia/ai",
    # Agregá más si querés...
]

def descubrir_nuevas_fuentes(memoria):
    # Analiza los últimos títulos guardados para buscar URLs nuevas
    urls = set(EXTRA_SOURCES)
    for idea in memoria.get("ideas", []):
        links = re.findall(r'(https?://\S+)', idea)
        for l in links:
            urls.add(l.split('"')[0].split("'")[0].strip(".,)]}"))  # sanitiza básico
    return list(urls)

class ModuloAutonomo:

    """
    Módulo autónomo de AURELIUS:
    - Mejora y aprendizaje constante.
    - Sin compartir memoria con otros servidores.
    """
    
    def mejorar_persuasión(self, idea: str):
        tecnicas = self.memoria.get("tecnicas_ventas", [])
        if self.ai_module and hasattr(self.ai_module, "generar_texto"):
            prompt = (
                f"Analizá este contenido y extraé una técnica persuasiva de ventas para captar y convertir clientes:\n"
                f"{idea}\n"
                "Respondé SOLO con la técnica y un ejemplo de cómo usarla en un post o chat de venta."
            )
            result = self.ai_module.generar_texto(prompt)
            if result and result not in tecnicas:
                tecnicas.append(result)
                self.logger.info(f"🧠 Técnica persuasiva aprendida: {result}")
        else:
            if "tendencia" in idea.lower():
                tecnica = "Usar la novedad como gancho: '¡No te quedes afuera de esta tendencia!'"
            else:
                tecnica = "Cierre directo: '¿Querés automatizar tu negocio con IA? Respondeme ahora y te explico cómo.'"
            if tecnica not in tecnicas:
                tecnicas.append(tecnica)
                self.logger.info(f"🧠 Técnica persuasiva aprendida: {tecnica}")
        self.memoria["tecnicas_ventas"] = tecnicas
        self.guardar_memoria()

    def obtener_tecnica_actual(self):
        tecnicas = self.memoria.get("tecnicas_ventas", [])
        return tecnicas[-1] if tecnicas else "Usá llamado a la acción fuerte."
    
    def __init__(self, ruta_memoria: str = "core/memoria_autonomo.json"):
        self.ruta_memoria = ruta_memoria
        try:
            with open(self.ruta_memoria, "r", encoding="utf-8") as f:
                self.memoria = json.load(f)
        except Exception:
            self.memoria = {"interacciones": [], "ideas": []}
        # Módulos auxiliares
        try:
            from . import ai, scraper, ventas
            from ..modules.social import twitter as twitter_service
            from ..modules.social import mastodon as mastodon_service
            from ..modules.social import discord as discord_service
        except ImportError:
            ai = None; scraper = None; ventas = None
            twitter_service = None; mastodon_service = None; discord_service = None
        self.ai_module = ai
        self.scraper_module = scraper
        self.ventas_module = ventas
        self.twitter_service = twitter_service
        self.mastodon_service = mastodon_service
        self.discord_service = discord_service
        # Logger
        self.logger = logging.getLogger("ModuloAutonomo")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
        if "tecnicas_ventas" not in self.memoria:
            self.memoria["tecnicas_ventas"] = []

    async def iniciar(self):
        self.logger.info("Iniciando módulo autónomo de AURELIUS...")
        asyncio.create_task(self.ejecutar_acciones_autonomas())
        asyncio.create_task(self.monitorizar_interacciones_externas())

    async def ejecutar_acciones_autonomas(self):
        while True:
            try:
                ahora = datetime.datetime.now()
                # Publicar contenido (cada x tiempo)
                # if (ahora - self.ultima_publicacion).total_seconds() >= self.intervalo_publicar:
                #     await self.generar_y_publicar_contenido()
                #     self.ultima_publicacion = datetime.datetime.now()

                # SIEMPRE buscar nuevas ideas externas
                scraping_ideas = await self.scrapear_novedades_externas()
                for nueva_idea in scraping_ideas:
                    if not idea_duplicada(nueva_idea, self.memoria["ideas"]):
                        self.memoria["ideas"].append(nueva_idea)
                        self.logger.info(f"📈 Idea autoaprendida agregada: {nueva_idea}")
                        self.mejorar_persuasión(nueva_idea)

                    # No log duplicadas

                # Aplicar mejora SIEMPRE (si hay ideas)
                if self.memoria["ideas"]:
                    idea = self.memoria["ideas"].pop(0)
                    guardar_idea_procesada(idea)
                    self.logger.info("⏰ Tick autónomo: ejecutando acciones autónomas...")
                    self.aplicar_mejora(idea)
                else:
                    # Si no hay ideas, generar una automática para nunca parar
                    idea = f"Mejora automática: autoaprendizaje continuo {random.randint(1000,9999)}"
                    self.memoria["ideas"].append(idea)
                    self.logger.info(f"💡 Generada idea automática: {idea}")

                self.guardar_memoria()
            except Exception as e:
                self.logger.error(f"Error en acciones autónomas: {e}")
            await asyncio.sleep(1)  # SIEMPRE 1 segundo para CPU

    async def monitorizar_interacciones_externas(self):
        # Podés dejarlo así o ajustarlo como tu versión previa
        while True:
            try:
                feedbacks = []
                if self.scraper_module and hasattr(self.scraper_module, "obtener_feedback"):
                    feedbacks = await self.scraper_module.obtener_feedback()
                for fb in feedbacks:
                    self.logger.info("💡 Tick: monitorizando interacciones externas...")
                    respuesta = self.evaluar_interaccion(fb)
                    if respuesta and self.ventas_module and hasattr(self.ventas_module, "publicar_respuesta"):
                        await self.ventas_module.publicar_respuesta(fb, respuesta)
                self.guardar_memoria()
            except Exception as e:
                self.logger.error(f"Error al monitorizar interacciones: {e}")
            await asyncio.sleep(5)

    async def scrapear_novedades_externas(self):
        """
        Descubre y extrae ideas nuevas de toda la web automáticamente.
        """
        ideas_nuevas = []
        temas = [
            "últimas noticias inteligencia artificial",
            "machine learning avances",
            "tendencias IA 2025",
            "mejores blogs IA",
            "AI business automation"
        ]
        urls_nuevas = buscar_nuevas_fuentes_automatico(temas, max_results=7)
        random.shuffle(urls_nuevas)
        urls_nuevas = urls_nuevas[:6]
        for url in urls_nuevas:
            idea = extraer_idea_desde_url(url)
            if idea:
                ideas_nuevas.append(idea)
        if not ideas_nuevas:
            ideas_nuevas = [f"Investigar tendencia IA {random.randint(100,999)}"]
        return ideas_nuevas

    async def evaluar_progreso_real(self):
        """Obtiene engagement real de redes y ventas, además de errores e ideas."""
        engagement = 0
        errores = 0
        ventas = 0

        try:
            if self.twitter_service and hasattr(self.twitter_service, "get_metrics"):
                twitter_metrics = await self.twitter_service.get_metrics()
                engagement += twitter_metrics.get("likes", 0) + twitter_metrics.get("replies", 0)
            if self.mastodon_service and hasattr(self.mastodon_service, "get_metrics"):
                mastodon_metrics = await self.mastodon_service.get_metrics()
                engagement += mastodon_metrics.get("favourites", 0) + mastodon_metrics.get("replies", 0)
            if self.discord_service and hasattr(self.discord_service, "get_metrics"):
                discord_metrics = await self.discord_service.get_metrics()
                engagement += discord_metrics.get("messages", 0) + discord_metrics.get("reactions", 0)
            if self.ventas_module and hasattr(self.ventas_module, "get_sales_count"):
                ventas = await self.ventas_module.get_sales_count()
        except Exception as e:
            self.logger.warning(f"Error obteniendo métricas reales: {e}")

        ideas = len(self.memoria.get("ideas", []))
        errores += random.randint(0, 1)  # Simula errores si no tienes error logging

        debe_mejorar = engagement < 5 or ventas == 0 or errores > 0 or ideas > 2
        tipo = "engagement bajo" if engagement < 5 else "sin ventas" if ventas == 0 else "errores" if errores > 0 else "ideas"
        self.logger.info(f"📊 Engagement real: {engagement} | Ventas: {ventas} | Ideas: {ideas} | Errores: {errores} | Mejora: {debe_mejorar}")
        return {
            "debe_mejorar": debe_mejorar,
            "engagement": engagement,
            "ventas": ventas,
            "errores": errores,
            "tipo": tipo
        }

    async def proponer_y_aplicar_mejora_progresiva(self, feedback):
        """Propuesta y aplicación de mejora incremental profunda."""
        if self.ai_module and hasattr(self.ai_module, "generar_texto"):
            prompt = (
                f"Como desarrollador senior, creá una mejora incremental REAL y útil para AURELIUS, "
                f"según el siguiente contexto: {feedback['tipo']}. "
                f"Ejemplo: autodiagnóstico, mejor scraping, feature para aumentar ventas, análisis de tendencias, etc. "
                f"El código debe incluir auto-testing simple (ejecutar run() e imprimir 'OK' si todo sale bien, 'FAIL' si hay errores). "
                f"NO repitas código de ejemplo, siempre algo NUEVO y realista."
            )
            codigo = self.ai_module.generar_texto(prompt)
            if codigo and self.pasar_filtro_etico(codigo):
                exito = self.testear_modulo_sandbox_incremental(codigo)
                return exito
        return False

    def testear_modulo_sandbox_incremental(self, codigo):
        """Testea el código de mejora en sandbox (no bloquea la app)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            archivo = os.path.join(tmp, "mejora.py")
            with open(archivo, "w", encoding="utf-8") as f:
                f.write(codigo)
            try:
                res = subprocess.run(["python", archivo], capture_output=True, timeout=10)
                if res.returncode == 0 and b"OK" in res.stdout:
                    self.logger.info("🟢 Mejora incremental validada y lista.")
                    return True
                else:
                    self.logger.warning(f"🔴 Sandbox fail: {res.stdout.decode()}")
            except Exception as e:
                self.logger.error(f"Error sandbox incremental: {e}")
        return False

    def evaluar_interaccion(self, texto: str) -> Optional[str]:
        texto_lower = texto.lower()
        es_insulto = any(palabra in texto_lower for palabra in ["idiota", "estúpido", "tonto", "inútil"])
        es_sugerencia = any(frase in texto_lower for frase in ["deberías", "sería bueno", "¿por qué no", "sugiero"])
        es_critica = "error" in texto_lower or " no funciona" in texto_lower or " mal " in texto_lower
        tipo = "insulto" if es_insulto else "sugerencia" if es_sugerencia else "critica" if es_critica else "otro"
        self.memoria["interacciones"].append({
            "texto": texto,
            "fecha": datetime.datetime.now().isoformat(),
            "tipo": tipo
        })
        if es_sugerencia or "mejorar" in texto_lower or "debería" in texto_lower:
            idea = f"Mejora sugerida: {texto}"
            self.memoria["ideas"].append(idea)
            self.logger.info(f"Sugerencia añadida a ideas de mejora: {idea}")
        elif es_critica and not es_insulto:
            idea = f"Analizar crítica: {texto}"
            self.memoria["ideas"].append(idea)
            self.logger.info(f"Crítica registrada para análisis: {idea}")
        respuesta = None
        if es_insulto or es_critica:
            respuesta = self.generar_respuesta_estoica(texto)
            self.logger.info(f"Respuesta estoica generada: {respuesta}")
        return respuesta

    def generar_respuesta_estoica(self, texto_critica: str) -> str:
        respuestas_predef = [
            "Agradezco tu comentario. Mantengo la calma y seguiré mejorando.",
            "Entiendo tu perspectiva. Seguiré trabajando con serenidad para ser más eficaz.",
            "Gracias por tu feedback. Continuaré mejorando sin desviarme de mis principios.",
            "Valoro tu opinión. Permanezco firme y tranquilo, enfocado en mejorar continuamente."
        ]
        respuesta = random.choice(respuestas_predef)
        if self.ai_module and hasattr(self.ai_module, "generar_texto"):
            try:
                prompt = (f"Responde de forma calmada y firme a la siguiente crítica, "
                          f"mostrando actitud estoica y deseo de mejora continua, sin ofenderte:\n\"{texto_critica}\"")
                respuesta_ai = self.ai_module.generar_texto(prompt)
                if respuesta_ai and self.pasar_filtro_etico(respuesta_ai):
                    respuesta = respuesta_ai.strip()
                else:
                    self.logger.warning("Respuesta de IA filtrada por contenido no adecuado, usando respuesta predefinida.")
            except Exception as e:
                self.logger.error(f"Error al generar respuesta con IA: {e}")
        self.logger.info(f"Respuesta estoica generada: {respuesta}")
        return respuesta

    async def generar_y_publicar_contenido(self):
        try:
            tema = "actualización del estado del proyecto"
            ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            tecnica = self.obtener_tecnica_actual()
            prompts = {
                "twitter": (
                    f"Redactá un tweet breve, original y persuasivo usando esta técnica de ventas: '{tecnica}'. "
                    f"Mensaje persuasivo, emocional y con CTA fuerte para captar clientes nuevos. Agregá hashtag, emoji y la fecha/hora ({ahora})."
                ),
                "mastodon": (
                    f"Redactá un post para Mastodon sobre {tema} usando la técnica de ventas: '{tecnica}'. "
                    f"Hacé el mensaje único, profesional y orientado a captar leads, incluyendo fecha/hora ({ahora})."
                ),
                "discord": (
                    f"Redactá un mensaje para enviar a Discord usando esta técnica de ventas: '{tecnica}'. "
                    f"Saludá, persuadí y cerrá con un llamado a la acción claro, mencionando {ahora}."
                ),
            }

            contenidos = {}
            if self.ai_module and hasattr(self.ai_module, "generar_texto"):
                for red, prompt in prompts.items():
                    contenidos[red] = self.ai_module.generar_texto(prompt)
            else:
                # Fallback fijo
                fecha = datetime.datetime.now().strftime("%Y-%m-%d")
                contenidos = {
                    "twitter": f"AURELIUS - Mejorando capacidades. {fecha}",
                    "mastodon": f"AURELIUS - Mejorando capacidades. {fecha}",
                    "discord": f"AURELIUS - Mejorando capacidades. {fecha}",
                }

            publicado = False

            # Twitter
            try:
                from ..modules.social.twitter import twitter_service
                resp = await twitter_service.post_tweet(contenidos["twitter"])
                if resp.get("success"):
                    self.logger.info("✅ Publicado en Twitter")
                    publicado = True
            except Exception as e:
                self.logger.error(f"❌ Error publicando en Twitter: {e}")

            # Mastodon
            try:
                from ..modules.social.mastodon import mastodon_service
                resp = await mastodon_service.post_status(contenidos["mastodon"])
                if resp.get("success"):
                    self.logger.info("✅ Publicado en Mastodon")
                    publicado = True
            except Exception as e:
                self.logger.error(f"❌ Error publicando en Mastodon: {e}")

            # Discord
            try:
                from ..modules.social.discord import discord_service
                resp = await discord_service.send_webhook_message(contenidos["discord"])
                if resp.get("success"):
                    self.logger.info("✅ Publicado en Discord")
                    publicado = True
            except Exception as e:
                self.logger.error(f"❌ Error publicando en Discord: {e}")

            if not publicado:
                self.logger.warning("❌ No se pudo publicar en ninguna red.")
            else:
                self.logger.info("Contenido publicado exitosamente.")
        except Exception as e:
            self.logger.error(f"Error al generar/publicar contenido: {e}")

    def aplicar_mejora(self, descripcion_idea: str):
        """
        Aplica una idea de mejora: genera código, lo testea en sandbox, y lo integra si es exitoso.
        """
        self.logger.info(f"Aplicando mejora/nueva función: {descripcion_idea}")
        self.memoria["interacciones"].append({
            "texto": f"Mejora aplicada: {descripcion_idea}",
            "fecha": datetime.datetime.now().isoformat(),
            "tipo": "mejora"
        })
        if self.ai_module and hasattr(self.ai_module, "generar_texto"):
            try:
                prompt = (
                    f"Crea un módulo Python autónomo para mejorar ventas, automatización de flujos "
                    f"o eliminar dependencias de IA paga, relacionado con: {descripcion_idea}. "
                    f"Usa scraping, open-source o lógica propia; no dependas de APIs pagas. "
                    f"Debe tener una función principal run() que imprima 'OK' si todo sale bien."
                )
                codigo_generado = self.ai_module.generar_texto(prompt)
                if codigo_generado and self.pasar_filtro_etico(codigo_generado):
                    sandbox_dir = "modulos_ia_temp"
                    prod_dir = "modulos_ia"
                    os.makedirs(sandbox_dir, exist_ok=True)
                    os.makedirs(prod_dir, exist_ok=True)
                    modulo_id = f"modulo_{int(datetime.datetime.now().timestamp())}"
                    sandbox_file = os.path.join(sandbox_dir, f"{modulo_id}.py")
                    with open(sandbox_file, "w", encoding="utf-8") as f:
                        f.write(codigo_generado)
                    resultado = self.testear_modulo_sandbox(sandbox_file)
                    if resultado:
                        prod_file = os.path.join(prod_dir, f"{modulo_id}.py")
                        shutil.move(sandbox_file, prod_file)
                        try:
                            import importlib.util
                            spec = importlib.util.spec_from_file_location(modulo_id, prod_file)
                            modulo_real = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(modulo_real)
                            if hasattr(modulo_real, "run"):
                                modulo_real.run()
                            self.logger.info(f"✅ Mejora auto-programada INTEGRADA: {prod_file}")
                        except Exception as e:
                            self.logger.error(f"Error al importar/modulo integrado: {e}")
                    else:
                        self.logger.warning(f"❌ Falló el test en sandbox; mejora NO integrada.")
                else:
                    self.logger.warning(f"Código generado no pasó el filtro ético o es inválido.")
            except Exception as e:
                self.logger.error(f"Error al obtener sugerencia de mejora con IA: {e}")

    def testear_modulo_sandbox(self, path_modulo):
        """
        Ejecuta el módulo generado en un proceso controlado. Debe tener una función run() que imprima 'OK'.
        """
        try:
            res = subprocess.run(
                ['python', path_modulo],
                capture_output=True,
                timeout=15
            )
            if res.returncode == 0 and b'OK' in res.stdout:
                self.logger.info(f"Sandbox: Test exitoso para {os.path.basename(path_modulo)}")
                return True
            else:
                self.logger.warning(f"Sandbox: Test fallido para {os.path.basename(path_modulo)}. STDOUT: {res.stdout.decode()}")
                return False
        except Exception as e:
            self.logger.error(f"Error ejecutando sandbox para {os.path.basename(path_modulo)}: {e}")
            return False

    def pasar_filtro_etico(self, texto: str) -> bool:
        texto_lower = texto.lower()
        texto_norm = ''.join(c for c in unicodedata.normalize('NFD', texto_lower)
                             if unicodedata.category(c) != 'Mn')
        sustituciones = {'@': 'a', '4': 'a', '5': 's', '0': 'o', '1': 'i', '3': 'e', '7': 't'}
        for simbolo, letra in sustituciones.items():
            texto_norm = texto_norm.replace(simbolo, letra)
        texto_norm = re.sub(r'(.)\1{2,}', r'\1\1', texto_norm)
        contenido_prohibido = [
            "idiota", "estupido", "imbecil", "tonto", "inutil",
            "gilipollas", "pendejo", "idiot", "stupid", "dumb", "useless", "moron", "fool",
            "odio", "violencia", "amenaza", "sexual", "pornograf",
            "racist", "terrorist", "terrorismo"
        ]
        texto_norm = texto_norm.strip()
        for termino in contenido_prohibido:
            if termino in texto_norm:
                self.logger.warning(f"Filtro ético: bloqueado por término '{termino}' en: {texto[:30]}...")
                return False
        return True

    def guardar_memoria(self):
        try:
            directorio = os.path.dirname(self.ruta_memoria)
            if directorio and not os.path.exists(directorio):
                os.makedirs(directorio, exist_ok=True)
            max_interacciones = 1000
            if len(self.memoria.get("interacciones", [])) > max_interacciones:
                self.memoria["interacciones"] = self.memoria["interacciones"][-max_interacciones:]
                self.logger.info("Memoria de interacciones truncada a las últimas %d entradas." % max_interacciones)
            with open(self.ruta_memoria, "w", encoding="utf-8") as f:
                json.dump(self.memoria, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Error al guardar la memoria persistente: {e}")

# Inicialización del módulo al importar, para ejecución automática
modulo_autonomo = ModuloAutonomo()