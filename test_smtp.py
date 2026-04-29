import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

load_dotenv(override=True)

sender_email = os.getenv("SMTP_EMAIL")
sender_password = os.getenv("SMTP_PASSWORD")

# Try to remove spaces from password if any
if sender_password:
    sender_password = sender_password.replace(" ", "")

print(f"Testing SMTP with Email: {sender_email}")
print(f"Password length: {len(sender_password) if sender_password else 0}")

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.set_debuglevel(1)
    server.starttls()
    server.login(sender_email, sender_password)
    print("Login Successful!")
    
    msg = MIMEText("This is a test email to verify SMTP configuration.")
    msg['Subject'] = "SMTP Test"
    msg['From'] = sender_email
    msg['To'] = sender_email
    
    server.sendmail(sender_email, [sender_email], msg.as_string())
    print("Email sent successfully!")
    server.quit()
except Exception as e:
    print(f"SMTP Error: {e}")
