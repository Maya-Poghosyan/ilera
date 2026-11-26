// Time zones shown in the calendar's setting, and the label an event gets when its zone differs.

export const US_TIMEZONES: { zone: string; label: string }[] = [
  { zone: "America/Los_Angeles", label: "Pacific" },
  { zone: "America/Denver", label: "Mountain" },
  { zone: "America/Phoenix", label: "Arizona" },
  { zone: "America/Chicago", label: "Central" },
  { zone: "America/New_York", label: "Eastern" },
  { zone: "America/Anchorage", label: "Alaska" },
  { zone: "Pacific/Honolulu", label: "Hawaii" },
];

export function timezoneLabel(zone: string): string {
  return US_TIMEZONES.find((z) => z.zone === zone)?.label ?? zone.split("/").pop()!.replaceAll("_", " ");
}

/** The zone's current offset from GMT, e.g. "GMT-8" (or "GMT-7" during daylight saving time). */
export function gmtOffset(zone: string, at = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" })
      .formatToParts(at).find((p) => p.type === "timeZoneName")?.value ?? "";
  } catch {
    return "";
  }
}

/** The zone's short name on that date (e.g. "EST"), shown only when it isn't the calendar's own zone. */
export function zoneSuffix(eventZone: string | null | undefined, isoDate: string | null | undefined, calendarZone: string | null): string {
  if (!eventZone || !isoDate || eventZone === calendarZone) return "";
  try {
    const noon = new Date(`${isoDate}T12:00:00Z`);
    const name = new Intl.DateTimeFormat("en-US", { timeZone: eventZone, timeZoneName: "short" })
      .formatToParts(noon).find((p) => p.type === "timeZoneName")?.value;
    return name ? ` ${name}` : "";
  } catch {
    return "";
  }
}
