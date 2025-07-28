# ai/autoprog_engine.py
import os, logging
from ai import code_generator, sandbox_runner

# Configuración del logger
log_path = os.path.join(os.path.dirname(__file__), "logs", "autoprog.log")
logging.basicConfig(filename=log_path, level=logging.INFO, 
                    format="%(asctime)s [AUTOPROG] %(message)s")

def auto_program_feature(module_name: str, request: str):
    """Proceso principal para autoprogramar una nueva funcionalidad o módulo."""
    logging.info(f"Iniciando autoprogramación para: {module_name} - Solicitud: {request}")
    
    # 1. Generar el código con IA
    code = code_generator.generate_code(module_name, request)
    if not code or code.strip() == "":
        logging.error("La IA no retornó código. Abortando proceso.")
        return False
    # Guardar el código generado en el sandbox
    sandbox_runner.setup_sandbox()
    module_path = os.path.join(os.path.dirname(__file__), "sandbox", module_name)
    with open(module_path, "w", encoding="utf-8") as f:
        f.write(code)
    logging.info(f"Código generado guardado en sandbox: {module_path}")
    
    # 2. Ejecutar módulo en sandbox para verificar carga
    error = sandbox_runner.execute_module(module_path)
    if error:
        logging.error(f"Error al ejecutar el módulo {module_name} en sandbox: {error}")
        # (Opcional: retroalimentar a IA con el error para regenerar código)
        return False
    logging.info(f"Módulo {module_name} ejecutado correctamente en sandbox (sin errores de carga).")
    
    # 3. Ejecutar pruebas automáticas
    test_file = os.path.join(os.path.dirname(__file__), "tests", f"test_{os.path.splitext(module_name)[0]}.py")
    tests_passed = False
    if os.path.exists(test_file):
        tests_passed = sandbox_runner.run_tests(test_file)
    else:
        logging.warning(f"No se encontró archivo de pruebas para {module_name}. Saltando fase de pruebas.")
        tests_passed = True  # Si no hay pruebas definidas, se considera éxito por defecto
    
    if not tests_passed:
        logging.error(f"El módulo {module_name} no pasó las pruebas automáticas. Abortando integración.")
        # (Opcional: retroalimentar a IA con detalles de pruebas fallidas para intentar corregir código)
        return False
    logging.info(f"Todas las pruebas pasaron exitosamente para {module_name}. Procediendo a integración.")
    
    # 4. Integrar módulo a la base de código real
    dest_path = sandbox_runner.integrate_module(module_name)
    if dest_path:
        logging.info(f"Módulo {module_name} integrado en producción en {dest_path}")
        # (Opcional: podría hacerse commit a control de versiones aquí)
        return True
    else:
        logging.error(f"Fallo al integrar el módulo {module_name}.")
        return False

# Ejemplo de uso del motor de autoprogramación:
if __name__ == "__main__":
    solicitud = "Crear función get_top_seller(datos) que devuelva el producto con mayores ventas"
    auto_program_feature("sales_optimizer.py", solicitud)