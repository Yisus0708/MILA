"""
db_reader.py
Permite a MILA leer (SOLO LECTURA) bases de datos MySQL o PostgreSQL.
Credenciales en config/db_config.json:
{
  "engine": "mysql" | "postgresql",
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "",
  "database": "mi_basededatos"
}
"""
import json
from pathlib import Path

_DB_CONFIG_PATH = Path(__file__).parent.parent / "config" / "db_config.json"

# Solo se permiten consultas de lectura por seguridad
_BLOCKED_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "truncate", "create", "grant")


def _load_db_config() -> dict:
    if not _DB_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "No se encontró config/db_config.json. "
            "Creá ese archivo con: engine, host, port, user, password, database."
        )
    with open(_DB_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_connection(cfg: dict):
    engine = cfg.get("engine", "").lower()
    if engine == "mysql":
        import pymysql
        return pymysql.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user", "root"),
            password=cfg.get("password", ""),
            database=cfg.get("database"),
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=8,
        )
    elif engine in ("postgresql", "postgres"):
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 5432)),
            user=cfg.get("user", "postgres"),
            password=cfg.get("password", ""),
            dbname=cfg.get("database"),
            connect_timeout=8,
        )
    else:
        raise ValueError(f"Motor de base de datos no soportado: {engine}")


def list_tables() -> str:
    try:
        cfg = _load_db_config()
        conn = _get_connection(cfg)
        engine = cfg.get("engine", "").lower()
        cur = conn.cursor()
        if engine == "mysql":
            cur.execute("SHOW TABLES;")
            rows = cur.fetchall()
            tables = [list(r.values())[0] for r in rows]
        else:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public';
            """)
            tables = [r[0] for r in cur.fetchall()]
        conn.close()
        if not tables:
            return "No se encontraron tablas."
        return "Tablas disponibles:\n" + "\n".join(f"- {t}" for t in tables)
    except Exception as e:
        return f"Error listando tablas: {e}"


def describe_table(table: str) -> str:
    if not table:
        return "Falta indicar el nombre de la tabla."
    try:
        cfg = _load_db_config()
        conn = _get_connection(cfg)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table} LIMIT 1;")
        col_names = [d[0] for d in cur.description]
        conn.close()
        return f"Columnas de '{table}':\n" + ", ".join(col_names)
    except Exception as e:
        return f"Error describiendo tabla: {e}"


def run_query(query: str, max_rows: int = 50) -> str:
    if not query:
        return "Falta la consulta SQL."
    lowered = query.strip().lower()
    if not lowered.startswith("select"):
        return "Por seguridad, MILA solo puede ejecutar consultas SELECT (solo lectura)."
    if any(word in lowered for word in _BLOCKED_KEYWORDS):
        return "Consulta bloqueada: contiene una palabra clave no permitida."
    try:
        cfg = _load_db_config()
        conn = _get_connection(cfg)
        cur = conn.cursor()
        cur.execute(query)
        col_names = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows)
        conn.close()

        if not rows:
            return "La consulta no devolvió resultados."

        lines = [" | ".join(col_names)]
        for row in rows:
            values = row.values() if isinstance(row, dict) else row
            lines.append(" | ".join(str(v) for v in values))
        suffix = f"\n\n(Mostrando hasta {max_rows} filas)" if len(rows) == max_rows else ""
        return "\n".join(lines) + suffix
    except Exception as e:
        return f"Error ejecutando consulta: {e}"


def db_reader(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if player:
        player.write_log(f"[db_reader] {action}")

    try:
        if action == "list_tables":
            return list_tables()
        elif action == "describe_table":
            return describe_table(params.get("table", ""))
        elif action == "query":
            return run_query(params.get("query", ""), max_rows=int(params.get("max_rows", 50)))
        else:
            return f"Acción desconocida: '{action}'. Usá: list_tables | describe_table | query"
    except Exception as e:
        return f"db_reader error ({action}): {e}"
