# Bot starten:
bash# Ins Bot-Verzeichnis wechseln
cd /root/leerstand-lg

### Virtual Environment aktivieren
source /root/venv-bot/bin/activate

### Bot starten
python3 bot.py


# Sonstiges
Läuft als Service
sudo systemctl stop leerstand-bot

#zum aktualiseren
cd /root/leerstand-lg

git status

git pull origin main

sudo systemctl restart leerstand-bot


### Wurde als systemd Service gespeichert (dauerhaft):

bashsudo nano /etc/systemd/system/leerstand-bot.service

