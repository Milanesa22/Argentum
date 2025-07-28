# ai/tests/test_generated_module.py
# Importar el módulo generado desde el sandbox para pruebas
import importlib.util, os
sandbox_dir = os.path.join(os.path.dirname(__file__), "..", "sandbox")
spec = importlib.util.spec_from_file_location("sales_optimizer", os.path.join(sandbox_dir, "sales_optimizer.py"))
sales_optimizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sales_optimizer)

def test_get_top_seller():
    """Prueba la función get_top_seller del módulo generado."""
    datos_ventas = [("ProductoA", 100), ("ProductoB", 150), ("ProductoC", 120)]
    resultado = sales_optimizer.get_top_seller(datos_ventas)
    # Se espera que devuelva "ProductoB" por ser el de mayor ventas (150)
    assert resultado == "ProductoB"
