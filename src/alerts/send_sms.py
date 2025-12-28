# send_emergency_sms.py
from twilio.rest import Client

def send_emergency_sms():
    ACCOUNT_SID = "ACbe4a53adb19f262742f903c25df60710"
    AUTH_TOKEN = "fc2f5ff8349a5f9d50b33775ff5dc1f5"
    TWILIO_NUMBER = "+18555768454"  # The number Twilio gave you

    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    # Verified numbers only
    contacts = ["+19495247009"]

    for number in contacts:
        message = client.messages.create(
            body="🚨 Emergency detected! Please check immediately.",
            from_=TWILIO_NUMBER,
            to=number
        )
        print(f"✅ Message sent to {number}: SID {message.sid}")

if __name__ == "__main__":
    send_emergency_sms()
