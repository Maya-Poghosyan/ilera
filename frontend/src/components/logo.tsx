import Link from "next/link";
import { Leaf } from "lucide-react";

import { cn } from "@/lib/utils";

const sizes = {
  sm: { box: "size-7 rounded-md", icon: "size-4", text: "text-base" },
  md: { box: "size-8 rounded-lg", icon: "size-[18px]", text: "text-lg" },
  lg: { box: "size-10 rounded-xl", icon: "size-5", text: "text-2xl" },
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
      <span
        className={cn(
          "inline-flex shrink-0 items-center justify-center bg-primary text-primary-foreground shadow-xs",
          s.box,
        )}
        aria-hidden
      >
        <Leaf className={s.icon} />
      </span>
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
