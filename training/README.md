# 🎓 Sistema de Entrenamiento y Aprendizaje de MILA

MILA cuenta con una arquitectura de **aprendizaje multi-nivel** diseñada para adaptarse a necesidades personales, técnicas o empresariales. El sistema no depende únicamente del modelo base, sino que se especializa a través de 4 capas complementarias:

---

## 🏛️ Las 4 Capas de Entrenamiento de MILA

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Prompt Engineering & Directrices (core/prompt.txt)       │
│    Personalidad, reglas de voz, restricciones y tools       │
├─────────────────────────────────────────────────────────────┤
│ 2. Memoria Continua en Vivo (memory/learning_memory.py)     │
│    Aprende de correcciones y preferencias en tiempo real    │
├─────────────────────────────────────────────────────────────┤
│ 3. Ingesta de Conocimiento y RAG (training/train_knowledge) │
│    Carga de manuales, PDFs, políticas y datos de negocio    │
├─────────────────────────────────────────────────────────────┤
│ 4. Fine-Tuning Supervisado / SFT (training/dataset_gen)     │
│    Afinamiento de pesos en Vertex AI / Bedrock / LoRA       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Capa 1: Personalidad y Reglas de Comportamiento (`core/prompt.txt`)
Define el tono, la voz, los límites y las reglas de ejecución de MILA.
- **Tono:** Español natural, conciso, profesional y cálido.
- **Políticas de llamada a herramientas:** Cuándo responder con voz y cuándo ejecutar una acción en el sistema.
- Puedes modificar `core/prompt.txt` para adaptar a MILA al tono de tu empresa o marca.

---

## ⚡ Capa 2: Aprendizaje Continuo en Vivo (`memory/`)
MILA aprende mientras interactúa contigo:
- **Correcciones automáticas:** Si le dices *"Mila, no me llames usuario, llámame Jesús"*, MILA registra la corrección en `memory/learning_data.json`.
- **Hechos aprendidos:** Cuando mencionas datos personales o profesionales (*"Mi proyecto se llama Sistema Omega"*), MILA los indexa automáticamente con coincidencia difusa (`SequenceMatcher`) para recordarlos en futuras sesiones.

---

## 📚 Capa 3: Entrenamiento por Ingesta de Conocimiento (`train_knowledge.py`)
Para que MILA conozca los productos de tu empresa, manuales técnicos o políticas internas sin necesidad de reprogramarla:

1. Coloca tus archivos de texto, markdown o JSON con datos en la carpeta `training/data/`.
2. Ejecuta el entrenador de conocimiento:
   ```bash
   python training/train_knowledge.py
   ```
3. El script extraerá conceptos, preguntas frecuentes y hechos clave, insertándolos directamente en la memoria semántica de MILA. Al preguntarle por voz, MILA responderá con esa información al instante.

---

## 🔬 Capa 4: Fine-Tuning Supervisado (SFT) en la Nube

Para entrenar un modelo fundacional personalizado (en Google Cloud Vertex AI, AWS Bedrock o con modelos open source como Llama/Mistral):

1. **Generar los datos de entrenamiento a partir del historial:**
   ```bash
   python training/dataset_generator.py --input memory/conversation_history.json --output training/train.jsonl
   ```
2. **Formato JSONL generado (estándar para Vertex AI / OpenAI / Bedrock):**
   ```json
   {
     "messages": [
       {"role": "system", "content": "You are MILA, an advanced AI desktop assistant..."},
       {"role": "user", "content": "Mila, ¿cuál es el estado de las ventas este mes?"},
       {"role": "assistant", "content": "Las ventas crecieron un 14% respecto al mes anterior, alcanzando el objetivo proyectado."}
     ]
   }
   ```
3. Sube `training/train.jsonl` a la consola de fine-tuning para entrenar tu modelo especializado.
