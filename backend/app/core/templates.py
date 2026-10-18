INVITATION_EMAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>{{ inviter_name }} shared a project with you on Tangent</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f2ef; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #2a2826;">
    <div style="display: none; max-height: 0; overflow: hidden; opacity: 0; color: #f3f2ef;">
        {{ inviter_name }} invited you to view {{ project_name }} on Tangent.
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f3f2ef" style="background-color: #f3f2ef;">
        <tr>
            <td height="6" bgcolor="#e5484a" style="background-color: #e5484a; height: 6px; font-size: 0; line-height: 0;">&nbsp;</td>
        </tr>
        <tr>
            <td align="center" style="padding: 48px 24px 56px 24px;">
                <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width: 100%; max-width: 560px;">
                    <tr>
                        <td style="padding-bottom: 40px;">
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td bgcolor="#2a2826" style="background-color: #2a2826; border-radius: 20px; padding: 40px 40px 44px 40px;">
                                        <img src="{{ logo_url }}" width="52" alt="Tangent" style="display: block; width: 52px; height: auto; border: 0; margin-bottom: 48px; color: #f3f2ef; font-size: 18px; font-weight: 700;">
                                        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td width="44" height="4" bgcolor="#e5484a" style="width: 44px; height: 4px; background-color: #e5484a; border-radius: 2px; font-size: 0; line-height: 0;">&nbsp;</td>
                                            </tr>
                                        </table>
                                        <div style="font-size: 34px; line-height: 40px; font-weight: 700; color: #f3f2ef; letter-spacing: -0.8px; padding-top: 20px;">
                                            A project was shared with you
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-size: 17px; line-height: 27px; color: #2a2826; padding-bottom: 8px;">
                            <strong>{{ inviter_name }}</strong> has invited you to view
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-bottom: 28px;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="border-bottom: 3px solid #e5484a; font-size: 17px; line-height: 26px; font-weight: 700; color: #2a2826;">
                                        {{ project_name }}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-size: 16px; line-height: 24px; color: #66625e; padding-bottom: 36px;">
                            This invite will expire after 7 days
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-bottom: 48px;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="center" bgcolor="#2a2826" style="background-color: #2a2826; border-radius: 10px;">
                                        <a href="{{ invite_url }}" style="display: inline-block; padding: 16px 34px; font-size: 17px; line-height: 20px; font-weight: 700; color: #f3f2ef; text-decoration: none; border-radius: 10px;">
                                            Open project
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="border-top: 1px solid #d9d7d2; padding-top: 24px; font-size: 13px; line-height: 20px; color: #66625e;">
                            Button not working? Paste this link into your browser:<br>
                            <a href="{{ invite_url }}" style="color: #2a2826; text-decoration: underline; word-break: break-all;">{{ invite_url }}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-top: 16px; font-size: 13px; line-height: 20px; color: #66625e;">
                            Not expecting this? You can safely ignore this email.
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""