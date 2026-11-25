import type { Metadata } from "next";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Privacy Policy · Ilera" };

const UPDATED = "November 24, 2026";
const CONTACT_EMAIL = "maya@ileracare.app";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-3">
      <h2 className="text-2xl">{title}</h2>
      {children}
    </section>
  );
}

export default function PrivacyPage() {
  const contact = <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary underline">{CONTACT_EMAIL}</a>;
  return (
    <main className="flex flex-1 flex-col">
      <SiteHeader />
      <article className="mx-auto w-full max-w-3xl space-y-10 px-6 py-16 text-base leading-relaxed [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-2">
        <header className="space-y-3">
          <h1 className="text-4xl">Privacy Policy</h1>
          <p className="text-sm text-muted-foreground">Last updated {UPDATED}</p>
          <p>
            Ilera helps family caregivers find benefit programs, fill out applications and keep track of care.
            This policy explains what information Ilera collects, how it is used, and the choices you have.
          </p>
        </header>

        <Section id="summary" title="In short">
          <ul>
            <li>We use your information only to provide Ilera to you. We don&rsquo;t sell it or use it for advertising.</li>
            <li>Documents you upload during intake are read once to suggest answers and are not stored.</li>
            <li>If you connect an email account, Ilera has read-only access, keeps only the suggestions it finds, and
              never stores the emails themselves. You can disconnect at any time.</li>
            <li>Every suggestion Ilera makes is shown to you for review before it is used.</li>
          </ul>
        </Section>

        <Section id="collect" title="Information we collect">
          <ul>
            <li><strong>Account information:</strong>{" "}your name, email address, phone number and password. Passwords
              are stored only as a secure hash.</li>
            <li><strong>Intake answers:</strong>{" "}what you tell us about yourself, the person you care for and your
              household, such as relationships, ages, care needs, work, income, assets, taxes, insurance and
              benefits. While you fill out
              the intake, your answers are saved in your browser. When you submit, they are stored on our servers.</li>
            <li><strong>Records you add:</strong>{" "}care hours, journal entries, renewals, reminders and calendar
              events.</li>
            <li><strong>Documents you upload during intake</strong>{" "}(for example pay stubs, tax forms or benefit
              letters): read once to suggest answers, then discarded. We don&rsquo;t store the file or its text.
              Suggestions stay in your browser tab until you use or dismiss them.</li>
            <li><strong>Connected email accounts</strong>{" "}(optional): see the next section.</li>
          </ul>
        </Section>

        <Section id="email" title="Connected email (Gmail and Outlook)">
          <p>
            You can connect a Gmail or Microsoft Outlook account so Ilera can find care appointments, benefit deadlines
            and renewals in your email. This is optional, and you can disconnect at any time from your dashboard.
          </p>
          <ul>
            <li><strong>Access:</strong>{" "}read-only. Ilera can&rsquo;t send, change or delete your email.</li>
            <li><strong>What is read:</strong>{" "}new messages that arrive in your inbox after you connect. Ilera reads
              each message once, to look for appointments, deadlines, renewals and care tasks.</li>
            <li><strong>What is kept:</strong>{" "}the suggestions Ilera finds (for example &ldquo;IHSS reassessment
              visit, December 8&rdquo;), your email address, an identifier for each message that was read so it
              isn&rsquo;t read twice, and the access granted by Google or Microsoft, encrypted. The content of your
              emails is not stored.</li>
            <li><strong>Automated processing:</strong>{" "}the subject and text of each message are sent to Microsoft&rsquo;s
              Azure OpenAI Service to find suggestions. The sender&rsquo;s address is not sent. No person at Ilera reads
              your email.</li>
            <li><strong>Disconnecting</strong>{" "}deletes the stored access immediately. For Gmail, Ilera also asks Google
              to revoke its access. You can also remove Ilera&rsquo;s access yourself at any time in your Google
              Account (Security &rarr; Third-party apps &amp; services) or your Microsoft account.</li>
          </ul>
          <p>
            Ilera&rsquo;s use and transfer of information received from Google APIs will adhere to the{" "}
            <a href="https://developers.google.com/terms/api-services-user-data-policy" className="text-primary underline">
              Google API Services User Data Policy</a>, including the Limited Use requirements. In particular, Gmail
            data is used only to show you suggestions in Ilera; it is not used for advertising, not sold, not used to
            train AI models, and not read by people except with your permission, for security, or when the law
            requires it.
          </p>
        </Section>

        <Section id="ai" title="How Ilera uses AI">
          <p>
            Ilera uses Microsoft&rsquo;s Azure OpenAI Service to research which programs you may qualify for, to read
            documents you upload and to read connected email. Ilera doesn&rsquo;t ask the service to save these
            requests, and the results are always presented as suggestions for you to review. Your information is not
            used to train AI models. Under Microsoft&rsquo;s terms, Azure may keep requests for up to 30 days to detect
            abuse of the service.
          </p>
        </Section>

        <Section id="share" title="How information is shared">
          <ul>
            <li><strong>Service providers:</strong>{" "}Ilera runs on Microsoft Azure, which hosts our servers and database,
              provides the AI service, stores encryption keys and sends our account emails. Microsoft processes this
              information on our behalf.</li>
            <li><strong>Google and Microsoft</strong>{" "}receive requests for your mailbox only if you connect it.</li>
            <li><strong>When required by law,</strong>{" "}or to protect the safety of Ilera&rsquo;s users or services.</li>
          </ul>
          <p>We don&rsquo;t sell your information, share it for advertising, or use advertising or analytics trackers.</p>
        </Section>

        <Section id="security" title="Security">
          <p>
            Information is encrypted in transit. Email account access is encrypted with keys held in Azure Key Vault,
            and passwords are stored only as secure hashes. Access to production systems is limited to the people who
            run Ilera.
          </p>
        </Section>

        <Section id="retention" title="How long we keep information">
          <ul>
            <li>An intake that isn&rsquo;t linked to an account within 5 days is deleted.</li>
            <li>Account information, intake answers, records and suggestions are kept while you have an account.</li>
            <li>Email access is deleted as soon as you disconnect.</li>
            <li>To delete your account and its information, email {contact}. We will confirm when it is done.</li>
          </ul>
        </Section>

        <Section id="cookies" title="Cookies and browser storage">
          <p>
            Ilera uses one cookie to keep you signed in, and your browser&rsquo;s storage to save your intake progress
            on your device. We don&rsquo;t use advertising or analytics cookies.
          </p>
        </Section>

        <Section id="children" title="Children">
          <p>Ilera is for adults caring for someone. It is not intended for children under 13.</p>
        </Section>

        <Section id="changes" title="Changes and contact">
          <p>
            If we change this policy, we will update the date above, and tell you by email before any change in how
            connected email is used. Questions or requests: {contact}.
          </p>
        </Section>
      </article>
      <SiteFooter />
    </main>
  );
}
