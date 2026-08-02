---
route: /privacy
title: Privacy Policy
description: How Tiddly collects, uses, and protects your personal information — what data we store, where and how it's secured, third-party services, and your GDPR/CCPA rights.
---

# Privacy Policy

## Introduction

Tiddly ("we", "our", or "us") is operated by Shane Kercheval as an individual. This Privacy Policy explains how we collect, use, and protect your personal information when you use tiddly.me (the "Service").

By using the Service, you agree to the collection and use of information in accordance with this policy.

## Information We Collect

### Information You Provide

- **Account Information:** When you sign up via Clerk, we collect your email address and Clerk user ID
- **Bookmarks:** URLs, titles, descriptions, and page content you save
- **Notes:** Titles, descriptions, and the note content you write
- **Prompt Templates:** Names, descriptions, template bodies, and the arguments you define on them
- **Tags and Lists:** Organization metadata you create
- **Personal Access Tokens:** API tokens you generate (stored hashed)

### Automatically Collected Information

- **Usage Data:** When your items (bookmarks, notes, and prompt templates) were created, updated, and last accessed
- **Authentication Data:** Login timestamps and session information (via Clerk)
- **Server Logs:** IP addresses, browser type, and access times (Railway infrastructure)

### Third-Party Content

When you save a bookmark, we automatically fetch and store:

- Page title and meta description
- Page content (up to 500KB) for search functionality
- This data is fetched from the URL you provide

## How We Use Your Information

We use your data to:

- **Provide the Service:** Store, organize, and search your bookmarks, notes, and prompt templates
- **Enable Features:** Full-text search, tagging, and custom lists
- **Authentication:** Verify your identity via Clerk
- **API Access:** Allow programmatic access via Personal Access Tokens
- **AI Suggestions:** Generate suggestions in response to actions you take in the app — for some features, opening the relevant control is the action that triggers a request; see the "AI Features" section below
- **Improve the Service:** Understand usage patterns (aggregated, not individual)

## Data Storage and Security

### Where Your Data is Stored

- **Database:** PostgreSQL hosted on Railway (US servers)
- **Encryption at Rest:** Data is encrypted at storage level by Railway
- **Data Isolation:** Multi-tenant architecture ensures your data is separate from other users

### Important Security Notes

- We do **not** use end-to-end encryption because it would prevent search functionality
- The database administrator (Shane Kercheval) has technical ability to access data through database queries
- We will never access your data except when legally required or with your explicit permission
- See our [FAQ](/docs/faq) for more details on data security

## Third-Party Services

We use the following third-party services that may access your data:

### Clerk (Authentication)

