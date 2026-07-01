"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface Props {
  suggestions: string[];
  value: string[];
  onChange: (tags: string[]) => void;
}

export function TagInput({ suggestions, value, onChange }: Props) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query.trim()
    ? suggestions.filter(
        (s) =>
          s.toLowerCase().includes(query.toLowerCase()) &&
          !value.includes(s),
      )
    : suggestions.filter((s) => !value.includes(s));

  function addTag(tag: string) {
    const trimmed = tag.trim();
    if (!trimmed || value.includes(trimmed)) return;
    onChange([...value, trimmed]);
    setQuery("");
  }

  function removeTag(tag: string) {
    onChange(value.filter((t) => t !== tag));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (query.trim()) addTag(query);
    }
    if (e.key === "Backspace" && !query && value.length > 0) {
      removeTag(value[value.length - 1]);
    }
  }

  const showDropdown = focused && filtered.length > 0;

  return (
    <div className="relative space-y-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs"
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="ml-0.5 text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${tag}`}
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 200)}
          onKeyDown={handleKeyDown}
          placeholder="Type to search or add..."
          className={cn(
            "h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none",
            "placeholder:text-muted-foreground",
            "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          )}
        />

        {showDropdown && (
          <div className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-lg border bg-background shadow-md">
            {filtered.map((s) => (
              <button
                key={s}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addTag(s)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-muted"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
