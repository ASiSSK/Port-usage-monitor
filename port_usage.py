#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import sqlite3
import signal
from datetime import datetime

# --- بخش ۱: نصب خودکار پیش‌نیازها (Auto-Install Dependencies) ---
def install_dependencies():
    required = ['rich', 'psutil']
    installed = False
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            print(f"⚠️  Library '{pkg}' not found. Installing automatically...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL)
            installed = True
    if installed:
        print("✅ Dependencies installed. Restarting panel...")
        os.execv(sys.executable, ['python3'] + sys.argv)

install_dependencies()

# --- ایمپورت کتابخانه‌های گرافیکی ---
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box
from rich.prompt import Prompt, IntPrompt
import psutil

console = Console()

# --- تنظیمات اصلی ---
DB_FILE = "/root/port_usage.db"
SERVICE_NAME = "port_master"
SCRIPT_PATH = os.path.abspath(__file__)
PAGINATION_LIMIT = 15 # تنظیم حداکثر پورت برای نمایش در هر صفحه

# --- بخش ۲: توابع دیتابیس و سیستم ---
def init_db():
    if not os.path.exists(os.path.dirname(DB_FILE)):
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ports
                 (port INTEGER PRIMARY KEY, 
                  added_at TEXT, 
                  time_limit_min INTEGER, 
                  data_limit_mb INTEGER, 
                  total_rx INTEGER, 
                  total_tx INTEGER,
                  is_blocked INTEGER)''')
    conn.commit()
    conn.close()

def setup_iptables(port):
    subprocess.run(f"iptables -I INPUT -p tcp --dport {port}", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run(f"iptables -I OUTPUT -p tcp --sport {port}", shell=True, stderr=subprocess.DEVNULL)

def remove_iptables_rules(port):
    subprocess.run(f"iptables -D INPUT -p tcp --dport {port}", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run(f"iptables -D OUTPUT -p tcp --sport {port}", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run(f"iptables -D INPUT -p tcp --dport {port} -j DROP", shell=True, stderr=subprocess.DEVNULL)

def block_port_system(port):
    subprocess.run(f"iptables -I INPUT -p tcp --dport {port} -j DROP", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run(f"ss -K dst :{port}", shell=True, stderr=subprocess.DEVNULL)

def get_iptables_traffic(port):
    try:
        result = subprocess.check_output(f"iptables -nvx -L", shell=True).decode()
        rx = 0
        tx = 0
        for line in result.split('\n'):
            if f"tcp dpt:{port}" in line:
                parts = line.split()
                rx = int(parts[1])
            elif f"tcp spt:{port}" in line:
                parts = line.split()
                tx = int(parts[1])
        return rx, tx
    except:
        return 0, 0

def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

# --- بخش ۳: هسته اصلی سرویس (Daemon) ---
def run_daemon():
    init_db()
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT * FROM ports WHERE is_blocked=0")
            rows = c.fetchall()
            
            for row in rows:
                port, added_at, t_limit, d_limit, last_rx, last_tx, blocked = row
                
                current_rx, current_tx = get_iptables_traffic(port)
                total_mb = (current_rx + current_tx) / (1024 * 1024)
                
                should_block = False
                
                if d_limit and total_mb >= d_limit:
                    should_block = True
                
                start_time = datetime.fromisoformat(added_at)
                elapsed_min = (datetime.now() - start_time).total_seconds() / 60
                if t_limit and elapsed_min >= t_limit:
                    should_block = True

                c.execute("UPDATE ports SET total_rx=?, total_tx=? WHERE port=?", (current_rx, current_tx, port))
                
                if should_block:
                    block_port_system(port)
                    c.execute("UPDATE ports SET is_blocked=1 WHERE port=?", (port,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            pass 
        
        time.sleep(2)

# --- بخش ۴: توابع رابط کاربری (Menu Logic) ---

def header():
    console.clear()
    console.print(Align.center(Panel.fit("[bold cyan]ASiS SK - Port Usage[/bold cyan]", style="bold cyan")))

def install_service_ui():
    header()
    service_content = f"""[Unit]
Description=Port Master Monitor Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 {SCRIPT_PATH} daemon
Restart=always
User=root

[Install]
WantedBy=multi-user.target
"""
    try:
        if not os.path.exists(os.path.dirname(DB_FILE)):
            os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
            
        with open(f"/etc/systemd/system/{SERVICE_NAME}.service", "w") as f:
            f.write(service_content)
        
        subprocess.run("systemctl daemon-reload", shell=True)
        subprocess.run(f"systemctl enable {SERVICE_NAME}", shell=True)
        subprocess.run(f"systemctl start {SERVICE_NAME}", shell=True)
        console.print(Panel("[bold green]✅ Service Installed & Started Successfully![/bold green]\nMonitoring runs in background now.", title="Success"))
    except Exception as e:
        console.print(f"[bold red]Error installing service:[/bold red] {e}")
    
    Prompt.ask("\nPress Enter to return")

def add_port_ui():
    header()
    console.print("[bold yellow]Add New Port to Monitor[/bold yellow]")
    
    try:
        port = IntPrompt.ask("[cyan]Enter Port Number[/cyan]")
        t_limit = Prompt.ask("[cyan]Time Limit (mins)[/cyan] [dim](0 for None)[/dim]", default="0")
        d_limit = Prompt.ask("[cyan]Data Limit (MB)[/cyan] [dim](0 for None)[/dim]", default="0")
        
        t_limit = int(t_limit) if t_limit != "0" else None
        d_limit = int(d_limit) if d_limit != "0" else None
        
        init_db()
        setup_iptables(port)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO ports (port, added_at, time_limit_min, data_limit_mb, total_rx, total_tx, is_blocked) VALUES (?, ?, ?, ?, 0, 0, 0)",
                  (port, datetime.now().isoformat(), t_limit, d_limit))
        conn.commit()
        conn.close()
        
        console.print(f"\n[bold green]✅ Port {port} is now being monitored![/bold green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
    
    time.sleep(1.5)

def delete_port_ui():
    header()
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT port FROM ports")
    ports = [str(r[0]) for r in c.fetchall()]
    conn.close()
    
    if not ports:
        console.print("[yellow]No ports found in database.[/yellow]")
        time.sleep(2)
        return

    console.print(f"[bold]Monitored Ports:[/bold] {', '.join(ports)}")
    port_to_del = IntPrompt.ask("[red]Enter Port to Stop Monitoring[/red]")
    
    if str(port_to_del) in ports:
        remove_iptables_rules(port_to_del)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM ports WHERE port=?", (port_to_del,))
        conn.commit()
        conn.close()
        console.print(f"[bold green]🗑️ Port {port_to_del} removed from monitor and iptables rules cleared.[/bold green]")
    else:
        console.print("[red]Port not found![/red]")
    
    time.sleep(1.5)

# تابع اصلی داشبورد با اعمال صفحه‌بندی و حذف لیست پورت‌های فعال دیگر
def port_dashboard_ui():
    if not os.path.exists(DB_FILE):
        console.print("[red]Database not found! Run 'Install Service' first.[/red]")
        time.sleep(2)
        return

    current_page = 0
    
    while True:
        header()
        
        # --- ۱. پورت‌های مانیتور شده ---
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT * FROM ports")
            all_rows = c.fetchall()
            conn.close()
        except:
            all_rows = []

        total_ports = len(all_rows)
        total_pages = (total_ports + PAGINATION_LIMIT - 1) // PAGINATION_LIMIT
        
        # محاسبه پورت‌های صفحه فعلی
        start_index = current_page * PAGINATION_LIMIT
        end_index = min(start_index + PAGINATION_LIMIT, total_ports)
        rows_on_page = all_rows[start_index:end_index]

        table = Table(title="📊 Monitored Ports (Detailed Stats)", box=box.HEAVY_EDGE, style="cyan", expand=True)
        table.add_column("Port", style="bold cyan", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Active Time", style="magenta", justify="center")
        table.add_column("Total Usage", style="white bold", justify="right")
        table.add_column("Limits (Time/Data)", style="yellow", justify="center")

        for row in rows_on_page:
            port, added_at, t_limit, d_limit, rx, tx, blocked = row
            
            status = "[bold red]⛔ BLOCKED[/bold red]" if blocked else "[bold green]● ACTIVE[/bold green]"
            
            start_dt = datetime.fromisoformat(added_at)
            elapsed = datetime.now() - start_dt
            uptime = str(elapsed).split('.')[0]
            
            t_str = f"{t_limit}m" if t_limit else "∞"
            d_str = f"{d_limit}MB" if d_limit else "∞"

            table.add_row(
                str(port), status, uptime,
                format_bytes(rx + tx),
                f"{t_str} / {d_str}"
            )
        console.print(table)
        
        # --- ۲. نمایش وضعیت صفحه و منو ---
        
        # ساختار منو بر اساس نیاز به صفحه‌بندی
        menu_options = [
            "[white]1.[/white] [green]Refresh Data Now[/green]",
            "[white]2.[/white] [red]Exit to Main Menu[/red]",
        ]
        available_choices = ["1", "2"]

        if total_pages > 1:
            menu_options.insert(1, f"[white]P.[/white] [yellow]Next Page ({current_page + 1}/{total_pages})[/yellow]")
            available_choices.insert(1, "P")
            menu_options.insert(1, f"[white]N.[/white] [yellow]Previous Page[/yellow]")
            available_choices.insert(1, "N")
        
        console.print()
        console.print(Panel.fit("\n".join(menu_options), title="Options", border_style="yellow"))
        
        # دریافت ورودی
        choice = input("Selection: ").upper()
        
        if choice == "2":
            break
        elif total_pages > 1 and choice == "P":
            current_page = (current_page + 1) % total_pages
        elif total_pages > 1 and choice == "N":
            current_page = (current_page - 1 + total_pages) % total_pages
        elif choice == "1":
            # رفرش (با ادامه حلقه)
            pass
        else:
            console.print("[red]Invalid selection. Please use the options provided.[/red]")

# --- منوی اصلی (Main Menu) ---
def main_menu():
    while True:
        header()
        
        menu_text = """
[bold white]1.[/bold white] [green]Install/Update Background Service[/green]  [dim](Run this first)[/dim]
[bold white]2.[/bold white] [cyan]Add New Port[/cyan]                       [dim](Set Limits)[/dim]
[bold white]3.[/bold white] [red]Delete/Reset Port[/red]                    [dim](Stop monitoring)[/dim]
[bold white]4.[/bold white] [bold yellow]Open Live Dashboard[/bold yellow]                  [dim](Check Status)[/dim]
[bold white]5.[/bold white] [white]Exit[/white]
        """
        console.print(Panel(menu_text, title="Main Menu", border_style="blue", subtitle="Select an option"))
        
        choice = input("Selection: ")
        
        if choice == "1":
            install_service_ui()
        elif choice == "2":
            add_port_ui()
        elif choice == "3":
            delete_port_ui()
        elif choice == "4":
            port_dashboard_ui()
        elif choice == "5":
            console.print("[yellow]Goodbye! Monitoring continues in background...[/yellow]")
            sys.exit()
        else:
            console.print("[red]Invalid selection. Please choose 1, 2, 3, 4, or 5.[/red]")

# --- نقطه شروع برنامه ---
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        run_daemon()
    else:
        try:
            main_menu()
        except KeyboardInterrupt:
            console.print("\n[yellow]Exiting...[/yellow]")
