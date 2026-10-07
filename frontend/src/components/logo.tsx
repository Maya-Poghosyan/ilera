import Link from "next/link";

import { cn } from "@/lib/utils";

const sizes = {
  sm: { text: "text-base" },
  md: { text: "text-lg" },
  lg: { text: "text-2xl" },
} as const;

type LogoProps = {
  className?: string;
  href?: string | null;
  size?: keyof typeof sizes;
  showWordmark?: boolean;
};

export function Logo({
  className,
  href = "/",
  size = "md",
  showWordmark = true,
}: LogoProps) {
  const s = sizes[size];
  const content = (
    <span className={cn("inline-flex items-center gap-2", className)}>
      {showWordmark && (
        <span className={cn("ilera-wordmark tracking-tight", s.text)}>Ilera</span>
      )}
    </span>
  );

  if (href) {
    return (
      <Link href={href} aria-label="Ilera home" className="inline-flex">
        {content}
      </Link>
    );
  }
  return content;
}
