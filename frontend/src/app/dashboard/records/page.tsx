"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createJournal,
  createRenewal,
  createTimekeeping,
  deleteJournalEntry,
  deleteRenewalItem,
  deleteTimekeepingEntry,
  listJournal,
  listRenewals,
  listTimekeeping,
  updateRenewalItem,
  updateTimekeeping,
  updateJournal,
  reviewIncident,
} from "@/lib/api";
import type { JournalEntry, RenewalItem, RenewalStatus, RenewalUrgency, ServiceType, TimekeepingEntry } from "@/lib/types";

const SERVICE_LABELS: Record<ServiceType, string> = {
  personal_care: "Personal Care",
  domestic: "Domestic",
  paramedical: "Paramedical",
  accompaniment: "Accompaniment",
};

const URGENCY_BADGE: Record<RenewalUrgency, { label: string; className: string }> = {
  overdue: { label: "Overdue", className: "bg-red-100 text-red-800 border border-red-300" },
  due_soon: { label: "Due soon", className: "bg-amber-100 text-amber-800 border border-amber-300" },
  upcoming: { label: "Upcoming", className: "bg-emerald-100 text-emerald-800 border border-emerald-300" },
  no_date: { label: "No date set", className: "bg-muted text-muted-foreground border" },
};

// Overdue first, then soonest-due, then upcoming, then undated.
const URGENCY_ORDER: Record<RenewalUrgency, number> = {
  overdue: 0,
  due_soon: 1,
  upcoming: 2,
  no_date: 3,
};

const RENEWAL_STATUSES: RenewalStatus[] = ["active", "pending", "overdue"];

const STATUS_LABELS: Record<RenewalStatus, string> = {
  active: "Active",
  pending: "Pending",
  overdue: "Overdue",
};

// How a flagged possible-fall entry reads to the caregiver, by review state.
const INCIDENT_BADGE: Record<JournalEntry["incident_status"], { label: string; className: string }> = {
  unreviewed: { label: "Possible fall — needs review", className: "bg-amber-100 text-amber-800 border border-amber-300" },
  confirmed: { label: "Confirmed fall", className: "bg-red-100 text-red-800 border border-red-300" },
  dismissed: { label: "Not a fall", className: "bg-muted text-muted-foreground border" },
};

const MS_PER_DAY = 1000 * 60 * 60 * 24;

/** Whole-day difference between an ISO date and today (negative = in the past). */
function daysUntil(iso: string): number {
  const target = new Date(iso + "T00:00:00").setHours(0, 0, 0, 0);
  const today = new Date().setHours(0, 0, 0, 0);
  return Math.round((target - today) / MS_PER_DAY);
}

/** Human, at-a-glance phrasing of a due date, e.g. "Due in 12 days" or "5 days overdue". */
function relativeDue(iso: string | null): string {
  if (!iso) return "No due date set";
  const days = daysUntil(iso);
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days === -1) return "1 day overdue";
  if (days < 0) return `${Math.abs(days)} days overdue`;
  return `Due in ${days} days`;
}

