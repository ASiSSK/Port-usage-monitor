#!/bin/bash

echo "======================================"
echo "      ASiS Port Usage Installer"
echo "======================================"

# --- 1) نصب Python3 و pip ---
echo "[+] Installing Python3 & pip..."
apt update -y
apt install -y python3 python3-pip iptables curl wget

# --- 2) ساخت دایرکتوری نصب ---
INSTALL_DIR="/opt/asis-port-usage"
mkdir -p $INSTALL_DIR

# --- 3) دانلود فایل اصلی ---
echo "[+] Downloading main script..."
wget -q --show-progress -O $INSTALL_DIR/port_usage.py "https://raw.githubusercontent.com/ASiSSK/Port-usage-monitor/main/port_usage.py"
chmod +x $INSTALL_DIR/port_usage.py

# --- 4) ساخت دستور global: asis-pu ---
echo "[+] Creating global command: asis-pu"
echo "#!/bin/bash
python3 $INSTALL_DIR/port_usage.py \"\$@\"
" > /usr/bin/asis-pu
chmod +x /usr/bin/asis-pu

# --- 5) نصب کتابخانه‌ها ---
echo "[+] Installing Python modules..."
python3 -m pip install --upgrade rich psutil

# --- 6) اصلاح مسیر دیتابیس در فایل اصلی ---
sed -i "s|DB_FILE = \"/root/port_usage.db\"|DB_FILE = \"$INSTALL_DIR/port_usage.db\"|g" $INSTALL_DIR/port_usage.py

echo "======================================"
echo "  ✅ Installation Completed!"
echo "  Run with:   asis-pu"
echo "======================================"
