import Link from "next/link";

const nav = [
  { href: "/dashboard", label: "Care Calendar" },
  { href: "/dashboard/records", label: "Records & Renewal" },
  { href: "/dashboard/documents", label: "Documents" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-1">
      <aside className="w-60 shrink-0 border-r p-4">
        <Link href="/" className="mb-6 block text-lg font-bold">
          Ilera
        </Link>
        <nav className="space-y-1">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="block rounded-md px-3 py-2 text-sm hover:bg-muted"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1 p-8">{children}</div>
    </div>
  );
}
