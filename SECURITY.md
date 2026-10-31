# Security

This repository is a sanitized portfolio snapshot.

Do not commit:
- Telegram bot tokens
- Webull cookies, access tokens, device/session identifiers or request signatures
- Payment provider credentials
- Webhook secrets
- Production SQLite databases
- Customer/user records
- Raw network captures

Use environment variables and local ignored files for runtime credentials.

If any credential from the original project has previously been shared outside its intended environment, rotate/revoke it at the provider.
