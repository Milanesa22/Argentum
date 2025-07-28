# ai/code_generator.py
import openai  # Ejemplo: usando la API de OpenAI (puede reemplazarse por modelo local)

# Configuración (claves de API, modelo, etc.) - se asume configurada aparte
# openai.api_key = "TU_API_KEY"

def generate_code(module_name: str, request: str) -> str:
    """
    Genera código fuente para un nuevo módulo o cambio solicitado.
    `module_name` es el nombre del módulo o archivo a crear/modificar.
    `request` es la descripción de lo que el módulo debe hacer.
    Devuelve el código fuente generado como string.
    """
    # Prompt para la IA, detallando la solicitud
    prompt = (f"Genera el código del módulo `{module_name}`. {request}. "
              f"Incluye las funciones necesarias y documentación en comentarios.")
    # Llamada a la IA (ejemplo con OpenAI; se puede usar modelo local de manera similar)
    try:
        response = openai.Completion.create(
            engine="gpt-4-code",   # Motor de IA (ficticio para ejemplo)
            prompt=prompt,
            max_tokens=1024,
            temperature=0.2
        )
        code = response['choices'][0]['text']
    except Exception as e:
        # En caso de error en la generación, registrar y lanzar excepción
        code = ""
        print(f"[CodeGen] Error al generar código: {e}")
    return code

# Ejemplo de uso (simplificado, en la práctica el autoprog_engine llamará a generate_code)
if __name__ == "__main__":
    spec = "Función get_top_seller(datos) que devuelve el producto con mayores ventas"
    new_code = generate_code("sales_optimizer.py", spec)
    print(new_code)