export default function RecordsPage() {
  const [caseId, setCaseId] = useState<string | null>(null);
  const [timekeeping, setTimekeeping] = useState<TimekeepingEntry[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [renewals, setRenewals] = useState<RenewalItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const [editingTk, setEditingTk] = useState<string | null>(null);
  const [editingJn, setEditingJn] = useState<string | null>(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  // Timekeeping form
  const [showTkForm, setShowTkForm] = useState(false);
  const [tkDate, setTkDate] = useState("");
  const [tkHours, setTkHours] = useState("");
  const [tkStartTime, setTkStartTime] = useState("");
  const [tkEndTime, setTkEndTime] = useState("");
  const [tkServiceType, setTkServiceType] = useState<ServiceType>("personal_care");
  const [tkTasks, setTkTasks] = useState("");
  const [tkNotes, setTkNotes] = useState("");

  // Journal form
  const [showJnForm, setShowJnForm] = useState(false);
  const [jnDate, setJnDate] = useState("");
  const [jnText, setJnText] = useState("");

  // Renewal add/edit form
  const [showRnForm, setShowRnForm] = useState(false);
  const [editingRn, setEditingRn] = useState<string | null>(null);
  const [rnProgram, setRnProgram] = useState("");
  const [rnDueDate, setRnDueDate] = useState("");
  const [rnStatus, setRnStatus] = useState<RenewalStatus>("active");
  const [rnLastCompleted, setRnLastCompleted] = useState("");
  const [rnPeriod, setRnPeriod] = useState("");
  const [rnNotes, setRnNotes] = useState("");

  const loadData = useCallback(async (id: string) => {
    setLoading(true);
    setLoadError(false);
    try {
      const [tk, jn, rn] = await Promise.all([
        listTimekeeping(id),
        listJournal(id),
        listRenewals(id),
      ]);
      setTimekeeping(tk);
      setJournal(jn);
      setRenewals(rn);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("ilera_case_id") : null;
    if (stored) {
      // Read the browser-only case after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCaseId(stored);
      loadData(stored);
    } else {
      setLoading(false);
    }
  }, [loadData]);

  const fallEntries = journal.filter((j) => j.fall_flagged && j.incident_status !== "dismissed");
  const inRange = (date: string) => (!fromDate || date >= fromDate) && (!toDate || date <= toDate);
  const visibleTimekeeping = timekeeping.filter((entry) => inRange(entry.date));
  const visibleJournal = journal.filter((entry) => inRange(entry.date));

  // Surface the most urgent renewals first, then soonest-due within a bucket.
  const sortedRenewals = [...renewals].sort((a, b) => {
    const order = URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency];
    if (order !== 0) return order;
    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
    return a.program.localeCompare(b.program);
  });
  const overdueCount = renewals.filter((r) => r.urgency === "overdue").length;
  const dueSoonCount = renewals.filter((r) => r.urgency === "due_soon").length;

  const mutate = async (action: () => Promise<void>) => {
    if (saving.current) return;
    saving.current = true;
    setPending(true);
    setSaveError("");
    try {
      await action();
    } catch {
      setSaveError("Could not save this change. Your inputs are still here; check your connection and try again.");
    } finally {
      saving.current = false;
      setPending(false);
    }
  };

  const editTimekeeping = (entry: TimekeepingEntry) => {
    setEditingTk(entry.id);
    setTkDate(entry.date); setTkHours(String(entry.hours));
    setTkStartTime(entry.start_time ?? ""); setTkEndTime(entry.end_time ?? "");
    setTkServiceType(entry.service_type); setTkTasks(entry.tasks.join(", ")); setTkNotes(entry.notes);
    setShowTkForm(true);
  };
  const editJournal = (entry: JournalEntry) => {
    setEditingJn(entry.id); setJnDate(entry.date); setJnText(entry.text); setShowJnForm(true);
  };

  const handleAddTimekeeping = async () => {
    if (!caseId) return;
    const hours = Number(tkHours);
    if (!tkDate || !Number.isFinite(hours) || hours <= 0 || hours > 24) {
      setSaveError("Enter a date and hours greater than 0 and at most 24."); return;
    }
    const minutes = (value: string) => { const [h, m] = value.split(":").map(Number); return h * 60 + m; };
    if (Boolean(tkStartTime) !== Boolean(tkEndTime) || (tkStartTime && tkEndTime &&
        (minutes(tkEndTime) <= minutes(tkStartTime) || Math.abs(hours * 60 - (minutes(tkEndTime) - minutes(tkStartTime))) > 0.01))) {
      setSaveError("Provide both times and matching hours. Split overnight care into separate dates."); return;
    }
    const save = editingTk ? (body: Parameters<typeof createTimekeeping>[0]) => updateTimekeeping(editingTk, body) : createTimekeeping;
    await save({
      case_id: caseId,
      date: tkDate,
      hours: parseFloat(tkHours),
      start_time: tkStartTime || undefined,
      end_time: tkEndTime || undefined,
      service_type: tkServiceType,
      tasks: tkTasks
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      notes: tkNotes || undefined,
    });
    setEditingTk(null);
    setShowTkForm(false);
    setTkDate("");
    setTkHours("");
    setTkStartTime("");
    setTkEndTime("");
    setTkServiceType("personal_care");
    setTkTasks("");
    setTkNotes("");
    await loadData(caseId);
  };

  const handleDeleteTimekeeping = async (id: string) => {
    if (!caseId) return;
    if (!window.confirm("Delete this timesheet entry? This cannot be undone.")) return;
    await deleteTimekeepingEntry(id, caseId);
    await loadData(caseId);
  };

  const handleAddJournal = async () => {
    if (!caseId) return;
    if (!jnDate || !jnText.trim()) { setSaveError("Enter a date and a journal note."); return; }
    const save = editingJn ? (body: Parameters<typeof createJournal>[0]) => updateJournal(editingJn, body) : createJournal;
    await save({
      case_id: caseId,
      date: jnDate,
      text: jnText,
    });
    setEditingJn(null);
    setShowJnForm(false);
    setJnDate("");
    setJnText("");
    await loadData(caseId);
  };

  const handleDeleteJournal = async (id: string) => {
    if (!caseId) return;
    if (!window.confirm("Delete this journal entry? This cannot be undone.")) return;
    await deleteJournalEntry(id, caseId);
    await loadData(caseId);
  };

  const resetRenewalForm = () => {
    setEditingRn(null); setRnProgram(""); setRnDueDate(""); setRnStatus("active");
    setRnLastCompleted(""); setRnPeriod(""); setRnNotes(""); setShowRnForm(false);
  };

  const editRenewal = (item: RenewalItem) => {
    setEditingRn(item.id);
    setRnProgram(item.program);
    setRnDueDate(item.due_date ?? "");
    setRnStatus(item.status);
    setRnLastCompleted(item.last_completed_date ?? "");
    setRnPeriod(item.renewal_period_months != null ? String(item.renewal_period_months) : "");
    setRnNotes(item.notes);
    setShowRnForm(true);
  };

  const handleSaveRenewal = async () => {
    if (!caseId) return;
    if (!rnProgram.trim()) { setSaveError("Enter the program this renewal is for."); return; }
    const period = rnPeriod.trim() ? Number(rnPeriod) : null;
    if (period != null && (!Number.isInteger(period) || period < 1 || period > 120)) {
      setSaveError("Renewal period must be a whole number of months between 1 and 120."); return;
    }
    const body = {
      program: rnProgram.trim(),
      due_date: rnDueDate || null,
      status: rnStatus,
      last_completed_date: rnLastCompleted || null,
      renewal_period_months: period,
      notes: rnNotes,
    };
    if (editingRn) {
      await updateRenewalItem(editingRn, caseId, body);
    } else {
      await createRenewal({ case_id: caseId, ...body });
    }
    resetRenewalForm();
    await loadData(caseId);
  };

  const handleDeleteRenewal = async (id: string) => {
    if (!caseId) return;
    if (!window.confirm("Delete this renewal? This cannot be undone.")) return;
    await deleteRenewalItem(id, caseId);
    await loadData(caseId);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };

  if (!caseId && !loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold">Records &amp; Renewal</h1>
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              Complete the intake wizard first to create a case profile, then return here to track
              timesheets, journal entries, and renewals.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <fieldset disabled={pending || loading || loadError} className="space-y-6 min-w-0">
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <h1 className="text-4xl font-bold">Records &amp; Renewal</h1>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1"><Label htmlFor="records-from">From</Label><Input id="records-from" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /></div>
        <div className="space-y-1"><Label htmlFor="records-to">Through</Label><Input id="records-to" type="date" min={fromDate} value={toDate} onChange={(e) => setToDate(e.target.value)} /></div>
        <Button variant="outline" onClick={() => { setFromDate(""); setToDate(""); }}>All dates</Button>
        <p className="text-sm" aria-live="polite">{visibleTimekeeping.reduce((total, entry) => total + entry.hours, 0).toFixed(2)} hours · {visibleJournal.length} journal entries</p>
      </div>
      {fromDate && toDate && fromDate > toDate && <p role="alert">The end date must be on or after the start date.</p>}

      {fallEntries.length > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <CardContent className="flex items-start gap-3 py-4 text-sm">
            <span aria-hidden>🚩</span>
            <p>
              {fallEntries.length} journal {fallEntries.length === 1 ? "entry mentions" : "entries mention"} a possible fall. Review the highlighted entries below to confirm or dismiss each flag.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Renewals */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold">Renewals</h2>
            {overdueCount > 0 && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 border border-red-300">
                {overdueCount} overdue
              </span>
            )}
            {dueSoonCount > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 border border-amber-300">
                {dueSoonCount} due soon
              </span>
            )}
          </div>
          <Button size="sm" variant="outline" onClick={() => { resetRenewalForm(); setShowRnForm(true); }}>
            + Renewal
          </Button>
        </div>

        {showRnForm && (
          <Card>
            <CardContent className="space-y-3 py-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="rn-program">Program</Label>
                  <Input id="rn-program" value={rnProgram} onChange={(e) => setRnProgram(e.target.value)} placeholder="IHSS, Medi-Cal, PFL, VA…" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="rn-due">Due date</Label>
                  <Input id="rn-due" type="date" value={rnDueDate} onChange={(e) => setRnDueDate(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="rn-last">Last completed</Label>
                  <Input id="rn-last" type="date" value={rnLastCompleted} onChange={(e) => setRnLastCompleted(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="rn-period">Renewal period (months)</Label>
                  <Input id="rn-period" type="number" min="1" max="120" value={rnPeriod} onChange={(e) => setRnPeriod(e.target.value)} placeholder="12" />
                </div>
              </div>
              <div className="space-y-1">
                <Label>Status</Label>
                <div className="flex flex-wrap gap-1.5">
                  {RENEWAL_STATUSES.map((s) => (
                    <Button key={s} type="button" variant={rnStatus === s ? "default" : "outline"} size="sm" onClick={() => setRnStatus(s)}>
                      {STATUS_LABELS[s]}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="rn-notes">Notes</Label>
                <Textarea id="rn-notes" value={rnNotes} onChange={(e) => setRnNotes(e.target.value)} placeholder="Renewal packet details, contacts, what's needed…" rows={2} maxLength={2000} />
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => mutate(handleSaveRenewal)}>{editingRn ? "Save changes" : "Add"}</Button>
                <Button size="sm" variant="outline" onClick={resetRenewalForm}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

        {!loading && !loadError && renewals.length === 0 && (
          <p className="text-sm text-muted-foreground">No renewals tracked yet. Add one to keep deadlines in view.</p>
        )}

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {sortedRenewals.map((r) => {
            const badge = URGENCY_BADGE[r.urgency];
            return (
              <Card key={r.id} className={r.urgency === "overdue" ? "border-red-300" : r.urgency === "due_soon" ? "border-amber-300" : ""}>
                <CardContent className="space-y-2 px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base font-semibold">{r.program}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>{badge.label}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost" onClick={() => editRenewal(r)}>Edit</Button>
                      <button onClick={() => mutate(() => handleDeleteRenewal(r.id))} className="text-muted-foreground hover:text-destructive" aria-label={`Delete ${r.program} renewal`}>
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </div>
                  <p className={`text-sm font-medium ${r.urgency === "overdue" ? "text-red-700" : r.urgency === "due_soon" ? "text-amber-700" : "text-foreground"}`}>
                    {relativeDue(r.due_date)}
                    {r.due_date && <span className="font-normal text-muted-foreground"> · {formatDate(r.due_date)}</span>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Status: {STATUS_LABELS[r.status]}
                    {r.renewal_period_months ? ` · Renews every ${r.renewal_period_months} mo` : ""}
                    {r.last_completed_date ? ` · Last completed ${formatDate(r.last_completed_date)}` : ""}
                  </p>
                  {r.notes && <p className="text-sm whitespace-pre-wrap">{r.notes}</p>}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold">Timesheets</h2>
              <a
                href="https://www.etimesheets.ihss.ca.gov"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-black underline hover:text-black/70"
              >
                Submit timesheet to IHSS portal
                <ExternalLink className="size-3.5" />
              </a>
            </div>
            <Button size="sm" variant="outline" onClick={() => { setEditingTk(null); setTkDate(""); setTkHours(""); setTkStartTime(""); setTkEndTime(""); setTkTasks(""); setTkNotes(""); setTkServiceType("personal_care"); setShowTkForm(true); }}>
              + Entry
            </Button>
          </div>

          {showTkForm && (
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="tk-date">Date</Label>
                    <Input
                      id="tk-date"
                      type="date"
                      value={tkDate}
                      onChange={(e) => setTkDate(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="tk-hours">Total Hours</Label>
                    <Input
                      id="tk-hours"
                      type="number"
                      step="0.25"
                      min="0"
                      max="24"
                      value={tkHours}
                      onChange={(e) => setTkHours(e.target.value)}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="tk-start">Start Time</Label>
                    <Input
                      id="tk-start"
                      type="time"
                      value={tkStartTime}
                      onChange={(e) => setTkStartTime(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="tk-end">End Time</Label>
                    <Input
                      id="tk-end"
                      type="time"
                      value={tkEndTime}
                      onChange={(e) => setTkEndTime(e.target.value)}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label>Service Type</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(SERVICE_LABELS) as ServiceType[]).map((st) => (
                      <Button
                        key={st}
                        type="button"
                        variant={tkServiceType === st ? "default" : "outline"}
                        size="sm"
                        onClick={() => setTkServiceType(st)}
                      >
                        {SERVICE_LABELS[st]}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-tasks">Activities (comma-separated)</Label>
                  <Input
                    id="tk-tasks"
                    value={tkTasks}
                    onChange={(e) => setTkTasks(e.target.value)}
                    placeholder="Bathing, dressing, meal prep, medication"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-notes">Notes</Label>
                  <Input
                    id="tk-notes"
                    value={tkNotes}
                    onChange={(e) => setTkNotes(e.target.value)}
                    placeholder="Any additional details"
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => mutate(handleAddTimekeeping)}>{editingTk ? "Save changes" : "Add"}</Button>
                  <Button size="sm" variant="outline" onClick={() => setShowTkForm(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {visibleTimekeeping.map((t) => (
            <Card key={t.id}>
              <CardContent className="px-4 py-3 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-semibold">{formatDate(t.date)}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
                      {t.hours} {t.hours === 1 ? "hr" : "hrs"}
                    </span>
                    {t.start_time && t.end_time && (
                      <span className="text-xs text-muted-foreground">{t.start_time}–{t.end_time}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" onClick={() => editTimekeeping(t)}>Edit</Button>
                    <button
                      onClick={() => mutate(() => handleDeleteTimekeeping(t.id))}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Delete timesheet entry for ${formatDate(t.date)}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full border px-2 py-0.5 text-xs font-medium">
                    {SERVICE_LABELS[t.service_type] ?? t.service_type}
                  </span>
                  {t.tasks.map((task) => (
                    <span key={task} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{task}</span>
                  ))}
                </div>
                {t.notes && <p className="text-xs text-muted-foreground">{t.notes}</p>}
              </CardContent>
            </Card>
          ))}

          {!loading && !loadError && visibleTimekeeping.length === 0 && (
            <p className="text-sm text-muted-foreground">No timesheet entries for these dates.</p>
          )}
        </section>

        {/* Care journal */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Care journal</h2>
            <Button size="sm" variant="outline" onClick={() => { setEditingJn(null); setJnDate(""); setJnText(""); setShowJnForm(true); }}>
              + Entry
            </Button>
          </div>

          {showJnForm && (
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="space-y-1">
                  <Label htmlFor="jn-date">Date</Label>
                  <Input
                    id="jn-date"
                    type="date"
                    value={jnDate}
                    onChange={(e) => setJnDate(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="jn-text">Entry</Label>
                  <Textarea
                    id="jn-text"
                    value={jnText}
                    onChange={(e) => setJnText(e.target.value)}
                    placeholder="How was today's care?"
                    rows={3}
                    maxLength={20000}
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => mutate(handleAddJournal)}>{editingJn ? "Save changes" : "Add"}</Button>
                  <Button size="sm" variant="outline" onClick={() => setShowJnForm(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {visibleJournal.map((j) => (
            <Card key={j.id} className={j.fall_flagged && j.incident_status !== "dismissed" ? "border-amber-300" : ""}>
              <CardContent className="px-4 py-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold">{formatDate(j.date)}</span>
                    {j.fall_flagged && (
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${INCIDENT_BADGE[j.incident_status].className}`}>
                        {INCIDENT_BADGE[j.incident_status].label}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" onClick={() => editJournal(j)}>Edit</Button>
                    <button
                      onClick={() => mutate(() => handleDeleteJournal(j.id))}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Delete journal entry for ${formatDate(j.date)}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
                <p className="text-sm whitespace-pre-wrap text-muted-foreground">{j.text}</p>
                {j.fall_flagged && (
                  <div className="flex flex-wrap items-center gap-2">
                    {j.incident_status !== "confirmed" && <Button size="sm" variant="outline" onClick={() => mutate(async () => { await reviewIncident(j.id, caseId!, "confirmed"); await loadData(caseId!); })}>Confirm fall</Button>}
                    {j.incident_status !== "dismissed" && <Button size="sm" variant="outline" onClick={() => mutate(async () => { await reviewIncident(j.id, caseId!, "dismissed"); await loadData(caseId!); })}>Not a fall</Button>}
                    {j.incident_status !== "unreviewed" && <Button size="sm" variant="ghost" onClick={() => mutate(async () => { await reviewIncident(j.id, caseId!, "unreviewed"); await loadData(caseId!); })}>Reset</Button>}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}

          {!loading && !loadError && visibleJournal.length === 0 && (
            <p className="text-sm text-muted-foreground">No journal entries for these dates.</p>
          )}
        </section>
      </div>
      </fieldset>
      {loadError && <div role="alert" className="rounded-md border border-destructive p-4">Could not load records. Existing data may be out of date. <Button variant="outline" onClick={() => caseId && loadData(caseId)}>Retry</Button></div>}
      {saveError && <p role="alert" className="text-destructive">{saveError}</p>}
      {pending && <p role="status">Saving changes…</p>}
    </div>
  );
}
