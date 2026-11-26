import { ExternalLink } from "lucide-react";
import type { DocumentGuide } from "@/features/applications/document-guide";

function Bullets({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="font-medium text-foreground">{label}</p>
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

/** What a document is, where to find it, what it fills in, and an official example. */
export function DocumentGuideDetails({ guide }: { guide: DocumentGuide }) {
  return (
    <div className="space-y-2 text-sm text-muted-foreground">
      <Bullets label="What it is" items={guide.what} />
      <Bullets label="Where to find it" items={guide.where} />
      {guide.fills && <Bullets label="Fills in" items={[guide.fills]} />}
      {guide.example && (
        <a href={guide.example.url} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-primary underline underline-offset-2">
          See an example: {guide.example.label}
          <ExternalLink aria-hidden="true" className="size-3.5" />
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      )}
    </div>
  );
}
