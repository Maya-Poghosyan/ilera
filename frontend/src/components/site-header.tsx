"use client";

import Link from "next/link";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

const navLink =
  "relative text-sm text-muted-foreground transition-colors hover:text-foreground after:absolute after:-bottom-1 after:left-0 after:h-px after:w-full after:origin-left after:scale-x-0 after:bg-current after:transition-transform after:duration-300 hover:after:scale-x-100";

function DefaultNav() {
  const { user, loading } = useAuth();
  return (
    <nav className="flex items-center gap-7">
      <Link href="/about" className={navLink}>About</Link>
      {!loading && user ? (
        <Button render={<Link href="/dashboard" />}>Dashboard</Button>
      ) : (
        <>
          <Link href="/login" className={navLink}>Sign in</Link>
          <Button render={<Link href="/intake" />}>Get started</Button>
        </>
      )}
    </nav>
  );
}

/** Site-wide top bar. `actions` replaces the default nav; pass `null` for a logo-only bar. */
export function SiteHeader({ actions }: { actions?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-10 border-b border-border/60 bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
        <Logo size="lg" />
        {actions === undefined ? <DefaultNav /> : actions}
      </div>
    </header>
  );
}
