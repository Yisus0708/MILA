"""
MILA - Generador de Datasets para Fine-Tuning (SFT)
Convierte historiales de conversación o pares pregunta/respuesta
en formato JSONL estándar para entrenamiento supervisado en Vertex AI o AWS Bedrock.
"""

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SYSTEM_PROMPT = (
    "You are MILA (Mi Inteligencia de Lenguaje Avanzada). "
    "Eres una asistente virtual inteligente, rápida, servicial y eficiente. "
    "Hablas en español de forma natural, concisa y cordial. Respondes con voz y ejecutas herramientas en el sistema."
)


def convert_conversations_to_jsonl(input_file: Path, output_file: Path):
    """Convierte un archivo de historial JSON en formato JSONL de entrenamiento."""
    if not input_file.exists():
        print(f"[DATASET GEN] Archivo de entrada no encontrado: {input_file}")
        return False

    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[DATASET GEN] Error leyendo {input_file}: {e}")
        return False

    records = []

    # Caso 1: Historial de mensajes tipo [{"role": "user", ...}, {"role": "assistant", ...}]
    if isinstance(data, list):
        current_messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        for item in data:
            role = item.get("role") or ("user" if item.get("sender") == "user" else "assistant")
            content = item.get("content") or item.get("text") or item.get("message")
            if role and content:
                current_messages.append({"role": role, "content": content})
                if role == "assistant" and len(current_messages) >= 3:
                    records.append({"messages": list(current_messages)})
                    # Reiniciar o mantener ventana
                    current_messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]

    # Caso 2: Memoria de aprendizaje
    elif isinstance(data, dict) and "knowledge" in data:
        for k in data["knowledge"]:
            records.append({
                "messages": [
                    {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Cuéntame sobre {k.get('topic')}"},
                    {"role": "assistant", "content": k.get("fact")}
                ]
            })

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[DATASET GEN] ✅ Dataset generado con {len(records)} ejemplos en: {output_file}")
    return True


if __name__ == "__main__":
    in_path = PROJECT_ROOT / "memory" / "conversation_history.json"
    out_path = PROJECT_ROOT / "training" / "mila_sft_dataset.jsonl"

    if len(sys.argv) > 1:
        in_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        out_path = Path(sys.argv[2])

    convert_conversations_to_jsonl(in_path, out_path)
