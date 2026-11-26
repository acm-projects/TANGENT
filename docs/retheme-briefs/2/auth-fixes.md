# 2 · Sign in with Google, properly

**Files you own:** `frontend/src/ui/features/auth/**`.

The sign-in button is the app's own primary button. Google's guidelines ask for Google's sign-in button
look. Make "Continue with Google" follow Google's branding guidelines for a custom button: the
multicolour "G" logo as an inline SVG (Google's official four-colour mark, unaltered, on a white or
light square), the label "Continue with Google" in the content face, a light surface with a hairline
border (Google's "light" theme) that still sits naturally on the torn paper card, full width of the card,
44px+ tall, visible focus ring, hover and pressed states. It stays a `<button>`/link with the same
handler and accessible name. The Google colours are allowed only inside the logo (an exception to the
token rule: write them in the SVG, not as tokens). Everything around it stays in the theme.

Also: the sign-in card's case badge shows "01" as a placeholder number. Drop the number on these screens
(the badge reads `CASE FILE` and the name) rather than show a fake one.
