# Google Cloud Console — what each piece is

A reference note. Written for myself, in plain language. Not a tutorial.

---

## The hierarchy

```
Project ───── one ─────►  Branding (one consent screen)
   │
   └─── one or more ────►  Clients
```

One project. One Branding. One or more Clients.

For a personal script, it's one of each. The system allows more, doesn't require more.

---

## What each piece actually is

### Project

A folder in Google's system. Everything I do for one app — APIs, credentials,
billing — lives inside one project. By default, projects can't talk to any
Google service. I have to enable each API I want.

### Enabling an API (e.g. Gmail API)

A switch per service. "Yes, this project is allowed to talk to Gmail."
Without flipping it, no code in this project can call Gmail at all.

### Branding (the OAuth consent screen)

The page a user sees when an app asks for access to their Google account.
The screen that says: *"PortfolioDigest wants to read your Gmail. Allow / Deny."*

Google forces me to define what that screen looks like before any app of mine
can show it. The "app name," support email, etc. — that's all what the user
sees on the consent screen.

In my case, the "user" is just me authorizing my own script. But Google
requires the screen to exist anyway.

### Client

The identity of my script.

When my Python code goes to Google and says "hi, I'm an app, I'd like
permission to read this user's Gmail," Google asks "which app are you?"
The **Client ID** and **client secret** are how the script answers.

The `credentials.json` file I download contains those two values. It's my
script's ID badge.

---

## Why multiple Clients per project?

Because one "app" might exist in several forms. Imagine I build "Portfolio
Digest" and make:

- A desktop Python script
- An iPhone app
- A website version

These are all the *same app* to the user — same consent screen, same brand.
That consent screen is the **Branding**. Defined once. Shared by all
versions.

But Google needs to identify each version *separately*, because they run
on different platforms with different security models:

- Desktop app → credentials on the laptop
- iOS app → iOS keychain
- Web app → server

So each platform gets its **own Client**.

> **Branding = what the user sees.
> Client = how the code identifies itself.**
> Same brand, different doors into it.

For my Portfolio Digest project: one Python script, one Client. Done.

---

## What `credentials.json` and `token.json` are for

When my Python script runs, this happens:

1. Script: "Hi Google, I'm the app identified by this `credentials.json`."
   → Google checks it's a real app I registered.
2. Script: "I want to access this user's Gmail. Show them the consent screen."
   → Google opens a browser, shows the Branding screen, I click Allow.
3. Google hands the script a **token** — a temporary key that proves the
   user said yes.
4. Script saves that token to `token.json` so steps 1–3 don't have to
   happen every time.
5. From then on, the script uses the saved token to actually read Gmail.

| File | What it is |
|---|---|
| `credentials.json` | Who the app is. Downloaded from Cloud Console. Stays the same. |
| `token.json` | Proof the user gave the app permission. Created on first run. Auto-refreshes. |

I need both. **Never commit either to git.**

---

## The renaming confusion

Google renamed things recently. Old tutorials still use the old names:

| Old name | New name |
|---|---|
| OAuth consent screen | Branding |
| Credentials | Clients |

Same things. Just different words.

Also: in OAuth, "Client" means *the thing requesting access on the user's
behalf* — i.e. my script. Not a person. This is why the name reads sideways
the first time you see it.

---

## What I had to do, in order

1. Create a Project in Google Cloud Console
2. Enable the Gmail API in that project
3. Configure Branding (consent screen) — app name, support email
4. Add myself as a Test User (otherwise the consent flow rejects me)
5. Create a Client → Desktop app type
6. Download the JSON, rename to `credentials.json`, put in project folder
7. Add `credentials.json` and `token.json` to `.gitignore`

The rest happens on my computer, not in the Cloud Console.
