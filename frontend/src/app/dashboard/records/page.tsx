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
  createTimekeeping,
  deleteJournalEntry,
  deleteTimekeepingEntry,
  getRenewal,
  listJournal,
  listTimekeeping,
  updateRenewal,
  updateTimekeeping,
  updateJournal,
  reviewIncident,
} from "@/lib/api";
import type { JournalEntry, RenewalInfo, ServiceType, TimekeepingEntry } from "@/lib/types";

const SERVICE_LABELS: Record<ServiceType, string> = {
  personal_care: "Personal Care",
  domestic: "Domestic",
  paramedical: "Paramedical",
  accompaniment: "Accompaniment",
};

export default function RecordsPage() {
  const [caseId, setCaseId] = useState<string | null>(null);
  const [timekeeping, setTimekeeping] = useState<TimekeepingEntry[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [renewal, setRenewal] = useState<RenewalInfo | null>(null);
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

  // Renewal editing
  const [editingRenewal, setEditingRenewal] = useState(false);
  const [renewalDate, setRenewalDate] = useState("");

  const loadData = useCallback(async (id: string) => {
    setLoading(true);
    setLoadError(false);
    try {
      const [tk, jn, rn] = await Promise.all([
        listTimekeeping(id),
        listJournal(id),
        getRenewal(id),
      ]);
      setTimekeeping(tk);
      setJournal(jn);
      setRenewal(rn);
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

  const handleSaveRenewal = async () => {
    if (!caseId) return;
    await updateRenewal(caseId, { due_date: renewalDate || null });
    setEditingRenewal(false);
    await loadData(caseId);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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

  const renewalDueDate = renewal?.due_date ? new Date(renewal.due_date + "T00:00:00") : null;
  const overdue = renewalDueDate ? renewalDueDate < new Date(new Date().setHours(0, 0, 0, 0)) : false;

  return (
    <div className="space-y-6">
      <fieldset disabled={pending || loading || loadError} className="space-y-6 min-w-0">
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <h1 className="text-4xl font-bold">Records &amp; Renewal</h1>
        <div className="flex items-center gap-2">
          {editingRenewal ? (
            <>
              <Input
                type="date"
                aria-label="Renewal due date"
                value={renewalDate}
                onChange={(e) => setRenewalDate(e.target.value)}
                className="w-40"
              />
              <Button size="sm" onClick={() => mutate(handleSaveRenewal)}>Save</Button>
              <Button size="sm" variant="outline" onClick={() => setEditingRenewal(false)}>Cancel</Button>
            </>
          ) : (
            <button
              className="text-sm font-medium text-muted-foreground hover:text-foreground"
              onClick={() => {
                setRenewalDate(renewal?.due_date ?? "");
                setEditingRenewal(true);
              }}
            >
              Renewal due: {renewal?.due_date ? formatDate(renewal.due_date) : "Not set (click to edit)"}
            </button>
          )}
        </div>
      </div>

      <p className="text-lg font-semibold">
        {renewal?.due_date ? `${renewal.program} renewal ${overdue ? "overdue" : "due"}: ${formatDate(renewal.due_date)}, ${renewalDueDate?.getFullYear()}` : "Renewal deadline not set"}
      </p>
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Timesheets */}
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
              <CardContent className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-base font-semibold">{formatDate(t.date)}</span>
                  <Button size="sm" variant="ghost" onClick={() => editTimekeeping(t)}>Edit</Button>
                  <button
                    onClick={() => mutate(() => handleDeleteTimekeeping(t.id))}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete entry"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  <span>Hours: <span className="font-medium">{t.hours}</span></span>
                  {t.start_time && t.end_time && <span> ({t.start_time}\u2013{t.end_time})</span>}
                  {" · "}{SERVICE_LABELS[t.service_type] ?? t.service_type}
                  {" · "}{t.tasks.length > 0 ? t.tasks.join(", ") : "No activities"}
                  {t.notes && <span> · {t.notes}</span>}
                </p>
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
              <CardContent className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-base font-semibold">{formatDate(j.date)}</span>
                  <Button size="sm" variant="ghost" onClick={() => editJournal(j)}>Edit</Button>
                  <button
                    onClick={() => mutate(() => handleDeleteJournal(j.id))}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete entry"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <p className="text-sm whitespace-pre-wrap text-muted-foreground">{j.text}</p>
                {j.fall_flagged && <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                  <span>Possible fall: {j.incident_status}</span>
                  {j.incident_status !== "confirmed" && <Button size="sm" variant="outline" onClick={() => mutate(async () => { await reviewIncident(j.id, caseId!, "confirmed"); await loadData(caseId!); })}>Confirm</Button>}
                  {j.incident_status !== "dismissed" && <Button size="sm" variant="outline" onClick={() => mutate(async () => { await reviewIncident(j.id, caseId!, "dismissed"); await loadData(caseId!); })}>Dismiss</Button>}
                </div>}
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
