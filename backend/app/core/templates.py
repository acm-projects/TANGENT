INVITATION_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f6f9fc; padding: 40px; margin: 0;">
    <div style="max-width: 560px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 32px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">
        <h2 style="color: #111827; margin-top: 0;">Join your team on the Platform</h2>
        <p style="color: #4b5563; font-size: 16px; line-height: 24px;">
            <strong>{{ inviter_name }}</strong> has invited you to join <strong>{{ project_name }}</strong>
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{{ invite_url }}" style="background-color: #238636; color: #ffffff; padding: 12px 24px; font-weight: 600; text-decoration: none; border-radius: 6px; display: inline-block;">
                Accept Invitation
            </a>
        </div>
        <p style="color: #9ca3af; font-size: 14px; line-height: 20px;">
            This invitation link will expire in 7 days.
        </p>
    </div>
</body>
</html>
"""