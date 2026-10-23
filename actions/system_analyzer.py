"""
system_analyzer.py
Analiza el sistema del usuario con Python puro.
Acciones: full_scan, processes, open_ports, disk_info, network_info, startup_info, windows_updates
"""
import os, socket, subprocess, platform, datetime
import psutil

# ─── helpers ────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout=8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"(error: {e})"

def _separator(title: str) -> str:
    return f"\n{'='*40}\n  {title}\n{'='*40}\n"

# ─── módulos individuales ────────────────────────────────────────────────────

def _system_info() -> str:
    info = platform.uname()
    boot = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
    mem  = psutil.virtual_memory()
    return (
        f"OS: {info.system} {info.release} ({info.machine})\n"
        f"Hostname: {info.node}\n"
        f"Procesador: {info.processor or 'desconocido'}\n"
        f"RAM total: {mem.total // 1024**3} GB | Usada: {mem.percent}%\n"
        f"Último arranque: {boot}"
    )

def _suspicious_processes() -> str:
    suspicious_keywords = [
        "miner", "xmr", "monero", "cryptonight", "keylog", "rat", "backdoor",
        "netcat", "nc.exe", "mimikatz", "empire", "metasploit", "cobaltstrike"
    ]
    results = []
    for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            name = proc.info["name"].lower()
            if any(kw in name for kw in suspicious_keywords):
                results.append(
                    f"⚠️  SOSPECHOSO: {proc.info['name']} (PID {proc.info['pid']}) "
                    f"CPU:{proc.info['cpu_percent']}% MEM:{proc.info['memory_percent']:.1f}%"
                )
        except Exception:
            pass
    # procesos con CPU muy alta
    for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            if proc.info["cpu_percent"] and proc.info["cpu_percent"] > 80:
                results.append(
                    f"🔥 CPU ALTA: {proc.info['name']} (PID {proc.info['pid']}) "
                    f"— {proc.info['cpu_percent']}% CPU"
                )
        except Exception:
            pass
    if not results:
        return "✅ No se encontraron procesos sospechosos."
    return "\n".join(results)

def _all_processes() -> str:
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(
                f"PID {proc.info['pid']:>6} | {proc.info['name']:<35} | "
                f"CPU: {proc.info['cpu_percent']:>5.1f}% | MEM: {proc.info['memory_percent']:>4.1f}%"
            )
        except Exception:
            pass
    return "\n".join(procs[:60]) + ("\n\n(mostrando 60 primeros)" if len(procs) > 60 else "")

def _open_ports() -> str:
    common_risky = {
        21: "FTP (riesgo: transferencia sin cifrar)",
        23: "Telnet (riesgo: acceso sin cifrar)",
        3389: "RDP (riesgo: acceso remoto expuesto)",
        445: "SMB (riesgo: compartición de archivos, vulnerabilidades WannaCry)",
        135: "RPC (riesgo: ejecución remota)",
        5900: "VNC (riesgo: escritorio remoto)",
        4444: "Puerto típico de backdoors/Metasploit",
        6666: "Puerto típico de troyanos",
        1080: "SOCKS proxy",
    }
    found = []
    warnings = []
    for conn in psutil.net_connections(kind="inet"):
        try:
            if conn.status == "LISTEN" and conn.laddr:
                port = conn.laddr.port
                pid  = conn.pid or 0
                try:
                    pname = psutil.Process(pid).name() if pid else "desconocido"
                except Exception:
                    pname = "desconocido"
                line = f"Puerto {port:>5} | {pname:<25} | PID {pid}"
                found.append(line)
                if port in common_risky:
                    warnings.append(f"⚠️  Puerto {port} abierto → {common_risky[port]}")
        except Exception:
            pass

    result = "Puertos escuchando:\n" + ("\n".join(found) if found else "ninguno detectado")
    if warnings:
        result += "\n\nALERTAS DE SEGURIDAD:\n" + "\n".join(warnings)
    else:
        result += "\n\n✅ No se detectaron puertos de alto riesgo abiertos."
    return result

def _disk_info() -> str:
    lines = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            pct   = usage.percent
            warn  = "⚠️  CASI LLENO" if pct > 85 else ""
            lines.append(
                f"{part.device} → {part.mountpoint} | "
                f"Total: {usage.total//1024**3}GB | "
                f"Libre: {usage.free//1024**3}GB | "
                f"Usado: {pct}% {warn}"
            )
        except Exception:
            pass
    return "\n".join(lines) if lines else "No se pudo leer la información de disco."

def _network_info() -> str:
    interfaces = []
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                interfaces.append(f"Interfaz: {name} | IP: {addr.address} | Máscara: {addr.netmask}")
    return "\n".join(interfaces) if interfaces else "No se encontraron interfaces de red."

def _startup_programs() -> str:
    """Lee los programas de inicio desde el registro de Windows."""
    try:
        import winreg
        keys = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]
        results = []
        for hive, path in keys:
            try:
                key = winreg.OpenKey(hive, path)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        results.append(f"  {name}: {val}")
                        i += 1
                    except OSError:
                        break
            except Exception:
                pass
        return ("Programas de inicio (Registro):\n" + "\n".join(results)) if results else "No se encontraron programas de inicio."
    except ImportError:
        return "(winreg no disponible — este análisis solo funciona en Windows)"

def _windows_updates() -> str:
    out = _run(["powershell", "-Command",
        "(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher().Search('IsInstalled=0').Updates | "
        "Select-Object -ExpandProperty Title | Select-Object -First 15"
    ], timeout=20)
    if not out or "error" in out.lower():
        return "No se pudo consultar actualizaciones (puede requerir permisos de administrador)."
    updates = [l for l in out.splitlines() if l.strip()]
    if not updates:
        return "✅ El sistema está actualizado, no hay actualizaciones pendientes."
    return f"⚠️  {len(updates)} actualizaciones pendientes:\n" + "\n".join(f"  - {u}" for u in updates)

# ─── escaneo completo ────────────────────────────────────────────────────────

def _full_scan() -> str:
    sections = [
        ("Información del Sistema",   _system_info),
        ("Procesos Sospechosos",      _suspicious_processes),
        ("Puertos Abiertos",          _open_ports),
        ("Disco",                     _disk_info),
        ("Red",                       _network_info),
        ("Programas de Inicio",       _startup_programs),
        ("Actualizaciones Pendientes",_windows_updates),
    ]
    report = "REPORTE DE ANÁLISIS DEL SISTEMA — " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + "\n"
    for title, fn in sections:
        report += _separator(title)
        try:
            report += fn()
        except Exception as e:
            report += f"(Error en esta sección: {e})"
    report += "\n\n⚠️  AVISO: Este análisis es básico (Python puro). No reemplaza un antivirus profesional."
    return report

# ─── dispatcher ─────────────────────────────────────────────────────────────

def system_analyzer(parameters: dict = None, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "full_scan").lower().strip()

    if player:
        player.write_log(f"[system_analyzer] {action}")

    actions = {
        "full_scan":       _full_scan,
        "processes":       _all_processes,
        "suspicious":      _suspicious_processes,
        "open_ports":      _open_ports,
        "disk_info":       _disk_info,
        "network_info":    _network_info,
        "startup_info":    _startup_programs,
        "windows_updates": _windows_updates,
        "system_info":     _system_info,
    }

    fn = actions.get(action)
    if not fn:
        return (
            f"Acción desconocida: '{action}'.\n"
            f"Opciones: {', '.join(actions.keys())}"
        )
    try:
        return fn()
    except Exception as e:
        return f"Error en system_analyzer ({action}): {e}"
