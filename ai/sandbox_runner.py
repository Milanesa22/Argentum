# ai/sandbox_runner.py
import importlib.util
import subprocess
import os
import shutil

SANDBOX_DIR = os.path.join(os.path.dirname(__file__), "sandbox")

def setup_sandbox():
    """Asegura que el entorno sandbox esté limpio."""
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    # Opcional: eliminar archivos previos del sandbox para limpieza
    for f in os.listdir(SANDBOX_DIR):
        if f.endswith(".py"):
            os.remove(os.path.join(SANDBOX_DIR, f))

def execute_module(module_path: str):
    """
    Carga y ejecuta un módulo Python desde la ruta dada en el sandbox.
    Retorna cualquier excepción ocurrida o None si la carga fue exitosa.
    """
    try:
        spec = importlib.util.spec_from_file_location("temp_module", module_path)
        temp_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(temp_module)
        return None  # ejecución satisfactoria
    except Exception as e:
        return e  # retornar la excepción para logging

def run_tests(test_file: str) -> bool:
    """
    Ejecuta un archivo de pruebas (por ejemplo con Pytest o unittest) en el sandbox.
    Retorna True si las pruebas pasan, False si alguna falla.
    """
    try:
        # Ejecutar pruebas en un subprocess para aislamiento
        result = subprocess.run(
            ["python", "-m", "pytest", "-q", test_file],  # usando Pytest en modo silencioso
            cwd=os.path.dirname(test_file),
            capture_output=True,
            text=True,
            timeout=30  # tiempo máximo de espera
        )
        # Retornar True si código de salida 0 (éxito), False si falló
        return result.returncode == 0
    except Exception as e:
        # En caso de error en ejecución (timeout u otro)
        print(f"[SandboxRunner] Error ejecutando pruebas: {e}")
        return False

def integrate_module(module_name: str):
    """
    Mueve el módulo probado desde el sandbox a la carpeta de producción correspondiente.
    Por ejemplo, si es un nuevo módulo de negocio, va a modules/, 
    o si es código core modificado, a core/.
    """
    src = os.path.join(SANDBOX_DIR, module_name)
    # Determinar destino según tipo de módulo
    if module_name in os.listdir(SANDBOX_DIR):
        if module_name.startswith("core_"):  # Convención: módulos que modifican core
            dest = os.path.join(os.path.dirname(__file__), "..", "core", module_name.split("core_")[1])
        else:
            dest = os.path.join(os.path.dirname(__file__), "..", "modules", module_name)
        shutil.copy(src, dest)
        return dest
    return None
async def run_autoprogramming_sandbox():
    """
    Entry point para la función llamada por el main loop de Aurelius.
    Por ahora, no hace nada. Expandilo con lógica real si lo necesitás.
    """
    pass
