import smtplib
from email.mime.text import MIMEText

# Change to your email login
EMAIL = "rajtani267@gmail.com"
PASSWORD = "wtwf foqm ebta mori"

# Your phone's SMS gateway address
TO = "8185187629@vtext.com"   # Replace with your carrier gateway

msg = MIMEText("Fall detected! Your Friend Needs some help!")
msg["From"] = EMAIL
msg["To"] = TO
msg["Subject"] = ""

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(EMAIL, PASSWORD)
    server.sendmail(EMAIL, TO, msg.as_string())

print("SMS sent through email gateway!")
