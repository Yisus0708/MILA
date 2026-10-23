# ☁️ Guía de Despliegue de MILA en Amazon Web Services (AWS)

Esta guía detalla cómo desplegar y ejecutar **MILA** en la infraestructura de AWS utilizando contenedores Docker, instancias virtuales EC2 o tareas serverless en ECS Fargate, integrando Amazon S3 para persistencia de memoria.

---

## 🏗️ Opciones de Arquitectura en AWS

```
               ┌───────────────────────────────┐
               │         Amazon Route 53       │
               └───────────────┬───────────────┘
                               │
               ┌───────────────▼───────────────┐
               │    Application Load Balancer  │
               └───────────────┬───────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       ▼                                               ▼
┌─────────────────────────┐               ┌─────────────────────────┐
│     AWS EC2 Instance    │  (o)          │    AWS ECS (Fargate)    │
│  - Docker Container     │               │  - Serverless Task      │
│  - Xvfb Virtual Display │               │  - Xvfb Virtual Display │
│  - ALSA Dummy Audio     │               │  - CloudWatch Logs      │
└────────────┬────────────┘               └────────────┬────────────┘
             │                                         │
             └───────────────────┬─────────────────────┘
                                 │
                     ┌───────────▼───────────┐
                     │       Amazon S3       │
                     │ (Persistencia memoria │
                     │  y base conocimiento) │
                     └───────────────────────┘
```

---

## 🚀 Opción 1: Despliegue en AWS EC2 con Docker (Recomendada)

### 1. Lanzar una instancia EC2
- **AMI:** Ubuntu 22.04 LTS o Ubuntu 24.04 LTS
- **Tipo de instancia:** `t3.medium` o superior (2 vCPUs, 4 GB RAM)
- **Almacenamiento:** 25 GB gp3
- **Security Group:** Abrir puertos SSH (22) y el puerto de tu aplicación si expones una API web.

### 2. Conectarse y aprovisionar el servidor
```bash
ssh -i "tu-llave.pem" ubuntu@<IP_PUBLICA_EC2>

# Clonar el repositorio
git clone <URL_DE_TU_REPOSITORIO>
cd MILA-main

# Ejecutar el script de aprovisionamiento
chmod +x aws/setup_aws_ec2.sh
./aws/setup_aws_ec2.sh
```

### 3. Configurar variables de entorno
Crea tu archivo `.env` en la raíz del proyecto:
```bash
cp .env.example .env
nano .env
```
Configura tu `GEMINI_API_KEY` y tus credenciales de AWS si deseas respaldos en S3.

### 4. Construir y ejecutar el contenedor
```bash
cd aws
docker compose up -d --build
```

Para verificar los registros en tiempo real:
```bash
docker compose logs -f mila-app
```

---

## 📦 Opción 2: Despliegue en AWS ECS Fargate (Serverless)

1. **Crear repositorio en Amazon ECR:**
   ```bash
   aws ecr create-repository --repository-name mila-assistant --region us-east-1
   ```

2. **Construir y subir la imagen Docker a ECR:**
   ```bash
   # Iniciar sesión en ECR
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

   # Construir
   docker build -t mila-assistant -f aws/Dockerfile .

   # Etiquetar y subir
   docker tag mila-assistant:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/mila-assistant:latest
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/mila-assistant:latest
   ```

3. **Registrar la Task Definition en ECS:**
   ```bash
   aws ecs register-task-definition --cli-input-json file://aws/ecs-task-definition.json
   ```

4. **Lanzar el servicio en un ECS Cluster** seleccionando capacidad FARGATE.

---

## 🗄️ Persistencia de Memoria en Amazon S3

Para que MILA conserve su aprendizaje, hechos recordados y preferencias entre despliegues o reinicios de contenedor en AWS:

### Respaldo automático a S3:
```bash
python aws/s3_backup.py upload
```

### Restauración automática desde S3:
```bash
python aws/s3_backup.py download
```
*(Puedes programar esto en un Cron job en EC2 o en el entrypoint del contenedor).*