- **Purpose:** User authentication and identity management
- **Data Shared:** Email address, login timestamps, and the date you accepted these policies
- **Privacy Policy:** [clerk.com/legal/privacy](https://clerk.com/legal/privacy)

### Railway (Hosting)

- **Purpose:** Database and application hosting
- **Data Shared:** All application data (bookmarks, notes, prompt templates, account info)
- **Privacy Policy:** [railway.app/legal/privacy](https://railway.app/legal/privacy)

### AI Providers

We use these providers to generate the AI suggestions described in the "AI Features" section below. Content is sent to them only in response to an action you take in the app — for some features, opening the relevant control is the action that sends it. The "AI Features" section describes exactly what triggers a request and what is sent.

#### OpenAI

- **Purpose:** AI suggestions (the default provider for suggestions we run on your behalf)
- **Data Shared:** The item you are working on and related content — see "AI Features" below
- **Privacy Policy:** [openai.com/policies/privacy-policy](https://openai.com/policies/privacy-policy)

#### Anthropic

- **Purpose:** AI suggestions
- **Data Shared:** The item you are working on and related content — see "AI Features" below
- **Privacy Policy:** [anthropic.com/legal/privacy](https://www.anthropic.com/legal/privacy)

#### Google (Gemini)

- **Purpose:** AI suggestions
- **Data Shared:** The item you are working on and related content — see "AI Features" below
- **Privacy Policy:** [policies.google.com/privacy](https://policies.google.com/privacy)

## AI Features

Tiddly offers AI-powered suggestions: suggested tags, suggested metadata (titles, descriptions, and — for prompt templates — names), suggested relationships between your items, and suggested arguments for your prompt templates.

**These features run in the foreground, in response to something you do.** Nothing is sent to an AI provider in the background, on a schedule, or when you simply save or view an item.

Some of them run as soon as you open the relevant control rather than waiting for a separate confirmation. Opening the tag control on an item, or opening the linked-content control, sends that item for suggestions right away. Others run only when you invoke them directly. If your account has AI features available, no further opt-in step stands between opening one of those controls and the request being made.

**What we send.** When a suggestion is requested, we send the item being worked on — its title, URL, description, content, and, for prompt templates, its existing name — along with data related to that request:

- For **tag suggestions**, your existing tag names and how often you use each one, so suggestions reuse your vocabulary instead of inventing new tags
- For **relationship suggestions**, the titles, descriptions, internal item identifiers, and a short content excerpt from the other items being considered as matches
- For **prompt-argument suggestions**, the body of the prompt template and its existing arguments

We do not send your email address, your account identifiers, or your Personal Access Tokens. Data is sent for the duration of the request; we do not store copies of what we send.

**Bring your own key.** If you supply your own AI provider API key, it is sent with your request and used for that request only. **We never store your key** — it is not written to our database, and it is not retained after the request completes.

**About the providers.** Each provider handles data it receives under its own privacy policy, linked above. Their practices — including whether and for how long they retain API data — are set by them and can change, so we link their current policies rather than making commitments on their behalf. The AI features are optional — the rest of the Service works without them.

## Your Rights (GDPR)

If you are in the European Union, you have the right to:

- **Access:** Request a copy of your data
- **Rectification:** Correct inaccurate data
- **Erasure:** Delete your account and all data
- **Portability:** Export your data in a machine-readable format
- **Object:** Object to processing of your data
- **Withdraw Consent:** Stop using the service and delete your account

To exercise these rights, contact us at [shane_kercheval@hotmail.com](mailto:shane_kercheval@hotmail.com) or delete your account in Settings.

## Your Rights (CCPA - California Users)

If you are a California resident, you have the right to:

- **Know:** What personal information we collect and how we use it
- **Delete:** Request deletion of your personal information
- **Opt-Out:** We don't sell personal information, so no opt-out is needed
- **Non-Discrimination:** We won't discriminate against you for exercising your rights

## Data Retention

- **Active Data:** We keep your bookmarks, notes, prompt templates, and account data as long as your account is active
- **Deleted Items:** Items in trash are kept until you permanently delete them (future: auto-delete after 30 days)
- **Account Deletion:** When you delete your account, all data is permanently deleted within 30 days

## Children's Privacy

The Service is not intended for children under 13. We do not knowingly collect data from children under 13. If we discover we have collected data from a child under 13, we will delete it immediately.

## International Data Transfers

If you are located outside the United States, your data will be transferred to and stored on servers in the United States. By using the Service, you consent to this transfer.

## Changes to This Policy

We may update this Privacy Policy from time to time. We will notify you of changes by:

- Updating the "Last Updated" date
- Posting a notice on the Service
- Sending an email to your registered address (for material changes)

Continued use of the Service after changes constitutes acceptance of the updated policy.

## Self-Hosting

If you self-host Tiddly, this Privacy Policy does not apply. You are responsible for your own data handling practices.

## Contact Us

If you have questions about this Privacy Policy, contact:

- **Name:** Shane Kercheval
- **Email:** [shane_kercheval@hotmail.com](mailto:shane_kercheval@hotmail.com)
- **GitHub:** [github.com/shanekercheval/bookmarks](https://github.com/shanekercheval/bookmarks)

## Data Controller (GDPR)

For GDPR purposes, the data controller is:

- **Entity:** Shane Kercheval (Individual)
- **Operating:** Tiddly
- **Location:** West Richland, WA, USA
- **Email:** [shane_kercheval@hotmail.com](mailto:shane_kercheval@hotmail.com)

---

*By using Tiddly, you acknowledge that you have read and understood this Privacy Policy and agree to its terms.*
