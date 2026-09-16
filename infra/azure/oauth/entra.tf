# Mailbox OAuth Entra application — MANAGED OUTSIDE TERRAFORM.
#
# The Entra application (`ilera-microsoft-mailbox`) and its client secret are deliberately
# NOT managed by this module. Managing a directory object from a CI service principal would
# require granting that principal standing Microsoft Graph app-management permissions
# (Application.ReadWrite.OwnedBy) with admin consent — a directory-level privilege we don't
# want the deploy identity to hold. Terraform here manages Azure *resources*; a human admin
# manages the *directory object*.
#
# Terraform only REFERENCES the app via var.mailbox_client_id (the existing client ID).
#
# The app must exist with:
#   - sign-in audience: AzureADMyOrg (single tenant)
#   - web redirect URI: var.redirect_uri (…/api/email/microsoft/callback)
#   - delegated Microsoft Graph scopes: Mail.Read, openid, profile, offline_access
#
# The client secret VALUE must be written into this module's Key Vault as the secret named
# var.client_secret_name, out-of-band (portal or an admin-run script). See README →
# "Entra app (out of band)". Terraform reads that secret name into the API config but never
# creates or rotates the credential.
#
# Current app (for reference): ilera-microsoft-mailbox
#   client id : c3b57022-1fcd-4434-a04a-b9ce41e54987   (= var.mailbox_client_id default)
