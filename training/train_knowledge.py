"""
MILA - Script de Entrenamiento e Ingesta de Conocimiento
Permite cargar documentos (txt, md, json) a la base de conocimiento
de MILA para que pueda responder sobre ellos inmediatamente por voz o chat.
"""

import os
import sys
import json
import re
from pathlib import Path

# Agregar raíz del proyecto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from memory.learning_memory import add_knowledge, load as load_memory, save as save_memory
except ImportError:
    print("[TRAINER] Advertencia: No se pudo importar learning_memory. Operando en modo directo.")
    add_knowledge = None


def extract_facts_from_text(text: str, filename: str) -> list:
    """Extrae hechos y conceptos de un texto estructurado."""
    facts = []
    lines = text.split("\n")
    current_topic = Path(filename).stem.replace("_", " ").title()
    buffer = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Encabezados Markdown (# Título o ## Subtítulo)
        header_match = re.match(r"^#{1,3}\s+(.+)", line_clean)
        if header_match:
            if buffer:
                facts.append((current_topic, " ".join(buffer)))
                buffer = []
            current_topic = header_match.group(1).strip()
            continue

        # Formato Pregunta: Respuesta o Clave: Valor
        qa_match = re.match(r"^([Q|P|Pregunta|Concepto]+[\s\d]*:|\*\*.+?\*\*:?)\s*(.+)", line_clean)
        if qa_match:
            if buffer:
                facts.append((current_topic, " ".join(buffer)))
                buffer = []
            topic = qa_match.group(1).replace("*", "").replace(":", "").strip()
            content = qa_match.group(2).strip()
            facts.append((topic, content))
            continue

        buffer.append(line_clean)

    if buffer:
        facts.append((current_topic, " ".join(buffer)))

    return facts


def train_from_directory(data_dir: Path):
    """Procesa todos los archivos de soporte en data_dir."""
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        # Crear un archivo de ejemplo
        sample_file = data_dir / "empresa_ejemplo.md"
        sample_file.write_text(
            "# M.I.L.A Asistente\n"
            "MILA significa Mi Inteligencia de Lenguaje Avanzada. Es un asistente de escritorio con voz en tiempo real.\n\n"
            "## Horario de Operación\n"
            "El soporte técnico de nuestra empresa atiende de lunes a viernes de 8:00 AM a 6:00 PM.\n\n"
            "## Política de Datos\n"
            "MILA procesa la información en memoria temporal segura y no almacena archivos en servidores externos sin autorización.\n",
            encoding="utf-8"
        )
        print(f"[TRAINER] Directorio creado con archivo de ejemplo: {sample_file}")

    files = list(data_dir.glob("*.txt")) + list(data_dir.glob("*.md")) + list(data_dir.glob("*.json"))
    if not files:
        print(f"[TRAINER] No se encontraron archivos de texto en {data_dir}")
        return

    print(f"[TRAINER] 🧠 Iniciando entrenamiento con {len(files)} archivo(s)...")
    total_learned = 0

    for file_path in files:
        try:
            if file_path.suffix.lower() == ".json":
                content = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(content, list):
                    for item in content:
                        topic = item.get("topic") or item.get("pregunta") or item.get("title") or "General"
                        fact = item.get("fact") or item.get("respuesta") or item.get("content") or str(item)
                        if add_knowledge:
                            add_knowledge(topic, fact)
                        total_learned += 1
                elif isinstance(content, dict):
                    for topic, fact in content.items():
                        if add_knowledge:
                            add_knowledge(str(topic), str(fact))
                        total_learned += 1
            else:
                raw_text = file_path.read_text(encoding="utf-8")
                facts = extract_facts_from_text(raw_text, file_path.name)
                for topic, fact in facts:
                    if add_knowledge:
                        add_knowledge(topic, fact)
                    total_learned += 1
            print(f"  ✅ Procesado: {file_path.name}")
        except Exception as e:
            print(f"  ❌ Error procesando {file_path.name}: {e}")

    print(f"\n[TRAINER] 🎉 ¡Entrenamiento completado! Se indexaron {total_learned} hechos/conceptos en la memoria de MILA.")


if __name__ == "__main__":
    target_dir = Path(__file__).resolve().parent / "data"
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1])
    train_from_directory(target_dir)
