import { Logo } from "@/components/logo";
import { DashboardNav } from "@/components/dashboard-nav";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-1">
      <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar p-4">
        <div className="mb-6 px-1">
          <Logo />
        </div>
        <DashboardNav />
      </aside>
      <div className="flex-1 bg-muted/40 p-8">{children}</div>
    </div>
  );
}
