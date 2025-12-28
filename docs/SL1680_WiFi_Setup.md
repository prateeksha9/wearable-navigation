# Wi-Fi Setup Guide for Synaptics SL1680 Board

This guide explains how to connect your Synaptics Astra SL1680 board to a Wi-Fi network (e.g., phone hotspot or router).

---

## 1️⃣ Check the Wi-Fi Interface

List available network interfaces:

```bash
ip link show
```

Look for `wlan0` (your Wi-Fi interface). If it's down, bring it up:

```bash
sudo ip link set wlan0 up
```

If your interface has a different name (e.g., `mlan0`, `wlp1s0`), use that instead of `wlan0` in all commands below.

---

## 2️⃣ Remove Existing Wi-Fi Connections

If any old connections exist, stop them cleanly:

```bash
ps | grep wpa_supplicant
sudo kill <PID>   # replace <PID> with the process ID(s) shown
sudo rm -rf /var/run/wpa_supplicant
```

This ensures there are no conflicting `wpa_supplicant` sessions.

---

## 3️⃣ Create Wi-Fi Configuration File

Create or edit the configuration file (replace SSID and PASSWORD with your network details):

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

Paste this:

```bash
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=US

network={
    ssid="Your_SSID"
    psk="Your_PASSWORD"
    key_mgmt=WPA-PSK
}
```

Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).

---

## 4️⃣ Connect to Wi-Fi

Run the following command to connect:

```bash
sudo wpa_supplicant -D nl80211 -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf -B
```

Wait 5–10 seconds and check connection status:

```bash
iw wlan0 link
```

If you see output like this:

```
Connected to <BSSID> (on wlan0)
SSID: Your_SSID
```

✅ You are connected to Wi-Fi.

If it says **Not connected**, ensure your router/hotspot is using **2.4 GHz** and **WPA2-PSK** (not WPA3).

---

## 5️⃣ Get an IP Address

Request an IPv4 address from the router:

```bash
sudo udhcpc -i wlan0
```

If successful, you’ll see:

```
udhcpc: lease of 192.168.x.x obtained
```

If DHCP doesn’t respond, assign a static IP manually (use your network’s subnet):

```bash
sudo ip addr add 192.168.43.50/24 dev wlan0
sudo ip route add default via 192.168.43.1
```

---

## 6️⃣ Set DNS (to resolve domain names)

```bash
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

---

## 7️⃣ Test Connectivity

Check connectivity:

```bash
ping -c 3 8.8.8.8
ping -c 3 google.com
```

✅ If both work → your Wi-Fi and Internet are configured successfully.

---

## 8️⃣ Make It Persistent on Boot (Optional)

Create an autoconnect script:

```bash
sudo tee /etc/init.d/wifi_autoconnect.sh >/dev/null <<'EOF'
#!/bin/sh
ip link set wlan0 up
wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
udhcpc -i wlan0
echo "nameserver 8.8.8.8" > /etc/resolv.conf
EOF
sudo chmod +x /etc/init.d/wifi_autoconnect.sh
sudo update-rc.d wifi_autoconnect.sh defaults
```

This will automatically connect to Wi-Fi when the board boots.

---

## ✅ Summary

| Step | Command | Description |
|------|----------|-------------|
| 1 | `ip link show` | Check Wi-Fi interface |
| 2 | `sudo kill <PID>` | Stop old connections |
| 3 | Edit config file | Add SSID and password |
| 4 | `sudo wpa_supplicant ...` | Connect to network |
| 5 | `sudo udhcpc -i wlan0` | Get IP address |
| 6 | Edit `/etc/resolv.conf` | Add DNS server |
| 7 | `ping google.com` | Verify Internet |
| 8 | Create script | Auto-connect on boot |

---

**Tip:**  
Always make sure your hotspot is 2.4 GHz and uses WPA2 security. Some SL1680 Wi-Fi modules do not support WPA3 or 5 GHz networks.
