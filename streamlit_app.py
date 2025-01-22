from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from email_validator import validate_email, EmailNotValidError
import dns.resolver
import smtplib
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import psutil
import pandas as pd

app = FastAPI()

# Data models
class EmailRequest(BaseModel):
    emails: list
    blacklist: list = []

class EmailResponse(BaseModel):
    email: str
    status: str
    message: str

# Function to validate emails (same as before)
def validate_email_address(email, blacklist, custom_sender="test@example.com"):
    """Enhanced email validation with DNS, SMTP, and blacklist checks."""
    try:
        validate_email(email)
    except EmailNotValidError as e:
        return email, "Invalid", f"Invalid syntax: {str(e)}"
    
    domain = email.split("@")[-1]
    if domain in blacklist:
        return email, "Blacklisted", "Domain is blacklisted."

    try:
        mx_records = dns.resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return email, "Invalid", "Domain does not exist."
    except dns.resolver.Timeout:
        return email, "Invalid", "DNS query timed out."
    except Exception as e:
        return email, "Invalid", f"DNS error: {str(e)}"

    try:
        mx_host = str(mx_records[0].exchange).rstrip(".")
        smtp = smtplib.SMTP(mx_host, timeout=10)
        smtp.helo()
        smtp.mail(custom_sender)
        code, _ = smtp.rcpt(email)
        smtp.quit()
        if code == 250:
            return email, "Valid", "Email exists and is reachable."
        elif code == 550:
            return email, "Invalid", "Mailbox does not exist."
        elif code == 451:
            return email, "Greylisted", "Temporary error, try again later."
        else:
            return email, "Invalid", f"SMTP response code {code}."
    except smtplib.SMTPConnectError:
        return email, "Invalid", "SMTP connection failed."
    except Exception as e:
        return email, "Invalid", f"SMTP error: {str(e)}"

    return email, "Invalid", "Unknown error."

# Endpoint to validate emails
@app.post("/validate_emails")
async def validate_emails(request: EmailRequest):
    emails = request.emails
    blacklist = set(request.blacklist)

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(validate_email_address, email.strip(), blacklist) for email in emails if email.strip()]
        for future in as_completed(futures):
            results.append(future.result())

    response_data = []
    for email, status, message in results:
        response_data.append(EmailResponse(email=email, status=status, message=message))

    return response_data

# Endpoint to get system resource metrics
@app.get("/metrics")
async def get_metrics():
    cpu_usage = psutil.cpu_percent(interval=1)
    ram_usage = psutil.virtual_memory().percent
    net_io = psutil.net_io_counters()
    bandwidth_usage = (net_io.bytes_sent + net_io.bytes_recv) / (1024 ** 2)  # in MB

    return {
        "cpu_usage": cpu_usage,
        "ram_usage": ram_usage,
        "bandwidth_usage": bandwidth_usage
    }
