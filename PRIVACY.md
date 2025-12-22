# Privacy Policy

**Last Updated: December 20, 2025**

## Introduction

Tiddly ("we", "our", or "us") is operated by Shane Kercheval as an individual. This Privacy Policy explains how we collect, use, and protect your personal information when you use tiddly.me (the "Service").

By using the Service, you agree to the collection and use of information in accordance with this policy.

## Information We Collect

### Information You Provide
- **Account Information**: When you sign up via Auth0, we collect your email address and Auth0 user ID
- **Bookmark Data**: URLs, titles, descriptions, and page content you save
- **Tags and Lists**: Organization metadata you create
- **Personal Access Tokens**: API tokens you generate (stored hashed)

### Automatically Collected Information
- **Usage Data**: When bookmarks were created, updated, and last accessed
- **Authentication Data**: Login timestamps and session information (via Auth0)
- **Server Logs**: IP addresses, browser type, and access times (Railway infrastructure)

### Third-Party Content
When you save a bookmark, we automatically fetch and store:
- Page title and meta description
- Page content (up to 500KB) for search functionality
- This data is fetched from the URL you provide

## How We Use Your Information

We use your data to:
- **Provide the Service**: Store, organize, and search your bookmarks
- **Enable Features**: Full-text search, tagging, and custom lists
- **Authentication**: Verify your identity via Auth0
- **API Access**: Allow programmatic access via Personal Access Tokens
- **Improve the Service**: Understand usage patterns (aggregated, not individual)

## Data Storage and Security

### Where Your Data is Stored
- **Database**: PostgreSQL hosted on Railway (US servers)
- **Encryption at Rest**: Data is encrypted at storage level by Railway
- **Data Isolation**: Multi-tenant architecture ensures your data is separate from other users

### Important Security Notes
- We do **not** use end-to-end encryption because it would prevent search functionality
- The database administrator (Shane Kercheval) has technical ability to access data through database queries
- We will never access your data except when legally required or with your explicit permission
- See our FAQ for more details on data security

## Third-Party Services

We use the following third-party services that may access your data:

### Auth0 (Authentication)
- **Purpose**: User authentication and identity management
- **Data Shared**: Email address, login timestamps
- **Privacy Policy**: https://auth0.com/privacy

### Railway (Hosting)
- **Purpose**: Database and application hosting
- **Data Shared**: All application data (bookmarks, account info)
- **Privacy Policy**: https://railway.app/legal/privacy

### Future AI Services (Not Yet Implemented)
We plan to offer **optional** AI-powered features (summarization, auto-suggestions) that may send your content to:
- OpenAI (ChatGPT API)
- Anthropic (Claude API)

**These features:**
- Are not yet available
- Will be completely opt-in when available
- Will be clearly marked in settings
- You can disable them at any time

## Your Rights (GDPR)

If you are in the European Union, you have the right to:

- **Access**: Request a copy of your data
- **Rectification**: Correct inaccurate data
- **Erasure**: Delete your account and all data
- **Portability**: Export your data in a machine-readable format
- **Object**: Object to processing of your data
- **Withdraw Consent**: Stop using the service and delete your account

To exercise these rights, contact us at shane_kercheval@hotmail.com or delete your account in Settings.

## Your Rights (CCPA - California Users)

If you are a California resident, you have the right to:

- **Know**: What personal information we collect and how we use it
- **Delete**: Request deletion of your personal information
- **Opt-Out**: We don't sell personal information, so no opt-out is needed
- **Non-Discrimination**: We won't discriminate against you for exercising your rights

## Data Retention

- **Active Data**: We keep your bookmarks and account data as long as your account is active
- **Deleted Bookmarks**: Items in trash are kept until you permanently delete them (future: auto-delete after 30 days)
- **Account Deletion**: When you delete your account, all data is permanently deleted within 30 days

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

**Shane Kercheval**
Email: shane_kercheval@hotmail.com
GitHub: https://github.com/shanekercheval/bookmarks

## Data Controller

For GDPR purposes, the data controller is:

**Shane Kercheval** (Individual)
Operating: Tiddly
Location: West Richland, WA, USA
Email: shane_kercheval@hotmail.com

---

**Consent**: By using Tiddly, you acknowledge that you have read and understood this Privacy Policy and agree to its terms.
