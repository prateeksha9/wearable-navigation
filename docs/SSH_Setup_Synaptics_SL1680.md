# SSH & VS Code Remote Setup for Synaptics SL1680 Board

This guide explains how to configure secure SSH access between your **Mac laptop** and the **Synaptics Astra (SL1680)** board running Poky/Yocto Linux, and how to use **VS Code Remote-SSH** for development.

---

## ⚙️ System Overview

| Device | OS / Toolchain | Purpose |
|---------|----------------|----------|
| **Laptop (Host)** | macOS with VS Code | Development machine |
| **Board (Target)** | Synaptics Astra SL1680 (Poky/Yocto Linux) | Embedded runtime environment |

---

## 🪜 STEP 1 — Verify Network Connectivity

### **On Board**
Check the IP address:
```bash
ifconfig wlan0
```
Example output:
```
inet addr:10.43.51.132  Bcast:10.43.51.255  Mask:255.255.255.0
```
→ **Board IP:** `10.43.51.132`

### **On Laptop**
Verify you’re on the same subnet:
```bash
ifconfig | grep inet
```
Example:
```
inet 10.43.51.226
```
✅ Both start with `10.43.51` → same network.

### **Test Connection**
From your laptop:
```bash
ping 10.43.51.132
```
You should see consistent replies (`64 bytes from …`).

---

## 🪜 STEP 2 — Ensure SSH Server Is Running on the Board

### **Check for Dropbear**
Run on the board:
```bash
ps | grep dropbear
```
If you see a process like `/usr/sbin/dropbear -R`, SSH is already running.  
You can confirm with:
```bash
netstat -tln | grep 22
```
Expected output:
```
tcp        0      0 :::22                   :::*                    LISTEN
```

If you don’t see that, start Dropbear manually:
```bash
/usr/sbin/dropbear
```

---

## 🪜 STEP 3 — Configure SSH Key Authentication

### **On Laptop**
Generate a key pair (if not already present):
```bash
ls ~/.ssh
```
If you see `id_ed25519` and `id_ed25519.pub`, skip this step.  
Otherwise:
```bash
ssh-keygen -t ed25519
```
Press Enter for all defaults.

View your public key:
```bash
cat ~/.ssh/id_ed25519.pub
```

Example:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPCAVNKLfNENm/GqjzysNBReZm5kGckiv285m/auNNCV GitLab Key Pair
```

---

### **On Board**
Create SSH config folder:
```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
```

Add your laptop’s public key:
```bash
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPCAVNKLfNENm/GqjzysNBReZm5kGckiv285m/auNNCV GitLab Key Pair' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Verify:
```bash
cat /root/.ssh/authorized_keys
```

---

### **Test SSH Connection**
From the laptop:
```bash
ssh root@10.43.51.132
```
✅ You should connect **without a password** and see:
```
root@sl1680:~#
```

---

## 🪜 STEP 4 — Add SSH Configuration (on Laptop)

Edit your SSH config file:
```bash
code ~/.ssh/config
```

Add:
```bash
Host synaptics-sl1680
    HostName 10.43.51.132
    User root
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
```

Save and test:
```bash
ssh synaptics-sl1680
```

---

## 🪜 STEP 5 — Setup VS Code Remote Connection

### **1️⃣ Install Required Extensions**
In VS Code:
- Install **Remote - SSH** (by Microsoft)
- Verify it’s enabled globally

### **2️⃣ Add Shell Command (to use `code` from terminal)**
In VS Code Command Palette (`⇧⌘P`):
```
Shell Command: Install 'code' command in PATH
```
Then restart the terminal and confirm:
```bash
code --version
```

### **3️⃣ Connect via VS Code**
Press `⇧⌘P` →  
```
Remote-SSH: Connect to Host → synaptics-sl1680
```

If you get `XHR failed` — continue below.

---

## 🪜 STEP 6 — Fix “XHR failed” (Manual VS Code Server Install)

Because SL1680’s Yocto image can’t download the server automatically, install it manually:

### **On Laptop**
Download the VS Code server (ARM64 build):
```bash
curl -L -o vscode-server.tar.gz https://update.code.visualstudio.com/commit:e7e037083ff4455cf320e344325dacb480062c3c/server-linux-arm64/stable
```

Copy it to the board:
```bash
scp vscode-server.tar.gz root@10.43.51.132:/home/root/
```

### **On Board**
Extract it:
```bash
mkdir -p /home/root/.vscode-server/bin/e7e037083ff4455cf320e344325dacb480062c3c
cd /home/root/.vscode-server/bin/e7e037083ff4455cf320e344325dacb480062c3c
tar -xzf /home/root/vscode-server.tar.gz --strip-components 1
chmod +x bin/code-server
```

### **On Laptop**
Reconnect VS Code:
```bash
code --remote ssh-remote+synaptics-sl1680 /home/root
```

✅ VS Code will detect the server and open your remote session.

---

## 🧹 Cleanup (optional)
Once connected, you can delete the tarball:
```bash
rm /home/root/vscode-server.tar.gz
```

---

## ✅ Final Verification

| Check | Command | Expected Output |
|-------|----------|----------------|
| SSH works | `ssh root@10.43.51.132` | `root@sl1680:~#` |
| Dropbear running | `ps | grep dropbear` | `/usr/sbin/dropbear -R` |
| Port 22 open | `netstat -tln | grep 22` | `:::22 LISTEN` |
| VS Code remote session | `code --remote ssh-remote+synaptics-sl1680 /home/root` | VS Code window connected to board |

---

## 📁 Folder Summary

| Location | Description |
|-----------|--------------|
| `/root/.ssh/authorized_keys` | Stores your Mac’s SSH key |
| `/home/root/.vscode-server/` | VS Code server files |
| `~/.ssh/config` (Mac) | Host alias for the board |

---
