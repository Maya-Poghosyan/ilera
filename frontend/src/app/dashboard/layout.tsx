"use client";

import { Logo } from "@/components/logo";
import { DashboardNav } from "@/components/dashboard-nav";
import { RequireAuth } from "@/components/require-auth";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <DashboardShell>{children}</DashboardShell>
    </RequireAuth>
  );
}

function DashboardShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-full flex-1">
      <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar p-4">
        <div className="mb-6 px-1">
          <Logo />
        </div>
        <DashboardNav />
        <div className="mt-auto border-t border-sidebar-border pt-4">
          <div className="px-1 text-xs text-muted-foreground truncate">
            {user?.name}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 w-full justify-start gap-2 text-muted-foreground"
            onClick={logout}
          >
            <LogOut className="size-3.5" />
            Sign out
          </Button>
        </div>
      </aside>
      <div className="flex-1 bg-muted/40 p-8">{children}</div>
    </div>
  );
}
