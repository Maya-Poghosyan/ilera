import Link from "next/link";

import { Logo } from "@/components/logo";

const columns = [
  {
    heading: "Product",
    links: [
      { href: "/login", label: "Sign in" },
      { href: "/dashboard", label: "Dashboard" },
    ],
  },
  {
    heading: "More info",
    links: [
      { href: "/about", label: "About" },
      { href: "/privacy", label: "Privacy" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="bg-muted">
      <div className="mx-auto grid w-full max-w-5xl gap-10 px-6 pt-14 pb-10 sm:grid-cols-[auto_auto_1fr] sm:gap-16">
        {columns.map((col) => (
          <div key={col.heading} className="space-y-3">
            <p className="text-xs tracking-wide text-muted-foreground uppercase">{col.heading}</p>
            <ul className="space-y-2 text-sm">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="transition-colors hover:text-primary">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="sm:justify-self-end">
          <Logo size="lg" />
        </div>
      </div>
      <div className="mx-auto w-full max-w-5xl px-6">
        <p className="border-t border-border py-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Ilera
        </p>
      </div>
    </footer>
  );
}
