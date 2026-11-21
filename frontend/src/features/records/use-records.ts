"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listJournal, listRenewals, listTimekeeping } from "@/features/records/api";
import type { JournalEntry, RenewalItem, TimekeepingEntry } from "@/features/records/types";

/** A case's timesheets, journal and renewals, the date range being viewed, and one-at-a-time saves. */
export function useRecords(caseId: string | null) {
  const [timekeeping, setTimekeeping] = useState<TimekeepingEntry[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [renewals, setRenewals] = useState<RenewalItem[]>([]);
  const [loading, setLoading] = useState(caseId !== null);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const reload = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setLoadError(false);
    try {
      const [tk, jn, rn] = await Promise.all([listTimekeeping(caseId), listJournal(caseId), listRenewals(caseId)]);
      setTimekeeping(tk);
      setJournal(jn);
      setRenewals(rn);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    // reload also backs the Retry button, so it resets loading itself; harmless here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  /** Run one save at a time; a failure keeps the inputs and says so. Returns whether it saved. */
  const run = async (action: () => Promise<void>): Promise<boolean> => {
    if (saving.current) return false;
    saving.current = true;
    setPending(true);
    setSaveError("");
    try {
      await action();
      return true;
    } catch {
      setSaveError("Could not save this change. Your inputs are still here; check your connection and try again.");
      return false;
    } finally {
      saving.current = false;
      setPending(false);
    }
  };

  const inRange = (date: string) => (!fromDate || date >= fromDate) && (!toDate || date <= toDate);
  return {
    caseId, loading, loadError, saveError, setSaveError, pending, run, reload,
    renewals,
    timekeeping: timekeeping.filter((e) => inRange(e.date)),
    journal: journal.filter((e) => inRange(e.date)),
    flaggedFalls: journal.filter((j) => j.fall_flagged && j.incident_status !== "dismissed").length,
    fromDate, toDate, setFromDate, setToDate,
  };
}

export type Records = ReturnType<typeof useRecords>;
