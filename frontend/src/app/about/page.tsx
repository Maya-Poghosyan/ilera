"use client";

import Image from "next/image";

import { Card, CardContent } from "@/components/ui/card";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

function LinkedInIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14zM7.12 20.45H3.55V9h3.57v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z" />
    </svg>
  );
}

type Member = {
  name: string;
  role: string;
  photo: string;
  bio: string;
  linkedin: string;
};

const TEAM: Member[] = [
  {
    name: "Maya Poghosyan",
    role: "Computer Science + Applied Math, Senior",
    photo: "/team/Maya Headshot.jpeg",
    bio: "A senior CS and Applied Math major and 2x AWS intern, passionate about using AI and cloud infrastructure for healthtech. She currently applies both at the Vanderbilt Cloud Innovation Lab, helping biomedical researchers and doctors conduct medical research.",
    linkedin: "https://www.linkedin.com/in/maya-poghosyan/",
  },
  {
    name: "Soham Saraf",
    role: "Medicine, Health & Society + English, Class of 2026",
    photo: "/team/Soham Saraf Headshot 7-2026.jpeg",
    bio: "A Medicine, Health & Society and English double major and Class of 2026 alum. He served as president of Vanderbilt Student Government and is currently completing a medical research postbacc at WashU.",
    linkedin: "https://www.linkedin.com/in/soham-saraf/",
  },
];

export default function AboutPage() {
  return (
    <main className="flex flex-1 flex-col">
      <SiteHeader />

      <section className="mx-auto flex max-w-3xl flex-col items-center gap-5 px-6 py-20 text-center">
        <h1 className="text-balance text-4xl sm:text-5xl">
          About Ilera
        </h1>
        <p className="max-w-2xl text-pretty text-lg text-muted-foreground">
          Ilera won the Harvard Health Systems Innovation Labs hackathon and was born of
          Vanderbilt students passionate about making caregiving easier.
        </p>
      </section>

      <section className="mx-auto grid w-full max-w-4xl grid-cols-1 gap-6 px-6 pb-24 sm:grid-cols-2">
        {TEAM.map((member) => (
          <Card key={member.name} className="gap-0 overflow-hidden">
            <div className="relative aspect-square w-full bg-muted">
              <Image
                src={member.photo}
                alt={`${member.name} headshot`}
                fill
                sizes="(max-width: 640px) 100vw, 50vw"
                className="object-cover"
              />
            </div>
            <CardContent className="space-y-3 py-5">
              <div className="space-y-1">
                <h2 className="text-xl">{member.name}</h2>
                <p className="text-sm font-medium text-muted-foreground">{member.role}</p>
              </div>
              <p className="text-sm text-muted-foreground">{member.bio}</p>
              <a
                href={member.linkedin}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
              >
                <LinkedInIcon className="size-4" />
                Connect on LinkedIn
              </a>
            </CardContent>
          </Card>
        ))}
      </section>

      <SiteFooter />
    </main>
  );
}
