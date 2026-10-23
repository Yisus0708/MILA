"""
MILA - S3 Cloud Memory Sync Utility
Permite sincronizar y respaldar la memoria de MILA (learning_data.json, long_term.json)
y archivos de entrenamiento en Amazon S3.
"""

import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_s3_client():
    if not BOTO3_AVAILABLE:
        print("[MILA S3] Error: 'boto3' no está instalado. Ejecuta: pip install boto3")
        return None
    
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    
    if aws_key and aws_secret:
        return boto3.client(
            "s3",
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name=aws_region
        )
    return boto3.client("s3", region_name=aws_region)


def upload_memory_to_s3(bucket_name: str, prefix: str = "mila-memory"):
    """Sube los archivos de memoria local a S3."""
    s3 = get_s3_client()
    if not s3:
        return False
        
    root = get_project_root()
    memory_dir = root / "memory"
    
    files_to_sync = [
        "learning_data.json",
        "long_term.json",
        "conversation_history.json"
    ]
    
    print(f"[MILA S3] Iniciando respaldo en s3://{bucket_name}/{prefix}/...")
    success_count = 0
    for filename in files_to_sync:
        file_path = memory_dir / filename
        if file_path.exists():
            s3_key = f"{prefix}/{filename}"
            try:
                s3.upload_file(str(file_path), bucket_name, s3_key)
                print(f"[MILA S3] ✅ Subido: {filename} -> s3://{bucket_name}/{s3_key}")
                success_count += 1
            except ClientError as e:
                print(f"[MILA S3] ❌ Error subiendo {filename}: {e}")
                
    print(f"[MILA S3] Respaldo finalizado ({success_count} archivos sincronizados).")
    return success_count > 0


def download_memory_from_s3(bucket_name: str, prefix: str = "mila-memory"):
    """Descarga los archivos de memoria desde S3 al entorno local."""
    s3 = get_s3_client()
    if not s3:
        return False
        
    root = get_project_root()
    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    files_to_sync = [
        "learning_data.json",
        "long_term.json",
        "conversation_history.json"
    ]
    
    print(f"[MILA S3] Descargando memoria desde s3://{bucket_name}/{prefix}/...")
    download_count = 0
    for filename in files_to_sync:
        s3_key = f"{prefix}/{filename}"
        local_path = memory_dir / filename
        try:
            s3.download_file(bucket_name, s3_key, str(local_path))
            print(f"[MILA S3] ✅ Restaurado: s3://{bucket_name}/{s3_key} -> {filename}")
            download_count += 1
        except ClientError as e:
            # Archivo no encontrado o sin permisos
            print(f"[MILA S3] ℹ️ No se pudo descargar {filename} ({e.response.get('Error', {}).get('Code', 'Error')})")
            
    return download_count > 0


if __name__ == "__main__":
    bucket = os.environ.get("AWS_S3_BUCKET_NAME")
    action = sys.argv[1] if len(sys.argv) > 1 else "upload"
    
    if not bucket:
        print("[MILA S3] Error: Define la variable de entorno AWS_S3_BUCKET_NAME")
        sys.exit(1)
        
    if action == "download":
        download_memory_from_s3(bucket)
    else:
        upload_memory_to_s3(bucket)
