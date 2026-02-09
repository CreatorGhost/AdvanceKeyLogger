# Legacy Scripts

These scripts predate the modular architecture and are kept for historical reference only.
They are **not used** by the current codebase.

## Files

### createfile.py
Original screenshot capture implementation with:
- Mouse click triggered screenshots
- Timer-based email reporting
- Direct integration with `mailLogger.py`

**Superseded by**: 
- `capture/screenshot_capture.py` - Modern screenshot capture module
- `transport/email_transport.py` - Configurable email transport

### mailLogger.py
Original SMTP email utility with:
- Gmail-specific SMTP settings
- Credentials from environment or `credentials.json`
- Attachment support for screenshots

**Superseded by**:
- `transport/email_transport.py` - Configurable email transport with retry logic

## Using Modern Equivalents

To capture screenshots and send via email, configure `config/default_config.yaml`:

```yaml
capture:
  screenshot:
    enabled: true
    quality: 80
    format: png

transport:
  method: email
  email:
    smtp_server: smtp.gmail.com
    smtp_port: 465
    use_ssl: true
    sender: your-email@gmail.com
    password: your-app-password
    recipient: recipient@example.com
```

Then run with:
```bash
python main.py
```

## Why Archived?

These files were part of the original prototype. The modular architecture provides:
- Configuration-driven behavior
- Multiple transport options (email, HTTP, FTP, Telegram, etc.)
- Better error handling and retry logic
- Integration with the rule engine and pipeline
- Dashboard for monitoring
